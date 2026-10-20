"""Focused SDK-free inventory framing and owned TCP readback checks."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint
from logixlab.native_symbols import NativeSymbols, Symbol
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient, ProbeError
from tools.upload_inventory import (InventoryError, Limits, _Reader, collect_inventory,
                                    decode_attribute_list, decode_instance_page, decode_reply,
                                    logical_path, values)


class InventoryFramingTests(unittest.TestCase):
    def test_sparse_numeric_program_paths_use_8_16_and_32_bit_segments(self):
        self.assertEqual(logical_path(0x6B,3),bytes.fromhex('206b2403'))
        self.assertEqual(logical_path(0x6A,70000,70000),bytes.fromhex('2068260070110100206a260070110100'))
        self.assertEqual(logical_path(0x6B,256),bytes.fromhex('206b25000001'))
        for invalid in (-1,True,1.5,0x100000000):
            with self.assertRaises(InventoryError):logical_path(0x6B,invalid)

    def test_partial_attribute_list_preserves_byte_alignment_order_and_duplicates(self):
        raw=(bytes.fromhex('83000a00')+struct.pack('<H',4)+struct.pack('<HHB',17,0,5)+
             struct.pack('<HH',1,0x14)+struct.pack('<HHH',3,0,20)+struct.pack('<HHB',17,0,5))
        result=decode_attribute_list(raw,(17,1,3,17),{17:1,3:2})
        self.assertEqual([r['attribute'] for r in result['attributes']],[17,1,3,17])
        self.assertEqual([r['value'] for r in result['attributes']],[5,None,20,5])
        self.assertEqual(result['attributes'][1]['status'],0x14)

    def test_string_units_and_unknown_catalog_do_not_turn_into_empty_success(self):
        raw=bytes.fromhex('83000000')+struct.pack('<HHHH',1,1,0,3)+b'Tag'
        self.assertEqual(values(decode_attribute_list(raw,(1,),{1:'ascii16'})),{1:'Tag'})
        raw=bytes.fromhex('83000000')+struct.pack('<HHHI',1,28,0,4)+b'Main'
        self.assertEqual(values(decode_attribute_list(raw,(28,),{28:'ascii32'})),{28:'Main'})
        missing=decode_instance_page(bytes.fromhex('cb000c00'),0)
        self.assertEqual(missing['status'],0x0C);self.assertIsNone(missing['instances'])

    def test_malformed_lists_reject_count_order_truncation_padding_and_status_contradiction(self):
        good=bytes.fromhex('830000000100010000000300')
        for raw in (good[:-1],good+b'\0',good[:4]+b'\2\0'+good[6:],
                    good[:6]+b'\2\0'+good[8:],b'\x83\0\x0a\0'+good[4:],
                    bytes.fromhex('83000000010001001400')):
            with self.subTest(raw=raw.hex()),self.assertRaises(InventoryError):
                decode_attribute_list(raw,(1,),{1:2})
        with self.assertRaises(InventoryError):decode_attribute_list(good,(1,),{})
        for text in (b'a\0b',b'\xff'):
            raw=bytes.fromhex('83000000')+struct.pack('<HHHH',1,1,0,len(text))+text
            with self.assertRaises(InventoryError):decode_attribute_list(raw,(1,),{1:'ascii16'})

    def test_reply_headers_and_partial_instance_pages_have_bounded_progress(self):
        for raw in (b'',bytes.fromhex('8e000000'),bytes.fromhex('83010000'),bytes.fromhex('83000002')):
            with self.assertRaises(InventoryError):decode_reply(raw,3)
        for ids,status,cursor in (([],6,0),([0],0,0),([5,5],0,0),([7,6],0,0),
                                 ([4],0,5),([0xFFFFFFFF],6,0)):
            raw=bytes((0xCB,0,status,0))+b''.join(struct.pack('<I',i) for i in ids)
            with self.subTest(ids=ids),self.assertRaises(InventoryError):decode_instance_page(raw,cursor)
        with self.assertRaises(InventoryError):decode_instance_page(bytes.fromhex('cb00000001'),0)

    def test_pagination_uses_last_sparse_id_and_verifies_count_not_maximum(self):
        responses=[bytes.fromhex('83000000')+struct.pack('<HHHHHHIHHI',3,1,0,1,2,0,300,3,0,3),
                   bytes.fromhex('cb000600')+struct.pack('<II',1,255),
                   bytes.fromhex('cb000000')+struct.pack('<I',300)]
        class Fake:
            def __init__(self):self.requests=[]
            def request(self,raw):self.requests.append(raw);return responses.pop(0)
        client=Fake();reader=_Reader(client,Limits(),False)
        result=reader.catalog(0x6B)
        self.assertEqual(result['instances'],[1,255,300])
        self.assertEqual(client.requests[-1],bytes.fromhex('4b03206b25000001'))

    def test_limits_reject_booleans_and_request_budget_stops_before_next_exchange(self):
        for name in ('instances','programs','pages','requests'):
            for value in (0,True,-1,1.5,100000):
                with self.subTest(name=name,value=value),self.assertRaises(InventoryError):Limits(**{name:value})
        class Fake:
            count=0
            def request(self,raw):self.count+=1;return bytes.fromhex('81000800')
        client=Fake();reader=_Reader(client,Limits(requests=1),False)
        reader.exchange(1,0x8E,1)
        with self.assertRaises(InventoryError):reader.exchange(1,0x8E,1)
        self.assertEqual(client.count,1)
        for service,cls in ((0x10,0x8E),(4,0x8E),(0x4B,0x378),(0x4F,0xAC)):
            with self.assertRaises(InventoryError):reader.exchange(service,cls,1)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class InventoryTcpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.tree=E.parse(Path(__file__).resolve().parents[1]/'samples/NetworkLab.L5X')
        controller=self.tree.getroot().find('Controller')
        controller.set('MatchProjectToController','false')
        controller.set('InhibitAutomaticFirmwareUpdate','5')
        controller.set('CanUseRPIFromProducer','true')
        tags=controller.find('Tags')
        fixed=E.SubElement(tags,'Tag',Name='Fixed',TagType='Base',DataType='DINT',Constant='true',ExternalAccess='Read Only')
        E.SubElement(E.SubElement(fixed,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='7')
        E.SubElement(tags,'Tag',Name='CommandAlias',TagType='Alias',DataType='DINT',AliasFor='Command',ExternalAccess='Read Only')
        local=E.SubElement(controller.find('./Programs/Program/Tags'),'Tag',Name='Local',TagType='Base',DataType='DINT',ExternalAccess='Read/Write')
        E.SubElement(E.SubElement(local,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='99')
        self.load()
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start()
        self.app.endpoint=self.endpoint

    def load(self):
        self.app.command('load',{'name':'inventory.L5X','content':base64.b64encode(E.tostring(self.tree.getroot())).decode()})
        self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,
            [Symbol('',0,'Command',3),Symbol('',0,'ControlWord',70000),Symbol('',0,'Observed',17),
             Symbol('',0,'Transfer',20),Symbol('',0,'Fixed',21),Symbol('',0,'CommandAlias',22),
             Symbol('MainProgram',70000,'Local',3)],programs=[{'name':'MainProgram','instance':70000}])

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def test_actual_signed_inventory_reads_scalars_and_retains_arrays_aliases_and_constants(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        report=collect_inventory(self.endpoint)
        self.assertTrue(report['catalog_consistent']);self.assertFalse(report['project_upload_complete'])
        self.assertEqual(report['native_acceptance'],'NOT ASSESSED')
        self.assertEqual(report['endpoint_clients_after_close'],0)
        self.assertEqual(report['controller_get_all']['status'],8)
        self.assertEqual([r['status'] for r in report['controller_handlers']],[0x14,0x14])
        self.assertEqual(values(report['controller_configuration'])[17],5)
        self.assertEqual(values(report['controller_configuration'])[23],1)
        self.assertEqual(report['program_catalog']['instances'],[70000])
        self.assertEqual(values(report['programs'][0]['metadata'])[19],0)
        scopes=report['scopes'];self.assertEqual([s['program_instance'] for s in scopes],[None,70000])
        rows={values(row['metadata'])[1]:row for row in scopes[0]['symbols']}
        self.assertEqual(rows['ControlWord']['value'],32)
        self.assertEqual(rows['Command']['value'],2)
        self.assertEqual(rows['Observed']['value'],0)
        self.assertEqual(rows['Transfer']['value_state'],'non_scalar_or_unsupported_type')
        self.assertEqual(rows['Fixed']['value_state'],'storage_unavailable')
        self.assertEqual(rows['CommandAlias']['value_state'],'table_unavailable')
        self.assertEqual(scopes[1]['symbols'][0]['instance'],3)
        self.assertEqual(scopes[1]['symbols'][0]['value'],99)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertTrue(any(r['service']==0x4F for r in report['requests']))
        json.dumps(report,allow_nan=False)

    def test_unbound_program_inventory_is_unavailable_and_values_can_be_omitted(self):
        self.app.native_symbols=None
        report=collect_inventory(self.endpoint,read_values=False)
        self.assertEqual(report['program_catalog']['status'],0x0C)
        self.assertIsNone(report['program_catalog']['instances'])
        self.assertEqual(len(report['scopes']),1)
        self.assertFalse(any(r['service']==0x4F for r in report['requests']))
        self.assertTrue(all(r['value_state']=='not_requested' or r['value_state']=='table_unavailable'
                            for r in report['scopes'][0]['symbols']))

    def test_request_budget_and_source_replacement_close_owned_client_without_running_logic(self):
        with self.assertRaises(InventoryError):collect_inventory(self.endpoint,limits=Limits(requests=2))
        original=AnonymousClient.request;calls=[]
        def changed(client,raw,wrapper=0x36):
            result=original(client,raw,wrapper)
            if raw.startswith(bytes.fromhex('030220ac2401')):
                calls.append(raw);self.app.generation+=1
            return result
        with patch.object(AnonymousClient,'request',changed):
            with self.assertRaises(ProbeError):collect_inventory(self.endpoint)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_wrong_policy_is_rejected_before_network_and_float_nonfinite_stays_json_safe(self):
        self.endpoint.allow_writes=True
        with self.assertRaises(ProbeError):collect_inventory(self.endpoint)
        self.endpoint.allow_writes=False
        observed=self.tree.getroot().find('./Controller/Tags/Tag[@Name="Observed"]')
        observed.set('DataType','REAL')
        observed.find('./Data/DataValue').set('DataType','REAL')
        self.load()
        original=AnonymousClient.request
        def nonfinite_reply(client,raw,wrapper=0x36):
            result=original(client,raw,wrapper)
            # Decoder fault injection after the independently checked wire
            # exchange; the model itself rejects nonfinite REAL writes.
            if raw.startswith(bytes.fromhex('4f02206a2411')):
                return result[:4]+struct.pack('<f',float('nan'))
            return result
        with patch.object(AnonymousClient,'request',nonfinite_reply):
            report=collect_inventory(self.endpoint)
        row=next(r for r in report['scopes'][0]['symbols'] if values(r['metadata'])[1]=='Observed')
        self.assertEqual(row['value_state'],'nonfinite');self.assertEqual(row['nonfinite'],'NaN')
        self.assertIsNone(row['value']);self.assertEqual(len(row['value_read']['data_hex']),8)
        json.dumps(report,allow_nan=False)


if __name__=='__main__':unittest.main()
