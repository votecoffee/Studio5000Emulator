"""Legacy LINT timestamps bridge raw DT microseconds without unit conversion."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
import test_lreal_math as rollback
from logixlab import time_values
from logixlab.model import Project
from logixlab.runtime import Engine

TICKS=1767225600000001


def scalar(parent,name,dtype,value):
    tag=E.SubElement(parent,'Tag',Name=name,DataType=dtype,TagType='Base')
    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
    return tag


class TimestampBridgeTests(unittest.TestCase):
    setUp=fixtures.BitTransferTests.setUp
    snapshot=staticmethod(rollback.LrealMathTests.snapshot)
    fault=rollback.LrealMathTests.fault

    def engine(self,logic=None,*,source='LINT',dest='DT',value=TICKS,mutate=None):
        return fixtures.BitTransferTests.engine(self,logic or ['MOV(Source,Dest);'],
            types=(source,'LINT',dest),values=(value,0,0),mutate=mutate)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_lint_dt_round_trip_retains_raw_microseconds_and_calendar_boundaries(self):
        for value in (0,1,TICKS,time_values.BOUNDS['DT'][1]):
            e=self.checked(['MOV(Source,Dest);','MOV(Dest,Mask);'],value=value)
            e.memory.values['dest']=None;e.memory.values['mask']=None;e.step()
            self.assertEqual(e.memory.read('Dest',allow_time=True),value)
            self.assertEqual(e.memory.read('Mask'),value)
            row=next(row for row in e.memory.leaves() if row['name']=='Dest')
            self.assertEqual((row['value'],row['kind']),(str(value),'integer_text'))

    def test_dt_and_ldt_tag_or_typed_literal_sources_keep_their_own_tick_units(self):
        for dtype,literal,value in [('DT','DT#2026-01-01-00:00:00.000_001',TICKS),
                                    ('LDT','LDT#2026-01-01-00:00:00.000_000_001',1767225600000000001)]:
            for ref in ('Source',literal):
                e=self.checked([f'MOV({ref},Dest);'],source=dtype,dest='LINT',value=value)
                e.step();self.assertEqual(e.memory.read('Dest'),value)

    def test_raw_bridges_do_not_change_existing_dt_to_ldt_scaling(self):
        def extra(root):
            tags=root.find('./Controller/Tags');scalar(tags,'NanoStamp','LDT',0);scalar(tags,'Promoted','LDT',0)
        e=self.checked(['MOV(Source,Dest);','MOV(Source,NanoStamp);','MOV(Dest,Promoted);','MOV(NanoStamp,Mask);'],mutate=extra)
        e.step();self.assertEqual(e.memory.read('Dest',allow_time=True),TICKS)
        self.assertEqual(e.memory.read('NanoStamp',allow_time=True),TICKS)
        self.assertEqual(e.memory.read('Promoted',allow_time=True),TICKS*1000)
        self.assertEqual(e.memory.read('Mask'),TICKS)

    def test_invalid_raw_dates_fault_at_execution_then_repair_without_partial_effects(self):
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
        e=self.checked(mutate=readonly);e.step();self.assertEqual(e.memory.read('Dest',allow_time=True),TICKS)
        for value in (-1,time_values.BOUNDS['DT'][1]+1):
            e=self.checked(['MOV(99,SpeedCommand);','MOV(Source,Dest);'],value=value)
            self.fault(e,'exact ticks in range');e.memory.write('Source',TICKS);e.step()
            self.assertEqual(e.memory.read('Dest',allow_time=True),TICKS)

    @staticmethod
    def selected(root):
        tags=root.find('./Controller/Tags')
        tag=E.SubElement(tags,'Tag',Name='Stamps',DataType='DT',Dimensions='3',TagType='Base')
        arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DT',Dimensions='3')
        for i,value in ((0,101),(2,999)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))
        E.SubElement(tags,'Tag',Name='SelectedStamp',DataType='DT',TagType='Alias',AliasFor='Stamps[SpeedSetpoint]')

    def test_false_prescan_skips_unknowns_and_indirect_aliases_then_establishes_selected_cell(self):
        e=self.checked(['XIC(StartPB)MOV(Source,SelectedStamp);','XIC(StartPB)MOV(SelectedStamp,Mask);'],mutate=self.selected)
        e.memory.write('SpeedSetpoint',99);e.memory.values['source']=None;e.step()
        self.assertEqual(e.memory.read('Stamps',allow_time=True),[101,None,999])
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('SpeedSetpoint',1);self.fault(e,'Unknown')
        e.memory.write('Source',TICKS);e.step()
        self.assertEqual(e.memory.read('Stamps',allow_time=True),[101,TICKS,999]);self.assertEqual(e.memory.read('Mask'),TICKS)

    def test_program_local_source_and_explicit_udt_members_retain_scope_and_storage(self):
        def record(root):
            c=root.find('Controller');types=c.find('DataTypes')
            members=E.SubElement(E.SubElement(types,'DataType',Name='LegacyStamp',Class='User'),'Members')
            for name,dtype in (('Stamp','DT'),('Echo','LINT')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='LegacyStamp',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='LegacyStamp')
            for name,dtype in (('Stamp','DT'),('Echo','LINT')):E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
            program=c.find('Programs/Program');tags=program.find('Tags')
            if tags is None:tags=E.SubElement(program,'Tags')
            scalar(tags,'Source','LINT',TICKS+1)
        e=self.checked(['MOV(Source,Packet.Stamp);','MOV(Packet.Stamp,Packet.Echo);'],mutate=record);e.step()
        self.assertEqual(e.memory.read('Packet')['Stamp'],TICKS+1);self.assertEqual(e.memory.read('Packet')['Echo'],TICKS+1)
        self.assertEqual(e.memory.read('Source'),TICKS)

    def test_other_types_constants_profiles_and_time_copy_guards_remain_structural(self):
        for source in ('Source.0','1767225600000001L','1','Mask+1'):
            self.assertTrue(self.engine([f'AFI()MOV({source},Dest);']).blockers,source)
        for source,dest,value in [('LINT','TIME',1),('TIME','LINT',1),('DINT','DT',1),('ULINT','DT',1),('DT','REAL',1)]:
            self.assertTrue(self.engine(['AFI()MOV(Source,Dest);'],source=source,dest=dest,value=value).blockers)
        for op in ('COP','CPS'):
            self.assertTrue(self.engine([f'AFI(){op}(Source,Dest,1);']).blockers)
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()MOV(Source,Dest);'],mutate=readonly).blockers)
        def old(root):root.find('Controller').set('MajorRev','34')
        self.assertTrue(self.engine(['AFI()MOV(Source,Dest);'],mutate=old).blockers)

    def test_warm_late_failure_restores_timestamp_echo_and_task_progress_then_retries(self):
        e=self.checked(['MOV(Source,Dest);','MOV(Dest,Mask);','DIV(1,SpeedSetpoint,SpeedCommand);'])
        e.memory.write('SpeedSetpoint',1);e.step();e.memory.write('Source',TICKS+9);e.memory.write('SpeedSetpoint',0)
        self.fault(e,'zero');self.assertEqual(e.memory.read('Dest',allow_time=True),TICKS)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Mask'),TICKS+9)

    def test_existing_aoi_inout_and_local_bindings_use_raw_date_ticks_and_warm_rollback(self):
        def aoi(root):
            c=root.find('Controller');defs=c.find('AddOnInstructionDefinitions')
            if defs is None:defs=E.SubElement(c,'AddOnInstructionDefinitions')
            d=E.SubElement(defs,'AddOnInstructionDefinition',Name='LegacyClockBridge',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            parameters=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(parameters,'Parameter',Name=name,DataType='BOOL',Usage=usage,Required='false',Visible='false')
            for name,dtype in (('Raw','LINT'),('Stamp','DT'),('Echo','LINT')):E.SubElement(parameters,'Parameter',Name=name,DataType=dtype,Usage='InOut',Required='true',Visible='true')
            E.SubElement(E.SubElement(d,'LocalTags'),'LocalTag',Name='LocalTicks',DataType='LINT')
            content=E.SubElement(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='MOV(Raw,Stamp)MOV(Stamp,Echo)MOV(Stamp,LocalTicks);'
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Bridge',DataType='LegacyClockBridge',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='LegacyClockBridge')
            for name,dtype in (('EnableIn','BOOL'),('EnableOut','BOOL'),('LocalTicks','LINT')):E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
        e=self.checked(['LegacyClockBridge(Bridge,Source,Dest,Mask);','DIV(1,SpeedSetpoint,SpeedCommand);'],mutate=aoi)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Bridge.LocalTicks'),TICKS)
        e.memory.write('Source',TICKS+5);e.memory.write('SpeedSetpoint',0);self.fault(e,'zero')
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Bridge.LocalTicks'),TICKS+5)

    def test_public_example_is_dormant_then_round_trips_and_reports_raw_tick_units(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/DataLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();self.assertIsNone(e.memory.read('MicrosecondStamps',allow_time=True)[1])
        e.memory.write('MicrosecondIndex',1);e.memory.write('MicrosecondBridge',True);e.step()
        self.assertEqual(e.memory.read('MicrosecondStamps',allow_time=True),[101,TICKS,999])
        self.assertEqual(e.memory.read('MicrosecondReadback'),TICKS);self.assertEqual(e.memory.read('LiteralMicrosecondTicks'),TICKS)
        report=e.report()['numeric_storage']['time_date'];self.assertIn('microseconds',report['conversion']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
