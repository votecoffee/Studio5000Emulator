"""Exact TimeSynchronize UTC reads share clock state without claiming PTP."""
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_gsv_wall_clock as reads
import test_gsv_configuration as fields
import test_lreal_math as rollback
import test_ssv_wall_clock as setters
from logixlab.model import ModelError
from logixlab.server import Application
from logixlab.time_values import BOUNDS

NS=reads.MICROSECONDS*1000+789
CLOCK='logixlab.software_clock.time.time_ns'
MICRO='TimeSynchronize,,CurrentTimeMicroseconds'
NANO='TimeSynchronize,,CurrentTimeNanoseconds'


class GsvTimeSyncTests(unittest.TestCase):
    setUp=reads.GsvWallClockTests.setUp
    snapshot=staticmethod(rollback.LrealMathTests.snapshot)
    fault=rollback.LrealMathTests.fault

    @staticmethod
    def destinations(root):
        tags=root.find('./Controller/Tags')
        fields.scalar(tags,'SyncDate','DT',0);fields.scalar(tags,'SyncNano','LDT',0)
        tag=E.SubElement(tags,'Tag',Name='NanoUnknown',DataType='LDT',TagType='Base',Dimensions='3')
        arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='LDT',Dimensions='3')
        for i,value in ((0,101),(2,999)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))
        E.SubElement(tags,'Tag',Name='NanoAlias',DataType='LDT',TagType='Alias',AliasFor='NanoUnknown[ClockIndex]')

    def engine(self,logic,*,mutate=None,**kwargs):
        def extra(root):
            self.destinations(root)
            if mutate:mutate(root)
        return reads.GsvWallClockTests.engine(self,logic,mutate=extra,local=False,**kwargs)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_microsecond_dt_lint_and_complete_dint_pair_reads_in_both_languages(self):
        for st in (False,True):
            e=self.checked([f'GSV({MICRO},SyncDate);',f'GSV({MICRO},ClockWide);',f'GSV({MICRO},ClockWords[1]);'],st=st)
            e.memory.values['syncdate']=None;e.memory.values['clockwide']=None
            with patch(CLOCK,return_value=NS):e.step()
            self.assertEqual(e.memory.read('SyncDate',allow_time=True),reads.MICROSECONDS)
            self.assertEqual(e.memory.read('ClockWide'),reads.MICROSECONDS)
            self.assertEqual(e.memory.read('ClockWords')[:4],[77,*reads.WORDS,77])

    def test_nanosecond_ldt_and_lint_keep_submicrosecond_precision_in_both_languages(self):
        for st in (False,True):
            e=self.checked([f'GSV({NANO},SyncNano);',f'GSV({NANO},ClockWide);'],st=st)
            e.memory.values['syncnano']=None
            with patch(CLOCK,return_value=NS):e.step()
            self.assertEqual(e.memory.read('SyncNano',allow_time=True),NS);self.assertEqual(e.memory.read('ClockWide'),NS)
            row=next(row for row in e.memory.leaves() if row['name']=='SyncNano')
            self.assertEqual((row['value'],row['kind']),(str(NS),'integer_text'))

    def test_clock_sampling_is_per_call_independent_of_scan_time_or_ptp_source(self):
        for ptp in (None,'true','false'):
            def source(root):
                c=root.find('Controller')
                for node in c.findall('TimeSynchronize'):c.remove(node)
                if ptp is not None:E.SubElement(c,'TimeSynchronize',PTPEnable=ptp,Priority1='128',Priority2='128')
            e=self.checked([f'GSV({MICRO},ClockWide);',f'GSV({NANO},SyncNano);'],mutate=source)
            with patch(CLOCK,side_effect=[NS,NS+13]) as clock:e.step(1000)
            self.assertEqual(clock.call_count,2);self.assertEqual(e.memory.read('ClockWide'),NS//1000)
            self.assertEqual(e.memory.read('SyncNano',allow_time=True),NS+13)

    def test_types_instances_permissions_setters_and_controller_profiles_are_structural(self):
        bad=[f'GSV({NANO},ClockWords[1]);',f'GSV({NANO},SyncDate);',f'GSV({MICRO},SyncNano);',
             f'GSV({MICRO},ClockWords[11]);',f'GSV({NANO},ClockWide.0);',f'SSV({NANO},SyncNano);',
             f'SSV({MICRO},ClockWide);','GSV(TimeSynchronize,THIS,CurrentTimeMicroseconds,ClockWide);',
             'GSV(TimeSynchronize,,DomainNumber,Out);']
        for call in bad:self.assertTrue(self.engine(['AFI()'+call]).blockers,call)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="SyncNano"]').set('Constant','true')
        self.assertTrue(self.engine([f'AFI()GSV({NANO},SyncNano);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine([f'AFI()GSV({MICRO},ClockWide);'],mutate=old).blockers)

    def test_false_prescan_skips_sampling_and_live_alias_indices_then_establishes_unknown_cell(self):
        e=self.checked([f'XIC(ReadClock)GSV({NANO},NanoAlias);'])
        with patch(CLOCK,side_effect=AssertionError('Dormant clock read')):
            e.step();e.memory.write('ReadClock',True);self.fault(e,'outside bounds')
        e.memory.write('ClockIndex',1)
        with patch(CLOCK,return_value=NS):e.step()
        self.assertEqual(e.memory.read('NanoUnknown',allow_time=True),[101,NS,999])

    def test_unavailable_and_unrepresentable_samples_roll_back_complete_outputs(self):
        for value in (-1,None,True,1.5,1<<63):
            e=self.checked(['MOV(99,Out);',f'GSV({NANO},SyncNano);'])
            with patch(CLOCK,return_value=value):self.fault(e,'unavailable')
        e=self.checked([f'GSV({MICRO},ClockWords[1]);'])
        with patch(CLOCK,side_effect=OSError('Clock unavailable')):self.fault(e,'unavailable')
        with patch(CLOCK,return_value=NS):e.step()
        self.assertEqual(e.memory.read('ClockWords')[1:3],reads.WORDS)

    def test_typed_date_ranges_do_not_narrow_raw_lint_clock_counters(self):
        for attribute,dest,raw,dtype in [(MICRO,'SyncDate',(BOUNDS['DT'][1]+1)*1000,'DT'),
                                         (NANO,'SyncNano',BOUNDS['LDT'][1]+1,'LDT')]:
            e=self.checked([f'GSV({attribute},{dest});'])
            with patch(CLOCK,return_value=raw):self.fault(e,dtype+' requires exact ticks')
            e=self.checked([f'GSV({attribute},ClockWide);'])
            with patch(CLOCK,return_value=raw):e.step()
            self.assertEqual(e.memory.read('ClockWide'),raw//1000 if attribute==MICRO else raw)

    def test_pending_clock_setting_is_shared_with_reads_and_committed_cip_then_rolls_back(self):
        h=setters.SsvWallClockTests();h.setUp();self.addCleanup(h.doCleanups);h.ns=NS
        e=h.engine(['SSV(WallClockTime,,CurrentValue,ClockTarget);',f'GSV({MICRO},SyncDate);',
                    f'GSV({NANO},SyncNano);','DIV(1,ClockDivisor,Out);'],mutate=self.destinations)
        e.memory.write('ClockDivisor',0);h.fault(e,'zero')
        e.memory.write('ClockDivisor',1);e.step()
        self.assertEqual(e.memory.read('SyncDate',allow_time=True),setters.TARGET)
        self.assertEqual(e.memory.read('SyncNano',allow_time=True),setters.TARGET*1000+789)
        attributes=e.project.time_sync.cip_attributes(read_time=True,clock_state=e.coordinated_clock.utc.state)
        self.assertEqual(struct.unpack('<q',attributes[4])[0],setters.TARGET*1000+789)

    def test_st_for_protects_the_complete_microsecond_window_and_keeps_legal_nano_writes(self):
        e=self.engine([f'FOR Index:=0 TO ClockWords[2] DO GSV({MICRO},ClockWords[1]); END_FOR;'],st=True)
        self.assertTrue(any('bounds/step' in message for message in e.blockers))
        e=self.checked([f'FOR Index:=0 TO Limit DO GSV({NANO},NanoUnknown[1]); END_FOR;'],st=True)
        with patch(CLOCK,return_value=NS):e.step()
        self.assertEqual(e.memory.read('NanoUnknown',allow_time=True),[101,NS,999])

    def test_aoi_inout_and_local_ldt_values_retain_warm_state_and_bindings_on_later_fault(self):
        def aoi(root):
            c=root.find('Controller');defs=c.find('AddOnInstructionDefinitions')
            if defs is None:defs=E.SubElement(c,'AddOnInstructionDefinitions')
            d=E.SubElement(defs,'AddOnInstructionDefinition',Name='ReadNanoClock',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            parameters=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(parameters,'Parameter',Name=name,DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(parameters,'Parameter',Name='Stamp',DataType='LDT',Usage='InOut',Required='true',Visible='true')
            E.SubElement(E.SubElement(d,'LocalTags'),'LocalTag',Name='LocalNanos',DataType='LDT')
            content=E.SubElement(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=f'GSV({NANO},Stamp)GSV({NANO},LocalNanos);'
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Reader',DataType='ReadNanoClock',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ReadNanoClock')
            for name,dtype in (('EnableIn','BOOL'),('EnableOut','BOOL'),('LocalNanos','LDT')):E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
        e=self.checked(['ReadNanoClock(Reader,SyncNano);','DIV(1,ClockDivisor,Out);'],mutate=aoi)
        with patch(CLOCK,return_value=NS):e.step()
        e.memory.write('ClockDivisor',0)
        with patch(CLOCK,return_value=NS+17):self.fault(e,'zero')
        self.assertEqual(e.memory.read('Reader.LocalNanos',allow_time=True),NS)
        e.memory.write('ClockDivisor',1)
        with patch(CLOCK,return_value=NS+17):e.step()
        self.assertEqual(e.memory.read('SyncNano',allow_time=True),NS+17)

    def test_public_ladder_and_st_example_reads_clock_without_claiming_synchronization(self):
        with tempfile.TemporaryDirectory() as folder,patch(CLOCK,return_value=NS):
            app=Application(folder);self.addCleanup(app.close)
            state=app.command('demo',{'sample':'SystemLab'});self.assertEqual(state['blockers'],[])
            app.command('step',{'dt':10});app.command('write',{'tag':'SyncIndex','value':1})
            app.command('write',{'tag':'ReadSyncClock','value':True});state=app.command('step',{'dt':10})
            row={row['name']:row['value'] for row in state['tags']}
            self.assertEqual(row['SyncMicros'],row['StSyncMicros']);self.assertEqual(row['SyncMicros'],str(NS//1000))
            self.assertEqual(row['SyncNanos'],row['StSyncNanos']);self.assertEqual(row['SyncNanos'],str(NS))
            self.assertEqual((row['SyncWords[0]'],row['SyncWords[3]']),(101,999))
            report=app.command('report',{})['system_values']['wall_clock']['time_synchronize']
            self.assertTrue(report['read_only']);self.assertFalse(report['ptp']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
