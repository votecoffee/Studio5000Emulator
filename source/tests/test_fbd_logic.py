"""BOOL truth tables and sampled memory in executable FBD graphs."""
import copy
import itertools
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.fbd_boolean import SCHEMAS,TYPES,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


class FBDBooleanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLES/'FBDLogicLab.L5X').getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'logic.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode,'MainProgram/BooleanLogic' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="BooleanLogic"]/FBDContent/Sheet')

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e):
        e.step(10);return tuple(e.memory.read(tag) for tag in ('AndOut','OrOut','NotOut','XorOut','DOut','ToggleOut','ResetLatch','SetLatch'))

    def test_all_two_input_truth_tables(self):
        e=self.checked()
        for a,b in itertools.product((False,True),repeat=2):
            e.memory.write('A',a);e.memory.write('B',b)
            self.assertEqual(self.step(e)[:4],(a and b,a or b,True,a!=b))

    def test_all_eight_and_inputs_and_chained_negated_reset(self):
        e=self.checked();e.memory.write('A',True);self.assertTrue(self.step(e)[0])
        for i in range(4,9):
            e.memory.write('AndGate.In'+str(i),False);self.assertFalse(self.step(e)[0])
            e.memory.write('AndGate.In'+str(i),True);self.assertTrue(self.step(e)[0])
        e.memory.write('ResetInput',True);v=self.step(e);self.assertFalse(v[0]);self.assertFalse(v[2])

    def test_all_eight_or_inputs_use_saved_unwired_values(self):
        e=self.checked();e.memory.write('B',False);self.assertFalse(self.step(e)[1])
        for i in range(3,9):
            e.memory.write('OrGate.In'+str(i),True);self.assertTrue(self.step(e)[1])
            e.memory.write('OrGate.In'+str(i),False);self.assertFalse(self.step(e)[1])

    def test_wired_values_overwrite_record_inputs_but_unwired_members_retain(self):
        e=self.checked();e.memory.write('AndGate.In1',True);e.memory.write('AndGate.In8',False)
        self.assertFalse(self.step(e)[0]);self.assertFalse(e.memory.read('AndGate.In1'));self.assertFalse(e.memory.read('AndGate.In8'))

    def test_boolean_literal_wires_are_typed_and_integer_literals_do_not_convert(self):
        def literals(root):
            self.sheet(root).find('IRef[@ID="1"]').set('Operand','TRUE');self.sheet(root).find('IRef[@ID="2"]').set('Operand','FALSE')
        self.assertEqual(self.step(self.checked(literals))[:4],(False,True,True,True))
        def integer(root):self.sheet(root).find('IRef[@ID="1"]').set('Operand','1')
        self.assertTrue(self.engine(integer).blockers)

    def test_shapes_member_types_and_boolean_record_classification(self):
        e=self.checked()
        for record,kind in (('AndGate','FBD_BOOLEAN_AND'),('OrGate','FBD_BOOLEAN_OR'),('NotGate','FBD_BOOLEAN_NOT'),('XorGate','FBD_BOOLEAN_XOR')):
            self.assertNotIn(kind,e.project.data_only_types)
            for name in SCHEMAS[kind]:self.assertEqual(e.memory.resolve(record+'.'+name)[2],'BOOL')
        self.assertTrue(all(default('FBD_BOOLEAN_AND')['In'+str(i)] for i in range(1,9)))
        self.assertTrue(default('FBD_BOOLEAN_NOT')['In']);self.assertFalse(default('FBD_BOOLEAN_OR')['EnableIn'])
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))

    def test_omitted_saved_and_input_remains_unknown_despite_true_shape(self):
        def omit(root):
            obj=root.find('./Controller/Tags/Tag[@Name="AndGate"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="In8"]'))
        e=self.checked(omit);self.assertFalse(e.memory.read('A'))
        with self.assertRaisesRegex(ModelError,'BAND In8 is unknown'):self.step(e)

    def test_or_does_not_short_circuit_away_unknown_input(self):
        e=self.checked();self.unknown(e,'OrGate.In8');self.assertTrue(e.memory.read('B'));before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'BOR In8 is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_not_and_xor_unknown_inputs_fault_without_boolean_coercion(self):
        for ident,pin,tag,expected in ((100,'In','NotGate.In','BNOT In'),(400,'In2','XorGate.In2','BXOR In2')):
            def unwire(root):
                sheet=self.sheet(root);sheet.remove(sheet.find(f'Wire[@ToID="{ident}"][@ToParam="{pin}"]'))
            e=self.checked(unwire);self.unknown(e,tag)
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,expected+' is unknown'):self.step(e)

    def test_non_bool_internal_values_are_rejected(self):
        for value in (0,1,1.0,'true'):
            e=self.checked();key,parts,_=e.memory.resolve('AndGate.In8');e.memory.store(key,parts,value)
            with self.subTest(value=value),self.assertRaisesRegex(ModelError,'not BOOL'):self.step(e)

    def test_default_complements_and_initial_dominant_latches(self):
        e=self.checked();self.assertEqual(self.step(e),(False,True,True,True,False,False,False,True))
        for output,complement in (('DOut','DNot'),('ToggleOut','ToggleNot'),('ResetLatch','ResetLatchNot'),('SetLatch','SetLatchNot')):
            self.assertEqual(e.memory.read(complement),not e.memory.read(output))
        self.assertEqual(len(e.last_timer),4);self.assertTrue(all(key[0]=='ST-DIGITAL' for key in e.last_timer))

    def test_latch_dominance_for_simultaneous_requests_and_retention(self):
        e=self.checked();self.step(e)
        for set_bit,reset_bit,expected in ((True,True,(False,True)),(True,False,(True,True)),(False,False,(True,True)),(False,True,(False,False)),(False,False,(False,False))):
            e.memory.write('SetInput',set_bit);e.memory.write('ResetInput',reset_bit)
            self.assertEqual(self.step(e)[6:],expected)

    def test_flip_flops_sample_rising_clock_and_ignore_held_data_changes(self):
        e=self.checked();e.memory.write('Clock',True);e.memory.write('DInput',True)
        self.assertEqual(self.step(e)[4:6],(False,False))
        e.memory.write('Clock',False);self.step(e);e.memory.write('Clock',True)
        self.assertEqual(self.step(e)[4:6],(True,True))
        e.memory.write('DInput',False);self.assertEqual(self.step(e)[4:6],(True,True))
        e.memory.write('Clock',False);self.step(e);e.memory.write('Clock',True)
        self.assertEqual(self.step(e)[4:6],(False,False))

    def test_clear_wins_and_samples_clock_without_retrigger_on_release(self):
        e=self.checked();self.step(e);e.memory.write('DInput',True);e.memory.write('Clock',True);self.step(e)
        e.memory.write('Clear',True);self.assertEqual(self.step(e)[4:6],(False,False))
        e.memory.write('Clear',False);self.assertEqual(self.step(e)[4:6],(False,False))
        e.memory.write('Clock',False);self.step(e);e.memory.write('Clock',True);self.assertEqual(self.step(e)[4:6],(True,True))

    def test_unused_d_may_be_unknown_until_an_uncleared_rising_edge(self):
        e=self.checked();self.unknown(e,'DInput');self.step(e);e.memory.write('Clear',True);e.memory.write('Clock',True);self.step(e)
        e.memory.write('Clear',False);self.step(e);e.memory.write('Clock',False);self.step(e);e.memory.write('Clock',True)
        with self.assertRaisesRegex(ModelError,'DFF D is unknown'):self.step(e)

    def test_disabled_blocks_retain_values_and_history_with_unknown_inputs(self):
        e=self.checked();before_values=self.step(e);before=copy.deepcopy(e.last_timer);e.memory.write('BlockEnable',False)
        for tag in ('A','B','ResetInput','SetInput','Clock','DInput','Clear'):self.unknown(e,tag)
        self.assertEqual(self.step(e),before_values);self.assertEqual(e.last_timer,before)
        for record in ('NotGate','AndGate','OrGate','XorGate','DState','ToggleState','ResetState','SetState'):
            self.assertFalse(e.memory.read(record+'.EnableOut'))

    def test_disabled_first_call_does_not_seed_digital_history(self):
        e=self.checked();e.memory.write('BlockEnable',False);self.step(e);self.assertEqual(e.last_timer,{})
        e.memory.write('Clock',True);e.memory.write('DInput',True);e.memory.write('BlockEnable',True)
        self.assertEqual(self.step(e)[4:6],(False,False))

    def test_reenabled_clock_uses_last_sample_and_clear_is_not_asynchronous(self):
        e=self.checked();self.step(e);e.memory.write('BlockEnable',False);e.memory.write('Clock',True);e.memory.write('DInput',True);self.step(e)
        e.memory.write('BlockEnable',True);self.assertEqual(self.step(e)[4:6],(True,True))
        e.memory.write('BlockEnable',False);e.memory.write('Clear',True);self.assertEqual(self.step(e)[4:6],(True,True))
        e.memory.write('BlockEnable',True);self.assertEqual(self.step(e)[4:6],(False,False))

    def test_unwired_enables_execute_even_with_saved_bor_enable_false(self):
        def unwire(root):
            sheet=self.sheet(root)
            for wire in list(sheet.findall('Wire')):
                if wire.get('ToParam')=='EnableIn':sheet.remove(wire)
        e=self.checked(unwire);e.memory.write('BlockEnable',False);self.assertEqual(self.step(e)[1],True)
        self.assertTrue(e.memory.read('OrGate.EnableIn'));self.assertTrue(e.memory.read('OrGate.EnableOut'))

    def test_skipped_routine_keeps_combinatorial_outputs_and_clock_samples(self):
        e=self.checked();before=self.step(e);history=copy.deepcopy(e.last_timer);e.memory.write('ExecuteGraph',False)
        e.memory.write('A',True);e.memory.write('Clock',True);e.memory.write('DInput',True)
        self.assertEqual(self.step(e),before);self.assertEqual(e.last_timer,history)
        e.memory.write('ExecuteGraph',True);self.assertEqual(self.step(e),(True,True,True,False,True,True,False,True))

    def test_direct_output_writes_do_not_replace_hidden_latch_or_clock_state(self):
        e=self.checked();self.step(e);e.memory.write('SetState.Out',False);e.memory.write('DState.Q',True)
        e.memory.write('DState.QNot',True);v=self.step(e);self.assertFalse(v[4]);self.assertTrue(v[7]);self.assertTrue(e.memory.read('DNot'))

    def test_late_ladder_fault_restores_truth_outputs_and_digital_history(self):
        e=self.checked();self.step(e);e.memory.write('A',True);e.memory.write('Clock',True);e.memory.write('DInput',True);e.memory.write('SetInput',True);e.memory.write('FaultDivisor',0)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('DInput',False);e.memory.write('FaultDivisor',1)
        v=self.step(e);self.assertFalse(v[4]);self.assertTrue(v[5]);self.assertEqual(v[6:],(True,True))
        self.assertTrue(self.step(e)[5])

    def test_late_digital_unknown_fault_restores_earlier_boolean_outputs(self):
        e=self.checked();self.step(e);e.memory.write('A',True);self.unknown(e,'Clock');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Clock is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_enable_unknown_is_not_false(self):
        e=self.checked();self.unknown(e,'BlockEnable');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'EnableIn is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_run_entry_resets_history_without_a_normal_scan(self):
        e=self.checked();self.step(e);e.memory.write('Clock',True);e.memory.write('DInput',True);e.memory.write('SetInput',True);self.step(e)
        e.memory.write('SetInput',False);e.enter_run();self.assertTrue(e.memory.read('DOut'));self.assertEqual(e.last_timer,{})
        v=self.step(e);self.assertEqual(v[4:],(False,False,False,True))

    def test_periodic_and_harness_prescan_preserve_saved_values_until_execution(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','Periodic');task.set('Rate','10')
        self.assertEqual(self.step(self.checked(periodic))[:4],(False,True,True,True))
        e=self.checked(mode='routine',defer=True);self.assertTrue(e.memory.read('AndGate.EnableIn'));self.assertFalse(e.memory.read('OrGate.EnableIn'))
        e.enter_run();self.assertFalse(e.memory.read('AndGate.EnableIn'));self.assertEqual(self.step(e)[:4],(False,True,True,True))

    def test_fbd_only_boolean_names_and_tagless_function_forms_block(self):
        for name,record in (('BAND','AndGate'),('BOR','OrGate'),('BNOT','NotGate'),('BXOR','XorGate')):
            for kind in ('ST','RLL'):
                def language(root):
                    routine=root.find('.//Routine[@Name="MainRoutine"]')
                    if kind=='ST':logic(routine,[name+'('+record+');'])
                    else:routine.find('RLLContent/Rung/Text').text=name+'('+record+');'
                with self.subTest(name=name,kind=kind):self.assertTrue(self.engine(language).blockers)
        def function(root):self.sheet(root).find('Block').tag='Function'
        self.assertTrue(self.engine(function).blockers)

    def test_wrong_types_profiles_constants_redefinitions_and_pin_direction_block(self):
        for kind in ('constant','profile','wrongrecord','wiretype','outputpin','xorinput','redefined'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='constant':root.find('./Controller/Tags/Tag[@Name="AndGate"]').set('Constant','true')
                elif kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='wrongrecord':sheet.find('Block[@Type="BAND"]').set('Operand','OrGate')
                elif kind=='wiretype':sheet.find('IRef[@ID="1"]').set('Operand','CallCount')
                elif kind=='outputpin':sheet.find('Wire[@ToID="200"]').set('ToParam','Out')
                elif kind=='xorinput':sheet.find('Block[@Type="BXOR"]').set('VisiblePins','In3')
                else:
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_BOOLEAN_AND',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='BOOL',Dimension='0')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_nested_boolean_record_and_program_local_alias_resolve_bool_members(self):
        def nested(root):
            tags=root.find('./Controller/Tags');gate=tags.find('Tag[@Name="AndGate"]');tags.remove(gate);root.find('./Controller/Programs/Program/Tags').append(gate)
            E.SubElement(tags,'Tag',Name='LocalAnd',TagType='Alias',AliasFor='Program:MainProgram.AndGate');self.sheet(root).find('Block[@Type="BAND"]').set('Operand','LocalAnd')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='BoolCell',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Gate',DataType='FBD_BOOLEAN_OR',Dimension='0')
            gate=tags.find('Tag[@Name="OrGate"]');structure=gate.find('Data/Structure');tags.remove(gate)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='BoolCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='BoolCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='BoolCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Gate');obj.append(item)
            self.sheet(root).find('Block[@Type="BOR"]').set('Operand','Cells[1].Gate')
        e=self.checked(nested);self.assertEqual(self.step(e)[:4],(False,True,True,True))
        self.assertEqual(e.memory.resolve('Cells[1].Gate.In8')[2],'BOOL');self.assertFalse(e.memory.read('Cells[0].Gate.Out'))

    def test_unrelated_udt_with_boolean_prefix_keeps_its_declared_member_types(self):
        def extra(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_BOOLEAN_CUSTOM',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Value',DataType='DINT',Dimension='0')
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Custom',TagType='Base',DataType='FBD_BOOLEAN_CUSTOM');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='FBD_BOOLEAN_CUSTOM');E.SubElement(obj,'DataValueMember',Name='Value',DataType='DINT',Value='7')
        e=self.checked(extra);self.assertEqual(e.memory.resolve('Custom.Value')[2],'DINT');self.assertEqual(e.memory.read('Custom.Value'),7)

    def test_st_digital_calls_share_fbd_clock_without_double_toggle(self):
        def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(BooleanLogic,0); DFF(DState); JKFF(ToggleState);'])
        e=self.checked(st);self.step(e);e.memory.write('Clock',True);e.memory.write('DInput',True)
        self.assertEqual(self.step(e)[4:6],(True,True));self.assertTrue(e.memory.read('ToggleState.Q'))

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(BooleanLogic,0); EVENT(LogicEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'BooleanLogic',Class='Standard',Disabled='false');E.SubElement(p,'Tags');routines=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(routines,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:routines.append(copy.deepcopy(root.find('.//Routine[@Name="BooleanLogic"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='LogicEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_task_shares_clock_history_without_double_toggle(self):
        e=self.event_engine();self.step(e);e.memory.write('Clock',True);e.memory.write('DInput',True)
        self.assertEqual(self.step(e)[4:6],(True,True))

    def test_event_fault_rolls_back_truth_and_latch_state(self):
        e=self.event_engine(True);self.step(e);e.memory.write('Clock',True);e.memory.write('DInput',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e)[4:6],(True,True))

    def test_budget_failure_rolls_back_boolean_writes_and_hidden_state(self):
        e=self.checked();e.instruction_limit=25;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_preserves_digital_state_and_new_inventory(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);e.memory.write('Clock',True);e.memory.write('DInput',True);self.step(e);before=self.snapshot(e)
        neutral=['JSR(BooleanLogic,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertTrue(all(candidate.project.instruction_counts[name]==1 for name in ('BAND','BOR','BNOT','BXOR','DFF','JKFF','RESD','SETD')))
        self.assertEqual(self.step(candidate)[4:6],(True,True))

    def test_report_has_twenty_three_blocks_and_four_fbd_only_boolean_types(self):
        e=self.checked();profile=e.report()['function_blocks'];self.assertEqual(len(profile['instructions']),23)
        self.assertEqual(profile['blocks']['boolean']['instructions'],['BAND','BNOT','BOR','BXOR'])
        self.assertFalse(profile['native_runtime_parity']);self.assertFalse(profile['blocks']['boolean']['native_runtime_parity'])


if __name__=='__main__':unittest.main()
