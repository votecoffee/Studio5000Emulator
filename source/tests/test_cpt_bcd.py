"""Scoped integer FRD/TOD operators inside ladder CPT expressions."""
import itertools
import unittest
from xml.etree import ElementTree as E

import test_array_index_functions as fixtures
from logixlab.expressions import Expression
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class CptBcdTests(unittest.TestCase):
    setUp=fixtures.ArrayIndexFunctionTests.setUp
    checked=fixtures.ArrayIndexFunctionTests.checked
    snapshot=staticmethod(fixtures.ArrayIndexFunctionTests.snapshot)
    fault=fixtures.ArrayIndexFunctionTests.fault

    def engine(self,rungs=None,*,source_type='DINT',dest_type='DINT',value=42,mutate=None,**options):
        def fields(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="Source"]');tag.set('DataType',source_type)
            node=tag.find('Data/DataValue');node.set('DataType',source_type);node.set('Value',str(value))
            tag=tags.find('Tag[@Name="Dest"]');tag.set('DataType',dest_type);tag.find('Data/DataValue').set('DataType',dest_type);tag.find('Data/DataValue').set('Value','0')
            tag=tags.find('Tag[@Name="Results"]');tag.set('DataType',dest_type);tag.find('Data/Array').set('DataType',dest_type)
            tag=tags.find('Tag[@Name="Inputs"]');tag.set('DataType',source_type);tag.find('Data/Array').set('DataType',source_type)
            if mutate:mutate(root)
        return fixtures.ArrayIndexFunctionTests.engine(self,rungs or ['CPT(Dest,FRD(Source));'],mutate=fields,**options)

    def test_all_nine_narrow_source_destination_pairs_and_two_conversions(self):
        for source,dest in itertools.product(('SINT','INT','DINT'),repeat=2):
            for function,value,want in [('FRD',26,20),('TOD',21,33)]:
                e=self.checked([f'CPT(Dest,{function}(Source));'],source_type=source,dest_type=dest,value=value);e.step()
                self.assertEqual(e.memory.read('Dest'),want);self.assertEqual(e.memory.read('Source'),value)

    def test_nesting_patterns_nondecimal_nibbles_and_integer_composition(self):
        for expr,want in [('FRD(16#12345678)',12345678),('FRD(16#1A)',20),('FRD(-1)',166666665),('FRD(-2147483648)',80000000),
                          ('TOD(0)',0),('TOD(99999999)',-1717986919),('FRD(TOD(99999999))',99999999),
                          ('TOD(99999999) AND 7',1),('FRD(TOD(Source+3))/2',22),('TRN(ABS(FRD(16#1234)-1235))',1),
                          ('(FRD(16#1234) MOD 100) OR (TOD(21) AND 7)',35),('NOT TOD(0)',-1)]:
            e=self.checked([f'CPT(Dest,{expr});']);e.step();self.assertEqual(e.memory.read('Dest'),want,expr)

    def test_signed_narrow_sources_promote_before_eight_nibble_frd(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(source_type=dtype,value=-1);e.step();self.assertEqual(e.memory.read('Dest'),166666665);self.assertEqual(e.memory.read('Source'),-1)

    def test_false_and_prescan_skip_bad_indices_unknowns_and_tod_ranges(self):
        e=self.checked(['XIC(StartPB)CPT(Results[Index],FRD(Inputs[Index]));'],index=99);e.enter_run();e.step()
        self.assertEqual(e.memory.read('Results'),[None]*3);e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',33);e.step();self.assertEqual(e.memory.read('Results'),[None,21,None])
        for value in (-1,100000000):
            e=self.checked(['XIC(StartPB)CPT(Dest,TOD(Source));'],value=value);e.step();e.memory.write('StartPB',True);self.fault(e,'qualified')
            e.memory.write('Source',42);e.step();self.assertEqual(e.memory.read('Dest'),66)

    def test_required_arguments_intermediates_ranges_and_later_faults_are_atomic(self):
        for expr,value,text in [('FRD(Source*2)',1073741824,'overflow'),('TOD(Source+1)',2147483647,'overflow'),('TOD(Source/Divisor)',42,'zero'),('FRD(2147483648)',42,'overflow')]:
            e=self.checked(['MOV(99,SpeedCommand);',f'CPT(Dest,{expr});'],value=value,divisor=0);self.fault(e,text)
        e=self.checked(['CPT(Dest,FRD(Inputs[Index])*0);']);self.fault(e,'Unknown');e.memory.write('Inputs[1]',33);e.step();self.assertEqual(e.memory.read('Dest'),0)
        e=self.checked(['CPT(Results[Index],FRD(TOD(Source)));','DIV(1,LateDivisor,SpeedCommand);']);e.memory.write('LateDivisor',0);self.fault(e,'zero')
        e.memory.write('LateDivisor',1);e.step();self.assertEqual(e.memory.read('Results'),[None,42,None])

    def test_result_narrowing_requires_a_representable_numeric_value(self):
        for expr,value in [('TOD(Source)',99),('FRD(Source)',-1)]:
            e=self.checked([f'CPT(Dest,{expr});'],value=value,dest_type='SINT');self.fault(e,'overflow')
        e=self.checked(['CPT(Dest,TOD(Source));'],value=79,dest_type='SINT');e.step();self.assertEqual(e.memory.read('Dest'),121)

    @staticmethod
    def packet(root):
        members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='BcdPacket',Class='User'),'Members')
        E.SubElement(members,'Member',Name='Value',DataType='DINT',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
        tags=root.find('./Controller/Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet',DataType='BcdPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='BcdPacket')
        E.SubElement(obj,'DataValueMember',Name='Value',DataType='DINT',Value='33');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(tags,'Tag',Name='Selected',DataType='DINT',TagType='Alias',AliasFor='Packet.Value')

    def test_alias_udt_and_nested_function_indices_use_exact_selected_cells(self):
        e=self.checked(['CPT(Results[FRD(TOD(Index))],FRD(Selected));'],mutate=self.packet);e.step()
        self.assertEqual(e.memory.read('Results'),[None,21,None]);self.assertEqual(e.memory.read('Packet.Guard'),777);self.assertEqual(e.memory.read('Packet.Value'),33)
        e=self.checked(['CPT(Results[TOD(Index)],FRD(Inputs[FRD(TOD(Index))]));']);e.memory.write('Inputs[1]',33);e.step();self.assertEqual(e.memory.read('Results'),[None,21,None])

    def aoi(self,dtype='SINT'):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def fields(root):
            queues.logic(root,['CPT(Buffer[Index],FRD(TOD(Value)));','CPT(Stack[Index],FRD(Value));'])
            definition=root.find('.//AddOnInstructionDefinition');definition.find('Parameters/Parameter[@Name="Value"]').set('DataType',dtype)
            for suffix,value in [('A',21),('B',34)]:
                tag=root.find(f'./Controller/Tags/Tag[@Name="Value{suffix}"]');tag.set('DataType',dtype);tag.find('Data/DataValue').set('DataType',dtype);tag.find('Data/DataValue').set('Value',str(value))
                node=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/DataValueMember[@Name="Value"]');node.set('DataType',dtype);node.set('Value',str(value))
        return f.engine(fields)

    def test_warm_aoi_copied_inputs_inout_local_state_and_binding_rollback(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.aoi(dtype);self.assertEqual(e.blockers,[]);e.step()
            self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[2]')),(21,34,15,22))
            e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.memory.write('ValueA',42);e.step();self.assertEqual(e.memory.read('BufferA[1]'),42)

    def test_scoped_cache_keeps_generic_and_st_forms_separate_from_ladder(self):
        e=self.checked();e.step()
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):e.extensions.expression('FRD(Source)')
        self.assertIn(('FRD(Source)',True,True,True),e.extensions.expressions)
        for code in ('Dest:=FRD(Source);','Dest:=TOD(Source);'):
            self.assertTrue(self.engine(code,st=True).blockers)
        for function in ('FRD','TOD'):
            e=self.checked([f'CMP({function}(Source)>0)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))
        import test_file_arithmetic as files
        f=files.FileArithmeticTests();f.setUp();self.addCleanup(f.doCleanups)
        for function in ('FRD','TOD'):
            e=f.checked([f'CPT(Outgoing,{function}(Incoming));',f'FAL(Ctl,?,?,ALL,Queue[Ctl.POS],{function}(Incoming));']);e.step();self.assertEqual(e.memory.read('Queue')[:4],[11 if function=='FRD' else 17]*4)
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):Expression('TOD(Source)')

    def test_other_types_real_functions_and_profiles_remain_guarded(self):
        for dtype in ('BOOL','REAL','LREAL','LINT','USINT','UINT','UDINT','ULINT'):
            for function in ('FRD','TOD'):
                self.assertTrue(self.engine([f'AFI()CPT(Dest,{function}(Source));'],source_type=dtype,value=1).blockers,(dtype,function))
                self.assertTrue(self.engine([f'AFI()CPT(Dest,{function}(Source));'],dest_type=dtype,value=1).blockers,(dtype,function,'destination'))
        for expr in ('FRD(1.0)','TOD(Source+0.5)','FRD(Source)+SQR(4.0)','TOD(Source)**2.0','TOD(TRUE)','TOD(1L)','FRD(Source,1)'):
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{expr});']).blockers,expr)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()CPT(Dest,FRD(Source));'],mutate=old).blockers)

    def test_report_keeps_bcd_profile_and_existing_index_functions_separate(self):
        d=self.checked().report()['integer_expression_execution'];self.assertEqual(d['bcd_cpt']['functions'],['FRD','TOD']);self.assertEqual(d['bcd_cpt']['types'],['SINT','INT','DINT']);self.assertFalse(d['bcd_cpt']['native_runtime_parity']);self.assertEqual(d['array_indices']['functions'],['FRD','TOD','SQR'])


if __name__=='__main__':unittest.main()
