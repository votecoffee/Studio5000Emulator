"""Checked array-index arithmetic/bitwise forms and exact simple integer tags."""
import unittest
from xml.etree import ElementTree as E

import test_math_operands as fixtures
import test_lreal_math as rollback
import test_lreal_advanced as advanced
from logixlab.expressions import Expression
from logixlab.model import INT_BITS,ModelError,Project
from logixlab.runtime import Engine

CASES={'Index/Divisor':1,'(Index+1)/Divisor':2,'Index AND 1':1,
       'Index OR 0':3,'Index XOR 2':1,'(NOT Index) AND 7':4,
       '(Index/Divisor) XOR 3':2,'Index/(Divisor+1)':1}


class ArrayIndexExpressionTests(unittest.TestCase):
    setUp=fixtures.MathOperandTests.setUp
    checked=fixtures.MathOperandTests.checked
    snapshot=staticmethod(rollback.LrealMathTests.snapshot)
    fault=rollback.LrealMathTests.fault

    def engine(self,rungs=None,*,index=3,index_type='DINT',divisor=2,mutate=None,st=False):
        def fields(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Index"]');tag.set('DataType',index_type);tag.find('Data/DataValue').set('DataType',index_type)
            for name,value in (('Divisor',divisor),('LateDivisor',1)):
                tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name=name,DataType='DINT',TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
            if st:
                routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
                E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=rungs
            if mutate:mutate(root)
        return fixtures.MathOperandTests.engine(self,['NOP();'] if st else rungs or ['MOV(Source,Results[Index/Divisor]);'],source='DINT',dest='DINT',value=7,index=index,mutate=fields)

    def test_division_and_bitwise_indices_follow_dint_precedence(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['NOP();'],index_type=dtype)
            for expr,want in CASES.items():
                with self.subTest(dtype=dtype,expr=expr):self.assertEqual(e.memory.index(expr,''),want)
        for a,b,want in ((7,2,3),(-7,2,-3),(7,-2,-3),(-7,-2,3),(-2147483648,3,-715827882)):
            e=self.checked(['NOP();'],index=a,divisor=b);self.assertEqual(e.memory.index('Index/Divisor',''),want)

    def test_all_eight_integer_tags_select_scalar_array_elements(self):
        for dtype in INT_BITS:
            e=self.checked(['MOV(Source,Results[Index]);'],index=1,index_type=dtype);e.step()
            self.assertEqual(e.memory.read('Results'),[None,7,None]);self.assertEqual(e.memory.read('Index'),1)
        for dtype,value in (('LINT',9007199254740993),('ULINT',2**64-1),('UDINT',2**32-1)):
            e=self.checked(['AFI()MOV(Source,Results[Index]);'],index=value,index_type=dtype)
            self.assertEqual(e.memory.index('Index',''),value);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
            e=self.checked(['MOV(Source,Results[Index]);'],index=value,index_type=dtype);self.fault(e,'outside bounds')

    def test_source_and_destination_indices_establish_unknowns_without_touching_neighbors(self):
        for expr in ('Index/Divisor','Index AND 1','Index XOR 2','(NOT Index) AND 1'):
            e=self.checked([f'MOV(Inputs[{expr}],Results[{expr}]);'])
            selected=e.memory.index(expr,'');e.memory.write(f'Inputs[{selected}]',123);e.step()
            self.assertEqual(e.memory.read(f'Results[{selected}]'),123)
            self.assertTrue(all(value is None for i,value in enumerate(e.memory.read('Results')) if i!=selected))

    def test_common_ladder_consumers_use_the_same_selected_cell(self):
        cases=[('MOV(Inputs[Index/Divisor],Results[Index/Divisor]);',77),
               ('ADD(Inputs[Index/Divisor],1,Results[Index/Divisor]);',78),
               ('BTD(Inputs[Index/Divisor],0,Results[Index/Divisor],0,32);',77),
               ('COP(Inputs[Index/Divisor],Results[Index/Divisor],1);',77),
               ('FLL(Inputs[Index/Divisor],Results[Index/Divisor],1);',77),
               ('CPT(Results[Index/Divisor],Inputs[Index/Divisor]+1);',78),
               ('SQR(Inputs[Index/Divisor],Results[Index/Divisor]);',9),
               ('FRD(Inputs[Index/Divisor],Results[Index/Divisor]);',53)]
        for call,want in cases:
            e=self.checked([call]);e.memory.write('Inputs[1]',77);e.step();self.assertEqual(e.memory.read('Results'),[None,want,None])
        e=self.checked(['CMP(Inputs[Index/Divisor]>0)OTE(RunLatch);']);e.memory.write('Inputs[1]',77);e.step();self.assertTrue(e.memory.read('RunLatch'))
        import test_queue_references as queues
        f=queues.QueueReferenceTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.checked(['XIC(StartPB)FFL(Incoming,Queue[Index/2],Ctl,?,?);'],length=3);e.step()
        e.memory.write('Index',2);e.memory.write('Incoming',88);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue[1]'),88)

    def test_false_prescan_and_unknown_indices_remain_lazy(self):
        for dtype,expr in (('DINT','Index/Divisor'),('ULINT','Index')):
            e=self.checked([f'XIC(StartPB)MOV(Source,Results[{expr}]);'],index_type=dtype,divisor=0)
            e.memory.values['index']=None;e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
            e.memory.write('StartPB',True);self.fault(e,'Unknown');e.memory.write('Index',1)
            if dtype=='DINT':self.fault(e,'zero');e.memory.write('Divisor',1)
            e.step();self.assertEqual(e.memory.read('Results'),[None,7,None])

    def test_zero_and_overflow_faults_restore_prior_writes_and_do_not_fold_masks(self):
        for expr,index,divisor,text in [('Index/Divisor',3,0,'zero'),('(Index/Divisor) AND 0',3,0,'zero'),
                                       ('Index/Divisor',-2147483648,-1,'overflow'),('(Index+1)/Divisor',2147483647,2,'overflow'),
                                       ('Index/Divisor',-3,2,'outside bounds')]:
            e=self.checked(['MOV(99,SpeedCommand);',f'MOV(Source,Results[{expr}]);'],index=index,divisor=divisor);self.fault(e,text)
        e=self.checked(['MOV(Source,Results[Index/Divisor]);','DIV(1,LateDivisor,SpeedCommand);']);e.memory.write('LateDivisor',0);self.fault(e,'zero')
        e.memory.write('LateDivisor',1);e.step();self.assertEqual(e.memory.read('Results'),[None,7,None])

    def test_alias_udt_member_nested_and_multidimensional_indices(self):
        def fields(root):
            tags=root.find('./Controller/Tags');members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='IndexPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Selected',DataType='ULINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet',DataType='IndexPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='IndexPacket')
            E.SubElement(obj,'DataValueMember',Name='Selected',DataType='ULINT',Value='1');E.SubElement(tags,'Tag',Name='Chosen',DataType='ULINT',TagType='Alias',AliasFor='Packet.Selected')
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Matrix',DataType='DINT',Dimensions='3,3',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3,3')
            E.SubElement(arr,'Element',Index='[1,1]',Value='42')
        e=self.checked(['MOV(Matrix[Index/Divisor,Chosen],Results[Chosen]);'],mutate=fields);e.step();self.assertEqual(e.memory.read('Results'),[None,42,None])
        e=self.checked(['MOV(Source,Results[Inputs[Index/Divisor]]);']);e.memory.write('Inputs[1]',2);e.step();self.assertEqual(e.memory.read('Results'),[None,None,7])

    def test_st_existing_assignments_and_skipped_branches_use_indices(self):
        e=self.checked('IF StartPB THEN Results[Index/Divisor]:=Inputs[Index AND 1]; END_IF;',st=True,divisor=0);e.step()
        e.memory.write('Divisor',2);e.memory.write('Inputs[1]',88);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Results'),[None,88,None])
        e=self.checked('Results[Index]:=Source;',st=True,index_type='ULINT',index=1);e.step();self.assertEqual(e.memory.read('Results'),[None,7,None])

    def aoi(self):
        f=advanced.LrealAdvancedTests();f.setUp();self.addCleanup(f.doCleanups);original=f.aoi();root=E.parse(original.project.path).getroot()
        locals=root.find('.//AddOnInstructionDefinition/LocalTags');tag=E.SubElement(locals,'LocalTag',Name='WideIndex',DataType='ULINT')
        E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='ULINT',Value='1')
        for suffix,value in (('A','1'),('B','2')):
            obj=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure');E.SubElement(obj,'DataValueMember',Name='WideIndex',DataType='ULINT',Value=value)
        advanced.queues.logic(root,['MOV(Value,Buffer[(Index*2)/2]);','MOV(Value,Stack[WideIndex]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(original.project.path))

    def test_warm_aoi_copied_indices_inout_arrays_and_local_wide_indices_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',4);e.memory.write('ValueB',9);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[2]')),(4,9,4,9))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('DriverB.Stack[2]'),9)

    def test_other_index_types_functions_literals_and_wide_expressions_stay_blocked(self):
        for dtype in ('BOOL','REAL','LREAL'):
            self.assertTrue(self.engine(['AFI()MOV(Source,Results[Index]);'],index=1,index_type=dtype).blockers,dtype)
        for expr in ('Index MOD 2','SQR(Index)','ABS(Index)','Index**2','Index/2.0','2147483648','Index<2'):
            self.assertTrue(self.engine([f'AFI()MOV(Source,Results[{expr}]);']).blockers,expr)
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            self.assertTrue(self.engine(['AFI()MOV(Source,Results[Index+0]);'],index=1,index_type=dtype).blockers,dtype)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()MOV(Source,Results[Index/2]);'],mutate=old).blockers)

    def test_report_exposes_expression_and_simple_index_type_boundaries(self):
        d=self.checked().report()['integer_expression_execution']['array_indices']
        self.assertEqual(len(d['simple_tag_types']),8);self.assertEqual(len(d['expression_types']),3);self.assertEqual(len(d['operators']),8)
        self.assertFalse(d['native_runtime_parity'])
