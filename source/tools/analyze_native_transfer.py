"""Summarize two saved emulator trace checkpoints; no SDK or network access.

Only signed Message Router envelopes are counted, avoiding duplicate inner CIP
trace events. Framing is checked without claiming MAC verification or inferring
the cause of a native client's higher-level failure. Payloads stay private.
"""
from collections import Counter,deque
import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab import signed_messages as sm
from logixlab.ethernetip import CIPError,decode_path

MAX_EVENTS=2048
MAX_REQUESTS=4096
MAX_REPORT_ROWS=64
MAX_FILE_BYTES=32*1024*1024
PHASES={'native_transport_inspection','native_download_image_preparation','native_download_result_query'}
PHASE_FIELDS=('record_count','expanded_bytes','records_prepared','templates_retained','diagnostics_retained',
              'programs_retained','routines_retained','tables_allocated','storage_bytes','preparation_started','commit')


def event_interval(before,after):
    """Find the retained checkpoint marker without comparing host/guest clocks."""
    previous=before.get('events');events=after.get('events')
    if (not isinstance(previous,list) or not isinstance(events,list)
            or len(previous)>MAX_EVENTS or len(events)>MAX_EVENTS
            or any(not isinstance(row,dict) for row in previous+events)):
        raise ValueError('Invalid or oversized trace event list')
    if not previous:
        # An empty starting checkpoint has no marker. Capture loss during the
        # call must still prevent a retained suffix from looking complete.
        old=before.get('trace_capture',{}).get('dropped_events',0)
        new=after.get('trace_capture',{}).get('dropped_events',0)
        if type(old) is not int or type(new) is not int or old<0 or new<old:
            raise ValueError('Invalid trace retention counters')
        return ([], 'checkpoint_not_retained') if new>old else (events,None)
    positions=[i for i,row in enumerate(events) if row==previous[-1]]
    if len(positions)!=1:return [],'checkpoint_not_retained' if not positions else 'checkpoint_ambiguous'
    return events[positions[0]+1:],None


def request_row(child,result,sequence,ordinal):
    end=2+2*child[1];path=decode_path(child[2:end]);start=4+2*result[3]
    row=dict(ordinal=ordinal,sequence=sequence,service=child[0],class_id=path.class_id,
        instance=path.instance,attribute=path.attribute,program_instance=path.program_instance,
        io_map_instance=path.io_map_instance,controller_instance=path.controller_instance,
        symbolic=bool(path.symbols),status=result[2],request_payload_bytes=len(child)-end,
        response_payload_bytes=len(result)-start,
        additional_status=list(struct.unpack('<'+'H'*result[3],result[4:start])))
    if child[0]==3 and path.attribute is None:
        data=child[end:]
        if len(data)>=2:
            count=struct.unpack_from('<H',data)[0];row['attribute_list_count']=count
            if 1<=count<=32 and len(data)==2+2*count:
                row['requested_attributes']=list(struct.unpack_from('<'+'H'*count,data,2))
    return row


def gap_delta(before,after):
    """Endpoint-wide counts; these do not attribute gaps to one native client."""
    fields=('generation','class_id','instance','program_instance','io_map_instance','controller_instance','service')
    def key(row):return tuple(row.get(k) for k in fields)+(tuple(a['id'] for a in row.get('attributes',[])),)
    for snapshot in (before,after):
        rows=snapshot.get('attribute_gaps',[])
        if (not isinstance(rows,list) or len(rows)>MAX_REPORT_ROWS or any(not isinstance(row,dict)
                or not isinstance(row.get('attributes',[]),list) or len(row.get('attributes',[]))>32
                or any(not isinstance(a,dict) or type(a.get('id')) is not int for a in row.get('attributes',[]))
                or type(row.get('count',0)) is not int or row.get('count',0)<0 for row in rows)):
            raise ValueError('Invalid attribute-gap counters')
    old={key(row):row.get('count',0) for row in before.get('attribute_gaps',[])}
    rows=[]
    for row in after.get('attribute_gaps',[]):
        count=row.get('count',0)-old.get(key(row),0)
        if count>0:
            rows.append({**{k:row.get(k) for k in fields},'attributes':[a['id'] for a in row.get('attributes',[])],
                         'interval_count':count})
    return rows[:MAX_REPORT_ROWS],len(rows)>MAX_REPORT_ROWS


