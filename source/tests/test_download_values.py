"""Initial bytes require complete named coverage, original layouts and source."""
import copy
from dataclasses import replace
import hashlib
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from logixlab.download_image import ImageError,Region
from logixlab.download_values import PreparedValues,encode_value,encode_initial,_local_ports
from logixlab.native_types import NativeTypes,Type,Member
from logixlab.native_symbols import Symbol
import test_download_changelog as logs


def builtins(dtype='TIMER'):
    flags=('EN','TT','DN') if dtype=='TIMER' else ('CU','CD','DN','OV','UN')
    rows=[Member('Control','DINT',0,None,(),'Read/Write',True),
          Member('PRE','DINT',4,None,(),'Read/Write',False),Member('ACC','DINT',8,None,(),'Read/Write',False)]
    rows += [Member(n,'BOOL',0,31-i,(),'Read/Write',False) for i,n in enumerate(flags)]
    return NativeTypes('a'*64,'b'*64,[Type(dtype,12,tuple(rows))],{dtype.lower():0xF82 if dtype=='COUNTER' else 0xF83})


class ValueTests(unittest.TestCase):
    def test_numeric_array_rank_dimensions_and_last_index_fast_saved_bytes(self):
        for dtype,value,code,dimensions,fmt,flat in (
                ('DINT',[-3,0,2147483647],0x20C4,(3,0,0),'3i',[-3,0,2147483647]),
                ('INT',[[-32768,32767],[1,-1]],0x40C3,(2,2,0),'4h',[-32768,32767,1,-1]),
                ('REAL',[[[.25,-2.5]],[[8.0,0.0]]],0x60CA,(2,1,2),'4f',[.25,-2.5,8.0,0.0]),
                ('USINT',[0,255],0x20C6,(2,0,0),'2B',[0,255]),
                ('LINT',[-2**63,2**63-1],0x20C5,(2,0,0),'2q',[-2**63,2**63-1])):
            with self.subTest(dtype=dtype):
                original=copy.deepcopy(value)
                self.assertEqual(encode_initial(dtype,value,None),(code,dimensions,len(flat),struct.pack('<'+fmt,*flat)))
                self.assertEqual(value,original)
        self.assertEqual(encode_initial('DINT',50,None),(0xC4,(0,0,0),1,struct.pack('<i',50)))

    def test_array_shape_rank_leaf_types_ranges_and_extent_are_not_guessed(self):
        for dtype,value in (('DINT',[]),('DINT',[[1],[2,3]]),('DINT',[1,[2]]),
                ('DINT',[[[[1]]]]),('DINT',[True]),('DINT',[2**31]),('DINT',[(1,2)]),
                ('REAL',[float('nan')]),('REAL',[float('inf')]),('REAL',[1]),
                ('BOOL',[True,False]),('TIMER',[{}]),('Unknown',[1]),('DINT',[0]*65537)):
            with self.subTest(dtype=dtype,shape=type(value)),self.assertRaises(ImageError):
                encode_initial(dtype,value,builtins())
        self.assertEqual(encode_initial('SINT',[0]*65536,None)[:3],(0x20C2,(65536,0,0),65536))

    def test_array_preparation_requires_exact_declared_shape_type_and_every_saved_element(self):
        headers,project=self.fixture();project.initial['x']=[[1,2,3],[4,5,6]]
        data=struct.pack('<6i',1,2,3,4,5,6);region=Region(1,0x40C4,(2,3,0),6,data)
        headers.namespace._image._regions[1]=region
        original=copy.deepcopy(project.initial);plan=PreparedValues.prepare(headers,None)
        self.assertEqual(plan.values,(('x',1,0x40C4,data),));self.assertTrue(plan.description()['atomic_arrays'])
        self.assertEqual(project.initial,original)
        for bad in (replace(region,dimensions=(3,2,0)),replace(region,type_code=0x20C4),
                    replace(region,elements=5),replace(region,data=data[:-1]),
                    replace(region,data=struct.pack('<6i',1,2,3,4,5,7))):
            headers.namespace._incremental._tables[1]=bad
            with self.assertRaises(ImageError):PreparedValues.prepare(headers,None)
        headers.namespace._incremental._tables.clear();project.initial['x'][1][2]=7
        with self.assertRaises(ImageError):plan.validate(headers,None)

    def test_explicit_scalars_and_original_builtin_offsets_bits_and_template_id(self):
        for dtype,value,code,data in (('BOOL',True,0xC1,b'\1'),('DINT',-123,0xC4,struct.pack('<i',-123)),
                                      ('REAL',1.25,0xCA,struct.pack('<f',1.25))):
            self.assertEqual(encode_value(dtype,value,None),(code,data))
        timer=dict(PRE=1000,ACC=123,EN=True,TT=False,DN=True)
        self.assertEqual(encode_value('TIMER',timer,builtins()),(0x8F83,struct.pack('<Iii',0xA0000000,1000,123)))
        counter=dict(PRE=5,ACC=-1,CU=True,CD=True,DN=False,OV=True,UN=True)
        self.assertEqual(encode_value('COUNTER',counter,builtins('COUNTER')),(0x8F82,struct.pack('<Iii',0xD8000000,5,-1)))
        types=builtins();row=types.types['timer'];types.types['timer']=replace(row,members=(replace(row.members[0],offset=4),*row.members[1:]))
        with self.assertRaises(ImageError):encode_value('TIMER',timer,types)

    def test_noncanonical_values_unsupported_arrays_fields_and_overflow_reject(self):
        for dtype,value in (('BOOL',1),('BOOL',None),('DINT',True),('DINT',2**31),('DINT',[1]),
                            ('REAL',float('nan')),('REAL',float('inf')),('REAL','1'),('Unknown',{})):
            with self.subTest(dtype=dtype,value=value),self.assertRaises(ImageError):encode_value(dtype,value,builtins())
        timer=dict(PRE=1000,ACC=0,EN=False,TT=False,DN=False)
        for value in ({**timer,'Control':0},{**timer,'EN':0},{**timer,'ACC':2**31}):
            with self.assertRaises(ImageError):encode_value('TIMER',value,builtins())

    def fixture(self):
        project=NS(tags={'x':NS(dtype='DINT',alias='',problem='',tag_class='Standard')},initial={'x':50})
        symbol=Symbol('',0,'x',9);image=NS(_symbols={(0,9):1},_regions={1:Region(1,0xC4,(0,0,0),1,struct.pack('<i',50))})
        ns=NS(_source='source',_image=image,_incremental=NS(_tables={}))
        return NS(namespace=ns,_project=lambda:project,stamp=lambda image,source:'fixed',
                  symbols=NS(by_key={'x':symbol}),auxiliary=None,engine=NS(project=project)),project

    def test_preparation_rechecks_values_coverage_dimensions_and_aliases(self):
        headers,project=self.fixture();plan=PreparedValues.prepare(headers,None)
        self.assertEqual(plan.values,(('x',1,0xC4,struct.pack('<i',50)),));self.assertTrue(plan.description()['all_tables_accounted'])
        project.initial['x']=51
        with self.assertRaises(ImageError):plan.validate(headers,None)
        project.initial['x']=50
        for region in (Region(1,0xC4,(1,0,0),1,struct.pack('<i',50)),Region(1,0xC3,(0,0,0),1,b'2\0')):
            headers.namespace._incremental._tables={1:region}
            with self.assertRaises(ImageError):PreparedValues.prepare(headers,None)
        headers.namespace._incremental._tables={};project.tags['x'].alias='y'
        with self.assertRaises(ImageError):PreparedValues.prepare(headers,None)
        project.tags['x'].alias='';project.tags['extra']=project.tags['x']
        with self.assertRaises(ImageError):PreparedValues.prepare(headers,None)

    def test_unknown_extra_table_refuses_whole_preparation(self):
        headers,_=self.fixture();headers.namespace._image._regions[2]=Region(2,0xC4,(0,0,0),1,bytes(4))
        with self.assertRaises(ImageError):PreparedValues.prepare(headers,None)

    def test_local_port_xml_matches_original_source_and_rejects_changed_file_or_bus(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.L5X'
            raw=b'<RSLogix5000Content><Controller><Modules><Module Name="Local"><Ports><Port Id="1" Type="ICP" Address="0" Upstream="false"><Bus Size="17"/></Port><Port Id="2" Type="Ethernet" Upstream="false"><Bus/></Port></Ports></Module></Modules></Controller></RSLogix5000Content>'
            path.write_bytes(raw);project=NS(path=path,sha256=hashlib.sha256(raw).hexdigest(),io_map=NS(empty=True,root_link_port=1))
            data=b'<in><Port Id="1" Type="ICP" Addr="0" Ups="False"><Bus Max="17" Size="17"/></Port><Port Id="2" Type="EN" Ups="False"/></in>\0'
            _local_ports(project,data)
            for bad in (data.replace(b'Max="17"',b'Max="18"'),data[:-1],data.replace(b'<in>',b'<!DOCTYPE in><in>')):
                with self.assertRaises(ImageError):_local_ports(project,bad)
            path.write_bytes(raw+b' ')
            with self.assertRaises(ImageError):_local_ports(project,data)
            path.unlink()
            with self.assertRaises(ImageError):_local_ports(project,data)


class ValuesSignedTests(logs.NamespaceFixture,unittest.TestCase):
    complete_tasks=logs.ChangelogSignedTests.complete_tasks
    configure=logs.ChangelogSignedTests.configure
    ready_setup=logs.ChangelogSignedTests.ready_setup
    ready_routines=logs.ChangelogSignedTests.ready_routines
    next_routines=logs.ChangelogSignedTests.next_routines
    ready_map=logs.ChangelogSignedTests.ready_map
    ready_log=logs.ChangelogSignedTests.ready_log
    proposal=logs.ChangelogSignedTests.proposal
    def setUp(self):
        route=logs.maps.map_route
        def complete_route(test):
            result=route(test);tags=result[1].find('Tags')
            for tag in list(tags):
                if tag.get('Name')!='SpeedSetpoint':tags.remove(tag)
                else:
                    for node in tag.findall('.//DataValue'):node.set('Value','0')
                    for node in tag.findall('Data[@Format="L5K"]'):node.text='0'
            return result
        with patch.object(logs.maps,'map_route',complete_route):logs.ChangelogSignedTests.setUp(self)
        # The shared protocol fixture adds controller configuration after load.
        # Match the epoch to that final source configuration before installation.
        from logixlab.change_detection import ChangeDetection
        project=self.app.engine.project
        self.app.engine.change_detection=ChangeDetection(project.sha256,project.controller_configuration.changes_to_detect)

    def test_prepare_and_install_from_signed_commit_request_has_exact_saved_values(self):
        self.ready_log();self.send(logs.CREATE_REQUEST);self.send(logs.CONFIG_REQUEST+logs.payload(self.proposal()))
        engine=self.app.engine;before=copy.deepcopy(engine.memory.values)
        self.assertEqual(self.send(logs.COMMIT)[2],0)
        self.assertIsNot(self.app.engine,engine);self.assertEqual(engine.memory.values,before)
        prepared=self.namespace.initial_values;self.assertEqual(len(prepared.values),1)
        headers=self.endpoint.router.download_header_bindings(self.endpoint.programming_lease)
        candidate=prepared.new_engine(headers,self.app.native_types)
        self.assertIsNot(candidate,engine);self.assertEqual(candidate.memory.values,engine.project.initial)
        self.assertEqual(candidate.scan_count,0);self.assertEqual(candidate.prescan_count,0)
        self.assertEqual(self.send(logs.ENUM)[2],0)
        self.assertEqual(self.send(logs.prep.END)[2],0);self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_failed_candidate_cannot_publish_prepared_values_or_replace_active_model(self):
        self.ready_log();self.send(logs.CREATE_REQUEST);self.send(logs.CONFIG_REQUEST+logs.payload(self.proposal()))
        engine=self.app.engine
        with patch('logixlab.download_values.Engine',return_value=NS(blockers=['unsupported'],fault='')):
            self.assertEqual(self.send(logs.COMMIT)[2],12)
        self.assertIsNone(self.namespace.initial_values);self.assertIs(self.app.engine,engine)
        self.assertEqual(engine.scan_count,0);self.assertEqual(self.send(logs.prep.END)[2],0)


if __name__=='__main__':unittest.main()
