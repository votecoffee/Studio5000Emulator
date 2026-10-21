"""Independent signed inventory of Template bytes, arrays and raw UDT values."""
import copy
import importlib.util
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint,Router
from logixlab.model import Tag
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient,ProbeError
from tools.upload_inventory import (InventoryError,Limits,array_shape,collect_inventory,
                                    decode_atomic_value,values)


class InventoryValueDecoderTests(unittest.TestCase):
    def test_unowned_targets_are_rejected_without_entering_endpoint_cleanup(self):
        with self.assertRaises(ProbeError):collect_inventory(object())

    def test_row_major_arrays_cover_three_dimensions_and_atomic_signedness(self):
        shape=array_shape(0x60C3,[2,2,2])
        value,nonfinite=decode_atomic_value(struct.pack('<8h',-4,-3,-2,-1,0,1,2,3),0xC3,shape)
        self.assertEqual(value,[[[-4,-3],[-2,-1]],[[0,1],[2,3]]]);self.assertEqual(nonfinite,[])
        self.assertEqual(decode_atomic_value(struct.pack('<Q',1<<63),0xC9,()),(1<<63,[]))
        self.assertEqual(decode_atomic_value(b'\1',0xC1,()),(True,[]))

    def test_invalid_ranks_zero_padding_byte_extents_and_packed_bools_are_rejected(self):
        for code,dims in ((0xC4,[2,0,0]),(0x20C4,[2,2,0]),(0x40C4,[2,0,2]),
                          (0x20C4,[True,0,0]),(0x20C4,[2,-1,0]),(0x20C4,[2,0])):
            with self.subTest(code=code,dims=dims),self.assertRaises(InventoryError):array_shape(code,dims)
        for data,code,shape in ((bytes(3),0xC4,()),(bytes(8),0xC4,()),(b'\2',0xC1,()),
                                (b'\1',0xC1,(1,)),(b'',0xC4,(1<<32,1<<32)),(b'',0xC4,(True,))):
            with self.subTest(code=code,shape=shape),self.assertRaises(InventoryError):decode_atomic_value(data,code,shape)
        for value in (0,True,-1,1025):
            with self.assertRaises(InventoryError):Limits(templates=value)

    def test_nonfinite_array_locations_are_json_safe_without_losing_finite_elements(self):
        raw=struct.pack('<4f',1.5,float('nan'),float('inf'),float('-inf'))
        value,nonfinite=decode_atomic_value(raw,0xCA,(2,2))
        self.assertEqual(value,[[1.5,None],[None,None]])
        self.assertEqual(nonfinite,[{'index':[0,1],'value':'NaN'},
                                   {'index':[1,0],'value':'Infinity'},
                                   {'index':[1,1],'value':'-Infinity'}])
        json.dumps({'value':value,'nonfinite':nonfinite},allow_nan=False)


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class InventoryTypesTcpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
        self.app.command('demo',{'sample':'StructureLab'})
        project=self.app.engine.project
        project.udts['compact']=E.fromstring('''<DataType Name="Compact" Class="User" Family="NoFamily"><Members>
            <Member Name="Count" DataType="DINT"/><Member Name="Position" DataType="REAL"/>
            <Member Name="Code" DataType="SINT"/></Members></DataType>''')
        self.add('Status','Compact',{'Count':17,'Position':1.5,'Code':-3})
        self.add('States','Compact',[{'Count':10,'Position':2.5,'Code':-4},{'Count':20,'Position':3.5,'Code':-5}])
        self.add('Grid','DINT',[[1,2],[3,4]])
        self.add('Grid','DINT',[[5,6],[7,8]],scope='MainProgram')
        self.bindings=[Symbol('',0,'Grid',3),Symbol('',0,'Status',4),Symbol('',0,'States',5),
                       Symbol('MainProgram',17,'Grid',3)]
        self.bind()
        self.app.native_project_identity=NativeProjectIdentity('a'*64,project.sha256,1,1,1,1,1,1)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start()
        self.app.endpoint=self.endpoint

    def add(self,name,dtype,value,**fields):
        tag=Tag(name,dtype,value,**fields)
        self.app.engine.project.tags[tag.key.lower()]=tag
        self.app.engine.memory.values[tag.key.lower()]=copy.deepcopy(value)

    def bind(self):
        self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,self.bindings,
            programs=[{'name':'MainProgram','instance':17}])

    def tearDown(self):self.app.close();self.temp.cleanup()

    def assert_closed_and_unchanged(self,before):
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertEqual(self.endpoint.state()['active_tcp_clients'],0)

    def test_actual_signed_catalog_definitions_arrays_and_raw_structure_links(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        report=collect_inventory(self.endpoint)
        self.assertEqual(len(report['templates']),1)
        template=report['templates'][0];definition=template['definition']
        self.assertEqual(definition['name'],'Compact')
        self.assertEqual([member['name'] for member in definition['members']],['Count','Position','Code'])
        self.assertEqual([member['offset_word'] for member in definition['members']],[0,4,8])
        self.assertEqual(template['unavailable_attributes'],[7,8]);self.assertEqual(values(template['metadata'])[6],0)
        self.assertEqual(definition['allocated_bytes'],definition['compact_bytes']+3)
        self.assertTrue(definition['reserved_padding_zero']);self.assertFalse(definition['member_offsets_interpreted'])
        rows={values(row['metadata'])[1]:row for row in report['scopes'][0]['symbols']}
        self.assertEqual(rows['Grid']['value'],[[1,2],[3,4]])
        self.assertEqual(report['scopes'][1]['symbols'][0]['value'],[[5,6],[7,8]])
        self.assertEqual(rows['Status']['value_state'],'raw_structure');self.assertIsNone(rows['Status']['value'])
        self.assertEqual(bytes.fromhex(rows['Status']['value_read']['data_hex']),struct.pack('<ifb3x',17,1.5,-3))
        self.assertEqual(bytes.fromhex(rows['States']['value_read']['data_hex']),
                         struct.pack('<ifb3xifb3x',10,2.5,-4,20,3.5,-5))
        self.assertEqual(rows['States']['template_instance'],template['instance'])
        self.assertEqual(rows['States']['element_count'],2)
        self.assertEqual(report['template_definition_bytes'],definition['allocated_bytes'])
        self.assertTrue(report['values_requested']);self.assertFalse(report['values_are_one_snapshot'])
        self.assertFalse(report['project_upload_complete']);self.assertEqual(report['native_acceptance'],'NOT ASSESSED')
        self.assert_closed_and_unchanged(before);json.dumps(report,allow_nan=False)

    def add_wide_type(self):
        members=''.join(f'<Member Name="Field{i:03}" DataType="DINT"/>' for i in range(70))
        self.app.engine.project.udts['wide']=E.fromstring('<DataType Name="Wide" Class="User" Family="NoFamily"><Members>'+members+'</Members></DataType>')
        self.add('WideTag','Wide',{f'Field{i:03}':i for i in range(70)})
        self.bindings.append(Symbol('',0,'WideTag',6));self.bind()

    def test_template_pagination_and_read_values_false_keep_metadata_and_omit_value_packets(self):
        self.add_wide_type();report=collect_inventory(self.endpoint,read_values=False)
        wide=next(row for row in report['templates'] if row['definition']['name']=='Wide')
        reads=[row for row in report['requests'] if row['service']==0x4C and row['instance']==wide['instance']]
        self.assertGreater(len(reads),1);self.assertEqual(reads[0]['status'],6);self.assertEqual(reads[-1]['status'],0)
        self.assertEqual(len(wide['definition']['members']),70)
        self.assertFalse(any(row['service']==0x4F for row in report['requests']))
        self.assertEqual(self.app.engine.scan_count,0)

    def test_template_count_page_and_aggregate_limits_close_client_without_running_logic(self):
        self.add_wide_type();before=copy.deepcopy(self.app.engine.memory.values)
        for limits in (Limits(templates=1),Limits(pages=1)):
            with self.subTest(limits=limits),self.assertRaises(InventoryError):collect_inventory(self.endpoint,limits=limits)
            self.assert_closed_and_unchanged(before)
        with patch('tools.upload_inventory.MAX_TOTAL_TEMPLATE_BYTES',1):
            with self.assertRaisesRegex(InventoryError,'aggregate byte budget'):collect_inventory(self.endpoint)
        self.assert_closed_and_unchanged(before)

    def test_short_empty_oversized_and_contradictory_definition_replies_stop_without_retries(self):
        original=AnonymousClient.request;before=copy.deepcopy(self.app.engine.memory.values)
        for mutation in ('short','empty','oversized','partial_complete','padding'):
            calls=[]
            def changed(client,raw,wrapper=0x36):
                reply=original(client,raw,wrapper)
                if raw[0]==0x4C:
                    calls.append(raw)
                    if mutation=='short':return reply[:-3]
                    if mutation=='empty':return b'\xCC\0\6\0'
                    if mutation=='oversized':return reply+b'\0'
                    if mutation=='partial_complete':return b'\xCC\0\6\0'+reply[4:]
                    return reply[:-1]+b'\1'
                return reply
            with self.subTest(mutation=mutation),patch.object(AnonymousClient,'request',changed):
                with self.assertRaises(InventoryError):collect_inventory(self.endpoint)
            self.assertEqual(len(calls),1);self.assert_closed_and_unchanged(before)

    def test_nonnull_multiply_code_is_rejected_before_definition_reads(self):
        original=Router.attribute_read;request=AnonymousClient.request
        before=copy.deepcopy(self.app.engine.memory.values);definition_reads=[]
        def changed(router,service,path,data,attributes):
            if path.class_id==0x6C and path.instance:attributes={**attributes,7:struct.pack('<I',1)}
            return original(router,service,path,data,attributes)
        def observed(client,raw,wrapper=0x36):
            if raw[0]==0x4C:definition_reads.append(raw)
            return request(client,raw,wrapper)
        with patch.object(Router,'attribute_read',changed),patch.object(AnonymousClient,'request',observed):
            with self.assertRaisesRegex(InventoryError,'nonnull Template code reference'):collect_inventory(self.endpoint)
        self.assertEqual(definition_reads,[])
        self.assert_closed_and_unchanged(before)

    def test_shape_and_template_size_disagreements_are_errors_even_with_successful_packets(self):
        original=Router.symbol_attributes;before=copy.deepcopy(self.app.engine.memory.values)
        def changed(router,symbol):
            attributes=original(router,symbol)
            if symbol['name']=='Status':attributes={**attributes,7:struct.pack('<H',11)}
            return attributes
        with patch.object(Router,'symbol_attributes',changed):
            with self.assertRaisesRegex(InventoryError,'element size'):collect_inventory(self.endpoint)
        self.assert_closed_and_unchanged(before)


if __name__=='__main__':unittest.main()
