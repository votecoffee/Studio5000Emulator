"""Read chunks keep framing, integrity, offsets and execution separate."""
from dataclasses import replace
import base64
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from logixlab import read_transport as rt,signed_messages as sm
from tools.inspect_cip_capture import summarize
from tools.analyze_native_transfer import analyze
from tools.upload_inventory import logical_path
from test_capture_inspection import packet

KEY=bytes(range(20))
PATH=logical_path(0x6d,7,program=11)
INNER=bytes((0x5d,len(PATH)//2))+PATH+struct.pack('<II',1,9)


def frame(sequence=1,*,position=0,data=b'source',total=None,final=True):
    request=rt.ReadRequest(sequence,1 if position else 0x101,position,b'' if position else INNER)
    raw=rt.encode_request(request,KEY)
    reply=rt.encode_response(request,data,KEY,total_bytes=(len(data) if total is None else total) if not position else None,final=final)
    return request,raw,reply


class ReadTransportTests(unittest.TestCase):
    def test_complete_empty_and_fragmented_reads_preserve_exact_bytes(self):
        for data in (b'',b'\1'+struct.pack('<III',13,13,0),bytes(range(255))):
            q,raw,reply=frame(data=data)
            self.assertEqual(sm.parse_request(raw),q)
            a=sm.parse_response(reply,q);self.assertEqual(a.data,data)
            self.assertEqual(sm.verify_request(raw,KEY,expected_sequence=1),q)
            self.assertEqual(sm.verify_response(reply,KEY,request=q),a)
            assembly=rt.Assembly();self.assertTrue(assembly.accept(q,a));self.assertEqual(assembly.value(),data)
        data=bytes(range(251))*6;assembly=rt.Assembly()
        for sequence,start in enumerate(range(0,len(data),462),1):
            chunk=data[start:start+462];q,raw,reply=frame(sequence,position=start,data=chunk,total=len(data),final=start+len(chunk)==len(data))
            assembly.accept(q,rt.verify_response(reply,KEY,request=q))
        self.assertEqual(assembly.value(),data);self.assertEqual(assembly.frames,4)

    def test_macs_cover_headers_payload_counter_and_context(self):
        q,raw,reply=frame()
        for message,verify in ((raw,lambda value:sm.verify_request(value,KEY,expected_sequence=1)),(reply,lambda value:sm.verify_response(value,KEY,request=q))):
            for offset in range(len(message)):
                changed=message[:offset]+bytes((message[offset]^1,))+message[offset+1:]
                with self.assertRaises(sm.EnvelopeError):verify(changed)
        with self.assertRaises(sm.EnvelopeError):rt.verify_request(raw,KEY,expected_sequence=2)
        with self.assertRaises(sm.EnvelopeError):rt.verify_response(reply,bytes(20),request=q)
        for key in (None,b'',bytes(19),bytearray(20)):
            with self.assertRaises(sm.EnvelopeError):rt.verify_request(raw,key)

    def test_malformed_truncated_and_mismatched_frames_are_rejected(self):
        q,raw,reply=frame()
        for end in range(len(raw)):
            with self.assertRaises(sm.EnvelopeError):rt.verify_request(raw[:end],KEY)
        for end in range(len(reply)):
            with self.assertRaises(sm.EnvelopeError):rt.parse_response(reply[:end],q)
        for request in (replace(q,service=0x39),replace(q,sequence=True),replace(q,sequence=-1),replace(q,position=1),
                        replace(q,container_format=0x301),replace(q,container_format=1,inner=b''),replace(q,inner=b'\1\xff')):
            with self.assertRaises(sm.EnvelopeError):rt.encode_request(request,KEY)
        for offset,word in ((4,1),(4,0x201),(8,7)):
            changed=bytearray(reply);struct.pack_into('<I',changed,offset,word)
            with self.assertRaises(sm.EnvelopeError):rt.parse_response(bytes(changed),q)
        for response in (reply+b'x',reply[:2]+b'\6'+reply[3:]):
            with self.assertRaises(sm.EnvelopeError):rt.parse_response(response,q)
        with self.assertRaises(sm.EnvelopeError):rt.encode_response(q,b'a',KEY,total_bytes=2)
        with self.assertRaises(sm.EnvelopeError):rt.encode_response(q,b'a',KEY,total_bytes=1,final=False)

    def test_assembly_rejects_gaps_overlap_replay_wrong_completion_and_bounds_atomically(self):
        q,raw,reply=frame(data=b'abc',total=8,final=False);first=rt.parse_response(reply,q)
        assembly=rt.Assembly();assembly.accept(q,first)
        with self.assertRaises(sm.EnvelopeError):assembly.value()
        for sequence,position,data,final in ((2,4,b'1234',True),(2,2,b'123456',True),(1,3,b'12345',True),
                (2,3,b'1234',True),(2,3,b'123456',True),(2,3,b'12345',False)):
            request=rt.ReadRequest(sequence,1,position);response=rt.ReadChunk(sequence,0x201 if final else 1,position,data)
            with self.assertRaises(sm.EnvelopeError):assembly.accept(request,response)
            self.assertEqual((assembly.frames,len(assembly._data)),(1,3))
        with self.assertRaises(sm.EnvelopeError):assembly.accept(q,first)
        tail=rt.ReadRequest(2,1,3);last=rt.ReadChunk(2,0x201,3,b'12345')
        self.assertTrue(assembly.accept(tail,last));self.assertEqual(assembly.value(),b'abc12345')
        with self.assertRaises(sm.EnvelopeError):assembly.accept(tail,last)
        missing=rt.Assembly()
        with self.assertRaises(sm.EnvelopeError):missing.accept(tail,last)
        with self.assertRaises(sm.EnvelopeError):rt.Assembly(max_bytes=7).accept(q,first)
        limited=rt.Assembly(max_frames=1);limited.accept(q,first)
        with self.assertRaises(sm.EnvelopeError):limited.accept(tail,last)
        assembly.clear();self.assertFalse(assembly.complete);self.assertEqual(assembly.frames,0)
        for bounds in ({'max_bytes':True},{'max_bytes':0},{'max_frames':0},{'max_frames':rt.MAX_FRAMES+1}):
            with self.assertRaises(sm.EnvelopeError):rt.Assembly(**bounds)

    def test_capture_and_transfer_reports_retain_scope_offsets_hashes_without_fake_cip_status(self):
        q,raw,reply=frame(data=b'private source')
        report=summarize([packet(1,raw),packet(2,reply,1)])
        exchange=report['exchanges'][0];request=exchange['request']['signed_envelope'];response=exchange['response']['signed_envelope']
        self.assertEqual(request['first_request']['object_path'][0]['instance'],11)
        self.assertEqual(response['chunk_sha256'],hashlib.sha256(b'private source').hexdigest())
        self.assertNotIn('inner',response);self.assertNotIn('chunk_hex',json.dumps(report));self.assertNotIn('private source',json.dumps(report))
        trace=analyze({'events':[]},{'events':[dict(kind='cip',request_hex=raw.hex(),response_hex=reply.hex())]},'upload')
        self.assertTrue(trace['analysis_complete']);self.assertEqual(trace['requests_observed'],0)
        self.assertEqual(trace['read_transport_frames_observed'],1);self.assertEqual(trace['read_transport_bytes'],14)
        self.assertNotIn('status',trace['read_transport_frames'][0])
        extended=summarize([packet(1,raw),packet(2,reply,1)],include_payloads=True)
        self.assertIn('chunk_hex',extended['exchanges'][0]['response']['signed_envelope'])

    def test_detached_codec_adds_no_live_route_or_sequence_consumption(self):
        from logixlab.ethernetip import Endpoint,Session
        from logixlab.native_session import NativeSession
        from logixlab.server import Application
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder)
            source=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes()
            app.command('load',dict(name='demo.L5X',content=base64.b64encode(source).decode()))
            endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True)
            session=Session();session.handle=1;session.native=NativeSession()
            session.native.key=KEY;session.native.sequence=1;session.native.stage='bound';session.native.deadline=time.monotonic()+300
            before=app.state()
            try:
                for inner in (INNER,bytes.fromhex('4d039105537065656400c400010001000000')):
                    request=rt.ReadRequest(1,0x101,0,inner)
                    reply=endpoint.router.handle(rt.encode_request(request,KEY),session)
                    self.assertNotEqual(reply[2],0);self.assertEqual(session.native.sequence,1)
                for key in ('tags','scan','ms','routines','controller'):self.assertEqual(app.state()[key],before[key])
            finally:app.close()


if __name__=='__main__':unittest.main()
