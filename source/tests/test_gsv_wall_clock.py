"""WallClockTime GSV UTC epochs, calendar windows, lazy selection and rollback."""
import copy
import struct
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_gsv_configuration as configuration
import test_aoi_queues as aoi
from logixlab.model import ModelError
from logixlab.time_values import BOUNDS

INSTANT=datetime(2024,2,29,23,59,58,123456,tzinfo=timezone.utc)
DELTA=INSTANT-datetime(1970,1,1,tzinfo=timezone.utc)
MICROSECONDS=(DELTA.days*86400+DELTA.seconds)*1000000+DELTA.microseconds
FIELDS=[2024,2,29,23,59,58,123456]
WORDS=list(struct.unpack('<ii',struct.pack('<q',MICROSECONDS)))


class GsvWallClockTests(unittest.TestCase):
    def setUp(self):
        configuration.GsvConfigurationTests.setUp(self)
        # Isolate per-invocation Task diagnostics from the GSV calls under test.
        clock=patch('logixlab.runtime.current_value_microseconds',return_value=MICROSECONDS)
        clock.start();self.addCleanup(clock.stop)

    def engine(self,logic,*,mutate=None,local=True,**kwargs):
        def fields(root):
            controller=root.find('Controller');tags=controller.find('Tags')
            for name,dtype,value in [('ClockWide','LINT',91),('ClockIndex','DINT',99),('ReadClock','BOOL',0),('ClockDivisor','DINT',1)]:
                configuration.scalar(tags,name,dtype,value)
            for name,dtype,count in [('ClockWords','DINT',12),('ClockUnknown','DINT',9),('WideUnknown','LINT',2),('DateUnknown','DT',2)]:
                tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base',Dimensions=str(count))
                array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions=str(count))
                if name=='ClockWords':
                    for i in range(count):E.SubElement(array,'Element',Index=f'[{i}]',Value='77')
            if local:E.SubElement(controller,'WallClockTime',TimeZone='0',LocalTimeAdjustment='0')
            if mutate:mutate(root)
        return configuration.GsvConfigurationTests.engine(self,logic,mutate=fields,**kwargs)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.scan_count,e.time_ms,
                              e.scheduler_description(),e.trace,e.last_timer,e._file_incremental))

    def fault(self,e,expected):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,expected):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_current_value_preserves_exact_lint_and_signed_low_high_dint_words(self):
        with patch('logixlab.wall_clock.time.time_ns',side_effect=AssertionError('Planning must not sample time')):
            e=self.checked(['GSV(wAlLcLoCkTiMe,,CurrentValue,ClockWide);','GSV(WallClockTime,,CURRENTVALUE,ClockWords[2]);'],local=False)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000+999) as clock:e.step()
        self.assertEqual(clock.call_count,2);self.assertEqual(e.memory.read('ClockWide'),MICROSECONDS)
        self.assertEqual(e.memory.read('ClockWords'),[77,77,*WORDS]+[77]*8)

    def test_current_value_writes_selected_dt_without_touching_unknown_sibling(self):
        for st,logic in [(False,'XIC(ReadClock)GSV(WallClockTime,,CurrentValue,DateUnknown[ClockIndex]);'),
                         (True,'IF ReadClock THEN GSV(WallClockTime,,CurrentValue,DateUnknown[ClockIndex]); END_IF;')]:
            with patch('logixlab.wall_clock.time.time_ns',side_effect=AssertionError('Unused clock read')):
                e=self.checked([logic],st=st,local=False);e.enter_run();e.step()
                e.memory.write('ReadClock',True);self.fault(e,'outside bounds')
            e.memory.write('ClockIndex',1)
            for ticks in (MICROSECONDS,BOUNDS['DT'][1]):
                with patch('logixlab.wall_clock.time.time_ns',return_value=ticks*1000+999):e.step()
                self.assertEqual(e.memory.values['dateunknown'],[None,ticks])
            with patch('logixlab.wall_clock.time.time_ns',return_value=(ticks+1)*1000):
                self.fault(e,'DT requires exact ticks')

    def test_datetime_and_qualified_local_datetime_write_seven_fields_with_guards(self):
        for attribute in ('DateTime','LocalDateTime'):
            e=self.checked([f'GSV(WallClockTime,,{attribute},ClockWords[1]);'])
            with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
            self.assertEqual(e.memory.read('ClockWords'),[77,*FIELDS]+[77]*4)

    def test_epoch_zero_exact_counter_limit_and_calendar_range_are_distinct(self):
        for value in (0,(1<<63)-1):
            e=self.checked(['GSV(WallClockTime,,CurrentValue,ClockWide);','GSV(WallClockTime,,CurrentValue,ClockWords[1]);'])
            with patch('logixlab.wall_clock.time.time_ns',return_value=value*1000):e.step()
            self.assertEqual(e.memory.read('ClockWide'),value);self.assertEqual(e.memory.read('ClockWords')[1:3],list(struct.unpack('<ii',struct.pack('<q',value))))
        e=self.checked(['GSV(WallClockTime,,DateTime,ClockWords[0]);'])
        with patch('logixlab.wall_clock.time.time_ns',return_value=0):e.step()
        self.assertEqual(e.memory.read('ClockWords')[:7],[1970,1,1,0,0,0,0])
        with patch('logixlab.wall_clock.time.time_ns',return_value=((1<<63)-1)*1000):self.fault(e,'unavailable')

    def test_local_time_requires_explicit_complete_unambiguous_utc_policy(self):
        logic=['AFI()GSV(WallClockTime,,LocalDateTime,ClockWords[0]);']
        self.assertTrue(self.engine(logic,local=False).blockers)
        for mode in ('offset','adjustment','missing','duplicate','context'):
            def invalid(root):
                node=root.find('./Controller/WallClockTime')
                if mode=='offset':node.set('TimeZone','60')
                elif mode=='adjustment':node.set('LocalTimeAdjustment','60')
                elif mode=='missing':node.attrib.pop('TimeZone')
                elif mode=='duplicate':E.SubElement(root.find('Controller'),'WallClockTime',TimeZone='0',LocalTimeAdjustment='0')
                else:root.set('ContainsContext','true')
            self.assertTrue(self.engine(logic,mutate=invalid).blockers,mode)
        e=self.checked(['GSV(WallClockTime,,DateTime,ClockWords[0]);'],local=False)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
        self.assertEqual(e.memory.read('ClockWords')[:7],FIELDS)

    def test_unknown_full_destinations_are_established_without_reading_other_cells(self):
        e=self.checked(['GSV(WallClockTime,,CurrentValue,WideUnknown[1]);','GSV(WallClockTime,,DateTime,ClockUnknown[1]);'])
        self.assertEqual(e.memory.values['wideunknown'],[None,None])
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
        self.assertEqual(e.memory.values['wideunknown'],[None,MICROSECONDS]);self.assertEqual(e.memory.values['clockunknown'],[None,*FIELDS,None])

    def test_false_prescan_and_skipped_st_skip_time_and_live_indices(self):
        for logic,st in [(['XIC(ReadClock)GSV(WallClockTime,,DateTime,ClockWords[ClockIndex]);'],False),
                         (['IF ReadClock THEN GSV(WallClockTime,,DateTime,ClockWords[ClockIndex]); END_IF;'],True)]:
            with patch('logixlab.wall_clock.time.time_ns',side_effect=AssertionError('Unused time read')):
                e=self.checked(logic,st=st);e.enter_run();e.step();self.assertEqual(e.memory.read('ClockWords'),[77]*12)
                e.memory.write('ReadClock',True);self.fault(e,'outside bounds')
            e.memory.write('ClockIndex',2)
            with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
            self.assertEqual(e.memory.read('ClockWords')[2:9],FIELDS)

    def test_each_reached_call_has_its_own_sample_and_scan_time_does_not_offset_it(self):
        e=self.checked(['GSV(WallClockTime,,CurrentValue,ClockWide);','GSV(WallClockTime,,CurrentValue,ClockWords[0]);'])
        with patch('logixlab.wall_clock.time.time_ns',side_effect=[MICROSECONDS*1000,(MICROSECONDS+123)*1000]):e.step(25)
        self.assertEqual(e.time_ms,25);self.assertEqual(e.memory.read('ClockWide'),MICROSECONDS)
        self.assertEqual(e.memory.read('ClockWords')[:2],list(struct.unpack('<ii',struct.pack('<q',MICROSECONDS+123))))

    def test_unavailable_host_time_rolls_back_and_recovery_uses_the_current_clock(self):
        for bad in (-1,True,None,((1<<63)*1000)):
            e=self.checked(['MOV(42,Out);','GSV(WallClockTime,,CurrentValue,ClockWide);'])
            with patch('logixlab.wall_clock.time.time_ns',return_value=bad):self.fault(e,'unavailable')
            with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
            self.assertEqual(e.memory.read('ClockWide'),MICROSECONDS);self.assertEqual(e.memory.read('Out'),42)
        e=self.checked(['GSV(WallClockTime,,CurrentValue,ClockWide);'])
        with patch('logixlab.wall_clock.time.time_ns',side_effect=OSError('clock unavailable')):self.fault(e,'unavailable')

    def test_later_fault_restores_all_destinations_scheduler_and_trace(self):
        e=self.checked(['GSV(WallClockTime,,DateTime,ClockWords[1]);','GSV(WallClockTime,,CurrentValue,ClockWide);','DIV(1,ClockDivisor,Out);'])
        e.memory.write('ClockDivisor',0)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):self.fault(e,'zero')
        e.memory.write('ClockDivisor',1)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
        self.assertEqual(e.memory.read('ClockWords')[1:8],FIELDS);self.assertEqual(e.memory.read('ClockWide'),MICROSECONDS)

    def test_alias_destinations_and_program_local_shadowing_use_normal_scope(self):
        def aliases(root):
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ClockAlias',TagType='Alias',AliasFor='ClockWords[ClockIndex]')
            configuration.scalar(root.find('./Controller/Programs/Program/Tags'),'ClockWide','LINT',19)
        e=self.checked(['GSV(WallClockTime,,DateTime,ClockAlias);','GSV(WallClockTime,,CurrentValue,ClockWide);'],mutate=aliases)
        e.memory.write('ClockIndex',1)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
        self.assertEqual(e.memory.read('ClockWords')[1:8],FIELDS);self.assertEqual(e.memory.read('ClockWide'),91)
        self.assertEqual(e.memory.read('ClockWide','BackgroundProgram'),MICROSECONDS)

    def test_st_for_protects_complete_static_and_conservative_dynamic_windows(self):
        for bound in ('ClockWords[1]','ClockWords[7]'):
            e=self.engine([f'FOR Index:=0 TO {bound} DO GSV(WallClockTime,,DateTime,ClockWords[1]); END_FOR;'],st=True)
            self.assertTrue(any('bounds/step' in item for item in e.blockers),e.blockers)
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ClockAlias',TagType='Alias',AliasFor='ClockWords[ClockIndex]')
        for dest in ('ClockWords[ClockIndex]','ClockAlias'):
            e=self.engine([f'FOR Index:=0 TO ClockWords[11] DO GSV(WallClockTime,,DateTime,{dest}); END_FOR;'],st=True,mutate=alias)
            self.assertTrue(any('bounds/step' in item for item in e.blockers),e.blockers)
        e=self.checked(['FOR Index:=0 TO Limit DO GSV(WallClockTime,,DateTime,ClockWords[2]); END_FOR;'],st=True)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
        self.assertEqual(e.memory.read('Index'),3);self.assertEqual(e.memory.read('ClockWords')[2:9],FIELDS)

    @staticmethod
    def clock_aoi(root):
        aoi.logic(root,['XIC(Load)GSV(WallClockTime,,CurrentValue,Buffer[Index]);',
                        'XIC(Push)GSV(WallClockTime,,CurrentValue,Stack[1]);'])

    def test_aoi_inout_and_local_windows_share_rollback_without_binding_conversion(self):
        e=aoi.AOIQueueTests.engine(self,self.clock_aoi);self.assertEqual(e.blockers,[]);e.step()
        for tag,value in [('Load',True),('Push',True),('FaultDivisor',0)]:e.memory.write(tag,value)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):self.fault(e,'zero')
        e.memory.write('FaultDivisor',1)
        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):e.step()
        self.assertEqual(e.memory.read('BufferA')[1:3],WORDS);self.assertEqual(e.memory.read('BufferB')[2:4],WORDS)
        self.assertEqual(e.memory.read('DriverA.Stack')[1:3],WORDS);self.assertEqual(e.memory.read('BufferA[0]'),101)

    def test_bad_instances_attributes_destinations_permissions_and_profiles_stay_blocked(self):
        for text in ('GSV(WallClockTime,This,CurrentValue,ClockWide);','GSV(WallClockTime,,CSTOffset,ClockWide);',
                     'GSV(WallClockTime,,ApplyDST,Out);','GSV(WallClockTime,,DateTime,ClockWide);','GSV(WallClockTime,,DateTime,DateUnknown[0]);',
                     'GSV(WallClockTime,,CurrentValue,ClockWide.0);','GSV(WallClockTime,,DateTime,ClockWords[6]);',
                     'SSV(WallClockTime,,CurrentValue,ClockWide);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="ClockWords"]').set('Constant','true')
        self.assertTrue(self.engine(['GSV(WallClockTime,,DateTime,ClockWords[0]);'],mutate=constant).blockers)
        for major,processor in [('34','1756-L85E'),('35','1756-L75')]:
            def target(root):root.find('Controller').set('MajorRev',major);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(['GSV(WallClockTime,,CurrentValue,ClockWide);'],mutate=target).blockers)

    def test_report_states_time_source_sampling_and_native_limits(self):
        e=self.checked(['NOP();']);report=e.report()['system_values']['wall_clock']
        self.assertIn('time.time_ns',report['source']);self.assertIn('separate calls',report['sampling'])
        self.assertFalse(report['clock_setters']);self.assertFalse(report['native_runtime_parity']);self.assertFalse(report['ptp'])
