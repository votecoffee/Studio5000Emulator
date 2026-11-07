"""Typed timer state selection, retained unknowns and canonical elapsed clocks."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_runtime as fixtures
from logixlab.model import ModelError
from logixlab.runtime import Engine


class LadderTimerTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp

    @staticmethod
    def fields(root):
        tags=root.find('./Controller/Tags')
        for name,value in [('Index',0),('BadIndex',99)]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        tag=E.SubElement(tags,'Tag',Name='TimerCells',DataType='TIMER',TagType='Base',Dimensions='3');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='TIMER',Dimensions='3')
        for i in (0,1):
            obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='TIMER')
            for name,dtype,value in [('PRE','DINT',20),('ACC','DINT',7 if i==0 else 0),('EN','BOOL',0),('TT','BOOL',0),('DN','BOOL',0)]:
                if i==0 and name=='DN':continue
                E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))

    def engine(self,rungs,mutate=None):
        self.root=E.parse(fixtures.SAMPLE).getroot()
        def fields(root):
            self.fields(root)
            if mutate:mutate(root)
        return fixtures.RuntimeTests.engine(self,rungs,fields)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def test_rto_false_retains_unknown_done_true_requires_it_and_recovers(self):
        e=self.checked(['XIC(StartPB)RTO(TimerCells[Index],?,?);']);e.step();obj=e.memory.read('TimerCells')[0];self.assertEqual(obj['ACC'],7);self.assertIsNone(obj['DN']);self.assertFalse(obj['EN']);self.assertFalse(obj['TT'])
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'TIMER.DN.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TimerCells[0].DN',False);e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),7);e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),17);e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),27);self.assertTrue(e.memory.read('TimerCells[0].DN'));self.assertFalse(e.memory.read('TimerCells[0].TT'))

    def test_required_en_history_is_not_inferred_and_other_paths_establish_outputs(self):
        for op in ('TON','RTO'):
            e=self.checked([f'XIC(StartPB){op}(TimerCells[1],?,?);']);e.memory.values['timercells'][1]['EN']=None;e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'TIMER.EN.*unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('StartPB',False);e.step();self.assertFalse(e.memory.read('TimerCells[1].EN'));self.assertFalse(e.memory.read('TimerCells[1].TT'))
        for op,power in [('TON',False),('TOF',True)]:
            e=self.checked([f'XIC(StartPB){op}(TimerCells[1],?,?);']);e.memory.values['timercells'][1].update(EN=None,DN=None,TT=None);e.memory.write('StartPB',power);e.step();obj=e.memory.read('TimerCells')[1];self.assertEqual(obj['EN'],power);self.assertEqual(obj['DN'],power);self.assertEqual(obj['ACC'],0);self.assertFalse(obj['TT'])

    def test_true_ton_and_false_tof_require_done_but_never_read_old_tt(self):
        for op,power in [('TON',True),('TOF',False)]:
            e=self.checked([f'XIC(StartPB){op}(TimerCells[1],?,?);']);e.memory.values['timercells'][1].update(DN=None,TT=None);e.memory.write('StartPB',power);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'TIMER.DN.*unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('TimerCells[1].DN',False);e.step();self.assertIs(type(e.memory.read('TimerCells[1].TT')),bool)

    def test_tof_false_requires_enable_then_done_and_delays_after_fall(self):
        e=self.checked(['XIC(StartPB)TOF(TimerCells[1],?,?);']);e.memory.values['timercells'][1].update(EN=None,DN=None);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'TIMER.EN.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TimerCells[1].EN',False);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'TIMER.DN.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TimerCells[1].DN',True);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),0);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),10);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),20);self.assertFalse(e.memory.read('TimerCells[1].DN'));self.assertFalse(e.memory.read('TimerCells[1].TT'))

    def test_all_paths_require_known_nonnegative_dint_preset_and_accumulator(self):
        for op in ('TON','TOF','RTO'):
            for power in (False,True):
                e=self.checked([f'XIC(StartPB){op}(TimerCells[1],?,?);']);e.memory.write('StartPB',power)
                for name,value in [('PRE',None),('ACC',None),('PRE',-1),('ACC',-1),('PRE',True),('ACC',2147483648)]:
                    obj=e.memory.values['timercells'][1];saved=dict(obj);obj[name]=value;before=self.snapshot(e)
                    with self.assertRaisesRegex(ModelError,'TIMER.'+name):e.step()
                    self.assertEqual(self.snapshot(e),before);e.memory.values['timercells'][1]=saved

    def test_retained_done_pause_resume_and_false_retention_keep_elapsed_rules(self):
        e=self.checked(['XIC(StartPB)RTO(TimerCells[1],?,?);']);e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),10)
        e.memory.write('TimerCells[1].DN',True);e.step();e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),10);self.assertFalse(e.memory.read('TimerCells[1].TT'))
        e.memory.write('TimerCells[1].DN',False);e.memory.write('TimerCells[1].PRE',100);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),20);e.memory.write('StartPB',False);e.step();e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),20);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),20);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),30)

    def test_late_fault_restores_timer_values_and_elapsed_history_for_all_three(self):
        for op in ('TON','TOF','RTO'):
            e=self.checked([f'XIC(StartPB){op}(TimerCells[1],?,?);','DIV(1,SpeedSetpoint,SpeedCommand);']);e.memory.write('StartPB',True);e.step()
            if op=='TOF':e.memory.write('StartPB',False);e.step()
            e.memory.write('SpeedSetpoint',0);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('TimerCells[1].ACC'),10)

    def test_accumulator_saturates_and_completes_at_the_dint_boundary(self):
        limit = 2147483647
        for op in ('TON', 'TOF', 'RTO'):
            for offset in (11, 10, 9):
                with self.subTest(instruction=op, offset=offset):
                    engine = self.checked([f'XIC(StartPB){op}(TimerCells[1],?,?);'])
                    engine.memory.write('TimerCells[1].PRE', limit)
                    engine.memory.write('StartPB', True)
                    engine.step()
                    on_delay = op != 'TOF'
                    if not on_delay:
                        engine.memory.write('StartPB', False)
                        engine.step()

                    engine.memory.write('TimerCells[1].ACC', limit - offset)
                    engine.step()
                    complete = offset <= 10
                    result = engine.memory.read('TimerCells')[1]
                    self.assertEqual(result, dict(PRE=limit, ACC=limit if complete else limit - 1,
                                                  EN=on_delay, DN=complete == on_delay, TT=not complete))
                    self.assertEqual(engine.last_timer[('timercells', (1,))], engine.time_ms)
                    self.assertIsNone(engine.last_cleared_program_fault)
                    if complete:
                        engine.step()
                        self.assertEqual(engine.memory.read('TimerCells')[1], result)

    def test_later_fault_rolls_back_saturated_value_and_timer_clock(self):
        engine = self.checked(['TON(TimerCells[1],?,?);', 'DIV(1,SpeedSetpoint,SpeedCommand);'])
        engine.memory.write('TimerCells[1].PRE', 2147483647)
        engine.memory.write('SpeedSetpoint', 1)
        engine.step()
        engine.memory.write('TimerCells[1].ACC', 2147483646)
        engine.memory.write('SpeedSetpoint', 0)
        before = self.snapshot(engine)

        with self.assertRaisesRegex(ModelError, 'zero'):
            engine.step()
        self.assertEqual(self.snapshot(engine), before)
        engine.memory.write('SpeedSetpoint', 1)
        engine.step()
        self.assertEqual(engine.memory.read('TimerCells[1].ACC'), 2147483647)
        self.assertTrue(engine.memory.read('TimerCells[1].DN'))

    def test_aliases_share_clock_identity_and_other_elements_remain_independent(self):
        def alias(root):E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',TagType='Alias',DataType='TIMER',AliasFor='TimerCells')
        e=self.checked(['XIC(StartPB)TON(TimerCells[0],?,?);','XIC(StartPB)TON(View[0],?,?);','XIC(PartSensor)TON(TimerCells[1],?,?);'],alias);e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),10);self.assertEqual(e.memory.read('TimerCells[1].ACC'),0)
        e.memory.write('PartSensor',True);e.step();e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),20);self.assertEqual(e.memory.read('TimerCells[1].ACC'),10);self.assertEqual(len(e.last_timer),2);self.assertIsNone(e.memory.read('TimerCells')[2]['ACC'])

    def test_skipped_subroutine_retains_existing_elapsed_since_last_call_policy(self):
        def routine(root):
            root.find('./Controller/Tags/Tag[@Name="TimerCells"]/Data/Array/Element/Structure/DataValueMember[@Name="PRE"]').set('Value','100')
            obj=E.SubElement(root.find('./Controller/Programs/Program/Routines'),'Routine',Name='Tick',Type='RLL');E.SubElement(E.SubElement(E.SubElement(obj,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='TON(TimerCells[0],?,?);'
        e=self.checked(['XIC(StartPB)JSR(Tick,0);'],routine);e.step();self.assertEqual(e.last_timer,{})
        e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),10);e.memory.write('StartPB',False);e.step();e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('TimerCells[0].ACC'),40)

    @staticmethod
    def aoi_logic(root):
        c=root.find('Controller');tags=c.find('Tags')
        for name,value in [('EnabledA',1),('EnabledB',1),('ResetA',1),('ResetB',0)]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType='BOOL',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='BOOL',Value=str(value))
        obj=tags.find('Tag[@Name="TimerCells"]/Data/Array/Element[@Index="[1]"]/Structure');obj.remove(obj.find('DataValueMember[@Name="DN"]'))
        definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='TimerWorker',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false');params=E.SubElement(definition,'Parameters')
        for name,dtype,usage,required in [('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),('State','TIMER','InOut','true'),('Trigger','BOOL','Input','true'),('Reset','BOOL','Input','true')]:E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage=usage,Required=required,Visible=required)
        E.SubElement(E.SubElement(definition,'LocalTags'),'LocalTag',Name='LocalTimer',DataType='TIMER');content=E.SubElement(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
        for i,text in enumerate(['XIC(Reset)RES(State);','XIC(Reset)RES(LocalTimer);','XIC(Trigger)RTO(State,?,?);','XIC(Trigger)RTO(LocalTimer,?,?);']):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        for name in ('First','Second'):
            obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name=name,DataType='TimerWorker',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='TimerWorker')
            for field in ('EnableIn','EnableOut','Trigger','Reset'):E.SubElement(obj,'DataValueMember',Name=field,DataType='BOOL',Value='0')
            local=E.SubElement(obj,'StructureMember',Name='LocalTimer',DataType='TIMER')
            for field,value in [('PRE',20),('ACC',7)]:E.SubElement(local,'DataValueMember',Name=field,DataType='DINT',Value=str(value))

    def test_aoi_local_inout_timer_clocks_and_later_binding_rollback(self):
        e=self.checked(['XIC(EnabledA)TimerWorker(First,TimerCells[0],StartPB,ResetA);','XIC(EnabledB)TimerWorker(Second,TimerCells[1],PartSensor,ResetB);'],self.aoi_logic);e.memory.write('PartSensor',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'TIMER.DN.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('ResetB',True);e.step();e.memory.write('ResetA',False);e.memory.write('ResetB',False);e.memory.write('StartPB',True);e.memory.write('PartSensor',False);e.step();e.step();self.assertEqual(e.memory.read('First.LocalTimer.ACC'),10);self.assertEqual(e.memory.read('Second.LocalTimer.ACC'),0)
        e.memory.values['timercells'][1]['DN']=None;e.memory.write('PartSensor',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'TIMER.DN.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('TimerCells[1].DN',False);e.step();self.assertEqual(e.memory.read('First.LocalTimer.ACC'),20);self.assertEqual(e.memory.read('TimerCells[1].ACC'),0)

    def test_static_types_permissions_operands_prescan_indices_and_profile_stay_bounded(self):
        for text in ('TON(Parts,?,?);','RTO(TimerCells,?,?);','TOF(TimerCells[99],?,?);','TON(TimerCells[Index],1,2);'):
            e=self.engine(['AFI()'+text]);self.assertTrue(e.blockers,text);self.assertFalse(e.memory.structural)
        for op in ('TON','TOF','RTO'):
            def constant(root):root.find('./Controller/Tags/Tag[@Name="TimerCells"]').set('Constant','true')
            self.assertTrue(self.engine([f'AFI(){op}(TimerCells[0],?,?);'],constant).blockers)
            self.assertTrue(any('Prescan' in b for b in self.engine([f'AFI(){op}(TimerCells[BadIndex],?,?);']).blockers))
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        e=self.engine(['AFI()TON(TimerCells[1],?,?);'],older);self.assertEqual(e.blockers,[]);self.assertFalse(e.report()['ladder_timers']['available'])
        report=self.checked(['AFI()RTO(TimerCells[0],?,?);']).report()['ladder_timers'];self.assertEqual(report['instructions'],['TON','TOF','RTO']);self.assertFalse(report['native_runtime_parity'])

    def test_literal_timer_values_seed_a_fresh_image_and_live_members_keep_changing(self):
        text = 'XIC(StartPB)RTO(TimerCells[1],60,7);'
        engine = self.checked([text])
        self.assertEqual(engine.project.routines['mainprogram/mainroutine'].rungs[0]['text'], text)
        self.assertEqual(engine.memory.read('TimerCells[1].PRE'), 60)
        self.assertEqual(engine.memory.read('TimerCells[1].ACC'), 7)
        engine.memory.write('TimerCells[1].PRE', 80)
        engine.memory.write('TimerCells[1].ACC', 11)
        engine.enter_run()
        engine.step()
        engine.memory.write('StartPB', True)
        engine.step()
        engine.step()
        self.assertEqual((engine.memory.read('TimerCells[1].PRE'), engine.memory.read('TimerCells[1].ACC')), (80, 21))
        reset = Engine(engine.project)
        self.assertEqual((reset.memory.read('TimerCells[1].PRE'), reset.memory.read('TimerCells[1].ACC')), (60, 7))

    def test_timer_initializers_combine_with_saved_fields_and_prescan(self):
        engine = self.checked([
            'AFI()RTO(TimerCells[0],?,11);',
            'AFI()RTO(TimerCells[0],+45,?);',
            'AFI()RTO(TimerCells[0],45,?);',
            'AFI()TON(TimerCells[1],?,12);',
        ])
        self.assertEqual((engine.memory.read('TimerCells[0].PRE'), engine.memory.read('TimerCells[0].ACC')), (45, 11))
        self.assertEqual(engine.project.initial['timercells'][1]['ACC'], 12)
        self.assertEqual((engine.memory.read('TimerCells[1].PRE'), engine.memory.read('TimerCells[1].ACC')), (20, 0))

    def test_conflicting_initializers_leave_all_saved_values_intact(self):
        engine = self.engine([
            'AFI()RTO(TimerCells[0],35,11);',
            'AFI()RTO(TimerCells[1],40,12);',
            'AFI()RTO(timercells[1],41,?);',
        ])
        self.assertTrue(any('Conflicting PRE initializers' in item for item in engine.blockers))
        self.assertEqual([row['PRE'] for row in engine.project.initial['timercells'][:2]], [20, 20])
        self.assertEqual([row['ACC'] for row in engine.project.initial['timercells'][:2]], [7, 0])

    def test_literal_timer_alias_chain_merges_with_direct_initializers(self):
        def aliases(root):
            tags = root.find('./Controller/Tags')
            E.SubElement(tags, 'Tag', Name='TimerArray', TagType='Alias', DataType='TIMER', AliasFor='TimerCells')
            E.SubElement(tags, 'Tag', Name='ActiveTimer', TagType='Alias', DataType='TIMER', AliasFor='TimerArray[1]')

        engine = self.checked(['AFI()RTO(TimerCells[1],45,?);', 'AFI()RTO(ActiveTimer,45,11);'], aliases)
        self.assertEqual((engine.memory.read('ActiveTimer.PRE'), engine.memory.read('ActiveTimer.ACC')), (45, 11))
        self.assertEqual(engine.project.initial['timercells'][0]['PRE'], 20)

        conflict = self.engine(['AFI()RTO(TimerCells[1],45,?);', 'AFI()RTO(ActiveTimer,46,11);'], aliases)
        self.assertTrue(any('Conflicting PRE initializers' in item for item in conflict.blockers))
        self.assertEqual(conflict.project.initial['timercells'][1]['PRE'], 20)
        self.assertEqual(conflict.project.initial['timercells'][1]['ACC'], 0)

    def test_dynamic_and_cyclic_literal_aliases_leave_the_saved_image_intact(self):
        for target in ('TimerCells[Index]', 'Selected'):
            with self.subTest(target=target):
                def alias(root):
                    E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Selected',
                                 TagType='Alias', DataType='TIMER', AliasFor=target)

                engine = self.engine(['AFI()RTO(TimerCells[0],35,11);', 'AFI()RTO(Selected,45,12);'], alias)
                self.assertTrue(any('static backing tag' in item for item in engine.blockers))
                self.assertEqual(engine.project.initial['timercells'][0]['PRE'], 20)
                self.assertEqual(engine.project.initial['timercells'][0]['ACC'], 7)

    def test_radix_timer_initializers_zero_fill_and_merge_with_decimal_values(self):
        engine = self.checked([
            'AFI()RTO(TimerCells[1],16#FFFF,8#12);',
            'AFI()RTO(TimerCells[1],65535,2#1010);',
        ])
        self.assertEqual((engine.memory.read('TimerCells[1].PRE'), engine.memory.read('TimerCells[1].ACC')),
                         (65535, 10))

    def test_routine_replacement_retains_unchanged_initializer_without_reseeding(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import RoutineSource, SourceRung

        text = 'AFI()RTO(TimerCells[1],16#32,2#1010);'
        def comment(root):
            rung = root.find('.//RLLContent/Rung')
            E.SubElement(rung, 'Comment').text = 'Imported preset'

        engine = self.checked([text, 'MOV(7,SpeedSetpoint);'], comment)
        engine.memory.write('TimerCells[1].PRE', 80)
        engine.memory.write('TimerCells[1].ACC', 21)
        original = engine.project.routines['mainprogram/mainroutine'].rungs[0]
        # A neutral equivalent must not consume the retained initializer match.
        replacement = ('AFI()RTO(TimerCells[1],?,?);', 'MOV(55,SpeedSetpoint);', text)
        source = RoutineSource('MainRoutine', tuple(SourceRung(i, rung) for i, rung in enumerate(replacement)),
                               0, '', 0, '')
        candidate, receipt = prepare(engine, source, replacement, 'MainProgram', 0)

        retained = candidate.project.routines['mainprogram/mainroutine'].rungs[2]
        self.assertEqual((retained['text'], retained['comment']), (text, 'Imported preset'))
        self.assertIsNot(retained['nodes'], original['nodes'])
        self.assertEqual(retained['nodes'][-1].args, ['TimerCells[1]', '?', '?'])
        self.assertEqual(receipt['revision'], 1)
        self.assertEqual(candidate.memory.read('TimerCells[1].PRE'), 80)
        self.assertEqual(candidate.memory.read('TimerCells[1].ACC'), 21)
        candidate.step()
        self.assertEqual(candidate.memory.read('SpeedSetpoint'), 55)
        self.assertEqual(candidate.memory.read('TimerCells[1].ACC'), 21)
        self.assertEqual(engine.memory.read('TimerCells[1].ACC'), 21)

    def test_routine_replacement_can_change_the_gate_of_an_existing_initializer(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import RoutineSource, SourceRung

        text = 'AFI()RTO(TimerCells[1],16#32,2#1010);'
        replacement = 'XIC(StartPB)RTO(TimerCells[1],16#32,2#1010);'
        engine = self.checked([text])
        engine.memory.write('TimerCells[1].PRE', 80)
        engine.memory.write('TimerCells[1].ACC', 21)
        source = RoutineSource('MainRoutine', (SourceRung(0, replacement),), 0, '', 0, '')
        candidate, _ = prepare(engine, source, (replacement,), 'MainProgram', 0)

        rung = candidate.project.routines['mainprogram/mainroutine'].rungs[0]
        self.assertEqual(rung['text'], replacement)
        self.assertEqual(rung['nodes'][-1].args, ['TimerCells[1]', '?', '?'])
        self.assertEqual(candidate.memory.read('TimerCells[1].PRE'), 80)
        self.assertEqual(candidate.memory.read('TimerCells[1].ACC'), 21)
        candidate.memory.write('StartPB', True)
        candidate.step(10)
        candidate.step(10)
        self.assertEqual(candidate.memory.read('TimerCells[1].ACC'), 31)
        self.assertEqual(engine.memory.read('TimerCells[1].ACC'), 21)

    def test_routine_replacement_cannot_duplicate_an_initializer_under_a_new_gate(self):
        from logixlab.routine_source import RoutineSource, SourceError, SourceRung, validate_plan

        text = 'AFI()RTO(TimerCells[1],30,4);'
        extra = 'XIC(StartPB)RTO(TimerCells[1],30,4);'
        engine = self.checked([text])
        before = self.snapshot(engine)
        source = RoutineSource('MainRoutine', (SourceRung(0, extra), SourceRung(1, text)), 0, '', 0, '')
        with self.assertRaisesRegex(SourceError, 'execution_plan_unsupported'):
            validate_plan(source, (extra, text), engine.project, 'MainProgram')
        self.assertEqual(self.snapshot(engine), before)

    def test_routine_replacement_cannot_add_another_literal_rung_from_one_existing_match(self):
        from logixlab.routine_source import RoutineSource, SourceError, SourceRung, validate_plan

        text = 'AFI()RTO(TimerCells[1],30,4);'
        engine = self.checked([text])
        before = self.snapshot(engine)
        source = RoutineSource('MainRoutine', (SourceRung(0, text), SourceRung(1, text)), 0, '', 0, '')
        with self.assertRaisesRegex(SourceError, 'execution_plan_unsupported'):
            validate_plan(source, (text, text), engine.project, 'MainProgram')
        self.assertEqual(self.snapshot(engine), before)

    def test_invalid_literal_initializers_and_runtime_edit_candidates_are_rejected(self):
        from logixlab.routine_source import RoutineSource, SourceError, SourceRung, validate_plan

        for token in ('-1', '2147483648', '2.0', '16#8000_0000', '16#1_0000_0000',
                      '2#102', '8#8', '16#FFL', '-16#01', 'Index'):
            with self.subTest(token=token):
                engine = self.engine([f'AFI()TOF(TimerCells[1],{token},0);'])
                self.assertTrue(engine.blockers)
                self.assertEqual(engine.project.initial['timercells'][1]['PRE'], 20)
        engine = self.checked(['AFI()RTO(TimerCells[1],30,4);'])
        before = self.snapshot(engine)
        text = 'AFI()RTO(TimerCells[1],45,9);'
        source = RoutineSource('MainRoutine', (SourceRung(0, text),), 0, '', 0, '')
        with self.assertRaisesRegex(SourceError, 'execution_plan_unsupported'):
            validate_plan(source, (text,), engine.project, 'MainProgram')
        self.assertEqual(self.snapshot(engine), before)
        self.assertEqual(engine.project.initial['timercells'][1]['PRE'], 30)


if __name__=='__main__':unittest.main()
