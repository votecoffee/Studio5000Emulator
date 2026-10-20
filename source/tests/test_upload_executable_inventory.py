"""Scoped Executable inventory using explicit native IDs and real loopback TCP."""
import copy
from dataclasses import replace
import importlib.util
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.native_symbols import NativeSymbols
from tools.upload_inventory import (InventoryError,Limits,_Reader,collect_inventory,decode_attribute_list,
                                    EXECUTABLE_SCHEMA,logical_path,values)
import test_upload_inventory as inventory


class ExecutableInventoryFramingTests(unittest.TestCase):
    def test_description_is_uint16_counted_unpadded_ascii_and_unknown_fields_preserve_status(self):
        text=b'First line\nSecond line'
        raw=(bytes.fromhex('83000a00')+struct.pack('<HHH',2,1,0x14)+struct.pack('<HHH',7,0,len(text))+text)
        result=decode_attribute_list(raw,(1,7),EXECUTABLE_SCHEMA)
        self.assertEqual(result['attributes'][0]['status'],0x14);self.assertIsNone(result['attributes'][0]['value'])
        self.assertEqual(values(result),{7:text.decode()});self.assertEqual(result['attributes'][1]['data_hex'],(struct.pack('<H',len(text))+text).hex())
        for data in (b'',b'A'*128):
            packet=bytes.fromhex('83000000')+struct.pack('<HHHH',1,7,0,len(data))+data
            self.assertEqual(values(decode_attribute_list(packet,(7,),EXECUTABLE_SCHEMA)),{7:data.decode()})
        for data in (b'A'*129,b'bad\0text',b'\xff'):
            packet=bytes.fromhex('83000000')+struct.pack('<HHHH',1,7,0,len(data))+data
            with self.assertRaises(InventoryError):decode_attribute_list(packet,(7,),EXECUTABLE_SCHEMA)
        packet=bytes.fromhex('83000000')+struct.pack('<HHHH',1,1,0,0)
        with self.assertRaises(InventoryError):decode_attribute_list(packet,(1,),EXECUTABLE_SCHEMA)

    def test_scoped_sparse_pagination_keeps_parent_for_metadata_and_every_cursor(self):
        metadata=bytes.fromhex('83000000')+struct.pack('<HHHHHHIHHI',3,1,0,1,2,0,70000,3,0,2)
        responses=[metadata,bytes.fromhex('cb000600')+struct.pack('<I',3),
                   bytes.fromhex('cb000000')+struct.pack('<I',70000)]
        class Client:
            def __init__(self):self.requests=[]
            def request(self,raw):self.requests.append(raw);return responses.pop(0)
        client=Client();reader=_Reader(client,Limits(),False)
        result=reader.catalog(0x6D,26038,max_instances=2)
        self.assertEqual(result['instances'],[3,70000])
        parent=bytes.fromhex('20682500b665')
        self.assertTrue(all(raw[2:].startswith(parent+b'\x20\x6d') for raw in client.requests))
        self.assertEqual(client.requests[-1],b'\x4b\x05'+parent+b'\x20\x6d\x24\x04')
        for program in (None,0,True):
            with self.assertRaises(InventoryError):reader.exchange(0x4B,0x6D,0,program=program)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class ExecutableInventoryTcpTests(unittest.TestCase):
    setUp=inventory.InventoryTcpTests.setUp
    tearDown=inventory.InventoryTcpTests.tearDown
    load=inventory.InventoryTcpTests.load

    def bind_routines(self):
        from logixlab.native_routines import NativeRoutines
        controller=self.tree.getroot().find('Controller');programs=controller.find('Programs');main=programs[0]
        routines=main.find('Routines');routine=routines[0]
        E.SubElement(routine,'Description').text='Main scoped\nroutine'
        extra=copy.deepcopy(routine);extra.set('Name','Reporting');extra.remove(extra.find('Description'));routines.append(extra)
        second=copy.deepcopy(main);second.set('Name','SecondProgram');second.find('Tags').clear()
        second_routines=second.find('Routines');second_routines.remove(second_routines[1])
        second_routines[0].find('Description').text=''
        programs.append(second);self.load()
        self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,
            tuple(replace(s,program_instance=60000) if s.scope=='MainProgram' else s
                  for s in self.app.native_symbols.by_key.values()),programs=[{'name':'MainProgram','instance':60000},
                                                                  {'name':'SecondProgram','instance':7}])
        rows=[{'program':'MainProgram','name':routine.get('Name'),'program_instance':60000,'instance':3},
              {'program':'MainProgram','name':'Reporting','program_instance':60000,'instance':60000},
              {'program':'SecondProgram','name':routine.get('Name'),'program_instance':7,'instance':3}]
        self.app.native_routines=NativeRoutines('a'*64,self.app.engine.project.sha256,rows)
        return rows

    def test_same_routine_id_in_two_programs_retains_distinct_scope_description_and_unknown_statuses(self):
        self.bind_routines();before=copy.deepcopy(self.app.engine.memory.values)
        report=collect_inventory(self.endpoint,read_values=False)
        self.assertEqual(report['executable_inventory']['state'],'available')
        self.assertEqual(report['executable_inventory']['discovered_count'],3)
        programs={p['instance']:p for p in report['programs']}
        self.assertEqual(programs[7]['executable_catalog']['instances'],[3])
        self.assertEqual(programs[60000]['executable_catalog']['instances'],[3,60000])
        main=programs[60000]['executables'][0];other=programs[7]['executables'][0]
        self.assertEqual((main['program_instance'],main['instance']),(60000,3))
        self.assertEqual((other['program_instance'],other['instance']),(7,3))
        self.assertEqual(values(main['metadata']),{7:'Main scoped\nroutine'})
        self.assertEqual(values(other['metadata']),{7:''})
        self.assertEqual([r['status'] for r in main['metadata']['attributes']],[0x14]*4+[0])
        self.assertEqual(values(programs[60000]['executables'][1]['metadata']),{})
        self.assertFalse(report['executable_inventory']['names_inferred'])
        requests=[r for r in report['requests'] if r['class_id']==0x6D]
        self.assertTrue(requests);self.assertEqual({r['program_instance'] for r in requests},{7,60000})
        self.assertEqual(report['endpoint_clients_after_close'],0)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        with self.assertRaises(InventoryError):collect_inventory(self.endpoint,read_values=False,limits=Limits(routines=2))

    def test_missing_stale_or_foreign_routine_binding_is_unavailable_without_synthetic_empty_catalog(self):
        from logixlab.native_routines import NativeRoutines
        rows=self.bind_routines()
        variants=(None,NativeRoutines('a'*64,'b'*64,rows),
                  NativeRoutines('c'*64,self.app.engine.project.sha256,rows))
        for binding in variants:
            self.app.native_routines=binding
            report=collect_inventory(self.endpoint,read_values=False)
            self.assertEqual(report['executable_inventory']['state'],'unavailable')
            for program in report['programs']:
                self.assertEqual(program['executable_catalog']['status'],0x0C)
                self.assertIsNone(program['executable_catalog']['instances']);self.assertIsNone(program['executables'])
            self.assertEqual(report['endpoint_clients_after_close'],0)
            self.assertEqual(self.app.engine.scan_count,0)
        self.app.native_routines=NativeRoutines('a'*64,self.app.engine.project.sha256,
                     [{**r,'program_instance':61000} if r['program']=='MainProgram' else r for r in rows])
        report=collect_inventory(self.endpoint,read_values=False)
        self.assertEqual(report['executable_inventory']['state'],'partial')
        programs={p['instance']:p for p in report['programs']}
        self.assertEqual(programs[60000]['executable_catalog']['status'],0x0C)
        self.assertIsNone(programs[60000]['executable_catalog']['instances']);self.assertIsNone(programs[60000]['executables'])
        self.assertEqual(programs[7]['executable_catalog']['instances'],[3])
        self.assertEqual(report['executable_inventory']['discovered_count'],1)


if __name__=='__main__':unittest.main()
