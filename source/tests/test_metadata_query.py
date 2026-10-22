"""Detached metadata records, fragmented streams, malformed captures and privacy."""
from dataclasses import FrozenInstanceError
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab import metadata_query as metadata
from tools import metadata_upload_query as tool
from tools.inspect_cip_capture import summarize
from tools.analyze_native_transfer import analyze
from test_capture_inspection import packet
from test_native_transfer_trace import event
from test_signed_messages import request as signed_request,response as signed_response
from test_signed_batches import batch


# Independent hand-authored target and full string record, including nonzero
# context/selector words and a qualifier. Their meaning is deliberately opaque.
TARGET=bytes.fromhex('68003412000078560000090002005131')
TEXT=TARGET+bytes.fromhex('090401000700000000000000000000000000000001000600')+b'Secret'


def record(value,word=8):
    return TARGET+struct.pack('<HHI',0x7f,4,word)+bytes(12)+value


def query(fmt=0x101,position=0,selection='all-objects',path=bytes.fromhex('210049032400')):
    return bytes((0x53,len(path)//2))+path+struct.pack('<II',fmt,position)+metadata.SELECTIONS[selection]


def reply(data=TEXT,fmt=0x301,position=0):return bytes.fromhex('d3000000')+struct.pack('<II',fmt,position)+data


def parts(data=TEXT,cut=19):
    return [(query(),reply(data[:cut],0x101)),(query(1,cut),reply(data[cut:],0x201,cut))]


class MetadataRecordTests(unittest.TestCase):
    def test_hand_authored_full_record_keeps_ids_context_locale_and_string_blob(self):
        rows=metadata.records(TEXT);self.assertEqual(len(rows),1);row=rows[0]
        self.assertEqual(row.target,metadata.Target(0x68,0x1234,0x5678,9,b'Q1'))
        self.assertEqual((row.locale_word,row.definition,row.record_word,row.kind),(0x409,1,7,1))
        self.assertEqual(row.data,b'Secret')
        with self.assertRaises(FrozenInstanceError):row.definition=2
        with self.assertRaises(FrozenInstanceError):row.target.qualifier=b'changed'
        summary=metadata.inventory(rows)
        self.assertEqual(summary['locales'],1);self.assertEqual(summary['value_kinds'],{'1':1})
        for text in ('Secret','536563726574','Q1','qualifier','record_word','instance_word'):
            self.assertNotIn(text,json.dumps(summary))
        self.assertFalse(summary['source_binding_verified']);self.assertFalse(summary['program_query_0x50_resolved'])

    def test_numeric_reference_empty_and_opaque_string_blobs_consume_exactly(self):
        numeric=[record(bytes.fromhex('0200c2000200807f'),8),record(bytes.fromhex('0200c30001000080'),9),
                 record(bytes.fromhex('0200c4000100ffffffff'),10)]
        reference=record(bytes.fromhex('030001000300')+b'Ref'+TARGET,11)
        empty=record(bytes.fromhex('0400'),12)
        blob=record(struct.pack('<HH',1,6)+bytes.fromhex('8082ffff789c'),13)
        rows=metadata.records(TEXT+b''.join(numeric)+reference+empty+blob)
        self.assertEqual([r.kind for r in rows],[1,2,2,2,3,4,1])
        self.assertEqual([len(r.data) for r in rows[1:4]],[2,2,4])
        self.assertEqual(rows[4].references,(metadata.Reference(b'Ref',rows[0].target),))
        self.assertEqual(rows[5].data,b'');self.assertEqual(rows[6].data,bytes.fromhex('8082ffff789c'))
        self.assertEqual(metadata.inventory(rows)['numeric_types'],{'194':1,'195':1,'196':1})
        self.assertFalse(metadata.inventory(rows)['string_blob_expansion'])

    def test_every_truncated_prefix_and_invalid_late_record_reject_the_whole_inventory(self):
        for n in range(1,len(TEXT)):
            with self.subTest(size=n),self.assertRaises(ValueError):metadata.records(TEXT[:n])
        for raw in (TEXT+b'x',TEXT+record(b'\x05\0'),TEXT+TEXT,
                    record(bytes.fromhex('0200ca00010000000000')),
                    record(bytes.fromhex('0200c2000000')),record(bytes.fromhex('03000000')),
                    record(bytes.fromhex('030001000300')+b'Ref'+TARGET[:-1]),record(b'\x04\0',0)):
            with self.assertRaises(ValueError):metadata.records(raw)
        for offset in (18,24):
            changed=bytearray(TEXT);changed[offset]=0
            if offset==24:changed[offset]=1
            with self.assertRaises(ValueError):metadata.records(bytes(changed))
        self.assertEqual(metadata.records(b''),())
        for data in (None,bytearray(TEXT),b'x'*(metadata.MAX_BYTES+1)):
            with self.assertRaises(ValueError):metadata.records(data)
        for limit in (True,0,metadata.MAX_RECORDS+1):
            with self.assertRaises(ValueError):metadata.records(TEXT,max_records=limit)
        with self.assertRaises(ValueError):metadata.records(TEXT+record(b'\x04\0'),max_records=1)


class MetadataStreamTests(unittest.TestCase):
    def test_every_split_point_including_record_headers_reassembles_the_same_bytes(self):
        for cut in range(1,len(TEXT)):
            assembly=metadata.Assembly()
            for request,response in parts(cut=cut):
                q,c,status=tool.frame(request,response);self.assertEqual(status,0);assembly.accept(q,c)
            self.assertTrue(assembly.complete);self.assertEqual(assembly.data(),TEXT)
            self.assertEqual(metadata.records(assembly.data()),metadata.records(TEXT))

    def test_three_fragments_echo_offsets_instead_of_claiming_a_byte_count(self):
        frames=[(query(),reply(TEXT[:5],0x101)),(query(1,5),reply(TEXT[5:27],1,5)),
                (query(1,27),reply(TEXT[27:],0x201,27))]
        report=tool.replay(frames)
        self.assertTrue(report['analysis_complete']);self.assertEqual(report['frames'],3)
        self.assertEqual(report['decoded_records'],1);self.assertEqual(report['streams'][0]['bytes'],len(TEXT))
        for selection in metadata.SELECTIONS:
            single=tool.replay([(query(selection=selection),reply(b''))])
            self.assertTrue(single['analysis_complete']);self.assertEqual(single['decoded_records'],0)
        self.assertEqual(tool.describe(*frames[0])['response_position'],0)

    def test_bad_cursor_duplicate_changed_selection_and_limits_leave_state_unchanged(self):
        a=metadata.Assembly();q,c,_=tool.frame(*parts()[0]);a.accept(q,c);before=a.description()
        invalid=[(metadata.Query(1,18,'all-objects'),metadata.Chunk(1,18,b'x')),
                 (metadata.Query(1,19,'controller-all'),metadata.Chunk(1,19,b'x')),
                 (q,c),(metadata.Query(1,19,'all-objects'),metadata.Chunk(0x201,20,b'x')),
                 (metadata.Query(1,19,'all-objects'),metadata.Chunk(1,19,b'')),
                 (metadata.Query(True,19,'all-objects'),metadata.Chunk(1,19,b'x'))]
        for request,response in invalid:
            with self.assertRaises(ValueError):a.accept(request,response)
            self.assertEqual(a.description(),before)
        with self.assertRaises(ValueError):a.data()
        for size,frames in ((18,2),(len(TEXT),1)):
            limited=metadata.Assembly(max_bytes=size,max_frames=frames)
            with self.assertRaises(ValueError):
                for request,response in parts():
                    q,c,_=tool.frame(request,response);limited.accept(q,c)
        for values in ({'max_bytes':True},{'max_frames':0},{'max_frames':metadata.MAX_FRAMES+1}):
            with self.assertRaises(ValueError):metadata.Assembly(**values)

    def test_missing_reordered_failed_frames_and_invalid_records_never_report_complete(self):
        first,last=parts()
        cases=[[first],[last],[last,first],[first,first,last],
               [first,(last[0],bytes.fromhex('d3000f00'))],
               [first,(query(1,20),reply(TEXT[19:],0x201,20))],
               [(query(),reply(TEXT+b'x'))],[(query(),reply(TEXT+TEXT))]]
        for rows in cases:
            report=tool.replay(rows)
            self.assertFalse(report['analysis_complete'])
        failed=tool.replay([(query(),bytes.fromhex('d3000f00'))])
        self.assertEqual(failed['failed_queries'],1);self.assertEqual(failed['complete_streams'],0)
        # A new independent initial query can be decoded, but cannot erase loss.
        report=tool.replay([first,(query(),reply())])
        self.assertEqual(report['complete_streams'],1);self.assertEqual(report['incomplete_streams'],1)
        self.assertFalse(report['analysis_complete'])

    def test_unknown_paths_selectors_formats_and_padding_reject(self):
        raw=query();end=2+2*raw[1]
        bad=[raw[:-1],raw+b'x',raw[:end]+struct.pack('<II',0x101,1)+raw[end+8:],
             raw[:end]+struct.pack('<II',0x201,0)+raw[end+8:],
             query(path=bytes.fromhex('210049032401')),query(path=bytes.fromhex('20682400')),
             query(path=bytes.fromhex('20682401210049032400')),
             query(path=bytes.fromhex('2100490324003001')),raw[:-2]+b'\0\0',b'\x53\xff'+raw[2:]]
        for value in bad:
            with self.assertRaises(ValueError):tool.frame(value,reply())
        for value in (reply()[:10],reply(fmt=1),reply(position=len(TEXT)),reply(b'',0x101),
                      bytes.fromhex('d3010000')+reply()[4:],bytes.fromhex('d3000001')+reply()[4:],
                      bytes.fromhex('d3000f00')+bytes(8)):
            with self.assertRaises(ValueError):tool.frame(raw,value)
        a=metadata.Assembly();q,c,_=tool.frame(raw,reply());a.accept(q,c)
        with self.assertRaises(ValueError):a.accept(q,c)


class MetadataToolTests(unittest.TestCase):
    def test_plain_signed_and_batch_capture_frames_and_checkpoint_diagnostics_agree(self):
        request=query();response=reply();expected=tool.describe(request,response)
        for a,b in ((request,response),(signed_request(inner=request),signed_response(inner=response)),
                    (batch((request,)),batch((response,),response=True))):
            report=summarize([packet(1,a),packet(2,b,1)],include_payloads=True)
            self.assertEqual(list(tool.capture_exchanges(report)),[(request,response)])
            replay=tool.replay(tool.capture_exchanges(report));self.assertEqual(replay['decoded_records'],1)
            leaf=report['exchanges'][0]['response']
            if 'signed_envelope' in leaf:
                env=leaf['signed_envelope'];leaf=env['inner'] if 'inner' in env else env['children'][0]
            self.assertEqual(leaf['metadata_upload_query'],expected)
        checkpoint=analyze({'events':[]},{'events':[event(request,response)]},'upload')
        self.assertTrue(checkpoint['analysis_complete']);self.assertEqual(checkpoint['metadata_query_frames_observed'],1)
        self.assertEqual(checkpoint['metadata_query_frames'][0]['metadata_upload_query'],expected)
        bad=analyze({'events':[]},{'events':[event(request,reply(fmt=1))]},'upload')
        self.assertFalse(bad['analysis_complete']);self.assertEqual(bad['metadata_query_errors'],1)

    def test_cli_reports_aggregates_only_preserves_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'private.json';output=Path(folder)/'report.json'
            source.write_text(json.dumps(summarize([packet(1,query()),packet(2,reply(),1)],include_payloads=True)))
            original=source.read_bytes()
            with patch('sys.argv',['metadata_upload_query','--input',str(source),'--output',str(output)]),patch('sys.stdout',io.StringIO()):
                self.assertEqual(tool.main(),0)
                before=output.read_bytes()
                with patch('sys.stderr',io.StringIO()):self.assertEqual(tool.main(),2)
            self.assertEqual(output.read_bytes(),before);self.assertEqual(source.read_bytes(),original)
            for text in ('Secret','536563726574','instance_word','record_word'):
                self.assertNotIn(text,output.read_text())
            incomplete=tool.replay(parts()[:1]);self.assertFalse(incomplete['analysis_complete'])

    def test_capture_payload_omission_and_mismatched_batch_cannot_be_silent_success(self):
        report=summarize([packet(1,query()),packet(2,reply(),1)])
        with self.assertRaises(ValueError):list(tool.capture_exchanges(report))
        req=dict(signed_envelope={'children':[{'service':0x53,'class_id':0x349}]});res=dict(signed_envelope={'children':[]})
        with self.assertRaises(ValueError):list(tool.capture_exchanges({'exchanges':[dict(request=req,response=res)]}))
        for request,response in (({'signed_envelope':{'structure':'UNSUPPORTED OR MALFORMED'}},{'signed_envelope':{}}),
                                 ({'object_path':[]},{}),({'signed_envelope':{}},{'signed_envelope':{}})):
            with self.assertRaises(ValueError):list(tool.capture_exchanges({'exchanges':[dict(request=request,response=response)]}))
        with patch.object(tool,'MAX_EXCHANGES',1):
            report={'exchanges':[dict(request={'signed_envelope':{'children':[{},{}]}},response={'signed_envelope':{'children':[{},{}]}})]}
            with self.assertRaises(ValueError):list(tool.capture_exchanges(report))
        # A known unrelated request does not require decoding its reply. An
        # unsupported metadata reply still prevents success for that query.
        other={'signed_envelope':{'inner':{'service':0x4b,'class_id':0x6a}}}
        unknown={'signed_envelope':{'structure':'UNSUPPORTED OR MALFORMED'}}
        self.assertEqual(list(tool.capture_exchanges({'exchanges':[dict(request=other,response=unknown)]})),[])
        many=tool.replay([(query(),reply(b''))]*70)
        self.assertEqual(many['complete_streams'],70);self.assertEqual(len(many['streams']),64)
        self.assertTrue(many['streams_truncated']);self.assertFalse(tool.replay([])['analysis_complete'])


if __name__=='__main__':unittest.main()
