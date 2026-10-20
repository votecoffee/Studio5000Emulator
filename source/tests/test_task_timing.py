"""Exact source millisecond conversion and wire reads without SDK activity."""
import base64
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint,Session
from logixlab.native_tasks import NativeTasks
from logixlab.server import Application
from logixlab.task_timing import TaskTiming,TaskTimes,microseconds

SOURCE=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
HASH='a'*64


def source():
    root=E.fromstring(SOURCE.read_bytes())
    return root,root.find('Controller')


class TaskTimingTests(unittest.TestCase):
    def test_decimal_milliseconds_convert_exactly_without_float_rounding(self):
        for raw,expected in (('500',500000),('0.001',1),('0.125',125),('10.500000',10500),
                             ('1234.567',1234567),('2147483.647',0x7FFFFFFF)):
            with self.subTest(raw=raw):self.assertEqual(microseconds(raw),expected)
        for raw in (None,1,True,'0','0.000','-1','+1',' 1','1 ','1e3','NaN','Infinity',
                    '01','1.000001','0.0001','2147483.648','9999999999','1.0000000','1.'):
            with self.subTest(raw=raw):self.assertIsNone(microseconds(raw))

    def test_only_explicit_periodic_rates_and_positive_watchdogs_are_available(self):
        root,controller=source();tasks=controller.find('Tasks');tasks[0].set('Rate','25')
        periodic=copy.deepcopy(tasks[0]);periodic.set('Name','PeriodicTask');periodic.set('Type','PERIODIC')
        periodic.set('Rate','0.125');periodic.set('Watchdog','250.001');tasks.append(periodic)
        event=copy.deepcopy(periodic);event.set('Name','EventTask');event.set('Type','Event');tasks.append(event)
        config=TaskTiming.from_source(root,controller,HASH)
        self.assertEqual(config.attributes('MainTask',source_sha256=HASH),{12:struct.pack('<I',500000)})
        self.assertEqual(config.attributes('PERIODICTASK',source_sha256=HASH),{2:struct.pack('<I',125),12:struct.pack('<I',250001)})
        self.assertEqual(config.attributes('EventTask',source_sha256=HASH),{12:struct.pack('<I',250001)})
        self.assertEqual(config.description()['periodic_rates_available'],1)
        self.assertFalse(config.description()['watchdog_enforced'])

    def test_zero_missing_or_malformed_values_never_create_a_default_native_time(self):
        for watchdog in (None,'0','bad','0.0001'):
            root,controller=source();task=controller.find('./Tasks/Task');task.set('Type','Periodic')
            if watchdog is None:task.attrib.pop('Watchdog')
            else:task.set('Watchdog',watchdog)
            self.assertEqual(TaskTiming.from_source(root,controller,HASH).attributes('MainTask',source_sha256=HASH),{})

    def test_source_context_scope_alias_and_safety_checks_are_retained(self):
        for kind in ('context','major','alias','namespace','safety','unknown-type','duplicate','nested'):
            root,controller=source();task=controller.find('./Tasks/Task')
            if kind=='context':root.set('ContainsContext','true')
            elif kind=='major':controller.set('MajorRev','36')
            elif kind=='alias':task.set('watchdog','20')
            elif kind=='namespace':task.set('{other}Rate','10')
            elif kind=='safety':task.set('Class','Safety')
            elif kind=='unknown-type':task.set('Type','Other')
            elif kind=='duplicate':controller.find('Tasks').append(copy.deepcopy(task))
            else:E.SubElement(controller,'Shadow').append(copy.deepcopy(task))
            with self.subTest(kind=kind):
                self.assertEqual(TaskTiming.from_source(root,controller,HASH).attributes('MainTask',source_sha256=HASH),{})

    def test_source_hash_and_immutable_rows_prevent_stale_or_external_changes(self):
        root,controller=source();config=TaskTiming.from_source(root,controller,HASH)
        controller.find('./Tasks/Task').set('Watchdog','1')
        self.assertEqual(config.attributes('MainTask',source_sha256=HASH)[12],struct.pack('<I',500000))
        self.assertEqual(config.attributes('MainTask',source_sha256='b'*64),{})
        self.assertEqual(config.attributes(None,source_sha256=HASH),{})
        with self.assertRaises(TypeError):config._tasks['other']=TaskTimes('Other','Continuous')
        with self.assertRaises(FrozenInstanceError):config.source_complete=False
        for args in (('Bad.name','Continuous'),('Task','Other'),('Task','Continuous',1),
                     ('Task','Periodic',True),('Task','Periodic',0),('Task','Periodic',None,0x80000000)):
            with self.assertRaises(ValueError):TaskTimes(*args)

    def test_task_wire_list_and_single_reads_keep_microseconds_and_unknown_fields_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder)
            try:
                root,controller=source();task=controller.find('./Tasks/Task')
                task.set('Type','Periodic');task.set('Rate','10.125')
                app.command('load',{'name':'timing.L5X','content':base64.b64encode(E.tostring(root)).decode()})
                app.native_tasks=NativeTasks(HASH,app.engine.project.sha256,[{'name':'MainTask','instance':1}])
                endpoint=Endpoint(app,0,False,'logix-v35-l85e');before=copy.deepcopy(app.state())
                for request,response in (
                    ('0e03207024013002',b'\x8e\0\0\0'+struct.pack('<I',10125)),
                    ('0e0320702401300c',b'\x8e\0\0\0'+struct.pack('<I',500000)),
                    ('03022070240103000c0002000c00',b'\x83\0\0\0'+struct.pack('<HHHIHHIHHI',3,12,0,500000,2,0,10125,12,0,500000)),
                    ('0e03207024013010',bytes.fromhex('8e001400')),
                    ('100320702401300c01000000',bytes.fromhex('90000800'))):
                    self.assertEqual(endpoint.router.handle(bytes.fromhex(request),Session()),response)
                for key in ('tags','scan','ms','controller','tasks'):self.assertEqual(app.state()[key],before[key])
            finally:app.close()


if __name__=='__main__':unittest.main()
