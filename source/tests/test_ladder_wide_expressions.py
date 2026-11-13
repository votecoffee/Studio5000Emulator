"""Ladder wide expressions: exact values, rung semantics and fault boundaries."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class LadderWideExpressionTests(unittest.TestCase):
    setUp=fixtures.BitTransferTests.setUp

    def engine(self,rungs,*,dtype='LINT',values=(7,3,13),types=None,mutate=None):
        return fixtures.BitTransferTests.engine(self,rungs,types=types or (dtype,)*3,values=values,mutate=mutate)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def test_cpt_arithmetic_for_all_five_types(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            for expression,expected in (('Source+Mask*2',13),('(Source+Mask)*2',20),('Source-Mask',4),
                                        ('Source/Mask',2),('Source MOD Mask',1),('ABS(Source)',7),('+Source',7)):
                with self.subTest(dtype=dtype,expression=expression):
                    e=self.checked(['CPT(Dest,'+expression+');'],dtype=dtype);e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_cpt_uses_destination_context_for_literal_only_expressions(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            e=self.checked(['CPT(Dest,1+2*3);'],dtype=dtype);e.step();self.assertEqual(e.memory.read('Dest'),7)
        e=self.checked(['CPT(Dest,-2147483648/2);']);e.step();self.assertEqual(e.memory.read('Dest'),-1073741824)

    def test_cpt_preserves_adjacent_values_above_double_precision(self):
        for dtype in ('LINT','ULINT'):
            e=self.checked(['CPT(Dest,Source+Mask);'],dtype=dtype,values=(9007199254740993,2,0));e.step()
            self.assertEqual(e.memory.read('Dest'),9007199254740995)
            self.assertEqual(next(row['value'] for row in e.memory.leaves() if row['name']=='Dest'),'9007199254740995')

    def test_quotients_and_remainders_are_exact_at_64_bit_limits(self):
        for dtype,a,b,q,r in (('LINT',-9223372036854775808,3,-3074457345618258602,-2),
                               ('LINT',7,-3,-2,1),('LINT',-7,-3,2,-1),
                               ('ULINT',18446744073709551615,3,6148914691236517205,0)):
            for expression,expected in (('Source/Mask',q),('Source MOD Mask',r)):
                e=self.checked(['CPT(Dest,'+expression+');'],dtype=dtype,values=(a,b,0));e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_each_intermediate_truncates_and_preserves_the_quotient_identity(self):
        e=self.checked(['CPT(Dest,(Source/Mask)*Mask);','CMP(Dest+(Source MOD Mask)=Source)OTE(RunLatch);'],values=(-7,3,0));e.step()
        self.assertEqual(e.memory.read('Dest'),-6);self.assertTrue(e.memory.read('RunLatch'))

    def test_cpt_bitwise_operators_respect_the_declared_width(self):
        for dtype,bits in (('LINT',64),('USINT',8),('UINT',16),('UDINT',32),('ULINT',64)):
            for expression,expected in (('Source AND Mask',3),('Source OR Mask',7),('Source XOR Mask',4),
                                        ('NOT Source',-8 if dtype=='LINT' else (1<<bits)-8)):
                e=self.checked(['CPT(Dest,'+expression+');'],dtype=dtype);e.step();self.assertEqual(e.memory.read('Dest'),expected)
        e=self.checked(['CPT(Dest,NOT Source);'],dtype='ULINT',values=(0,1,0));e.step();self.assertEqual(e.memory.read('Dest'),18446744073709551615)

    def test_cmp_relations_preserve_adjacent_large_values(self):
        for dtype in ('LINT','ULINT'):
            for relation,expected in (('=',False),('<>',True),('<',True),('<=',True),('>',False),('>=',False)):
                e=self.checked(['CMP(Source'+relation+'Mask)OTE(RunLatch);'],dtype=dtype,values=(9007199254740992,9007199254740993,0));e.step()
                self.assertEqual(e.memory.read('RunLatch'),expected)

    def test_cmp_all_declared_types_and_bool_logic(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            for expression,expected in (('(Source>Mask)&&!StartPB',True),('(Source<Mask)||(Source=7)',True),
                                        ('(Source>Mask)^^(Source=7)',False),('(Source>Mask) AND NOT StartPB',True),
                                        ('(Source AND Mask)=3',True),('(Source<Mask)||(Source>Mask)&&StartPB',False)):
                e=self.checked(['CMP('+expression+')OTE(RunLatch);'],dtype=dtype);e.step();self.assertEqual(e.memory.read('RunLatch'),expected)

    def test_meq_matches_each_type_and_rechecks_changing_operands(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            e=self.checked(['MEQ(Source,Mask,Dest)OTE(RunLatch);'],dtype=dtype,values=(0x37,0x0f,7));e.step();self.assertTrue(e.memory.read('RunLatch'))
            e.memory.write('Dest',8);e.step();self.assertFalse(e.memory.read('RunLatch'))
            e.memory.write('Mask',0);e.step();self.assertTrue(e.memory.read('RunLatch'))
            self.assertEqual(e.memory.read('Source'),0x37);self.assertEqual(e.memory.read('Dest'),8)

    def test_meq_signed_and_unsigned_high_64_bit_patterns(self):
        for dtype,source,mask,compare,expected in (('LINT',-9223372036854775808,-9223372036854775808,-1,True),
                                                  ('LINT',-1,-1,0,False),('ULINT',18446744073709551615,1<<63,1<<63,True),
                                                  ('ULINT',1<<63,1<<63,0,False)):
            e=self.checked(['MEQ(Source,Mask,Dest)OTE(RunLatch);'],dtype=dtype,values=(source,mask,compare));e.step();self.assertEqual(e.memory.read('RunLatch'),expected)

    def test_meq_accepts_bounded_representable_decimal_and_radix_literals(self):
        for mask in ('15','16#F','8#17','2#1111'):
            e=self.checked([f'MEQ(Source,{mask},7)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['MEQ(Source,-1,Source)OTE(RunLatch);'],values=(-1,0,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_rungs_retain_cpt_dest_and_clear_downstream_coils(self):
        e=self.checked(['AFI()CPT(Dest,Source/0);','AFI()CMP(Source/0>Mask)OTE(RunLatch);','AFI()MEQ(Source,Mask,Dest)OTE(BatchComplete);'])
        e.memory.values['source']=None;e.memory.write('RunLatch',True);e.memory.write('BatchComplete',True);e.step()
        self.assertEqual(e.memory.read('Dest'),13);self.assertFalse(e.memory.read('RunLatch'));self.assertFalse(e.memory.read('BatchComplete'))

    def test_unknown_dest_can_be_established_without_reading_old_value(self):
        e=self.checked(['CPT(Dest,Source+Mask);']);e.memory.values['dest']=None;e.step();self.assertEqual(e.memory.read('Dest'),10)

    def test_required_unknowns_fault_even_under_zero_mask_or_true_logic(self):
        for rung in ('CPT(Dest,Source+1);','CMP((1=1)||(Source>Mask))OTE(RunLatch);','MEQ(Source,0,0)OTE(RunLatch);'):
            e=self.checked(['MOV(99,SpeedCommand);',rung]);e.memory.values['source']=None;before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_cmp_logical_operands_are_eager(self):
        for expression in ('(1=1)||(Source/Mask>0)','(1=2)&&(Source/Mask>0)','(1=1)^^(Source/Mask>0)'):
            e=self.checked(['MOV(99,SpeedCommand);','CMP('+expression+')OTE(RunLatch);'],values=(7,0,13));before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_overflow_underflow_and_division_fault_roll_back_whole_advance(self):
        for dtype,expression,a,b in (('LINT','Source+Mask',9223372036854775807,1),
                                      ('ULINT','Source+Mask',18446744073709551615,1),('USINT','Source-Mask',0,1),
                                      ('LINT','ABS(Source)',-9223372036854775808,1),('LINT','Source/Mask',-9223372036854775808,-1),
                                      ('UINT','Source/Mask',7,0),('LINT','(Source+Mask)-Mask',9223372036854775807,1)):
            e=self.checked(['MOV(99,SpeedCommand);','CPT(Dest,'+expression+');'],dtype=dtype,values=(a,b,13));before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_mixed_types_float_power_functions_and_large_immediates_block_even_false(self):
        for expression in ('Source+1.0','Source+2147483648','Source+16#100000000','Source**2.0','SQRT(Source)','TRN(Source)',
                           'Source+RunLatch','NOT RunLatch','Source+1UL','Source+Unknown'):
            self.assertTrue(self.engine(['AFI()CPT(Dest,'+expression+');']).blockers,expression)
        for types in (('LINT','DINT','LINT'),('LINT','ULINT','LINT'),('LINT','LINT','REAL'),('LINT','LINT','DINT')):
            self.assertTrue(self.engine(['AFI()CPT(Dest,Source+(Mask+1));'],types=types).blockers)
        for expression in ('Source','Source&&StartPB','!(Source)','Source=1.0','Source**2.0=1','Source>Mask>Dest'):
            self.assertTrue(self.engine(['AFI()CMP('+expression+')OTE(RunLatch);']).blockers,expression)

    def test_meq_bad_literals_and_nonintegers_remain_blocked(self):
        for types in (('LINT','REAL','LINT'),('USINT','BOOL','USINT')):
            self.assertTrue(self.engine(['AFI()MEQ(Source,Mask,Dest)OTE(RunLatch);'],types=types).blockers)
        for operand in ('2147483648','-2147483649','16#100000000','1.0','RunLatch'):
            self.assertTrue(self.engine([f'AFI()MEQ(Source,{operand},Dest)OTE(RunLatch);']).blockers)
        self.assertTrue(self.engine(['CPT(Dest,-1);'],dtype='UINT').blockers)

    def test_controller_firmware_and_constant_destination_gates(self):
        for key,value in (('ProcessorType','1756-L75'),('ProcessorType','5069-L340ERM'),('MajorRev','34')):
            for rung in ('CPT(Dest,Source+Mask);','CMP(Source>Mask)OTE(RunLatch);','MEQ(Source,Mask,Dest)OTE(RunLatch);'):
                self.assertTrue(self.engine([rung],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        self.assertTrue(self.engine(['CPT(Dest,Source);'],mutate=lambda root:root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')).blockers)

    def test_alias_program_local_udt_and_dynamic_array_members(self):
        def tags(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Values',DataType='LINT',Dimension='2');E.SubElement(members,'Member',Name='Guard',DataType='LINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            array=E.SubElement(obj,'ArrayMember',Name='Values',DataType='LINT',Dimensions='2')
            for i,value in enumerate((17,19)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='9223372036854775807')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasA',DataType='LINT',TagType='Alias',AliasFor='Source')
            tag=E.SubElement(c.find('./Programs/Program/Tags'),'Tag',Name='Local',DataType='LINT',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LINT',Value='0')
        e=self.checked(['CPT(Packet1.Values[SpeedCommand],AliasA+Mask);','CPT(Local,Packet1.Values[SpeedCommand]);',
                        'CMP(Local>Source)MEQ(Local,0,0)OTE(RunLatch);'],values=(9007199254740993,2,0),mutate=tags)
        e.step();self.assertEqual(e.memory.read('Packet1.Values'),[9007199254740995,19]);self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('SpeedCommand',1);e.memory.write('Source',20);e.step();self.assertEqual(e.memory.read('Packet1.Values'),[9007199254740995,22])
        self.assertEqual(e.memory.read('Packet1.Guard'),9223372036854775807)
        e.memory.write('SpeedCommand',2);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_typed_jsr_sbr_ret_and_rll_aoi_inout(self):
        def aoi(root):
            sample=E.parse(Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()
            definition=copy.deepcopy(sample.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition'))
            for node in definition.iter():
                if node.get('DataType')=='DINT':node.set('DataType','LINT')
            body=definition.find('./Routines/Routine[@Name="Logic"]/RLLContent');body.clear()
            for i,text in enumerate(('CPT(Count,Count+Step);','CPT(Total,Count);','CPT(Shared,Shared+Step);','CMP(Count<Limit)MEQ(Shared,0,0)OTE(EnableOut);')):
                E.SubElement(E.SubElement(body,'Rung',Number=str(i),Type='N'),'Text').text=text
            root.find('./Controller/AddOnInstructionDefinitions').append(definition)
            obj=E.SubElement(E.SubElement(E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',TagType='Base',DataType='LabAccumulator'),'Data',Format='Decorated'),'Structure',DataType='LabAccumulator')
            for name,dtype,value in (('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Step','LINT',0),('Total','LINT',0),('Limit','LINT',100)):
                E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
        e=self.checked(['LabAccumulator(Instance,Mask,Dest,Source);'],values=(9007199254740993,2,0),mutate=aoi);e.step();e.step()
        self.assertEqual(e.memory.read('Source'),9007199254740997);self.assertEqual(e.memory.read('Dest'),4);self.assertEqual(e.calls.stack,[])
        def sub(root):
            program=root.find('./Controller/Programs/Program');tag=E.SubElement(program.find('Tags'),'Tag',Name='Local',TagType='Base',DataType='LINT')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LINT',Value='0')
            content=E.SubElement(E.SubElement(program.find('Routines'),'Routine',Name='Sub',Type='RLL'),'RLLContent')
            for i,text in enumerate(('SBR(Local);','CPT(Local,Local+1);','RET(Local);')):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        e=self.checked(['JSR(Sub,1,Source,Dest);'],values=(9007199254740993,2,0),mutate=sub);e.step();self.assertEqual(e.memory.read('Dest'),9007199254740994)

    def test_periodic_event_and_isolated_routine_execution(self):
        sample=Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'
        root=E.parse(sample).getroot();task=root.find('./Controller/Tasks/Task');task.set('Type','Periodic');task.set('Rate','10')
        path=Path(self.tmp.name)/'periodic.L5X';E.ElementTree(root).write(path,encoding='utf8')
        for e in (Engine(Project(path)),Engine(Project(sample),mode='routine',routine='MainProgram/MainRoutine')):
            self.assertEqual(e.blockers,[]);e.step(10);self.assertEqual(e.memory.read('SignedResult'),9007199254740995)
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventCalc',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            content=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventCalc',Type='RLL'),'RLLContent')
            for i,text in enumerate(('CPT(Dest,Source+Mask);','CMP(Dest>Source)MEQ(Dest,0,0)OTE(RunLatch);')):
                E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='CalcEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(['EVENT(CalcEvent);'],mutate=event);e.step();self.assertEqual(e.memory.read('Dest'),10);self.assertTrue(e.memory.read('RunLatch'))

    def test_run_entry_retains_cpt_destination_and_prescans_comparison_coils(self):
        e=self.checked(['XIC(StartPB)CPT(Dest,Source+Mask);','CMP(Source>Mask)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.enter_run();self.assertEqual(e.memory.read('Dest'),13);self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Dest'),10)

    def test_instruction_budget_failure_rolls_back(self):
        e=self.checked(['CPT(Dest,Source+Mask);','CMP(Dest>Source)MEQ(Dest,0,0)OTE(RunLatch);']);e.instruction_limit=2;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_report_preserves_dispatch_inventory_and_marks_remaining_forms(self):
        from logixlab.model import ARITIES, ST_ONLY_ARITIES
        e=self.checked(['CPT(Dest,Source+Mask);']);profile=e.report()['wide_ladder_expressions']
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(108,29));self.assertEqual(profile['instructions'],['CPT','CMP','MEQ'])
        self.assertTrue(profile['available']);self.assertTrue(profile['mixed_numeric_types']);self.assertFalse(profile['native_runtime_parity'])

    def test_wide_helpers_stay_opt_in_and_file_consumers_qualify_separately(self):
        from logixlab.model import Op
        e=self.checked(['CMP(Source>Mask)OTE(RunLatch);'])
        with self.assertRaises(ModelError):e.extensions.condition('Source>Mask').validate(e.memory,'MainProgram')
        self.assertTrue(e.extensions.condition('Source>Mask',allow_wide=True).evaluate(e.memory,'MainProgram'))
        with self.assertRaises(ModelError):e.extensions.expression('Source+Mask').validate(e.memory,'MainProgram','LINT')
        import test_array_statistics as files
        for rung in ('FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>0);','FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1);'):
            file_engine=files.ArrayStatisticsTests.engine(self,[rung],dtype='LINT');self.assertEqual(file_engine.blockers,[]);file_engine.step()

    def test_bundled_ladder_lab_large_values_gating_and_late_fault_retry(self):
        from logixlab.server import SAMPLES
        self.assertIn('WideExpressionLab',SAMPLES);e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[])
        self.assertEqual({r.kind for r in e.project.routines.values()},{'RLL'});e.step()
        self.assertEqual(e.memory.read('SignedResult'),9007199254740995);self.assertEqual(e.memory.read('UnsignedResult'),18446744073709551615)
        self.assertTrue(e.memory.read('ExactCompare'));self.assertTrue(e.memory.read('MaskMatches'));self.assertEqual(e.memory.read('SignedQuotient'),-3074457345618258602)
        e.memory.write('Execute',False);e.memory.write('SignedInput',1);e.step();self.assertEqual(e.memory.read('SignedResult'),9007199254740995);self.assertFalse(e.memory.read('ExactCompare'))
        e.memory.write('Execute',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('SignedResult'),3)


if __name__=='__main__':unittest.main()
