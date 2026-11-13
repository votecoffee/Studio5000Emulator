"""Typed source settings and unsynchronized software state without UTC sampling."""
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_gsv_configuration as configuration
import test_gsv_wall_clock as clocks
import test_lreal_math as rollback
from logixlab.server import Application

CLOCK='logixlab.software_clock.time.time_ns'
ATTRIBUTES=[('PTPEnable','PtpOut'),('IsSynchronized','SyncOut'),('NumberOfPorts','PortsOut'),
            ('Priority1','P1Out'),('Priority2','P2Out')]


class TimeSyncStatusTests(unittest.TestCase):
    setUp=clocks.GsvWallClockTests.setUp
    snapshot=staticmethod(rollback.LrealMathTests.snapshot)
    fault=rollback.LrealMathTests.fault

    def engine(self,logic,*,ptp='false',p1='128',p2='255',mutate=None,**kwargs):
        def extra(root):
            c=root.find('Controller');tags=c.find('Tags')
            if ptp is not None:E.SubElement(c,'TimeSynchronize',PTPEnable=ptp,Priority1=p1,Priority2=p2)
            for name,dtype,value in [('PtpOut','DINT',-9),('SyncOut','DINT',-9),('PortsOut','INT',-9),
                                     ('P1Out','SINT',1),('P2Out','SINT',1),('Divisor','DINT',1)]:
                configuration.scalar(tags,name,dtype,value)
            tag=E.SubElement(tags,'Tag',Name='StatusValues',DataType='DINT',Dimensions='3',TagType='Base')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
            for i,value in ((0,101),(2,999)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))
            E.SubElement(tags,'Tag',Name='StatusAlias',DataType='DINT',TagType='Alias',AliasFor='StatusValues[Index]')
            if mutate:mutate(root)
        return configuration.GsvConfigurationTests.engine(self,logic,mutate=extra,**kwargs)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_all_five_attributes_have_exact_types_in_ladder_and_st_without_clock_reads(self):
        for st in (False,True):
            for enabled in ('false','true'):
                e=self.checked([f'GSV(TimeSynchronize,,{attribute},{dest});' for attribute,dest in ATTRIBUTES],st=st,ptp=enabled)
                for _,dest in ATTRIBUTES:e.memory.values[dest.lower()]=None
                with patch(CLOCK,side_effect=AssertionError('Metadata must not sample UTC')):e.step()
                self.assertEqual([e.memory.read(dest) for _,dest in ATTRIBUTES],[int(enabled=='true'),0,0,-128,-1])

    def test_unsigned_priority_bytes_keep_signed_sint_storage_and_cip_agreement(self):
        for priority in (0,127,128,255):
            e=self.checked(['GSV(TimeSynchronize,,Priority1,P1Out);','GSV(TimeSynchronize,,Priority2,P2Out);'],p1=str(priority),p2=str(priority))
            e.step();expected=priority if priority<128 else priority-256
            self.assertEqual((e.memory.read('P1Out'),e.memory.read('P2Out')),(expected,expected))
            wire=e.project.time_sync.cip_attributes()
            self.assertEqual((wire[16],wire[17]),(struct.pack('<b',expected),)*2)

    def test_absent_or_invalid_source_settings_stay_unknown_but_software_state_is_known(self):
        e=self.checked(['GSV(TimeSynchronize,,IsSynchronized,SyncOut);','GSV(TimeSynchronize,,NumberOfPorts,PortsOut);'],ptp=None)
        with patch(CLOCK,side_effect=OSError('No UTC source')):e.step()
        self.assertEqual((e.memory.read('SyncOut'),e.memory.read('PortsOut')),(0,0))
        for attribute,dest in (ATTRIBUTES[0],ATTRIBUTES[3],ATTRIBUTES[4]):
            self.assertTrue(self.engine([f'AFI()GSV(TimeSynchronize,,{attribute},{dest});'],ptp=None).blockers)
        for field,value,attribute,dest in [('PTPEnable','TRUE','PTPEnable','PtpOut'),('Priority1','256','Priority1','P1Out'),('Priority2','-1','Priority2','P2Out')]:
            def invalid(root):root.find('./Controller/TimeSynchronize').set(field,value)
            self.assertTrue(self.engine([f'AFI()GSV(TimeSynchronize,,{attribute},{dest});'],mutate=invalid).blockers)
        def duplicate(root):E.SubElement(root.find('Controller'),'TimeSynchronize',PTPEnable='false',Priority1='128',Priority2='255')
        self.assertTrue(self.engine(['AFI()GSV(TimeSynchronize,,Priority1,P1Out);'],mutate=duplicate).blockers)

    def test_destination_types_instances_permissions_and_setters_are_structural(self):
        for attribute,dest in [('PTPEnable','PortsOut'),('IsSynchronized','P1Out'),('NumberOfPorts','SyncOut'),('Priority1','SyncOut'),('Priority2','P1Out.0')]:
            self.assertTrue(self.engine([f'AFI()GSV(TimeSynchronize,,{attribute},{dest});']).blockers)
        self.assertTrue(self.engine(['AFI()GSV(TimeSynchronize,THIS,IsSynchronized,SyncOut);']).blockers)
        for attribute,dest in ATTRIBUTES:self.assertTrue(self.engine([f'AFI()SSV(TimeSynchronize,,{attribute},{dest});']).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="P1Out"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()GSV(TimeSynchronize,,Priority1,P1Out);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()GSV(TimeSynchronize,,IsSynchronized,SyncOut);'],mutate=old).blockers)

    def test_false_prescan_skips_live_alias_index_then_establishes_unknown_status_cell(self):
        e=self.checked(['XIC(Flag)GSV(TimeSynchronize,,IsSynchronized,StatusAlias);'])
        e.memory.write('Index',99);e.step();self.assertEqual(e.memory.read('StatusValues'),[101,None,999])
        e.memory.write('Flag',True);self.fault(e,'outside bounds');e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('StatusValues'),[101,0,999])

    def test_scoped_user_record_members_resolve_in_the_calling_program(self):
        def record(root):
            c=root.find('Controller');types=c.find('DataTypes')
            members=E.SubElement(E.SubElement(types,'DataType',Name='SyncFlags',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Status',DataType='DINT',Dimension='0')
            program=c.find('./Programs/Program[@Name="BackgroundProgram"]');tags=program.find('Tags')
            if tags is None:tags=E.SubElement(program,'Tags')
            tag=E.SubElement(tags,'Tag',Name='LocalFlags',DataType='SyncFlags',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='SyncFlags')
            E.SubElement(obj,'DataValueMember',Name='Status',DataType='DINT',Value='-9')
        e=self.checked(['GSV(TimeSynchronize,,IsSynchronized,LocalFlags.Status);'],mutate=record);e.step()
        self.assertEqual(e.memory.read('LocalFlags','BackgroundProgram')['Status'],0)

    def test_st_for_tracks_the_destination_and_allows_disjoint_metadata_reads(self):
        e=self.engine(['FOR Index:=0 TO Out DO GSV(TimeSynchronize,,IsSynchronized,Out); END_FOR;'],st=True)
        self.assertTrue(any('bounds/step' in message for message in e.blockers))
        e=self.checked(['FOR Index:=0 TO Limit DO GSV(TimeSynchronize,,IsSynchronized,StatusValues[Index]); END_FOR;'],st=True)
        e.step();self.assertEqual(e.memory.read('StatusValues'),[0,0,0])

    def test_warm_late_fault_restores_outputs_and_task_state_then_retries(self):
        e=self.checked(['GSV(TimeSynchronize,,Priority1,P1Out);','GSV(TimeSynchronize,,PTPEnable,PtpOut);','DIV(1,Divisor,Out);'])
        e.step();e.memory.write('P1Out',37);e.memory.write('PtpOut',77);e.memory.write('Divisor',0)
        self.fault(e,'zero');self.assertEqual((e.memory.read('P1Out'),e.memory.read('PtpOut')),(37,77))
        e.memory.write('Divisor',1);e.step();self.assertEqual((e.memory.read('P1Out'),e.memory.read('PtpOut')),(-128,0))

    def test_aoi_inout_output_and_local_status_reads_share_binding_rollback(self):
        def aoi(root):
            c=root.find('Controller');defs=c.find('AddOnInstructionDefinitions')
            if defs is None:defs=E.SubElement(c,'AddOnInstructionDefinitions')
            d=E.SubElement(defs,'AddOnInstructionDefinition',Name='ReadSyncFlags',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            parameters=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(parameters,'Parameter',Name=name,DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(parameters,'Parameter',Name='Ports',DataType='INT',Usage='InOut',Required='true',Visible='true')
            E.SubElement(parameters,'Parameter',Name='Priority',DataType='SINT',Usage='Output',Required='true',Visible='true')
            E.SubElement(E.SubElement(d,'LocalTags'),'LocalTag',Name='Status',DataType='DINT')
            content=E.SubElement(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='GSV(TimeSynchronize,,NumberOfPorts,Ports)GSV(TimeSynchronize,,Priority1,Priority)GSV(TimeSynchronize,,IsSynchronized,Status);'
            tag=E.SubElement(c.find('Tags'),'Tag',Name='Reader',DataType='ReadSyncFlags',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ReadSyncFlags')
            for name,dtype in (('EnableIn','BOOL'),('EnableOut','BOOL'),('Priority','SINT'),('Status','DINT')):E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
        e=self.checked(['ReadSyncFlags(Reader,PortsOut,P1Out);','DIV(1,Divisor,Out);'],mutate=aoi);e.step()
        self.assertEqual((e.memory.read('PortsOut'),e.memory.read('P1Out'),e.memory.read('Reader.Status')),(0,-128,0))
        e.memory.write('P1Out',37);e.memory.write('Divisor',0);self.fault(e,'zero')
        e.memory.write('Divisor',1);e.step();self.assertEqual(e.memory.read('P1Out'),-128)

    def test_public_ladder_st_status_example_and_report_preserve_source_priority_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);self.addCleanup(app.close);state=app.command('demo',{'sample':'SystemLab'})
            self.assertEqual(state['blockers'],[]);app.command('step',{'dt':10})
            app.command('write',{'tag':'SyncStatusIndex','value':1});app.command('write',{'tag':'ReadSyncStatus','value':True})
            state=app.command('step',{'dt':10});row={row['name']:row['value'] for row in state['tags']}
            self.assertEqual([row[name] for name in ('SyncPtpEnabled','SyncSynchronized','SyncPortCount','SyncPriority1','SyncPriority2')],[0,0,0,-128,-1])
            self.assertEqual([row[name] for name in ('StSyncPtpEnabled','StSyncSynchronized','StSyncPortCount','StSyncPriority1')],[0,0,0,-128])
            report=app.command('report',{})['system_values']['configuration']['time_synchronize']
            self.assertEqual(len(report['attributes']),5);self.assertTrue(report['read_only']);self.assertFalse(report['clock_sampling']);self.assertFalse(report['ptp'])


if __name__=='__main__':unittest.main()
