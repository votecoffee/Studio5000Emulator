"""Shared signal models in real FBD graphs, typed diagnostics and rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


class FBDSignalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLES/'FBDSignalLab.L5X').getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'signals.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode,'MainProgram/ConditionSignals' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e):e.step(10);return tuple(e.memory.read(tag) for tag in ('Scaled','Limited','Negated','Summed'))

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="ConditionSignals"]/FBDContent/Sheet')

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    def test_default_chain_and_all_four_block_traces(self):
        e=self.checked();self.assertEqual(self.step(e),(50,50,50,53))
        self.assertEqual([t['detail'] for t in e.trace if t.get('language')=='FBD'],['SCL','HLL','SNEG','SSUM'])
        self.assertEqual(e.last_timer,{})

    def test_scaling_extrapolation_limiting_and_raw_alarm_wires(self):
        e=self.checked();e.memory.write('RawInput',15);self.assertEqual(self.step(e),(150,80,80,83))
        self.assertTrue(e.memory.read('Scaler.MaxAlarm'));self.assertFalse(e.memory.read('Scaler.MinAlarm'))
        e.memory.write('Limiting',True);self.assertEqual(self.step(e),(100,80,80,83))
        e.memory.write('RawInput',-5);self.assertEqual(self.step(e),(0,20,20,23));self.assertTrue(e.memory.read('Scaler.MinAlarm'))

    def test_reversed_engineering_range_and_endpoint_alarm_rules(self):
        e=self.checked();e.memory.write('EUMax',0);e.memory.write('EUMin',100)
        e.memory.write('RawInput',0);self.assertEqual(self.step(e),(100,80,80,83));self.assertFalse(e.memory.read('Scaler.MinAlarm'))
        e.memory.write('RawInput',10);self.assertEqual(self.step(e),(0,20,20,23));self.assertFalse(e.memory.read('Scaler.MaxAlarm'))

    def test_scaler_invalid_range_preserves_prior_output_and_sets_bool_diagnostics(self):
        e=self.checked();self.step(e);e.memory.write('RawMax',0);self.assertEqual(self.step(e),(50,50,50,53))
        self.assertEqual(e.memory.read('ScaleStatus'),3);self.assertTrue(e.memory.read('ScaleFault'));self.assertTrue(e.memory.read('RangeInvalid'))
        e.memory.write('RawMax',20);self.assertEqual(self.step(e),(25,25,25,28));self.assertFalse(e.memory.read('ScaleFault'))

    def test_invalid_scaling_range_does_not_read_unknown_unused_operands(self):
        e=self.checked();self.step(e);e.memory.write('RawMax',0)
        for tag in ('RawInput','EUMax','EUMin','Limiting'):self.unknown(e,tag)
        self.assertEqual(self.step(e),(50,50,50,53));e.memory.write('RawMax',10)
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)

    def test_hll_modes_inclusive_alarms_and_ignored_limit(self):
        e=self.checked();e.memory.write('RawInput',8);self.assertEqual(self.step(e),(80,80,80,83));self.assertTrue(e.memory.read('HighAlarm'))
        e.memory.write('RawInput',2);self.step(e);self.assertTrue(e.memory.read('LowAlarm'))
        e.memory.write('LimitMode',1);self.unknown(e,'LowLimit');self.assertEqual(self.step(e),(20,20,20,23));self.assertFalse(e.memory.read('LowAlarm'))
        e.memory.write('LimitMode',2);e.memory.write('LowLimit',30);self.unknown(e,'HighLimit')
        self.assertEqual(self.step(e),(20,30,30,33));self.assertFalse(e.memory.read('HighAlarm'))

    def test_limit_selector_and_range_status_bits_are_independent(self):
        e=self.checked();e.memory.write('LimitMode',9);self.assertEqual(self.step(e),(50,50,50,53))
        self.assertEqual(e.memory.read('LimitStatus'),5);self.assertTrue(e.memory.read('ModeInvalid'));self.assertFalse(e.memory.read('LimitsInvalid'))
        e.memory.write('HighLimit',10);e.memory.write('LowLimit',90);self.assertEqual(self.step(e),(50,90,90,93))
        self.assertEqual(e.memory.read('LimitStatus'),7);self.assertTrue(e.memory.read('LimitsInvalid'));self.assertTrue(e.memory.read('LimitFault'))
        e.memory.write('LimitMode',0);self.step(e);self.assertEqual(e.memory.read('LimitStatus'),3);self.assertFalse(e.memory.read('ModeInvalid'))

    def test_negation_weighted_inputs_gain_bias_and_no_selection(self):
        e=self.checked();e.memory.write('Negate',True);e.memory.write('Trim',3);e.memory.write('Gain',4)
        self.assertEqual(self.step(e),(50,50,-50,-37))
        e.memory.write('IncludePrimary',False);self.assertEqual(self.step(e),(50,50,-50,13))
        e.memory.write('IncludeTrim',False);e.memory.write('Bias',-7);self.assertEqual(self.step(e),(50,50,-50,-7))

    def test_unselected_summer_pairs_may_be_unknown(self):
        e=self.checked();e.memory.write('IncludeTrim',False)
        for tag in ('Trim','Gain','Summer.In8','Summer.Gain8'):self.unknown(e,tag)
        self.assertEqual(self.step(e),(50,50,50,51));e.memory.write('IncludeTrim',True)
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)

    def test_unknown_required_enable_selector_signal_and_gain_fault(self):
        for tag in ('BlockEnable','RawInput','Negate','IncludeTrim','Gain','Bias'):
            e=self.checked();self.unknown(e,tag);before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
            self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)

    def test_disabled_blocks_hold_outputs_alarms_status_and_skip_unknown_inputs(self):
        e=self.checked();e.memory.write('RawInput',15);self.step(e);e.memory.write('BlockEnable',False)
        for tag in ('RawInput','RawMax','EUMax','Negate','Gain','IncludeTrim','LimitMode'):self.unknown(e,tag)
        self.assertEqual(self.step(e),(150,80,80,83));self.assertTrue(e.memory.read('HighAlarm'))
        for record in ('Scaler','Limiter','Sign','Summer'):self.assertFalse(e.memory.read(record+'.EnableIn'));self.assertFalse(e.memory.read(record+'.EnableOut'))

    def test_disabled_diagnostics_are_held_and_recover_when_enabled(self):
        e=self.checked();e.memory.write('LimitMode',9);self.step(e);e.memory.write('BlockEnable',False)
        e.memory.write('LimitMode',0);self.step(e);self.assertTrue(e.memory.read('ModeInvalid'));self.assertEqual(e.memory.read('LimitStatus'),5)
        e.memory.write('BlockEnable',True);self.step(e);self.assertFalse(e.memory.read('ModeInvalid'))

    def test_unwired_enables_are_true_regardless_of_saved_bits(self):
        def unwire(root):
            sheet=self.sheet(root)
            for wire in list(sheet.findall('Wire')):
                if wire.get('ToParam')=='EnableIn':sheet.remove(wire)
        e=self.checked(unwire);e.memory.write('BlockEnable',False);self.assertEqual(self.step(e),(50,50,50,53))
        for record in ('Scaler','Limiter','Sign','Summer'):self.assertTrue(e.memory.read(record+'.EnableOut'))

    def test_enableout_wires_gate_downstream_blocks(self):
        def chain(root):
            sheet=self.sheet(root)
            for source,target in ((100,200),(200,300),(300,400)):
                wire=sheet.find(f'Wire[@ToID="{target}"][@ToParam="EnableIn"]');wire.set('FromID',str(source));wire.set('FromParam','EnableOut')
        e=self.checked(chain);self.step(e);e.memory.write('BlockEnable',False);e.memory.write('RawInput',2)
        self.assertEqual(self.step(e),(50,50,50,53));self.assertFalse(e.memory.read('Summer.EnableOut'))

    def test_status_alias_wire_can_control_another_block(self):
        def diagnostic(root):
            wire=self.sheet(root).find('Wire[@ToID="300"][@ToParam="NegateEnable"]');wire.set('FromID','100');wire.set('FromParam','InRawRangeInv')
        e=self.checked(diagnostic);self.assertEqual(self.step(e),(50,50,50,53))
        e.memory.write('RawMax',0);self.assertEqual(self.step(e),(50,50,-50,-47))

    def test_unknown_status_alias_output_never_becomes_false(self):
        def aliases_only(root):
            sheet=self.sheet(root);sheet.remove(sheet.find('ORef[@Operand="ScaleStatus"]'))
            sheet.remove(sheet.find('Wire[@ToID="506"]'))
        e=self.checked(aliases_only);self.unknown(e,'Scaler.Status');e.memory.write('BlockEnable',False)
        with self.assertRaisesRegex(ModelError,'unknown: ScaleFault'):self.step(e)

    def test_status_alias_sources_are_bool_and_cannot_be_driven(self):
        def wrong_type(root):self.sheet(root).find('ORef[@Operand="ScaleFault"]').set('Operand','ScaleStatus')
        self.assertTrue(self.engine(wrong_type).blockers)
        def write_output(root):self.sheet(root).find('Wire[@ToID="100"]').set('ToParam','InRawRangeInv')
        self.assertTrue(self.engine(write_output).blockers)
        def wrong_visible(root):self.sheet(root).find('Block').set('VisiblePins','InstructFault InRawRangeInv')
        self.assertEqual(self.step(self.checked(wrong_visible)),(50,50,50,53))

    def test_existing_mux_status_alias_can_feed_bool_oref(self):
        root=E.parse(SAMPLES/'SelectorLab.L5X').getroot();tags=root.find('./Controller/Tags')
        t=E.SubElement(tags,'Tag',Name='BadChannel',TagType='Base',DataType='BOOL');E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'DataValue',DataType='BOOL',Value='0')
        sheet=root.find('.//FBDContent/Sheet');E.SubElement(sheet,'ORef',ID='700',Operand='BadChannel')
        E.SubElement(sheet,'Wire',FromID='20',FromParam='SelectorInv',ToID='700',ToParam='Out')
        path=Path(self.tmp.name)/'mux.L5X';E.ElementTree(root).write(path,encoding='utf8');e=Engine(Project(path));self.assertEqual(e.blockers,[])
        e.memory.write('Channel',0);e.step();self.assertTrue(e.memory.read('BadChannel'))
        e.memory.write('Channel',1);e.step();self.assertFalse(e.memory.read('BadChannel'))

    def test_skipped_graph_and_run_entry_preserve_visible_outputs_until_reached(self):
        e=self.checked();self.step(e);e.memory.write('ExecuteGraph',False);e.memory.write('RawInput',8)
        self.assertEqual(self.step(e),(50,50,50,53));e.enter_run();self.assertEqual(e.memory.read('Scaled'),50)
        e.memory.write('ExecuteGraph',True);self.assertEqual(self.step(e),(80,80,80,83))

    def test_late_fault_rolls_back_shared_models_diagnostics_and_trace(self):
        e=self.checked();self.step(e);e.memory.write('RawMax',0);e.memory.write('LimitMode',99);e.memory.write('FaultDivisor',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.trace,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.trace,e.scheduler_description()),before)
        e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e),(50,50,50,53));self.assertTrue(e.memory.read('ScaleFault'));self.assertTrue(e.memory.read('ModeInvalid'))

    def test_late_summer_overflow_rolls_back_earlier_scaler_and_limiter(self):
        e=self.checked();e.memory.write('RawInput',2);e.memory.write('Trim',3e38);e.memory.write('Gain',2)
        before=copy.deepcopy((e.memory.values,e.time_ms))
        with self.assertRaisesRegex(ModelError,'finite REAL'):self.step(e)
        self.assertEqual((e.memory.values,e.time_ms),before)
        e.memory.write('Gain',0);self.assertEqual(self.step(e),(20,20,20,21))

    def test_periodic_harness_and_deferred_prescan(self):
        e=self.checked(mode='routine',defer=True);self.assertTrue(e.memory.read('Scaler.EnableIn'))
        e.enter_run();self.assertFalse(e.memory.read('Scaler.EnableIn'));self.assertEqual(self.step(e),(50,50,50,53))
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','Periodic');task.set('Rate','10')
        self.assertEqual(self.step(self.checked(periodic)),(50,50,50,53))

    def test_readonly_wrong_record_and_profile_gates(self):
        for kind in ('constant','record','profile','redefined'):
            def mutate(root):
                if kind=='constant':root.find('./Controller/Tags/Tag[@Name="Scaler"]').set('Constant','true')
                elif kind=='record':self.sheet(root).find('Block').set('Operand','Limiter')
                elif kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                else:
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SCALE',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_cross_language_numerical_profile_matches_with_st_enable_difference(self):
        def st(root):
            routine=root.find('.//Routine[@Name="ConditionSignals"]')
            logic(routine,['Scaler.In:=RawInput; Scaler.InRawMax:=RawMax; Scaler.InRawMin:=RawMin; Scaler.InEUMax:=EUMax; Scaler.InEUMin:=EUMin; Scaler.Limiting:=Limiting; SCL(Scaler);',
                'Limiter.In:=Scaler.Out; Limiter.HighLimit:=HighLimit; Limiter.LowLimit:=LowLimit; Limiter.SelectLimit:=LimitMode; HLL(Limiter);',
                'Sign.In:=Limiter.Out; Sign.NegateEnable:=Negate; SNEG(Sign);',
                'Summer.In1:=Sign.Out; Summer.Select1:=IncludePrimary; Summer.In2:=Trim; Summer.Gain2:=Gain; Summer.Select2:=IncludeTrim; Summer.Bias:=Bias; SSUM(Summer);',
                'Scaled:=Scaler.Out; Limited:=Limiter.Out; Negated:=Sign.Out; Summed:=Summer.Out;'])
        fbd=self.checked();text=self.checked(st)
        for values in ({},{'RawInput':-2,'Negate':True},{'RawInput':12,'Limiting':True},{'RawMax':0},{'LimitMode':9},{'IncludePrimary':False,'Gain':3}):
            for tag,value in values.items():fbd.memory.write(tag,value);text.memory.write(tag,value)
            self.assertEqual(self.step(fbd),self.step(text))
        for e in (fbd,text):e.memory.write('BlockEnable',False);e.memory.write('RawMax',10);e.memory.write('RawInput',8);e.memory.write('IncludePrimary',True)
        self.assertNotEqual(self.step(fbd),self.step(text))

    def test_program_local_alias_record(self):
        def nested(root):
            tags=root.find('./Controller/Tags');t=tags.find('Tag[@Name="Scaler"]');tags.remove(t);root.find('./Controller/Programs/Program/Tags').append(t)
            E.SubElement(tags,'Tag',Name='LocalScaler',TagType='Alias',AliasFor='Program:MainProgram.Scaler');self.sheet(root).find('Block').set('Operand','LocalScaler')
        self.assertEqual(self.step(self.checked(nested)),(50,50,50,53))

    def test_event_fault_rolls_back_completed_signal_graph(self):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(ConditionSignals,0); EVENT(SignalEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            logic(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='SignalEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);e.memory.write('FaultDivisor',0);before=copy.deepcopy((e.memory.values,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.scheduler_description()),before);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e),(50,50,50,53))

    def test_detached_rll_replacement_preserves_graph_and_public_inventory(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);before=copy.deepcopy(e.memory.values)
        neutral=['JSR(ConditionSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual(e.memory.values,before);self.assertEqual(candidate.memory.values,before)
        self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in ('SCL','HLL','SNEG','SSUM')))
        self.assertEqual(self.step(candidate),(50,50,50,53))

    def test_registry_pins_remain_typed_and_legacy_selectors_report_is_retained(self):
        from logixlab.fbd_blocks import PINS,OUTPUTS
        e=self.checked();self.assertEqual(PINS['SCALE']['InRawRangeInv'],'BOOL');self.assertIn('InRawRangeInv',OUTPUTS['SCALE'])
        report=e.report()['function_blocks'];self.assertEqual(report['instructions'],['ABS','ADD','AND','BAND','BNOT','BOR','BXOR','CTUD','DERV','DFF','DIV','EQU','ESEL','GEQ','GRT','HLL','INTG','JKFF','LEQ','LES','LIM','MAXC','MEQ','MINC','MUL','MUX','MVMT','NEG','NEQ','NOT','OR','OSFI','OSRI','RESD','RLIM','RTOR','SCL','SEL','SETD','SNEG','SSUM','SUB','TOFR','TONR','UPDN','XOR'])
        self.assertFalse(report['native_runtime_parity']);self.assertIn('selectors',report)


if __name__=='__main__':unittest.main()