def analyze(before,after,operation,report=None):
    if operation not in ('upload','download'):raise ValueError('Expected upload or download')
    base=dict(operation=operation,correlation='saved_emulator_trace_checkpoints',
        mac_verification='NOT PERFORMED',failure_cause='NOT INFERRED',payloads_exposed=False)
    method=operation.capitalize()+'Async'
    steps=[row for row in (report or {}).get('steps',[]) if row.get('method')==method]
    if len(steps)==1:base.update(sdk_method=method,sdk_status=steps[0].get('status'))
    events,error=event_interval(before,after)
    if error:return {**base,'status':error,'analysis_complete':False,'requests_observed':0}
    failures=[];wrappers=[];tail=deque(maxlen=16);phases=[];objects=Counter()
    matched=envelopes=fragments=fragment_bytes=unparsed=failed=wrapper_count=phase_count=0
    limited=False
    for event in events:
        if event.get('kind') in PHASES:
            phase_count+=1
            if len(phases)<16:
                fields={k:event[k] for k in PHASE_FIELDS if k in event and
                        (type(event[k]) is bool if k in ('preparation_started','commit')
                         else type(event[k]) is int and 0<=event[k]<=0xFFFFFFFF)}
                phases.append({'kind':event['kind'],**fields})
        if event.get('kind')!='cip':continue
        try:
            text=event.get('request_hex','')
            if not isinstance(text,str) or len(text)>2*sm.MAX_MESSAGE:raise ValueError('Request extent')
            raw=bytes.fromhex(text)
            if not raw or raw[0] not in (0x36,0x37,0x38,0x39):continue
            if event.get('truncated'):raise ValueError('Truncated event')
            text=event.get('response_hex','')
            if not isinstance(text,str) or len(text)>2*sm.MAX_MESSAGE:raise ValueError('Response extent')
            response=bytes.fromhex(text);request=sm.parse_request(raw)
            if (len(response)>=4 and response[0]==(raw[0]|0x80) and response[1]==0
                    and response[2]!=0 and len(response)==4+2*response[3]):
                wrapper_count+=1;envelopes+=1
                if len(wrappers)<MAX_REPORT_ROWS:
                    wrappers.append(dict(service=raw[0],status=response[2],sequence=request.sequence,
                        additional_status=list(struct.unpack('<'+'H'*response[3],response[4:]))))
                continue
            reply=sm.parse_response(response,request);envelopes+=1
            if isinstance(request,sm.FragmentEnvelope):
                fragments+=1;fragment_bytes+=len(request.fragment);continue
            children=(tuple(zip(request.children,reply.children)) if isinstance(request,sm.BatchEnvelope)
                      else ((request.inner,reply.inner),))
            # Decode a whole envelope before publishing any of its child rows.
            rows=[request_row(child,result,request.sequence,matched+i+1) for i,(child,result) in enumerate(children)]
            if matched+len(rows)>MAX_REQUESTS:limited=True;break
            for row in rows:
                matched+=1;tail.append(row)
                key=tuple(row[k] for k in ('class_id','instance','program_instance','io_map_instance','controller_instance','symbolic'))
                objects[key]+=1
                if row['status']:
                    failed+=1
                    if len(failures)<MAX_REPORT_ROWS:failures.append(row)
        except (ValueError,IndexError,KeyError,TypeError,CIPError,struct.error):unparsed+=1
    gaps,gaps_truncated=gap_delta(before,after)
    object_rows=[dict(zip(('class_id','instance','program_instance','io_map_instance','controller_instance','symbolic'),key),requests=count)
                 for key,count in objects.items()]
    return {**base,'status':'observed' if envelopes else 'no_complete_signed_events',
        'analysis_complete':not (unparsed or limited),'signed_envelopes':envelopes,'requests_observed':matched,
        'fragment_acknowledgements':fragments,'fragment_bytes':fragment_bytes,'unparsed_events':unparsed,
        'request_limit_reached':limited,'failed_request_count':failed,'failed_requests':failures,
        'failures_truncated':failed>MAX_REPORT_ROWS,'last_requests':list(tail),
        'wrapper_rejections':wrappers,'wrapper_rejections_truncated':wrapper_count>MAX_REPORT_ROWS,
        'objects':object_rows[:MAX_REPORT_ROWS],'objects_truncated':len(object_rows)>MAX_REPORT_ROWS,
        'preparation_events':phases,'preparation_events_truncated':phase_count>16,
        'endpoint_attribute_gaps':gaps,'attribute_gaps_truncated':gaps_truncated,
        'attribute_gap_scope':'all endpoint readers between checkpoints'}


def read_json(path):
    path=Path(path)
    if not 1<=path.stat().st_size<=MAX_FILE_BYTES:raise ValueError('JSON file size limit')
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value,dict):raise ValueError('Expected a JSON object')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',required=True);p.add_argument('--after',required=True)
    p.add_argument('--operation',required=True,choices=('upload','download'))
    p.add_argument('--sdk-result');p.add_argument('--output',required=True)
    args=p.parse_args()
    result=analyze(read_json(args.before),read_json(args.after),args.operation,
                   read_json(args.sdk_result) if args.sdk_result else None)
    with Path(args.output).open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:result.get(k) for k in ('operation','status','analysis_complete','requests_observed','failed_request_count')},indent=2))


if __name__=='__main__':main()
