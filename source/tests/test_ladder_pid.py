"""Bounded ladder P/PI arithmetic, storage, modes and transaction semantics."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES, ModelError, Project
from logixlab.runtime import Engine

SAMPLE = Path(__file__).resolve().parents[1] / 'samples/PIDLab.L5X'


class LadderPIDTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, values=None, lines=None, mutate=None, **kwargs):
        root = E.parse(SAMPLE).getroot()
        for name, value in (values or {}).items():
            root.find('./Controller/Tags/Tag[@Name="Loop"]/Data/Structure/DataValueMember[@Name="'+name+'"]').set('Value', str(value))
        if lines is not None:
            content = root.find('.//RLLContent');content.clear()
            for i, text in enumerate(lines):
                E.SubElement(E.SubElement(content, 'Rung', Number=str(i), Type='N'), 'Text').text = text
        if mutate:mutate(root)
        p = Path(self.tmp.name) / 'pid.L5X';E.ElementTree(root).write(p, encoding='utf-8', xml_declaration=True)
        return Engine(Project(p), **kwargs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs);self.assertEqual(e.blockers, []);return e

    def run_step(self, e, **values):
        for name, value in values.items():e.memory.write(name.replace('__', '.'), value)
        e.step();return e.memory.read('CV')

    def snapshot(self, e):
        return copy.deepcopy((e.memory.values, e.last_timer, e.time_ms, e.scan_count,
                              e.memory.first_scan, e.trace, e._program_scanned))

    def test_independent_pi_percent_error_and_per_call_update(self):
        e = self.checked();self.assertEqual(self.run_step(e, Execute=True),45)
        self.assertEqual(self.run_step(e),60);self.assertEqual(e.memory.read('Loop.DATA[0]'),30)
        self.assertEqual((e.memory.read('Loop.PV'),e.memory.read('Loop.ERR'),e.memory.read('Loop.OUT')),(20,30,60))
        self.assertEqual(e.memory.read('Loop.DATA[14]'),60)

    def test_proportional_bias_and_reverse_direct_actions(self):
        e = self.checked({'KI':0,'BIAS':10});self.assertEqual(self.run_step(e,Execute=True),40)
        self.assertEqual(self.run_step(e,Loop__CA=True,PV=60),20)
        self.assertEqual(self.run_step(e,PV=40),0)

    def test_dependent_reset_minutes_and_zero_integral(self):
        e=self.checked({'KP':2,'KI':1,'CTL':1<<23});self.run_step(e,Execute=True)
        self.assertEqual(e.memory.read('Loop.DATA[0]'),1);self.assertEqual(e.memory.read('CV'),61)
        self.assertEqual(self.run_step(e),62);self.assertEqual(self.run_step(e,Loop__KI=0),60)

    def test_raw_pv_and_cv_scaling(self):
        e=self.checked({'MINS':-50,'MAXS':150,'MINI':4000,'MAXI':20000,'MINCV':4000,'MAXCV':20000,'SP':50,'KI':0})
        self.assertEqual(self.run_step(e,Execute=True,PV=8000),8000)
        self.assertEqual((e.memory.read('Loop.PV'),e.memory.read('Loop.ERR'),e.memory.read('Loop.OUT')),(0,50,25))

    def test_update_uses_upd_not_step_interval_or_omitted_time(self):
        e=self.checked({'UPD':.5});e.memory.write('Execute',True);e.step(60000)
        self.assertEqual(e.memory.read('CV'),37.5);e.step(1);self.assertEqual(e.memory.read('CV'),45)

    def test_saturation_prevents_outward_integral_and_recovers(self):
        e=self.checked({'MAXO':50});self.assertEqual(self.run_step(e,Execute=True),45)
        self.assertEqual(self.run_step(e),50);self.assertEqual(e.memory.read('Loop.DATA[0]'),20)
        self.assertTrue(e.memory.read('Loop.OLH'));self.assertEqual(self.run_step(e),50)
        self.assertEqual(self.run_step(e,PV=60),5);self.assertFalse(e.memory.read('Loop.OLH'))
        self.assertEqual(self.run_step(e,PV=40),30);self.assertFalse(e.memory.read('Loop.OLL'))

    def test_proportional_only_limit_flags_and_equal_limit_reset(self):
        e=self.checked({'KP':4,'KI':0,'MINO':10,'MAXO':60});self.assertEqual(self.run_step(e,Execute=True),60)
        self.assertTrue(e.memory.read('Loop.OLH'));self.assertFalse(e.memory.read('Loop.OLL'))
        self.assertEqual(self.run_step(e,Loop__MINO=5,Loop__MAXO=5),100)
        self.assertEqual((e.memory.read('Loop.MINO'),e.memory.read('Loop.MAXO')),(0,100))

    def test_software_manual_backcalculates_i_and_returns_without_increment(self):
        e=self.checked();self.assertEqual(self.run_step(e,Execute=True),45)
        self.assertEqual(self.run_step(e,Loop__SWM=True,Loop__SO=70),70)
        self.assertEqual(e.memory.read('Loop.DATA[0]'),40)
        self.assertEqual(self.run_step(e,Loop__SWM=False),70);self.assertEqual(self.run_step(e),85)

    def test_manual_bias_backcalculation_and_nobc_option(self):
        for no_bc,expected in ((False,70),(True,30)):
            with self.subTest(no_bc=no_bc):
                e=self.checked({'KI':0});self.run_step(e,Execute=True,Loop__NOBC=no_bc,Loop__SWM=True,Loop__SO=70)
                self.assertEqual(e.memory.read('Loop.BIAS'),0 if no_bc else 40)
                self.assertEqual(self.run_step(e,Loop__SWM=False),expected)

    def test_disabling_integral_removes_active_i_before_manual_bias_tracking(self):
        e=self.checked();self.run_step(e,Execute=True);self.run_step(e)
        self.assertEqual(self.run_step(e,Loop__KI=0),30);self.assertEqual(e.memory.read('Loop.DATA[0]'),0)
        self.assertEqual(self.run_step(e,Loop__SWM=True,Loop__SO=70),70)
        self.assertEqual(e.memory.read('Loop.BIAS'),40)
        self.assertEqual(self.run_step(e,Loop__SWM=False),70)

    def test_manual_uses_full_percent_range_and_updates_set_output_in_auto(self):
        e=self.checked({'MINO':20,'MAXO':60});self.assertEqual(self.run_step(e,Execute=True,Loop__SWM=True,Loop__SO=200),100)
        self.assertFalse(e.memory.read('Loop.OLH'));self.assertEqual(e.memory.read('Loop.SO'),100)
        self.assertEqual(self.run_step(e,Loop__SO=-1),0)

    def test_false_rung_clears_only_enable_and_skips_unknown_inputs(self):
        e=self.checked();self.run_step(e,Execute=True);state=copy.deepcopy(e.last_timer)
        e.memory.values['pv']=None
        self.assertEqual(self.run_step(e,Execute=False),45);self.assertEqual(e.last_timer,state)
        self.assertFalse(e.memory.read('Loop.EN'));self.assertTrue(e.memory.read('Loop.INI'))
        self.assertEqual(self.run_step(e,PV=20,Execute=True),60)

    def test_prescan_ignores_saved_active_i_and_run_reinitializes_history(self):
        e=self.checked({'CTL':-(1<<31)|(1<<15),'OUT':99});self.assertFalse(e.memory.read('Loop.EN'))
        self.assertEqual(self.run_step(e,Execute=True),45);self.assertEqual(self.run_step(e),60)
        e.enter_run();self.assertEqual(self.run_step(e),45)

    def test_explicit_ini_clear_restarts_integral_without_fabricating_data_slots(self):
        e=self.checked();e.memory.write('Loop.DATA[1]',123);self.run_step(e,Execute=True);self.run_step(e)
        self.assertEqual(self.run_step(e,Loop__INI=False),45);self.assertEqual(e.memory.read('Loop.DATA[1]'),123)

    def test_ctl_aliases_share_one_signed_word_and_preserve_reserved_bits(self):
        e=self.checked({'CTL':1});self.run_step(e,Execute=True,Loop__PE=True)
        word=e.memory.read('Loop.CTL');self.assertLess(word,0);self.assertEqual(word&1,1)
        self.assertTrue(e.memory.read('Loop.EN'));self.assertTrue(e.memory.read('Loop.PE'))
        e.memory.write('Loop.ctl.26',True);self.assertTrue(e.memory.read('loop.swm'))
        e.memory.write('LOOP.SWM',False);self.assertFalse(e.memory.read('Loop.CTL.26'))

    def test_alarm_hysteresis_high_low_and_deviation(self):
        e=self.checked({'KI':0});self.run_step(e,Execute=True,PV=90)
        self.assertTrue(e.memory.read('Loop.PVHA'));self.assertTrue(e.memory.read('Loop.DVNA'))
        self.run_step(e,PV=79);self.assertTrue(e.memory.read('Loop.PVHA'))
        self.run_step(e,PV=77);self.assertFalse(e.memory.read('Loop.PVHA'))
        self.run_step(e,PV=5);self.assertTrue(e.memory.read('Loop.PVLA'));self.assertTrue(e.memory.read('Loop.DVPA'))
        self.run_step(e,PV=13);self.assertFalse(e.memory.read('Loop.PVLA'))

    def test_later_fault_restores_public_hidden_and_clock_then_retry(self):
        e=self.checked();self.run_step(e,Execute=True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,FaultDivisor=1),60)

    def test_invalid_and_unsupported_live_options_roll_back(self):
        for member,value in [('DB',-1),('KD',-1),('CL',True),
                             ('UPD',0),('UPD',-1),('KP',-1),('KI',-1),('MAXI',0),('MAXS',0),
                             ('MAXCV',0),('SP',101),('MINO',101),('MAXO',-1),('PVDB',-1),('DVDB',-1),('PVL',90)]:
            with self.subTest(member=member,value=value):
                e=self.checked();e.memory.write('Execute',True);e.memory.write('Loop.'+member,value);before=self.snapshot(e)
                with self.assertRaises(ModelError):e.step()
                self.assertEqual(self.snapshot(e),before)

    def test_missing_saved_inputs_stay_unknown_and_false_calls_can_skip_them(self):
        def omit(root):
            p=root.find('.//Structure[@DataType="PID"]');p.remove(p.find('DataValueMember[@Name="KP"]'));p.remove(p.find('ArrayMember'))
        e=self.checked(mutate=omit);self.run_step(e);self.assertIsNone(e.memory.values['loop']['KP'])
        with self.assertRaises(ModelError):self.run_step(e,Execute=True)
        self.assertEqual(self.run_step(e,Loop__KP=1),45)
        self.assertIsNone(e.memory.values['loop']['DATA'][1]);self.assertEqual(e.memory.read('Loop.DATA[0]'),15)

    def test_unsupported_operand_types_profiles_and_optional_forms_block(self):
        for text in ('PID(Loop,20,0,CV,0,0,0);','PID(Loop,PV,0,PV,Loop,0,0);','PID(Loop,PV,TRUE,CV,0,0,0);','PID(Loop,PV,0,Loop.PV,0,0,0);','PID(Loop,PV,0,CV,0,PV,0);'):
            with self.subTest(text=text):self.assertTrue(self.engine(lines=[text]).blockers)
        for name in ('PV','CV'):
            def integer(root):root.find('./Controller/Tags/Tag[@Name="'+name+'"]').set('DataType','LINT')
            self.assertTrue(self.engine(mutate=integer).blockers)
        def old(root):root.find('Controller').set('MajorRev','34')
        self.assertTrue(self.engine(mutate=old).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Loop"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_distinct_loops_are_independent_and_duplicate_true_calls_rejected(self):
        def second(root):
            tags=root.find('./Controller/Tags');p=copy.deepcopy(tags.find('Tag[@Name="Loop"]'));p.set('Name','Other');tags.append(p)
        e=self.checked(lines=['XIC(Execute)PID(Loop,PV,0,CV,0,0,0);','XIC(Execute)PID(Other,PV,0,PV,0,0,0);'],mutate=second)
        self.run_step(e,Execute=True);self.assertEqual(len(e.last_timer),2)
        e=self.checked(lines=['PID(Loop,PV,0,CV,0,0,0);','PID(Loop,PV,0,CV,0,0,0);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'one true execution'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_periodic_release_and_routine_harness(self):
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='250')
        e=self.checked(mutate=periodic);e.memory.write('Execute',True);e.step(250);self.assertEqual(e.memory.read('CV'),45)
        e=self.checked(mode='routine',routine='MainProgram/MainRoutine');self.assertEqual(self.run_step(e,Execute=True),45)

    def test_float32_overflow_rolls_back(self):
        e=self.checked({'KP':3e38});e.memory.write('Execute',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_report_storage_and_unavailable_st_form(self):
        e=self.checked();self.assertNotIn('PID',e.project.data_only_types)
        p=e.report()['ladder_pid'];self.assertFalse(p['native_runtime_parity']);self.assertFalse(p['packed_layout'])
        self.assertEqual(ARITIES['PID'],7);self.assertEqual(p['data_elements'],17)
        def st(root):
            routine=root.find('.//Routine');routine.clear();routine.attrib.update(Name='MainRoutine',Type='ST')
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='PID(Loop,PV,0,CV,0,0,0);'
        self.assertTrue(self.engine(mutate=st).blockers)

    def test_record_and_scalar_aliases_resolve_to_canonical_storage(self):
        def aliases(root):
            tags=root.find('./Controller/Tags')
            for name,target in (('AliasLoop','Loop'),('AliasPV','PV'),('AliasCV','CV')):
                E.SubElement(tags,'Tag',Name=name,TagType='Alias',AliasFor=target)
        e=self.checked(lines=['PID(AliasLoop,AliasPV,0,AliasCV,0,0,0);'],mutate=aliases)
        self.assertEqual(self.run_step(e),45);self.assertTrue(e.memory.read('AliasLoop.EN'))
        self.assertEqual(len(e.last_timer),1)

    def test_array_pid_records_keep_separate_histories(self):
        def array(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Loop"]');tag.set('Dimensions','2')
            data=tag.find('Data');obj=data.find('Structure');data.remove(obj)
            arr=E.SubElement(data,'Array',DataType='PID',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]').append(copy.deepcopy(obj))
        e=self.checked(lines=['PID(Loop[0],PV,0,CV,0,0,0);','PID(Loop[1],PV,0,CV,0,0,0);'],mutate=array)
        e.memory.write('Loop[1].KI',1)
        self.assertEqual(self.run_step(e),60);self.assertEqual(e.memory.read('Loop[0].DATA[0]'),15)
        self.assertEqual(e.memory.read('Loop[1].DATA[0]'),30);self.assertEqual(len(e.last_timer),2)
        self.assertTrue(e.memory.read('Loop[1].EN'));self.assertEqual(self.run_step(e),90)
        self.assertEqual(e.memory.read('Loop[0].DATA[0]'),30)

    def test_skipped_routine_retains_enable_and_resumes_without_elapsed_catchup(self):
        def subroutine(root):
            routines=root.find('.//Routines');routine=copy.deepcopy(routines.find('Routine'))
            routine.set('Name','Regulate');routine.find('RLLContent').find('Rung/Text').text='PID(Loop,PV,0,CV,0,0,0);';routines.append(routine)
        e=self.checked(lines=['XIC(Execute)JSR(Regulate,0);'],mutate=subroutine)
        self.assertEqual(self.run_step(e,Execute=True),45);self.assertEqual(self.run_step(e,Execute=False),45)
        self.assertTrue(e.memory.read('Loop.EN'));self.assertEqual(self.run_step(e,Execute=True),60)

    def test_missing_ctl_and_constant_cv_fail_closed(self):
        def missing(root):
            obj=root.find('.//Structure[@DataType="PID"]');obj.remove(obj.find('DataValueMember[@Name="CTL"]'))
        e=self.engine(mutate=missing);self.assertTrue(e.blockers)
        with self.assertRaises(ModelError):e.step()
        def constant(root):root.find('./Controller/Tags/Tag[@Name="CV"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)


if __name__ == '__main__':unittest.main()
