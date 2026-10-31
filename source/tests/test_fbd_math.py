"""Finite REAL arithmetic Block forms, logical records and transactional faults."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.fbd_math import SCHEMAS,default
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDMathLab.L5X'


class FBDMathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="ComputeSignals"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'math.L5X';E.ElementTree(root).write(p,encoding='utf8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/ComputeSignals' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def settings(e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e):
        e.step(10);return tuple(e.memory.read(t) for t in ('Sum','Difference','Product','Quotient','Negative','Magnitude'))

    def test_six_block_chain_and_operand_order(self):
        e=self.checked();self.assertEqual(self.step(e),(8,7,21,7,-7,7));self.assertEqual(e.last_timer,{})
        self.settings(e,A=2,B=6,Offset=10,Gain=4,Divisor=2)
        self.assertEqual(self.step(e),(8,-2,-8,-4,4,4))

    def test_negative_divisor_and_zero_multiplication(self):
        e=self.checked();self.settings(e,Divisor=-3);self.assertEqual(self.step(e),(8,7,21,-7,7,7))
        self.settings(e,Gain=0);self.assertEqual(self.step(e),(8,7,0,0,0,0))

    def test_float32_rounding_occurs_between_connected_blocks(self):
        e=self.checked();self.settings(e,A=16777216,B=1,Offset=16777216,Gain=1,Divisor=1)
        self.assertEqual(self.step(e),(16777216,0,0,0,0,0))

    def test_negation_and_absolute_value_signed_zero(self):
        e=self.checked();self.settings(e,A=0,B=0,Offset=0);self.step(e)
        self.assertEqual(math.copysign(1,e.memory.read('Negative')),-1)
        self.assertEqual(math.copysign(1,e.memory.read('Magnitude')),1)

    def test_math_schemas_and_member_types_are_exact(self):
        e=self.checked();self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))
        for tag,dtype in (('Adder','FBD_MATH'),('Absolute','FBD_MATH_ADVANCED')):
            self.assertNotIn(dtype,e.project.data_only_types)
            for pin,kind in SCHEMAS[dtype].items():self.assertEqual(e.memory.resolve(tag+'.'+pin)[2],kind)
            self.assertTrue(default(dtype)['EnableIn']);self.assertFalse(default(dtype)['EnableOut'])
        self.assertEqual(len(SCHEMAS['FBD_MATH']),5);self.assertEqual(len(SCHEMAS['FBD_MATH_ADVANCED']),4)

    def test_prescan_is_noop_for_math_enables_and_saved_destinations(self):
        def saved(root):
            for obj in root.findall('./Controller/Tags/Tag/Data/Structure'):
                obj.find('DataValueMember[@Name="EnableIn"]').set('Value','0')
                obj.find('DataValueMember[@Name="EnableOut"]').set('Value','1')
                obj.find('DataValueMember[@Name="Dest"]').set('Value','99')
        e=self.checked(saved)
        for tag in ('Adder','Subtracter','Multiplier','Divider','Negater','Absolute'):
            self.assertFalse(e.memory.read(tag+'.EnableIn'));self.assertTrue(e.memory.read(tag+'.EnableOut'));self.assertEqual(e.memory.read(tag+'.Dest'),99)
        self.assertEqual(self.step(e),(8,7,21,7,-7,7))

    def test_run_preserves_math_enables_dest_and_has_no_hidden_state(self):
        e=self.checked();self.step(e);before=copy.deepcopy(e.memory.values);e.enter_run()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})
        self.settings(e,A=10);self.assertEqual(self.step(e),(12,11,33,11,-11,11))

    def test_disabled_blocks_hold_dest_and_skip_unknowns_and_zero_divisor(self):
        e=self.checked();expected=self.step(e);self.settings(e,BlockEnable=False,Divisor=0)
        for tag in ('A','B','Offset','Gain'):self.unknown(e,tag)
        self.assertEqual(self.step(e),expected);self.assertFalse(e.memory.read('MathEnabled'));self.assertEqual(e.last_timer,{})

    def test_unwired_enable_executes_despite_saved_false(self):
        def unwire(root):
            sheet=self.sheet(root)
            for w in list(sheet.findall('Wire')):
                if w.get('ToParam')=='EnableIn':sheet.remove(w)
        e=self.checked(unwire);self.settings(e,BlockEnable=False)
        for tag in ('Adder','Subtracter','Multiplier','Divider','Negater','Absolute'):e.memory.write(tag+'.EnableIn',False)
        self.assertEqual(self.step(e),(8,7,21,7,-7,7));self.assertTrue(e.memory.read('MathEnabled'))

    def test_skipped_routine_keeps_outputs_until_next_reached_call(self):
        e=self.checked();expected=self.step(e);self.settings(e,ExecuteGraph=False,A=10)
        self.assertEqual(self.step(e),expected);self.settings(e,ExecuteGraph=True)
        self.assertEqual(self.step(e),(12,11,33,11,-11,11))

    def test_unwired_source_uses_saved_value_and_wired_source_overwrites_it(self):
        def unwire(root):
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="SourceB"]'))
        e=self.checked(unwire);self.settings(e,**{'Adder.SourceA':100,'Adder.SourceB':4})
        self.assertEqual(self.step(e),(10,9,27,9,-9,9));self.assertEqual(e.memory.read('Adder.SourceA'),6)

    def test_omitted_saved_source_stays_unknown_without_shape_substitution(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Adder"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="SourceB"]'))
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="SourceB"]'))
        e=self.checked(missing)
        with self.assertRaisesRegex(ModelError,'ADD SourceB is unknown'):self.step(e)

    def test_unknown_on_either_binary_input_and_unary_input_faults(self):
        for tag in ('A','B','Offset','Gain','Divisor'):
            e=self.checked();self.unknown(e,tag);before=self.snapshot(e)
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)
        def unwire(root):
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="600"][@ToParam="Source"]'))
        e=self.checked(unwire);self.unknown(e,'Absolute.Source')
        with self.assertRaisesRegex(ModelError,'ABS Source is unknown'):self.step(e)

    def test_binary_does_not_short_circuit_unknown_when_other_operand_is_zero(self):
        e=self.checked();self.settings(e,A=-2);self.unknown(e,'Gain');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'MUL SourceB is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_non_numeric_bool_nonfinite_inputs_are_not_coerced_to_real(self):
        def unwire(root):
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="SourceA"]'))
        for value in (True,'1',float('inf'),float('nan')):
            e=self.checked(unwire);key,parts,_=e.memory.resolve('Adder.SourceA');e.memory.store(key,parts,value)
            with self.subTest(value=value),self.assertRaises(ModelError):self.step(e)
            self.assertIs(e.memory.at(key,parts),value);self.assertEqual(e.scan_count,0)

    def test_zero_divisor_is_an_explicit_unsupported_minor_fault_and_rolls_back(self):
        for value in (0.0,-0.0):
            e=self.checked();self.step(e);self.settings(e,A=10,Divisor=value);before=self.snapshot(e)
            with self.subTest(value=value),self.assertRaisesRegex(ModelError,'zero-divisor minor-fault'):self.step(e)
            self.assertEqual(self.snapshot(e),before);self.settings(e,Divisor=3)
            self.assertEqual(self.step(e),(12,11,33,11,-11,11))

    def test_result_overflow_rolls_back_earlier_blocks_and_all_enables(self):
        e=self.checked();self.step(e);self.settings(e,Gain=3.4028234663852886e38);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'finite REAL'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,Gain=3);self.assertEqual(self.step(e),(8,7,21,7,-7,7))

    def test_late_ladder_fault_restores_computed_destinations(self):
        e=self.checked();self.step(e);self.settings(e,A=10,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,A=20,FaultDivisor=1)
        self.assertEqual(self.step(e),(22,21,63,21,-21,21))

    def test_direct_dest_write_holds_disabled_and_is_recomputed_enabled(self):
        e=self.checked();self.step(e);self.settings(e,BlockEnable=False,**{'Divider.Dest':99})
        self.assertEqual(self.step(e)[3],99);self.settings(e,BlockEnable=True);self.assertEqual(self.step(e)[3],7)

    def test_enableout_bool_can_gate_downstream_math_block(self):
        def gate(root):
            sheet=self.sheet(root)
            for ident in (200,300,400,500,600):
                w=sheet.find(f'Wire[@ToID="{ident}"][@ToParam="EnableIn"]');w.set('FromID',str(ident-100));w.set('FromParam','EnableOut')
        e=self.checked(gate);self.step(e);self.settings(e,BlockEnable=False,Divisor=0)
        self.assertEqual(self.step(e),(8,7,21,7,-7,7));self.assertFalse(e.memory.read('MathEnabled'))

    def test_periodic_harness_and_deferred_prescan_keep_math_behavior(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        self.assertEqual(self.step(self.checked(periodic)),(8,7,21,7,-7,7))
        e=self.checked(mode='routine',defer=True);e.enter_run();self.assertTrue(e.memory.read('Adder.EnableIn'))
        self.assertEqual(self.step(e),(8,7,21,7,-7,7))

    def test_rll_and_st_existing_arithmetic_do_not_gain_record_call_overloads(self):
        for language in ('ST','RLL'):
            def wrong(root):
                routine=root.find('.//Routine[@Name="MainRoutine"]')
                if language=='ST':logic(routine,['ADD(Adder);'])
                else:routine.find('RLLContent/Rung/Text').text='ADD(Adder);'
            with self.subTest(language=language):self.assertTrue(self.engine(wrong).blockers)

    def test_nested_unary_record_and_program_local_binary_alias(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="Adder"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='LocalAdder',TagType='Alias',AliasFor='Program:MainProgram.Adder');self.sheet(root).find('Block[@Type="ADD"]').set('Operand','LocalAdder')
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='MathCell',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Value',DataType='FBD_MATH_ADVANCED',Dimension='0')
            tag=tags.find('Tag[@Name="Absolute"]');structure=tag.find('Data/Structure');tags.remove(tag)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='MathCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='MathCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='MathCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Value');obj.append(item)
            self.sheet(root).find('Block[@Type="ABS"]').set('Operand','Cells[1].Value')
        e=self.checked(nested);self.assertEqual(self.step(e),(8,7,21,7,-7,7));self.assertEqual(e.memory.read('Cells[0].Value.Dest'),0)

    def test_unrelated_math_prefix_udt_retains_declared_member_type(self):
        def extra(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_MATH_CUSTOM',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Count',DataType='DINT',Dimension='0')
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Custom',TagType='Base',DataType='FBD_MATH_CUSTOM');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='FBD_MATH_CUSTOM');E.SubElement(obj,'DataValueMember',Name='Count',DataType='DINT',Value='7')
        e=self.checked(extra);self.assertEqual(e.memory.resolve('Custom.Count')[2],'DINT');self.assertEqual(e.memory.read('Custom.Count'),7)

    def test_wrong_profile_constant_record_redefinition_and_pin_directions_block(self):
        for kind in ('profile','constant','record','redefined','wiretype','output','wrongpin','function'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="Adder"]').set('Constant','true')
                elif kind=='record':sheet.find('Block[@Type="ADD"]').set('Operand','Absolute')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_MATH',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Dest',DataType='REAL',Dimension='0')
                elif kind=='wiretype':sheet.find('IRef[@ID="1"]').set('Operand','CallCount')
                elif kind=='output':sheet.find('Wire[@ToID="100"]').set('ToParam','Dest')
                elif kind=='wrongpin':sheet.find('Block[@Type="ABS"]').set('VisiblePins','SourceA')
                else:sheet.find('Block').tag='Function'
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(ComputeSignals,0); EVENT(MathEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'ComputeSignals',Class='Standard',Disabled='false');E.SubElement(p,'Tags');rs=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(rs,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:rs.append(copy.deepcopy(root.find('.//Routine[@Name="ComputeSignals"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='MathEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_calls_are_stateless_and_deterministic(self):
        e=self.event_engine();self.assertEqual(self.step(e),(8,7,21,7,-7,7));self.assertEqual(e.last_timer,{})

    def test_event_failure_rolls_back_earlier_graph(self):
        e=self.event_engine(True);self.settings(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_budget_failure_restores_all_destinations(self):
        e=self.checked();e.instruction_limit=20;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_retains_values_and_graph_inventory(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);before=self.snapshot(e)
        texts=['JSR(ComputeSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.memory.values,e.memory.values)
        self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in ('ADD','SUB','MUL','DIV','NEG','ABS')))
        self.assertEqual(self.step(candidate),(8,7,21,7,-7,7))

    def test_inventory_reports_thirty_three_blocks_and_math_limits(self):
        e=self.checked();p=e.report()['function_blocks'];self.assertEqual(len(p['instructions']),33)
        self.assertEqual(p['blocks']['math']['instructions'],['ABS','ADD','DIV','MUL','NEG','SUB'])
        self.assertFalse(p['blocks']['math']['native_runtime_parity']);self.assertIn('prescan leaves',p['blocks']['math']['lifecycle'])


if __name__=='__main__':unittest.main()
