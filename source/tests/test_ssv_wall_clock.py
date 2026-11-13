"""Transactional software UTC setting, coherent consumers and host-clock isolation."""
import copy
import struct
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_gsv_wall_clock as reads
from logixlab.ethernetip import Endpoint,Session
from logixlab.model import ModelError
from logixlab.server import Application
from logixlab.wall_clock import CoordinatedClock,ClockAdjustment,MAX_SET_MICROSECONDS

RAW=reads.MICROSECONDS
TARGET=1_893_456_000_000_000


def scalar(tags,name,dtype,value):
    tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base')
    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
    return tag


class SsvWallClockTests(unittest.TestCase):
    def setUp(self):
        self.now=1_000_000_000;self.ns=RAW*1000
        self.patches=ExitStack();self.addCleanup(self.patches.close)
        self.patches.enter_context(patch('logixlab.wall_clock.time.time_ns',side_effect=lambda:self.ns))
        self.patches.enter_context(patch('logixlab.wall_clock.time.monotonic_ns',side_effect=lambda:self.now))
        self.patches.enter_context(patch('logixlab.runtime.current_value_microseconds',return_value=RAW))

    def engine(self,logic,*,mutate=None,checked=True,**kwargs):
        h=reads.GsvWallClockTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            tags=root.find('./Controller/Tags');scalar(tags,'ClockTarget','LINT',TARGET);scalar(tags,'ClockMeasured','LINT',0)
            if mutate:mutate(root)
        e=h.engine(logic,mutate=fields,**kwargs);e.coordinated_clock=CoordinatedClock(0)
        if checked:self.assertEqual(e.blockers,[])
        return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.time_ms,e.scan_count,e.trace,
                              e.last_timer,e.scheduler_description(),e.coordinated_clock.utc.state,e._wall_clock_pending))

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_scalar_dt_and_lint_sources_are_read_only_and_gsv_sees_pending_time(self):
        for dtype in ('DT','LINT'):
            def fields(root):
                tag=root.find('./Controller/Tags/Tag[@Name="ClockTarget"]');tag.set('DataType',dtype);tag.set('Constant','true')
                tag.find('./Data/DataValue').set('DataType',dtype)
            e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);','GSV(WallClockTime,,CurrentValue,ClockMeasured);'],mutate=fields)
            e.step();self.assertEqual(e.memory.read('ClockMeasured'),TARGET);self.assertEqual(e.memory.read('ClockTarget',allow_time=True),TARGET)
            self.assertEqual(e.coordinated_clock.utc.state,ClockAdjustment(TARGET-RAW,1_000_000));self.assertIsNone(e._wall_clock_pending)
        self.ns+=250_000_000
        value=e.project.wall_clock.attributes(read_time=True,coordinated_clock=e.coordinated_clock)[6]
        self.assertEqual(struct.unpack('<q',value)[0],TARGET+250_000)

    def test_two_dint_source_words_aliases_and_surrounding_guards_are_preserved(self):
        words=struct.unpack('<ii',struct.pack('<q',TARGET))
        def fields(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="ClockWords"]');tag.set('Constant','true')
            for i,value in zip((2,3),words):tag.find(f'./Data/Array/Element[@Index="[{i}]"]').set('Value',str(value))
            E.SubElement(tags,'Tag',Name='SetWords',DataType='DINT',TagType='Alias',AliasFor='ClockWords[2]')
        e=self.engine(['SSV(WallClockTime,,CurrentValue,SetWords);','GSV(WallClockTime,,CurrentValue,ClockMeasured);'],mutate=fields)
        e.step();self.assertEqual(e.memory.read('ClockMeasured'),TARGET);self.assertEqual(e.memory.read('ClockWords'),[77,77,*words]+[77]*8)

    def test_false_prescan_skips_source_indices_values_and_time_sampling(self):
        e=self.engine(['XIC(ReadClock)SSV(WallClockTime,,CurrentValue,ClockUnknown[ClockIndex]);'])
        with patch('logixlab.wall_clock.current_value_microseconds',side_effect=AssertionError('No clock sampling')):e.step()
        e.memory.write('ReadClock',True);self.fault(e,'outside bounds')
        e.memory.write('ClockIndex',1);self.fault(e,'Unknown')
        for i,value in enumerate(struct.unpack('<ii',struct.pack('<q',TARGET)),1):e.memory.write(f'ClockUnknown[{i}]',value)
        e.step();self.assertEqual(e.coordinated_clock.utc.state.offset_us,TARGET-RAW)

    def test_types_attributes_instances_and_controller_profiles_are_structural(self):
        for text in ['SSV(CST,,CurrentValue,ClockTarget);','SSV(WallClockTime,,DateTime,ClockWords[0]);',
                     'SSV(WallClockTime,THIS,CurrentValue,ClockTarget);','SSV(WallClockTime,,CurrentValue,1);',
                     'SSV(WallClockTime,,CurrentValue,ReadClock);','SSV(WallClockTime,,CurrentValue,ClockWords[11]);',
                     'SSV(WallClockTime,,CurrentValue,WideUnknown);']:
            self.assertTrue(self.engine(['AFI()'+text],checked=False).blockers,text)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()SSV(WallClockTime,,CurrentValue,ClockTarget);'],checked=False,
                                       mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_setting_range_includes_epoch_and_2068_limit_but_rejects_other_values(self):
        for value in (0,MAX_SET_MICROSECONDS):
            e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);','GSV(WallClockTime,,CurrentValue,ClockMeasured);',
                           'GSV(WallClockTime,,CSTOffset,ClockWords[0]);'])
            e.memory.write('ClockTarget',value);e.step();self.assertEqual(e.memory.read('ClockMeasured'),value)
            self.assertEqual(struct.unpack('<q',struct.pack('<ii',*e.memory.read('ClockWords')[:2]))[0],value-1_000_000)
        for value in (-1,MAX_SET_MICROSECONDS+1):
            e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);']);e.memory.write('ClockTarget',value);self.fault(e,'2068')

    def test_late_fault_discards_clock_and_readback_then_retry_has_no_throttle_debt(self):
        e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);','GSV(WallClockTime,,CurrentValue,ClockMeasured);',
                       'DIV(1,ClockDivisor,ClockDivisor);'])
        e.memory.write('ClockDivisor',0);self.fault(e,'zero');self.assertEqual(e.coordinated_clock.utc.state,ClockAdjustment())
        e.memory.write('ClockDivisor',1);e.step();self.assertEqual(e.memory.read('ClockMeasured'),TARGET)

    def test_multiple_settings_in_one_advance_roll_back_the_first_pending_update(self):
        e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);','SSV(WallClockTime,,CurrentValue,ClockTarget);'])
        self.fault(e,'15 seconds');self.assertEqual(e.coordinated_clock.utc.state,ClockAdjustment())

    def test_interval_uses_monotonic_time_and_survives_failed_attempts(self):
        e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);'],harness=True);e.step(60000)
        self.fault(e,'15 seconds');e.memory.write('ClockTarget',TARGET+7)
        self.now=15_999_999_000;self.fault(e,'15 seconds')
        self.now=16_000_000_000;e.step();self.assertEqual(e.coordinated_clock.utc.state,ClockAdjustment(TARGET+7-RAW,16_000_000))

    def test_clock_jump_does_not_reset_timers_simulation_time_or_cst_origin(self):
        def fields(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ClockTimer',DataType='TIMER',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='TIMER')
            for name,value in dict(PRE=1000,ACC=0,EN=0,TT=0,DN=0).items():
                E.SubElement(obj,'DataValueMember',Name=name,DataType='DINT' if name in ('PRE','ACC') else 'BOOL',Value=str(value))
        e=self.engine(['XIC(ReadClock)SSV(WallClockTime,,CurrentValue,ClockTarget)OTU(ReadClock);','TON(ClockTimer,?,?);'],mutate=fields)
        e.memory.write('ReadClock',True);e.step();first=e.memory.read('ClockTimer.ACC');e.step()
        self.assertEqual(e.time_ms,20);self.assertEqual(e.memory.read('ClockTimer.ACC'),first+10)
        self.assertEqual(e.coordinated_clock.origin_ns,0);self.assertEqual(e.coordinated_clock.microseconds(),1_000_000)

    def test_cip_wall_clock_time_sync_and_denied_network_setters_share_committed_time(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);self.addCleanup(app.close);app.coordinated_clock=CoordinatedClock(0)
            app.command('demo',dict(sample='SystemLab'));app.command('write',dict(tag='SetClock',value=True));app.command('step',dict(dt=10))
            endpoint=Endpoint(app,0,False,'logix-v35-l85e');self.addCleanup(endpoint.stop)
            for cls,attribute in [(0x8B,6),(0x43,3)]:
                path=bytes((0x20,cls,0x24,1,0x30,attribute));reply=endpoint.router.handle(bytes((0x0E,3))+path,Session())
                self.assertEqual(reply[:4],b'\x8e\0\0\0');self.assertEqual(struct.unpack('<q',reply[4:])[0],TARGET)
            reply=endpoint.router.handle(bytes.fromhex('1003208b24013006')+struct.pack('<q',RAW),Session())
            self.assertNotEqual(reply[2],0);self.assertEqual(app.coordinated_clock.utc.state.offset_us,TARGET-RAW)

    def test_application_reload_preserves_time_and_explicit_host_reset_is_program_only(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);self.addCleanup(app.close);app.coordinated_clock=CoordinatedClock(0)
            app.command('demo',dict(sample='SystemLab'));app.command('write',dict(tag='SetClock',value=True));app.command('step',dict(dt=10))
            state=app.command('demo',dict(sample='ConveyorDemo'));self.assertEqual(state['wall_clock']['adjustment_microseconds'],str(TARGET-RAW))
            self.assertEqual(app.command('reset',{})['wall_clock'],state['wall_clock'])
            for data in ({'use_host_utc':False},{'use_host_utc':1},{'use_host_utc':True,'extra':0}):
                with self.assertRaises(ModelError):app.command('clock-configure',data)
            app.running=True
            with self.assertRaises(ModelError):app.command('clock-configure',{'use_host_utc':True})
            app.running=False;state=app.command('clock-configure',{'use_host_utc':True})
            self.assertEqual(state['wall_clock']['adjustment_microseconds'],'0');self.assertIsNone(state['wall_clock']['last_set_cst_microseconds'])
            self.assertEqual(app.coordinated_clock.origin_ns,0)

    def test_generic_msg_wall_clock_and_time_sync_replies_use_adjusted_utc(self):
        import test_ladder_message as messages
        h=messages.MessageTests();self.addCleanup(h.doCleanups)
        def fields(tree):
            c=tree.getroot().find('Controller');tags=c.find('Tags');scalar(tags,'SetClock','BOOL',1);scalar(tags,'ClockTarget','LINT',TARGET)
            content=c.find('./Programs/Program/Routines/Routine/RLLContent')
            rung=E.Element('Rung',Number='900',Type='N');E.SubElement(rung,'Text').text='XIC(SetClock)SSV(WallClockTime,,CurrentValue,ClockTarget)OTU(SetClock);';content.insert(0,rung)
        e=h.engine(fields);e.coordinated_clock=CoordinatedClock(0);self.assertEqual(e.blockers,[])
        e.memory.write('ClockReadControl.Attribute',6);e.memory.write('SendClockRead',True);e.memory.write('SendTimeSyncRead',True)
        for _ in range(3):e.step()
        self.assertEqual(e.memory.read('ClockReply')[:2],list(struct.unpack('<ii',struct.pack('<q',TARGET))))
        self.assertEqual(e.memory.read('TimeSyncReply'),list(struct.unpack('<4i',struct.pack('<qq',0,TARGET))))

    def test_alarms_take_adjusted_event_timestamps_and_progtime_stays_explicit(self):
        import test_ladder_alarm as digital
        import test_ladder_analog_alarm as analog
        for kind in (digital.LadderAlarmTests,analog.LadderAnalogAlarmTests):
            h=kind();h.setUp();self.addCleanup(h.doCleanups)
            def fields(c):
                tags=c.find('Tags');scalar(tags,'SetClock','BOOL',1);scalar(tags,'ClockTarget','LINT',TARGET)
                content=c.find('./Programs/Program/Routines/Routine/RLLContent');rung=E.Element('Rung',Number='900',Type='N')
                E.SubElement(rung,'Text').text='XIC(SetClock)SSV(WallClockTime,,CurrentValue,ClockTarget)OTU(SetClock);';content.insert(0,rung)
            e=h.engine(fields);e.coordinated_clock=CoordinatedClock(0)
            if kind is digital.LadderAlarmTests:
                e.memory.write('Trip',True)
                for _ in range(3):e.step()
                self.assertEqual(e.memory.read('MotorAlarm.InAlarmTime'),TARGET)
                e.memory.write('MotorAlarm.UseProgTime',True);e.memory.write('MotorAlarm.ProgTime',7);e.memory.write('MotorAlarm.AlarmCountReset',True);e.step()
                self.assertEqual(e.memory.read('MotorAlarm.AlarmCountResetTime'),7)
            else:
                e.memory.write('Pressure',80)
                for _ in range(3):e.step()
                self.assertEqual(e.memory.read('PressureAlarm.HInAlarmTime'),TARGET)

    def test_existing_st_and_aoi_calls_keep_clock_setting_transactional(self):
        e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);','GSV(WallClockTime,,CurrentValue,ClockMeasured);'],st=True)
        e.step();self.assertEqual(e.memory.read('ClockMeasured'),TARGET)
        import test_aoi_queues as queues
        import test_ladder_integer_literals as types
        h=queues.AOIQueueTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            types.LadderIntegerLiteralTests.aoi_fields(root)
            queues.logic(root,['SSV(WallClockTime,,CurrentValue,Value)GSV(WallClockTime,,CurrentValue,Item);'])
        e=h.checked(fields);e.coordinated_clock=CoordinatedClock(0);e.memory.write('EnabledB',False);e.memory.write('ValueA',TARGET);e.step()
        self.assertEqual(e.memory.read('ItemA'),TARGET);e.memory.write('ValueA',TARGET+3);e.memory.write('FaultDivisor',0);self.now=16_000_000_000
        self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('ItemA'),TARGET+3)

    def test_unavailable_clock_samples_leave_no_committed_setting(self):
        e=self.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);'])
        with patch('logixlab.runtime.current_value_microseconds',return_value=None):self.fault(e,'available')
        self.now=-1;self.fault(e,'available');self.now=1_000_000_000;e.step()
        self.assertEqual(e.coordinated_clock.utc.state.offset_us,TARGET-RAW)
        with patch('logixlab.wall_clock.time.time_ns',return_value=-1):
            self.assertNotIn(6,e.project.wall_clock.attributes(read_time=True,coordinated_clock=e.coordinated_clock))
            values=e.project.time_sync.cip_attributes(read_time=True,clock_state=e.wall_clock_state)
            self.assertTrue({3,4,28}.isdisjoint(values))


if __name__=='__main__':unittest.main()
