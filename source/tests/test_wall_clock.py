"""Software UTC counters stay distinct from legacy epochs and source settings."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E
from logixlab.ethernetip import Endpoint, Session
from logixlab.model import Project
from logixlab.wall_clock import WallClock, LEGACY_EPOCH_MICROSECONDS, UTC_ZONE
from logixlab.server import Application


class WallClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e')
        self.app.endpoint=self.endpoint
        self.root=E.parse(self.app.engine.project.path).getroot()
        E.SubElement(self.root.find('Controller'),'WallClockTime',TimeZone='0',LocalTimeAdjustment='0')
        self.load(self.root)

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def load(self,root):
        path=Path(self.tmp.name)/'wall-clock.L5X';E.ElementTree(root).write(path)
        self.app.engine.project=Project(path)

    def send(self,attr=None,service=0x0E,data=b'',instance=1):
        path=bytes((0x20,0x8B,0x24,instance))+(b'\x30'+bytes((attr,)) if attr is not None else b'')
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_legacy_counter_and_utc_counters_have_distinct_exact_epochs_and_one_list_snapshot(self):
        # 2000-02-29 12:34:56.123456 UTC, independently specified calendar fields.
        microseconds=951827696123456
        attrs=(1,6,11,5,7,6)
        query=struct.pack('<7H',len(attrs),*attrs)
        with patch('logixlab.wall_clock.time.time_ns',side_effect=(microseconds*1000+999,0)) as clock:
            result=self.send(service=3,data=query);clock.assert_called_once_with()
        calendar=struct.pack('<7I',2000,2,29,12,34,56,123456)
        values={1:struct.pack('<Q',microseconds-LEGACY_EPOCH_MICROSECONDS),6:struct.pack('<q',microseconds),
                11:struct.pack('<q',microseconds),5:calendar,7:calendar}
        expected=bytes.fromhex('83000000')+struct.pack('<H',len(attrs))+b''.join(
            struct.pack('<HH',attr,0)+values[attr] for attr in attrs)
        self.assertEqual(result,expected)

    def test_boundary_epochs_and_calendar_overflow_never_invent_zero_values(self):
        clock=WallClock(True)
        for microseconds in (0,LEGACY_EPOCH_MICROSECONDS-1,LEGACY_EPOCH_MICROSECONDS,0x7FFFFFFFFFFFFFFF):
            with patch('logixlab.wall_clock.time.time_ns',return_value=microseconds*1000):
                values=clock.attributes(read_time=True)
            self.assertEqual(values[6],values[11]);self.assertEqual(struct.unpack('<q',values[6])[0],microseconds)
            if microseconds<LEGACY_EPOCH_MICROSECONDS:self.assertNotIn(1,values)
            else:self.assertEqual(struct.unpack('<Q',values[1])[0],microseconds-LEGACY_EPOCH_MICROSECONDS)
            if microseconds==0x7FFFFFFFFFFFFFFF:self.assertNotIn(5,values);self.assertNotIn(7,values)
        for invalid in (-1,None,True,1.5,'1',0x8000000000000000*1000):
            with patch('logixlab.wall_clock.time.time_ns',return_value=invalid):
                self.assertEqual(clock.attributes(read_time=True),{2:bytes(2),4:bytes(2),
                    8:struct.pack('<I',len(UTC_ZONE))+UTC_ZONE,9:bytes(2),10:bytes(1)})
        for error in (OSError('unavailable'),OverflowError('range'),ValueError('invalid')):
            with patch('logixlab.wall_clock.time.time_ns',side_effect=error):
                self.assertEqual(self.send(6),bytes.fromhex('8e001400'))

    def test_absent_nonzero_context_and_ambiguous_source_only_disable_legacy_local_fields(self):
        for mode in ('absent','nonzero','duplicate','namespace','context','shadow','opaque','export_context','missing'):
            root=copy.deepcopy(self.root);controller=root.find('Controller');node=controller.find('WallClockTime')
            if mode=='absent':controller.remove(node)
            elif mode=='nonzero':node.set('TimeZone','-300')
            elif mode=='duplicate':E.SubElement(controller,'WallClockTime',TimeZone='0',LocalTimeAdjustment='0')
            elif mode=='namespace':node.tag='{test}WallClockTime'
            elif mode=='context':node.set('Use','Context')
            elif mode=='shadow':node.set('TimeZoneUId','0')
            elif mode=='opaque':E.SubElement(node,'Hidden')
            elif mode=='export_context':root.set('ContainsContext','true')
            else:node.attrib.pop('LocalTimeAdjustment')
            self.load(root)
            with patch('logixlab.wall_clock.time.time_ns',return_value=1000):
                self.assertEqual(self.send(6),bytes.fromhex('8e0000000100000000000000'))
                for attr in (1,2,3,4,5,8,9,10):self.assertEqual(self.send(attr)[2],0x14)

    def test_static_class_and_legacy_settings_do_not_sample_or_set_host_time(self):
        with patch('logixlab.wall_clock.time.time_ns',side_effect=AssertionError('Unneeded time read')):
            self.assertEqual(self.send(1,instance=0),bytes.fromhex('8e0000000400'))
            self.assertEqual(self.send(2,instance=0),bytes.fromhex('8e0000000100'))
            for attr in (2,4):self.assertEqual(self.send(attr),bytes.fromhex('8e0000000000'))
            self.assertEqual(self.send(8)[4:],struct.pack('<I',len(UTC_ZONE))+UTC_ZONE)
            self.assertEqual(self.send(9)[4:],bytes(2));self.assertEqual(self.send(10)[4:],bytes(1))
            self.assertEqual(self.send(100)[2],0x14)
            for service,attr,data in ((0x10,6,bytes(8)),(4,None,bytes.fromhex('01000600')+bytes(8)),
                                      (1,None,b''),(3,None,b''),(3,None,bytes(2)),(0x0E,6,b'x')):
                self.assertNotEqual(self.send(attr,service,data)[2],0)
            self.assertEqual(self.send(1,instance=2)[2],5)

    def test_runtime_clock_reads_preserve_values_scans_source_and_unsupported_offsets(self):
        before=copy.deepcopy(self.app.engine.memory.values);self.app.engine.time_ms=1234
        source=self.app.engine.project.path.read_bytes()
        with patch('logixlab.wall_clock.time.time_ns',side_effect=(1_000_000,999_000)):
            self.assertEqual(struct.unpack('<q',self.send(6)[4:])[0],1000)
            self.assertEqual(struct.unpack('<q',self.send(11)[4:])[0],999)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.app.engine.time_ms,1234);self.assertEqual(self.app.engine.project.path.read_bytes(),source)
        info=self.app.engine.project.wall_clock.description()
        for name in ('cst_offset','clock_setters','physical_clock','ptp_engine'):
            self.assertFalse(info[name])
        for name in ('timezone_string','dst_parameters'):self.assertTrue(info[name])
        self.assertTrue(info['source_legacy_utc_available'])


if __name__=='__main__':unittest.main()
