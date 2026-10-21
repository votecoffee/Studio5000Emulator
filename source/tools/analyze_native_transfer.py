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
from tools.collection_inventory import instance_supported as collection_instance, scope_supported as collection_scope, CollectionError, decode_attribute_list
from tools.inspect_cip_capture import describe_path

MAX_EVENTS=2048
MAX_REQUESTS=4096
MAX_REPORT_ROWS=64
MAX_FILE_BYTES=32*1024*1024
PHASES={'native_transport_inspection','native_download_image_preparation','native_download_result_query'}
PHASE_FIELDS=('record_count','expanded_bytes','records_prepared','templates_retained','diagnostics_retained',
              'programs_retained','routines_retained','tables_allocated','storage_bytes','preparation_started','commit')
VERIFICATIONS={
    'native_source_type_verification':(
        ('types_matched','members_matched','types_unavailable','template_ids_matched','template_ids_unresolved'),
        ('member_locations_verified','template_identities_verified','storage_mapping_supported','signature_verified',
         'definitions_exposed','execution_supported')),
    'native_source_object_verification':(
        ('programs_matched','routines_matched','symbols_matched','auxiliary_symbols_matched','symbols_unresolved',
         'tables_matched','tables_unresolved'),
        ('identity_checks_only','table_identities_verified','compiled_code_verified','addresses_verified',
         'install_authority','active_catalog_replaced','commit'))}


def verification_row(event):
    """Retain advertised aggregate evidence without source IDs or error text."""
    if event.get('status') not in ('idle','unavailable','matched','partial','mismatch'):
        raise ValueError('Invalid source verification status')
    counters,flags=VERIFICATIONS[event['kind']]
    result={'kind':event['kind'],'status':event['status']}
    for field in counters:
        if field in event:
            if type(event[field]) is not int or not 0<=event[field]<=0xFFFFFFFF:
                raise ValueError('Invalid source verification count')
            result[field]=event[field]
    for field in flags:
        if field in event:
            if type(event[field]) is not bool:raise ValueError('Invalid source verification flag')
            result[field]=event[field]
    errors=event.get('errors')
    if not isinstance(errors,list) or len(errors)>MAX_REPORT_ROWS:raise ValueError('Invalid source verification errors')
    result['error_categories']=len(errors)
    return result


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
    end=2+2*child[1];start=4+2*result[3]
    try:
        path=decode_path(child[2:end])
        fields={key:getattr(path,key) for key in ('class_id','instance','attribute','program_instance',
            'io_map_instance','controller_instance','aoi_instance')}
        fields['symbolic']=bool(path.symbols)
    except CIPError:
        # Offline inspection must retain well-framed scoped requests that the
        # live dispatcher does not support. This does not authorize routing.
        observed=describe_path(child[2:end]);scopes=observed.get('object_path')
        if not scopes:raise
        leaf=scopes[-1]
        fields={key:None for key in ('program_instance','io_map_instance','controller_instance','aoi_instance')}
        fields.update({key:leaf[key] for key in ('class_id','instance','attribute')},
            symbolic=observed['symbolic_path'],object_path=scopes,dispatch_path_supported=False)
        if len(scopes)==2 and scopes[0]['class_id']==0x68:fields['program_instance']=scopes[0]['instance']
    row=dict(ordinal=ordinal,sequence=sequence,service=child[0],**fields,
        status=result[2],request_payload_bytes=len(child)-end,
        response_payload_bytes=len(result)-start,
        additional_status=list(struct.unpack('<'+'H'*result[3],result[4:start])))
    if child[0]==3 and row['attribute'] is None:
        data=child[end:]
        if len(data)>=2:
            count=struct.unpack_from('<H',data)[0];row['attribute_list_count']=count
            if 1<=count<=32 and len(data)==2+2*count:
                row['requested_attributes']=list(struct.unpack_from('<'+'H'*count,data,2))
                if (collection_instance(row['class_id'],row['instance']) and not row['symbolic'] and 'object_path' not in row and
                        collection_scope(row['class_id'],**{name:row[name] for name in ('program_instance','io_map_instance','controller_instance','aoi_instance')}) and
                        result[2] in (0,6,0x0A)):
                    try:row['collection_attribute_list']=decode_attribute_list(result,row['requested_attributes'],row['class_id'])
                    except CollectionError as error:
                        row['collection_attribute_list']={'structure':'UNSUPPORTED OR MALFORMED','reason':str(error)}
    return row


def gap_delta(before,after):
    """Endpoint-wide counts; these do not attribute gaps to one native client."""
    fields=('generation','class_id','instance','program_instance','io_map_instance','controller_instance','aoi_instance','service')
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
    failures=[];wrappers=[];tail=deque(maxlen=16);phases=[];objects=Counter();verifications=[]
    matched=envelopes=fragments=fragment_bytes=unparsed=failed=wrapper_count=phase_count=0
    verification_count=invalid_verifications=0
    collections=[];collection_count=collection_errors=0
    limited=False
    for event in events:
        if event.get('kind') in VERIFICATIONS:
            verification_count+=1
            try:row=verification_row(event)
            except ValueError:invalid_verifications+=1
            else:
                if len(verifications)<16:verifications.append(row)
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
                if 'collection_attribute_list' in row:
                    collection_count+=1
                    if row['collection_attribute_list'].get('structure')=='UNSUPPORTED OR MALFORMED':collection_errors+=1
                    if len(collections)<MAX_REPORT_ROWS:collections.append(row)
                scopes=tuple((p['class_id'],p['instance'],p['attribute'],p['symbolic_path']) for p in row.get('object_path',()))
                key=tuple(row[k] for k in ('class_id','instance','program_instance','io_map_instance','controller_instance','aoi_instance','symbolic'))+(scopes,)
                objects[key]+=1
                if row['status']:
                    failed+=1
                    if len(failures)<MAX_REPORT_ROWS:failures.append(row)
        except (ValueError,IndexError,KeyError,TypeError,CIPError,struct.error):unparsed+=1
    gaps,gaps_truncated=gap_delta(before,after)
    object_rows=[dict(zip(('class_id','instance','program_instance','io_map_instance','controller_instance','aoi_instance','symbolic'),key[:-1]),requests=count,
                     **({'object_path':[dict(zip(('class_id','instance','attribute','symbolic_path'),scope)) for scope in key[-1]]} if key[-1] else {}))
                 for key,count in objects.items()]
    return {**base,'status':'observed' if envelopes else 'no_complete_signed_events',
        'analysis_complete':not (unparsed or limited or invalid_verifications or collection_errors),'signed_envelopes':envelopes,'requests_observed':matched,
        'fragment_acknowledgements':fragments,'fragment_bytes':fragment_bytes,'unparsed_events':unparsed,
        'request_limit_reached':limited,'failed_request_count':failed,'failed_requests':failures,
        'failures_truncated':failed>MAX_REPORT_ROWS,'last_requests':list(tail),
        'wrapper_rejections':wrappers,'wrapper_rejections_truncated':wrapper_count>MAX_REPORT_ROWS,
        'objects':object_rows[:MAX_REPORT_ROWS],'objects_truncated':len(object_rows)>MAX_REPORT_ROWS,
        'preparation_events':phases,'preparation_events_truncated':phase_count>16,
        'source_verifications':verifications,'source_verifications_observed':verification_count,
        'source_verifications_invalid':invalid_verifications,'source_verifications_truncated':verification_count-invalid_verifications>16,
        'collection_attribute_lists':collections,'collection_lists_observed':collection_count,
        'collection_layout_errors':collection_errors,'collection_lists_truncated':collection_count>MAX_REPORT_ROWS,
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
