"""Exact UTC calendar sources share the existing transactional clock setting."""
import unittest
from datetime import datetime,timezone
from xml.etree import ElementTree as E

import test_ssv_wall_clock as clocks
from logixlab.model import ModelError
from logixlab.wall_clock import ClockAdjustment

FIELDS=[2032,2,29,12,34,56,123456]
NAMES=('Year','Month','Day','Hour','Minute','Second','Microsecond')


def micros(fields):
    d=datetime(*fields,tzinfo=timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
    return (d.days*86400+d.seconds)*1_000_000+d.microseconds


def array(tags,name,fields=FIELDS):
    tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',Dimensions='9',TagType='Base')
    obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='9')
    for i,value in enumerate([101,*fields,999]):E.SubElement(obj,'Element',Index=f'[{i}]',Value=str(value))
    return tag


class SsvCalendarTests(unittest.TestCase):
    snapshot=staticmethod(clocks.SsvWallClockTests.snapshot)
    fault=clocks.SsvWallClockTests.fault

    def engine(self,logic,*,fields=FIELDS,mutate=None,**kwargs):
        h=clocks.SsvWallClockTests();h.setUp();self.addCleanup(h.doCleanups);self.clock=h
        def tags(root):
            c=root.find('Controller');values=c.find('Tags');array(values,'Calendar',fields)
            clocks.scalar(values,'CalendarIndex','DINT',1)
            E.SubElement(values,'Tag',Name='CalendarView',DataType='DINT',TagType='Alias',AliasFor='Calendar[CalendarIndex]')
            types=c.find('DataTypes')
            if types is None:types=E.SubElement(c,'DataTypes')
            members=E.SubElement(E.SubElement(types,'DataType',Name='ClockCalendarRecord',Class='User'),'Members')
            for name in (*NAMES,'Guard'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0')
            tag=E.SubElement(values,'Tag',Name='CalendarRecord',DataType='ClockCalendarRecord',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ClockCalendarRecord')
            for name,value in zip((*NAMES,'Guard'),[*fields,777]):E.SubElement(obj,'DataValueMember',Name=name,DataType='DINT',Value=str(value))
            if mutate:mutate(root)
        return h.engine(logic,mutate=tags,**kwargs)

    def test_datetime_and_utc_localdatetime_preserve_microseconds_and_source_guards(self):
        for attribute in ('DateTime','LocalDateTime'):
            e=self.engine([f'SSV(WallClockTime,,{attribute},Calendar[1]);','GSV(WallClockTime,,CurrentValue,ClockMeasured);'])
            e.step();self.assertEqual(e.memory.read('ClockMeasured'),micros(FIELDS))
            self.assertEqual(e.memory.read('Calendar'),[101,*FIELDS,999])
            self.assertEqual(e.coordinated_clock.utc.state.offset_us,micros(FIELDS)-clocks.RAW)

    def test_read_only_array_alias_and_record_sources_keep_their_permissions(self):
        def readonly(root):
            for name in ('Calendar','CalendarRecord'):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
        for source in ('CalendarView','CalendarRecord.Year'):
            e=self.engine([f'SSV(WallClockTime,,DateTime,{source});','GSV(WallClockTime,,CurrentValue,ClockMeasured);'],mutate=readonly)
            e.step();self.assertEqual(e.memory.read('ClockMeasured'),micros(FIELDS));self.assertEqual(e.memory.read('CalendarRecord.Guard'),777)

    def test_source_windows_cross_rows_and_program_local_names_resolve_normally(self):
        def matrix(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='CalendarMatrix',DataType='DINT',Dimensions='2,5',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2,5')
            for offset,value in enumerate(FIELDS,3):E.SubElement(obj,'Element',Index=f'[{offset//5},{offset%5}]',Value=str(value))
        e=self.engine(['SSV(WallClockTime,,DateTime,CalendarMatrix[0,3]);'],mutate=matrix);e.step()
        self.assertEqual(e.coordinated_clock.utc.state.offset_us,micros(FIELDS)-clocks.RAW);self.assertIsNone(e.memory.read('CalendarMatrix')[0][0])
        local=[2040,*FIELDS[1:]]
        e=self.engine(['SSV(WallClockTime,,DateTime,Calendar[1]);'],mutate=lambda root:array(root.find('./Controller/Programs/Program[@Name="BackgroundProgram"]/Tags'),'Calendar',local))
        e.step();self.assertEqual(e.coordinated_clock.utc.state.offset_us,micros(local)-clocks.RAW)

    def test_false_prescan_skips_invalid_index_and_unknown_fields_then_recovers(self):
        e=self.engine(['XIC(ReadClock)SSV(WallClockTime,,DateTime,CalendarView);'])
        e.memory.write('CalendarIndex',99);e.memory.values['calendar'][7]=None;e.step()
        self.assertEqual(e.coordinated_clock.utc.state,ClockAdjustment())
        e.memory.write('ReadClock',True);self.fault(e,'outside bounds')
        e.memory.write('CalendarIndex',1);self.fault(e,'Unknown')
        e.memory.write('Calendar[7]',FIELDS[6]);e.step();self.assertEqual(e.coordinated_clock.utc.state.offset_us,micros(FIELDS)-clocks.RAW)

    def test_invalid_dates_time_fields_and_unsupported_years_do_not_roll_over(self):
        for fields in ([2031,2,29,0,0,0,0],[2032,2,30,0,0,0,0],[2032,13,1,0,0,0,0],
                       [2032,1,0,0,0,0,0],[2032,1,1,24,0,0,0],[2032,1,1,0,60,0,0],
                       [2032,1,1,0,0,60,0],[2032,1,1,0,0,0,1_000_000],[2032,1,1,0,0,0,-1],
                       [1969,12,31,23,59,59,999999],[2068,12,30,0,0,0,0]):
            e=self.engine(['SSV(WallClockTime,,DateTime,Calendar[1]);'],fields=fields);self.fault(e,'valid UTC|2068')
        for fields in ([1970,1,1,0,0,0,0],[2068,12,29,23,59,59,999999]):
            e=self.engine(['SSV(WallClockTime,,DateTime,Calendar[1]);'],fields=fields);e.step()
            self.assertEqual(e.coordinated_clock.utc.state.offset_us,micros(fields)-clocks.RAW)

    def test_calendar_source_shapes_and_record_layouts_block_even_false_calls(self):
        for source in ('ClockTarget','ClockWords[6]','Calendar[3]','CalendarRecord.Month','CalendarRecord','Calendar[1].0'):
            self.assertTrue(self.engine([f'AFI()SSV(WallClockTime,,DateTime,{source});'],checked=False).blockers,source)
        for change in [lambda node:node.set('DataType','INT'),lambda node:node.set('Dimension','2'),lambda node:node.set('Hidden','true')]:
            def bad(root):change(root.find('./Controller/DataTypes/DataType[@Name="ClockCalendarRecord"]/Members/Member[@Name="Second"]'))
            self.assertTrue(self.engine(['AFI()SSV(WallClockTime,,DateTime,CalendarRecord.Year);'],mutate=bad,checked=False).blockers)

    def test_localdatetime_requires_explicit_utc_policy_but_datetime_does_not(self):
        e=self.engine(['SSV(WallClockTime,,DateTime,Calendar[1]);'],local=False);e.step()
        self.assertTrue(self.engine(['SSV(WallClockTime,,LocalDateTime,Calendar[1]);'],local=False,checked=False).blockers)
        for change in (lambda root:root.find('./Controller/WallClockTime').set('TimeZone','60'),
                       lambda root:E.SubElement(root.find('Controller'),'WallClockTime',TimeZone='0',LocalTimeAdjustment='0')):
            self.assertTrue(self.engine(['AFI()SSV(WallClockTime,,LocalDateTime,Calendar[1]);'],mutate=change,checked=False).blockers)

    def test_warm_late_fault_restores_previous_clock_and_update_admission_then_retries(self):
        e=self.engine(['SSV(WallClockTime,,DateTime,Calendar[1]);','GSV(WallClockTime,,CurrentValue,ClockMeasured);','DIV(1,ClockDivisor,ClockDivisor);'])
        e.step();previous=e.coordinated_clock.utc.state;self.clock.now=16_000_000_000
        e.memory.write('Calendar[1]',2036);e.memory.write('ClockDivisor',0);self.fault(e,'zero')
        self.assertEqual(e.coordinated_clock.utc.state,previous)
        e.memory.write('ClockDivisor',1);e.step();self.assertEqual(e.memory.read('ClockMeasured'),micros([2036,*FIELDS[1:]]))

    def test_all_setting_forms_share_the_same_interval_and_transaction(self):
        for attribute,source in [('DateTime','Calendar[1]'),('LocalDateTime','Calendar[1]'),('CurrentValue','ClockTarget')]:
            e=self.engine(['SSV(WallClockTime,,DateTime,Calendar[1]);',f'SSV(WallClockTime,,{attribute},{source});'])
            self.fault(e,'15 seconds');self.assertEqual(e.coordinated_clock.utc.state,ClockAdjustment())

    def test_existing_st_calendar_setting_uses_the_same_exact_source_contract(self):
        e=self.engine(['SSV(WallClockTime,,DateTime,CalendarRecord.Year);','GSV(WallClockTime,,CurrentValue,ClockMeasured);'],st=True)
        e.step();self.assertEqual(e.memory.read('ClockMeasured'),micros(FIELDS))

    def test_aoi_inout_and_saved_local_calendar_arrays_use_frame_bindings(self):
        for source in ('Calendar[1]','LocalCalendar[1]'):
            def definition(root):
                c=root.find('Controller');defs=c.find('AddOnInstructionDefinitions')
                if defs is None:defs=E.SubElement(c,'AddOnInstructionDefinitions')
                d=E.SubElement(defs,'AddOnInstructionDefinition',Name='LabSetCalendar',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
                p=E.SubElement(d,'Parameters')
                for name,usage in [('EnableIn','Input'),('EnableOut','Output')]:E.SubElement(p,'Parameter',Name=name,DataType='BOOL',Usage=usage,Required='false',Visible='false')
                E.SubElement(p,'Parameter',Name='Calendar',DataType='DINT',Dimensions='9',Usage='InOut',Required='true',Visible='true')
                E.SubElement(E.SubElement(d,'LocalTags'),'LocalTag',Name='LocalCalendar',DataType='DINT',Dimensions='9')
                content=E.SubElement(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
                E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=f'SSV(WallClockTime,,DateTime,{source});'
                tag=E.SubElement(c.find('Tags'),'Tag',Name='ClockSetter',DataType='LabSetCalendar',TagType='Base')
                obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='LabSetCalendar')
                for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
                a=E.SubElement(obj,'ArrayMember',Name='LocalCalendar',DataType='DINT',Dimensions='9')
                for i,value in enumerate([101,*FIELDS,999]):E.SubElement(a,'Element',Index=f'[{i}]',Value=str(value))
            e=self.engine(['LabSetCalendar(ClockSetter,Calendar);'],mutate=definition);e.step()
            self.assertEqual(e.coordinated_clock.utc.state.offset_us,micros(FIELDS)-clocks.RAW)
            self.assertEqual(e.memory.read('ClockSetter.LocalCalendar')[::8],[101,999])

    def test_public_examples_preserve_guard_cells_and_clear_each_successful_request(self):
        import tempfile
        from logixlab.server import Application
        h=clocks.SsvWallClockTests();h.setUp();self.addCleanup(h.doCleanups)
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);self.addCleanup(app.close)
            for name in ('SetClockDateTime','SetClockLocalTime'):
                app.command('clock-configure',{'use_host_utc':True});self.assertEqual(app.command('demo',{'sample':'SystemLab'})['blockers'],[])
                app.command('write',{'tag':name,'value':True});state=app.command('step',{'dt':10})
                row={r['name']:r['value'] for r in state['tags']}
                self.assertFalse(row[name]);self.assertEqual(row['ClockCalendarReadback'],str(micros(FIELDS)))
                self.assertEqual((row['ClockCalendarSetpoint[0]'],row['ClockCalendarSetpoint[8]']),(101,999))
                report=app.command('report',{})['system_values']['wall_clock'];self.assertIn('DateTime',report['setting']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
