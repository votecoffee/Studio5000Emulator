"""Replay a saved download offline and compare its image with a saved trace.

Never opens a network connection, invokes the SDK, or dispatches native requests.
Trace envelopes are parsed structurally; no session-key/MAC claim is made.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab import device_payload,signed_messages
from logixlab.download_image import DownloadImage
from logixlab.template_staging import TemplateStaging
from logixlab.diagnostic_staging import DiagnosticStaging
from logixlab.object_staging import ObjectStaging
from logixlab.native_types import NativeTypes
from logixlab.resilient_transport import DEVICE_HEADER
from logixlab.ethernetip import decode_path,CIPError
from logixlab.model import ModelError

MAX_SOURCE_BYTES=100_000_000
MAX_TRACE_BYTES=16*1024*1024
MAX_TRACE_EVENTS=20000
MAX_RTO_EXCHANGES=64


def _hash(raw):return hashlib.sha256(raw).hexdigest()


def _read(path,limit):
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if not 1<=len(raw)<=limit:raise ValueError('Input size is outside the replay limit')
    return raw


def _digest(path):
    if not 1<=path.stat().st_size<=MAX_SOURCE_BYTES:raise ValueError('Source size is outside the replay limit')
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def replay(raw,expected_bytes,native_types,*,include_records=False):
    """Rebuild actual temporary objects and compare all retained outcomes."""
    batch=device_payload.decode(raw,expected_bytes)
    templates=TemplateStaging.from_batch(batch);diagnostics=DiagnosticStaging.from_batch(batch)
    objects=ObjectStaging.from_batch(batch,templates.templates)
    verified=native_types.verify(templates.templates)
    image=DownloadImage.prepare(batch,templates,diagnostics,objects,native_types,verified)
    if image.description()['status']!='prepared':raise ValueError('Source-bound download image is unavailable')
    request_matches=resource_matches=historical=0;details=[];failures=[]
    for start in range(0,len(batch),64):
        for result in image.preparation_results(start,64,image.source):
            request=batch[result.ordinal]
            request_match=(result.request_bytes==len(request.request) and result.request_sha256==_hash(request.request)
                           and result.service==request.service
                           and result.scopes==tuple((s.class_id,s.instance) for s in request.scopes))
            request_matches+=request_match
            readback=image.read_preparation_effect(result.ordinal,image.source)
            if readback.historical_transition:historical+=readback.matches
            else:resource_matches+=readback.matches
            if not request_match or not readback.matches:failures.append(result.ordinal)
            if include_records:details.append({**asdict(readback),'effect_kind':type(result.effect).__name__,
                                              'request_matches':request_match})
    report={'status':'replayed' if not failures else 'mismatch','offline_only':True,
            'payload_sha256':_hash(raw),'encoded_bytes':len(raw),'expanded_bytes':expected_bytes,
            'source_acd_sha256':image.source.acd_sha256,'source_l5x_sha256':image.source.l5x_sha256,
            'source_type_verification':verified,'image':image.description(),
            'request_fingerprints_matched':request_matches,'resource_effects_matched':resource_matches,
            'historical_transitions_matched':historical,'mismatched_ordinals':failures,
            'native_execution_performed':False,'vendor_result_encoding':'unresolved',
            'native_controller_equivalence':'NOT ASSESSED'}
    if include_records:report['operation_readbacks']=details
    return image,report


def _event_hex(event,key):
    value=event.get(key,'')
    if not isinstance(value,str) or len(value)>2*signed_messages.MAX_MESSAGE:
        raise ValueError('Invalid or oversized captured message')
    try:return bytes.fromhex(value)
    except ValueError as error:raise ValueError('Invalid captured message encoding') from error


def compare_trace(trace,raw,image):
    """Compare real bytes with captured prefixes and preparation aggregates.

    A truncated trace proves matching prefixes only, never uncaptured bytes.
    Matching does not authenticate the trace or establish a vendor result format.
    """
    if not isinstance(trace,dict) or not isinstance(trace.get('events'),list) or len(trace['events'])>MAX_TRACE_EVENTS:
        raise ValueError('Invalid or oversized replay trace')
    events=trace['events']
    if any(not isinstance(e,dict) for e in events):raise ValueError('Invalid replay trace event')
    preparations=[i for i,e in enumerate(events) if e.get('kind')=='native_download_image_preparation']
    if len(preparations)!=1:raise ValueError('Trace must contain exactly one image preparation event')
    end=preparations[0];actual=events[end];expected=image.description();mismatches=[]
    correlation=trace.get('native_correlation')
    bound=(isinstance(correlation,dict)
           and correlation.get('source_acd_sha256')==image.source.acd_sha256
           and correlation.get('source_l5x_sha256')==image.source.l5x_sha256
           and trace.get('source_l5x_sha256')==image.source.l5x_sha256)
    if not bound:mismatches.append('source_binding')
    fields=('status','source_bound','records_prepared','record_sha256','tables_allocated','templates_retained',
            'diagnostics_retained','programs_retained','routines_retained','storage_bytes','symbols_linked',
            'symbols_unresolved','initial_values_applied','compiled_routines_installed','active_catalog_replaced',
            'native_execution_supported','commit')
    for field in fields:
        if actual.get(field)!=expected[field]:mismatches.append('preparation_'+field)
    if actual.get('preparation_started') is not True:mismatches.append('preparation_not_started')
    if actual.get('preparation_results')!=expected['preparation_results']:mismatches.append('preparation_results')
    first=next((i for i in range(end-1,-1,-1) if events[i].get('kind')=='native_transport_fragment'
                and events[i].get('fragments')==1),0)
    progress=[e for e in events[first:end] if e.get('kind')=='native_transport_fragment']
    captured=[]
    for event in events[first:end]:
        if event.get('kind')!='cip':continue
        request=_event_hex(event,'request_hex')
        if request.startswith(bytes.fromhex('390220022401')) and len(request)>=14:
            word,position=struct.unpack_from('<II',request,6)
            if word in signed_messages.FRAGMENT_FORMATS:captured.append((event,request,word,position))
    if len(progress)!=len(captured):mismatches.append('fragment_event_count')
    fragments=[];previous=0;prefix_bytes=0
    for ordinal,(event,request,word,position) in enumerate(captured,1):
        matching=True;meta=progress[ordinal-1] if ordinal<=len(progress) else {}
        received=meta.get('received_bytes')
        if type(received) is not int or not previous<received<=len(raw):
            matching=False;received=previous
        first_fragment=ordinal==1;last=received==len(raw)
        if (word!=(0x101 if first_fragment else 0x201 if last else 1)
                or position!=(len(raw) if first_fragment else previous)
                or meta.get('position')!=position or meta.get('container_format')!=word
                or meta.get('total_bytes')!=len(raw) or meta.get('fragments')!=ordinal
                or meta.get('complete') is not last):matching=False
        truncated=event.get('truncated') is True
        if truncated:prefix=request[14:]
        else:
            try:parsed=signed_messages.parse_request(request)
            except signed_messages.EnvelopeError as error:raise ValueError('Malformed complete captured fragment') from error
            if not isinstance(parsed,signed_messages.FragmentEnvelope):raise ValueError('Captured message is not a fragment')
            prefix=parsed.fragment
        if first_fragment:
            if not prefix.startswith(DEVICE_HEADER):matching=False;prefix=b''
            else:prefix=prefix[len(DEVICE_HEADER):]
        if not prefix or len(prefix)>received-previous or raw[previous:previous+len(prefix)]!=prefix:matching=False
        if not truncated and len(prefix)!=received-previous:matching=False
        prefix_bytes+=len(prefix)
        fragments.append({'ordinal':ordinal,'offset':previous,'end':received,'captured_payload_bytes':len(prefix),
                          'capture_truncated':truncated,'matches':matching})
        if not matching:mismatches.append('fragment_'+str(ordinal))
        previous=received
    if not captured or previous!=len(raw):mismatches.append('incomplete_fragment_chain')
    rto=[]
    for event in events[end:]:
        if event.get('kind')!='cip' or event.get('truncated'):continue
        request=_event_hex(event,'request_hex');answer=_event_hex(event,'response_hex')
        if not request or request[0] not in (0x36,0x37,0x38,0x39):continue
        try:
            outer=signed_messages.parse_request(request)
            if isinstance(outer,signed_messages.FragmentEnvelope):continue
            response=signed_messages.parse_response(answer,outer)
            pairs=zip(outer.children,response.children) if isinstance(outer,signed_messages.BatchEnvelope) else ((outer.inner,response.inner),)
            for inner,reply in pairs:
                path=decode_path(inner[2:2+inner[1]*2])
                if path.class_id!=0x412:continue
                if len(rto)>=MAX_RTO_EXCHANGES:raise ValueError('Captured result exchange limit')
                rto.append({'service':inner[0],'request_bytes':len(inner),'request_sha256':_hash(inner),
                            'request_payload_bytes':len(inner)-2-inner[1]*2,'observed_status':reply[2],
                            'response_bytes':len(reply),'response_payload_bytes':len(reply)-4-2*reply[3],
                            'response_sha256':_hash(reply)})
        except (signed_messages.EnvelopeError,CIPError,IndexError) as error:
            raise ValueError('Malformed captured result exchange') from error
        if rto and rto[-1]['service']==9:break
    queries=[e for e in rto if e['service']==0x4D]
    return {'status':'matched' if not mismatches else 'mismatch','source_binding_matches':bound,
            'preparation_receipt_matches':not any(m.startswith('preparation_') for m in mismatches),
            'mismatches':mismatches,'fragments':fragments,'captured_payload_prefix_bytes':prefix_bytes,
            'encoded_payload_bytes':len(raw),'uncaptured_payload_bytes':max(0,len(raw)-prefix_bytes),
            'fragment_comparison_scope':'Captured payload prefixes and complete progress ranges',
            'rto_exchanges':rto,'result_queries_observed':len(queries),
            'mac_verification':'NOT PERFORMED','vendor_result_encoding':'unresolved'}


def run(payload,out,expected_bytes,source_acd,source_l5x,*,trace=None,include_records=False):
    payload=Path(payload).resolve(strict=True);sources=[Path(p).resolve(strict=True) for p in (source_acd,source_l5x)]
    trace_path=Path(trace).resolve(strict=True) if trace is not None else None
    out=Path(out).resolve();inputs=[payload,*sources,*([trace_path] if trace_path else [])]
    if out.exists():raise ValueError('Replay output must be a new file')
    if any(out==p for p in inputs):raise ValueError('Replay output must not overwrite an input')
    source_hashes=[_digest(p) for p in sources];raw=_read(payload,device_payload.MAX_ENCODED_BYTES);payload_hash=_hash(raw)
    trace_raw=_read(trace_path,MAX_TRACE_BYTES) if trace_path else None
    native=NativeTypes.from_acd(sources[0],source_hashes[1])
    if native.source_acd_sha256!=source_hashes[0]:raise ValueError('Source ACD changed during replay')
    image,report=replay(raw,expected_bytes,native,include_records=include_records)
    if trace_raw is not None:
        report['capture_comparison']=compare_trace(json.loads(trace_raw),raw,image)
        report['trace_sha256']=_hash(trace_raw)
        if report['capture_comparison']['status']=='mismatch':report['status']='mismatch'
    if source_hashes!=[_digest(p) for p in sources]:raise ValueError('Source changed during replay')
    if _hash(_read(payload,device_payload.MAX_ENCODED_BYTES))!=payload_hash:raise ValueError('Payload changed during replay')
    if trace_path and _hash(_read(trace_path,MAX_TRACE_BYTES))!=_hash(trace_raw):raise ValueError('Trace changed during replay')
    report.update(inputs_unchanged=True,detailed_results_included=include_records)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload',required=True,type=Path)
    parser.add_argument('--expanded-bytes',required=True,type=int)
    parser.add_argument('--source-acd',required=True,type=Path)
    parser.add_argument('--source-l5x',required=True,type=Path)
    parser.add_argument('--trace',type=Path,help='Saved emulator trace; no connection is made')
    parser.add_argument('--out',required=True,type=Path,help='New report in private local storage')
    parser.add_argument('--include-records',action='store_true',help='Include private object scopes and typed per-record details')
    args=parser.parse_args()
    try:report=run(args.payload,args.out,args.expanded_bytes,args.source_acd,args.source_l5x,
                   trace=args.trace,include_records=args.include_records)
    except (ValueError,OSError,ModelError) as error:parser.exit(1,str(error)+'\n')
    print(json.dumps({k:report[k] for k in ('status','offline_only','request_fingerprints_matched','vendor_result_encoding')}))
    if report['status']=='mismatch':parser.exit(1)


if __name__=='__main__':main()
