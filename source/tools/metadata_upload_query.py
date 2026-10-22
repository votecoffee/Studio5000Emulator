"""Inspect saved v35 Metadata Definition query streams without contacting a PLC.

Input is an inspect_cip_capture JSON report saved with --include-payloads.
Output contains bounded aggregate inventories, never metadata values or IDs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab import metadata_query as metadata
from logixlab.ethernetip import decode_path,CIPError

MAX_INPUT_BYTES=128*1024*1024
MAX_EXCHANGES=250000
MAX_STREAMS=64


def frame(request,response):
    if (not isinstance(request,bytes) or not isinstance(response,bytes) or not 6<=len(request)<=64
            or not 4<=len(response)<=metadata.MAX_BYTES+12 or request[0]!=0x53):
        raise ValueError('Unsupported metadata query message extent or service')
    end=2+2*request[1]
    if end>len(request):raise ValueError('Truncated metadata query path')
    try:path=decode_path(request[2:end])
    except CIPError as error:raise ValueError('Invalid metadata query path') from error
    if (path.class_id!=0x349 or path.instance!=0 or path.attribute is not None or path.symbols
            or any(getattr(path,key) is not None for key in
                ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
        raise ValueError('Unsupported metadata query scope')
    query=metadata.parse_query(request[end:])
    if response[0]!=0xD3 or response[1]!=0 or response[3]!=0:
        raise ValueError('Unsupported metadata query response header')
    if response[2]:
        if len(response)!=4:raise ValueError('Unexpected rejected metadata query data')
        return query,None,response[2]
    return query,metadata.parse_chunk(response[4:],query),0


def describe(request,response):
    query,chunk,status=frame(request,response)
    return dict(profile='metadata-query-v35-observed',selection=query.selection,request_format=query.format,
        request_position=query.position,status=status,response_format=chunk.format if chunk else None,
        response_position=chunk.position if chunk else None,chunk_bytes=len(chunk.data) if chunk else 0,
        chunk_sha256=hashlib.sha256(chunk.data).hexdigest() if chunk else None,
        complete=bool(chunk and chunk.format in (0x301,0x201)),
        source_binding_verified=False,mac_verified=False,native_acceptance_verified=False,payloads_exposed=False)


def replay(exchanges):
    """Decode serial streams; missing/reordered/failed fragments cannot be complete."""
    streams=[];stream_count=complete_count=frame_count=errors=failed=incomplete=record_count=0
    active=None;poisoned=False
    def retain(assembly,*,abandoned=False):
        nonlocal stream_count,complete_count,errors,incomplete,record_count
        row=assembly.description();stream_count+=1
        if abandoned or not assembly.complete:
            incomplete+=1;row['record_structure']='INCOMPLETE'
        else:
            try:summary=metadata.inventory(metadata.records(assembly.data()))
            except ValueError:
                errors+=1;row['record_structure']='UNSUPPORTED OR MALFORMED'
            else:
                complete_count+=1;record_count+=summary['records'];row['inventory']=summary
        if len(streams)<MAX_STREAMS:streams.append(row)
    for ordinal,(request,response) in enumerate(exchanges):
        if ordinal>=MAX_EXCHANGES:raise ValueError('Metadata query exchange limit')
        frame_count+=1
        try:
            query,chunk,status=frame(request,response)
            if query.format==0x101:
                if active is not None:retain(active,abandoned=True)
                active=None;poisoned=False
            if status:
                failed+=1
                if active is not None:retain(active,abandoned=True);active=None
                poisoned=True;continue
            if poisoned:raise ValueError('Metadata query follows an invalid fragment')
            if active is None:active=metadata.Assembly()
            active.accept(query,chunk)
            if active.complete:retain(active);active=None
        except ValueError:
            errors+=1;poisoned=True
            if active is not None:retain(active,abandoned=True);active=None
    if active is not None:retain(active,abandoned=True)
    return dict(profile='metadata-query-v35-observed',offline_only=True,frames=frame_count,
        analysis_scope='decoded-service-0x53-exchanges',
        streams_observed=stream_count,complete_streams=complete_count,decoded_records=record_count,
        framing_or_record_errors=errors,failed_queries=failed,incomplete_streams=incomplete,
        analysis_complete=bool(frame_count) and not (errors or failed or incomplete),
        streams=streams,streams_truncated=stream_count>MAX_STREAMS,source_binding_verified=False,
        mac_verified=False,native_acceptance_verified=False,live_dispatch_added=False,payloads_exposed=False)


def capture_exchanges(report):
    if (not isinstance(report,dict) or not isinstance(report.get('exchanges'),list)
            or len(report['exchanges'])>MAX_EXCHANGES):raise ValueError('Invalid metadata capture report')
    visited=0
    def relevant(request,depth):
        nonlocal visited
        visited+=1
        if visited>MAX_EXCHANGES:raise ValueError('Metadata capture exchange limit')
        # Select by the decoded request before inspecting an unrelated reply.
        # An unknown request envelope could hide a query and remains an error.
        if not isinstance(request,dict):raise ValueError('Invalid captured request')
        envelope=request.get('signed_envelope')
        if envelope is not None:
            if depth>=2 or not isinstance(envelope,dict) or envelope.get('structure')=='UNSUPPORTED OR MALFORMED':
                raise ValueError('Unsupported captured request envelope')
            if 'inner' in envelope:return relevant(envelope['inner'],depth+1)
            if 'children' in envelope:
                children=envelope['children']
                if not isinstance(children,list) or len(children)>MAX_EXCHANGES:raise ValueError('Invalid captured batch')
                return any([relevant(child,depth+1) for child in children])
            if envelope.get('read_transport') is True or 'fragment_bytes' in envelope:return False
            raise ValueError('Unsupported captured request envelope shape')
        scopes=request.get('object_path',[request])
        if not isinstance(scopes,list) or not scopes or not isinstance(scopes[-1],dict):
            raise ValueError('Invalid captured object path')
        return request.get('service')==0x53 and scopes[-1].get('class_id')==0x349
    def leaf(request,response,depth=0):
        if not relevant(request,depth):return
        if not isinstance(request,dict) or not isinstance(response,dict):raise ValueError('Invalid captured exchange')
        envelope=request.get('signed_envelope')
        if envelope is not None:
            if depth>=2 or not isinstance(envelope,dict) or not isinstance(response.get('signed_envelope'),dict):
                raise ValueError('Unsupported captured signed envelope')
            answer=response['signed_envelope']
            if envelope.get('structure')=='UNSUPPORTED OR MALFORMED' or answer.get('structure')=='UNSUPPORTED OR MALFORMED':
                raise ValueError('Malformed captured signed envelope')
            if 'inner' in envelope:
                if 'inner' not in answer:raise ValueError('Missing captured signed reply')
                yield from leaf(envelope['inner'],answer['inner'],depth+1)
            elif 'children' in envelope:
                children=envelope['children'];replies=answer.get('children')
                if (not isinstance(children,list) or not isinstance(replies,list) or len(children)!=len(replies)
                        or len(children)>MAX_EXCHANGES):raise ValueError('Invalid captured signed batch')
                for a,b in zip(children,replies):yield from leaf(a,b,depth+1)
            elif not (envelope.get('read_transport') is True or 'fragment_bytes' in envelope):
                raise ValueError('Unsupported captured signed envelope shape')
            # Read/fragment wrappers contain no paired decoded query exchange.
            return
        scopes=request.get('object_path',[request])
        if not isinstance(scopes,list) or not scopes or not isinstance(scopes[-1],dict):
            raise ValueError('Invalid captured object path')
        target=scopes[-1]
        if request.get('service')!=0x53 or target.get('class_id')!=0x349:return
        raw=[]
        for item in (request,response):
            text=item.get('message_hex')
            if not isinstance(text,str) or len(text)>2*(metadata.MAX_BYTES+12):
                raise ValueError('Metadata capture requires complete bounded payloads')
            try:raw.append(bytes.fromhex(text))
            except ValueError as error:raise ValueError('Invalid captured metadata encoding') from error
        yield tuple(raw)
    for row in report['exchanges']:
        if not isinstance(row,dict):raise ValueError('Invalid captured exchange row')
        yield from leaf(row.get('request'),row.get('response'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();source=Path(args.input);output=Path(args.output)
    try:
        with source.open('rb') as stream:raw=stream.read(MAX_INPUT_BYTES+1)
        if not 1<=len(raw)<=MAX_INPUT_BYTES:raise ValueError('Metadata capture input size limit')
        report=replay(capture_exchanges(json.loads(raw)))
        report['input_sha256']=hashlib.sha256(raw).hexdigest()
        with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        print('Metadata query inspection failed; input must contain complete supported exchanges.',file=sys.stderr)
        return 2
    print(json.dumps({k:report[k] for k in ('frames','complete_streams','decoded_records','analysis_complete')}))
    return 0 if report['analysis_complete'] else 1


if __name__=='__main__':raise SystemExit(main())
