"""Common PID numeric operands and hardware manual, with transactional effects."""
import copy
import unittest
import test_ladder_pid as fixtures
from xml.etree import ElementTree as E
from logixlab.model import ModelError


class PIDOperandTests(unittest.TestCase):
    setUp = fixtures.LadderPIDTests.setUp
    engine = fixtures.LadderPIDTests.engine
    checked = fixtures.LadderPIDTests.checked
    run_step = fixtures.LadderPIDTests.run_step
    snapshot = fixtures.LadderPIDTests.snapshot

    def typed(self, pv='REAL', cv='REAL', tie='REAL', values=None, mutate=None, **kwargs):
        def types(root):
            for name,kind in (('PV',pv),('CV',cv),('Tieback',tie)):
                tag=root.find('./Controller/Tags/Tag[@Name="'+name+'"]');tag.set('DataType',kind)
                tag.find('./Data/DataValue').set('DataType',kind)
            if mutate:mutate(root)
        return self.checked(dict(KI=0)|dict(values or {}),mutate=types,**kwargs)

    def test_all_narrow_pv_and_cv_type_pairs(self):
        for pv in ('SINT','INT','DINT','REAL'):
            for cv in ('SINT','INT','DINT','REAL'):
                with self.subTest(pv=pv,cv=cv):
                    e=self.typed(pv,cv);self.assertEqual(self.run_step(e,Execute=True),30)
                    self.assertEqual(e.memory.read('Loop.PV'),20)
                    self.assertIs(type(e.memory.read('CV')),float if cv=='REAL' else int)

    def test_integer_pv_promotes_to_float32_before_scaling(self):
        e=self.typed('DINT',values={'KP':0,'BIAS':50,'MAXI':33554432,'MAXS':33554432,'SP':0})
        self.run_step(e,Execute=True,PV=16777217);self.assertEqual(e.memory.read('Loop.PV'),16777216)
        self.assertEqual(e.memory.read('Loop.ERR'),-16777216)

    def test_signed_negative_pv_is_not_clamped_to_scaling_range(self):
        e=self.typed('SINT',values={'SP':0});self.assertEqual(self.run_step(e,Execute=True,PV=-128),100)
        self.assertEqual(e.memory.read('Loop.PV'),-128)

    def test_integer_cv_rounds_ties_even_and_data14_mirrors_assigned_value(self):
        for cv in ('SINT','INT','DINT'):
            for low,high,expected in ((0,5,2),(1,6,4),(-5,0,-2)):
                with self.subTest(cv=cv,low=low):
                    e=self.typed(cv=cv,values={'KP':0,'BIAS':50,'MINCV':low,'MAXCV':high})
                    self.assertEqual(self.run_step(e,Execute=True),expected)
                    self.assertEqual(e.memory.read('Loop.DATA[14]'),expected)
                    self.assertEqual(e.memory.read('Loop.OUT'),50)

    def test_integer_cv_limits_and_overflow_roll_back_integral(self):
        e=self.typed(cv='SINT',values={'KP':0,'BIAS':100,'MAXCV':127})
        self.assertEqual(self.run_step(e,Execute=True),127)
        e.memory.write('Loop.MAXCV',128);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'SINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertEqual(self.run_step(e,Loop__MAXCV=127),127)

    def test_integer_cv_zero_in_automatic_band_before_and_after_crossing(self):
        e=self.typed(cv='INT',values={'DB':2,'KI':.5,'BIAS':50})
        self.assertEqual(self.run_step(e,Execute=True,PV=47),54)
        self.assertEqual(self.run_step(e,PV=49),0);self.assertEqual(e.memory.read('Loop.OUT'),53)
        self.assertFalse(e.memory.read('Loop.EWD'));self.assertEqual(e.memory.read('Loop.DATA[14]'),0)
        self.assertEqual(self.run_step(e,PV=51),0);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(e.memory.read('Loop.OUT'),53)
        self.assertEqual(self.run_step(e,PV=47),56);self.assertFalse(e.memory.read('Loop.EWD'))

    def test_integer_cv_deadband_manual_modes_bypass_zero_rule(self):
        e=self.typed(cv='INT',values={'DB':2,'CTL':1<<20})
        self.assertEqual(self.run_step(e,Execute=True,PV=49),0)
        self.assertEqual(self.run_step(e,Loop__SWM=True,Loop__SO=70),70)
        self.assertEqual(self.run_step(e,Loop__MO=True,Tieback=60),60)
        self.assertFalse(e.memory.read('Loop.EWD'))

    def test_hardware_manual_scales_tieback_and_cv_and_tracks_integral(self):
        e=self.typed(values={'KI':.5,'MINTIE':4000,'MAXTIE':20000,'MINCV':4000,'MAXCV':20000})
        self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True,Tieback=16000),16000)
        self.assertEqual((e.memory.read('Loop.OUT'),e.memory.read('Loop.TIE'),e.memory.read('Loop.DATA[0]')),(75,16000,45))
        self.assertEqual(self.run_step(e,Loop__MO=False),16000)
        self.assertEqual(self.run_step(e),18400)

    def test_all_tieback_tag_types_and_numeric_immediates(self):
        for kind in ('SINT','INT','DINT','REAL'):
            with self.subTest(kind=kind):
                e=self.typed(tie=kind);self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True,Tieback=60),60)
        for text,value in (('0',0),('60',60),('60.5',60.5),('16#003C',60)):
            with self.subTest(immediate=text):
                e=self.typed(lines=[f'PID(Loop,PV,{text},CV,0,0,0);'])
                self.assertEqual(self.run_step(e,Loop__MO=True),value)
                self.assertEqual(e.memory.read('Loop.TIE'),value)

    def test_hardware_manual_overrides_software_manual(self):
        e=self.typed(values={'KI':.5})
        self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True,Loop__SWM=True,Loop__SO=20,Tieback=75),75)
        self.assertEqual(e.memory.read('Loop.SO'),75)
        self.assertEqual(self.run_step(e,Loop__MO=False,Loop__SO=40),40)
        self.assertEqual(self.run_step(e,Loop__SWM=False),40)

    def test_manual_percent_clamps_to_full_range_not_automatic_limits(self):
        e=self.typed(values={'MINO':20,'MAXO':60})
        for raw,expected in ((-10,0),(75,75),(110,100)):
            self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True,Tieback=raw),expected)
            self.assertEqual(e.memory.read('Loop.TIE'),raw)
            self.assertFalse(e.memory.read('Loop.OLL'));self.assertFalse(e.memory.read('Loop.OLH'))

    def test_bias_tracking_and_nobc_in_hardware_manual(self):
        for nobc,expected in ((False,70),(True,30)):
            with self.subTest(nobc=nobc):
                e=self.typed();self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True,Loop__NOBC=nobc,Tieback=70),70)
                self.assertEqual(e.memory.read('Loop.BIAS'),0 if nobc else 40)
                self.assertEqual(self.run_step(e,Loop__MO=False),expected)

    def test_hardware_manual_suppresses_derivative_then_primes_auto(self):
        e=self.typed(values={'KP':0,'BIAS':50,'KD':2,'CTL':1<<22})
        self.run_step(e,Execute=True);self.assertEqual(self.run_step(e,PV=25),40)
        self.assertEqual(self.run_step(e,Loop__MO=True,Tieback=70,PV=30),70)
        self.assertEqual(self.run_step(e,Loop__MO=False),70)
        self.assertEqual(self.run_step(e,PV=31),68)

    def test_hardware_manual_resets_deadband_latch(self):
        e=self.typed(values={'DB':2,'CTL':1<<20})
        self.run_step(e,Execute=True,PV=49);self.assertTrue(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,Loop__MO=True,Tieback=70),70);self.assertFalse(e.memory.read('Loop.EWD'))
        self.assertEqual(self.run_step(e,Loop__MO=False),70);self.assertTrue(e.memory.read('Loop.EWD'))

    def test_tieback_value_and_range_only_consumed_in_hardware_manual(self):
        e=self.typed();e.memory.values['tieback']=None;e.memory.values['loop']['MINTIE']=None;e.memory.values['loop']['MAXTIE']=None
        self.assertEqual(self.run_step(e,Execute=True),30)
        self.assertEqual(self.run_step(e,Loop__SWM=True,Loop__SO=70),70)
        e.memory.write('Loop.MO',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        self.assertEqual(self.run_step(e,Tieback=60,Loop__MINTIE=0,Loop__MAXTIE=100),60)

    def test_hardware_manual_does_not_consume_unknown_set_output(self):
        e=self.typed();e.memory.values['loop']['SO']=None
        self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True,Tieback=60),60)

    def test_invalid_tieback_span_rolls_back_and_false_calls_skip_it(self):
        for low,high in ((0,0),(10,5)):
            e=self.typed(values={'MINTIE':low,'MAXTIE':high})
            self.run_step(e,Loop__MO=True);e.memory.write('Execute',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'tieback scaling span'):e.step()
            self.assertEqual(self.snapshot(e),before)
            self.assertEqual(self.run_step(e,Loop__MINTIE=0,Loop__MAXTIE=100),50)

    def test_aliases_selected_array_sources_and_destinations(self):
        def aliases(root):
            tags=root.find('./Controller/Tags')
            for name,kind,values in (('Inputs','DINT',[20,60]),('Outputs','INT',[0,777])):
                tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=kind,Dimensions='2')
                arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=kind,Dimensions='2')
                for i,value in enumerate(values):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))
            for name,target in (('PVRef','Inputs[0]'),('TieRef','Inputs[1]'),('CVRef','Outputs[0]')):E.SubElement(tags,'Tag',Name=name,TagType='Alias',AliasFor=target)
        e=self.typed(lines=['PID(Loop,PVRef,TieRef,CVRef,0,0,0);'],mutate=aliases)
        self.run_step(e,Loop__MO=True);self.assertEqual(e.memory.read('Outputs[0]'),60)
        self.assertEqual(e.memory.read('Outputs[1]'),777)

    def test_unsupported_types_literals_aggregates_and_overlap_still_block(self):
        for text in ('PID(Loop,20,0,CV,0,0,0);','PID(Loop,PV,TRUE,CV,0,0,0);','PID(Loop,PV,2147483648,CV,0,0,0);',
                     'PID(Loop,PV,Tieback+1,CV,0,0,0);','PID(Loop,PV,Loop.TIE,CV,0,0,0);','PID(Loop,PV,Tieback,CV,0,PV,0);'):
            with self.subTest(text=text):self.assertTrue(self.engine(lines=[text]).blockers)
        for name,kind in (('PV','LINT'),('CV','UDINT'),('Tieback','BOOL')):
            def bad(root):
                tag=root.find('./Controller/Tags/Tag[@Name="'+name+'"]');tag.set('DataType',kind)
                tag.find('./Data/DataValue').attrib.update(DataType=kind,Value='1')
            self.assertTrue(self.engine(mutate=bad).blockers)

    def test_late_fault_restores_tieback_tracking_and_integer_output(self):
        e=self.typed(cv='INT',values={'KI':.5});self.run_step(e,Execute=True)
        e.memory.write('Loop.MO',True);e.memory.write('Tieback',75);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        self.assertEqual(self.run_step(e,FaultDivisor=1),75);self.assertEqual(self.run_step(e,Loop__MO=False),75)

    def test_integer_overflow_after_manual_tracking_restores_hidden_state(self):
        e=self.typed(cv='SINT',values={'KI':.5,'MAXCV':200});e.memory.write('Execute',True);e.memory.write('Loop.MO',True);e.memory.write('Tieback',75);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'SINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before)
        self.assertEqual(self.run_step(e,Loop__MAXCV=100),75);self.assertEqual(self.run_step(e,Loop__MO=False),75)

    def test_independent_lab_loops_and_guards(self):
        e=self.checked();self.assertEqual(self.run_step(e,Execute=True,IntExecute=True),45)
        self.assertEqual((e.memory.read('RawCV'),e.memory.read('IntLoop.PV')),(8192,25))
        self.assertEqual(len(e.last_timer),2)
        self.run_step(e,Loop__MO=True,IntLoop__MO=True,Tieback=60)
        self.assertEqual((e.memory.read('CV'),e.memory.read('RawCV')),(60,19660))

    def test_constant_inputs_allowed_and_constant_output_rejected(self):
        def inputs(root):
            for name in ('PV','Tieback'):root.find('./Controller/Tags/Tag[@Name="'+name+'"]').set('Constant','true')
        e=self.typed(mutate=inputs);self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True),50)
        def output(root):root.find('./Controller/Tags/Tag[@Name="CV"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=output).blockers)

    def test_periodic_and_routine_modes_for_integer_hardware_manual(self):
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='250')
        e=self.typed('INT','INT','INT',mutate=periodic);e.memory.write('Execute',True);e.memory.write('Loop.MO',True);e.step(250)
        self.assertEqual(e.memory.read('CV'),50)
        e=self.typed('INT','INT','INT',mode='routine',routine='MainProgram/MainRoutine')
        self.assertEqual(self.run_step(e,Execute=True,Loop__MO=True),50)

    def test_report_keeps_numeric_conversion_and_remaining_boundaries_explicit(self):
        p=self.checked().report()['ladder_pid']
        self.assertIn('SINT/INT/DINT/REAL',p['operands']);self.assertIn('MO overrides SWM',p['manual'])
        self.assertIn('ties-to-even',p['conversions']);self.assertFalse(p['native_runtime_parity']);self.assertFalse(p['packed_layout'])

    def test_lab_mode_aliases_are_bool_controls_for_each_record(self):
        e=self.checked()
        self.assertIs(type(e.memory.read('Manual')),bool)
        self.run_step(e,Execute=True,IntExecute=True,Manual=True,IntManual=True,Tieback=60)
        self.assertEqual((e.memory.read('CV'),e.memory.read('RawCV')),(60,19660))
        self.assertTrue(e.memory.read('Loop.MO'));self.assertTrue(e.memory.read('IntLoop.MO'))
        self.run_step(e,IntManual=False,IntSoftwareManual=True,IntLoop__SO=50)
        self.assertEqual(e.memory.read('RawCV'),16384)


if __name__ == '__main__':unittest.main()
