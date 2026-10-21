"""Exercise real anonymous protocol exchanges on an isolated loopback emulator.

Requires a matching ACD and complete converted L5X, preserved by SHA-256.
This creates its own temporary controller; it cannot retarget the running app
or a physical controller. No Studio SDK or Windows service is used. It does
not establish native Studio acceptance, firmware identity or controller parity.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import zlib
from xml.etree import ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab import __version__
from logixlab.ethernetip import Endpoint,logical,symbol_path,CIPError
from logixlab.server import Application
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols
from logixlab.native_types import NativeTypes
from logixlab.native_tasks import NativeTasks
from logixlab.native_routines import NativeRoutines
from logixlab.native_aois import NativeAOIs
from logixlab.model import Project,ModelError
from logixlab.resilient_transport import DEVICE_HEADER,MAX_BUFFER_BYTES
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import collect_inventory
from tools.routine_edit_probe import replace_routine


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exercise(app,client,payload=None,expanded=None):
    checks=[]
    def check(name,request,expected):
        response=client.request(request)
        if response!=expected:raise ValueError(f'{name}: unexpected CIP reply {response[:4].hex()}')
        checks.append({'check':name,'status':response[2],'reply_bytes':len(response)})
    client.bind()
    check('signed_identity_vendor',bytes.fromhex('0e03200124013001'),bytes.fromhex('8e0000000100'))
    scalar=None
    for key,tag in app.engine.project.tags.items():
        if tag.dtype=='BOOL' and not tag.scope and not tag.alias and not isinstance(tag.value,list) and tag.external_access!='None':
            scalar=tag;break
    if scalar is not None:
        path=symbol_path(scalar.name)
        expected=bytes.fromhex('cc000000c100')+bytes((int(app.engine.memory.read(scalar.name)),))
        check('signed_actual_bool_value',bytes((0x4C,len(path)//2))+path+b'\1\0',expected)
    for number in (15,17,23,31):
        value=app.engine.project.controller_configuration.compatibility_attributes().get(number)
        if value is not None:check(f'controller_source_field_{number}',bytes.fromhex('0e03208e240130')+bytes((number,)),b'\x8e\0\0\0'+value)
    check('edit_reservation',bytes.fromhex('4b04208e24012074240101'),bytes.fromhex('cb000000'))
    check('edit_preparation_open',bytes.fromhex('5502208e2401'),bytes.fromhex('d5000000'))
    for row in app.endpoint.router.programs():
        semaphore=b'\x20\x68'+logical(0x24,row['id'])+b'\x20\x74\x24\1'
        check('program_reservation',bytes((0x4B,len(semaphore)//2))+semaphore+b'\0',bytes.fromhex('cb000000'))
        assert app.endpoint.state()['native_programming_lease']['scan_inhibited']
        path=b'\x20\x68'+logical(0x24,row['id'])
        if app.endpoint.router.zero_program_stack_supported(row):
            check('program_zero_stack_preparation',bytes((4,len(path)//2))+path+b'\1\0\x1b\0'+bytes(4),
                  bytes.fromhex('8400000001001b000000'))
            check('program_zero_stack_readback',bytes((0x0E,len(path)//2+1))+path+b'\x30\x1b',
                  bytes.fromhex('8e00000000000000'))
            if app.native_routines is not None:
                routine=next((routine for routine in app.endpoint.router.routines(row['id'])
                    if app.engine.project.routines[(routine['program']+'/'+routine['name']).lower()].kind=='RLL'),None)
                if routine is not None:
                    target=path+b'\x20\x6d'+logical(0x24,routine['id'])
                    prefix=bytes((0x5C,len(target)//2))+target+struct.pack('<4I',3,1,0,0)
                    elf=b'\x7fELF\x01\x01\x01'+bytes(45)
                    body=struct.pack('<5I',9,0,0,0,len(elf))+elf
                    for name,word,position,data in (
                            ('compiled_edit_first_fragment',0x101,len(body),prefix+body[:32]),
                            ('compiled_edit_continuation',1,32,body[32:40]),
                            ('compiled_edit_code_receipt',0x201,40,body[40:])):
                        client.fragment(word,position,data)
                        checks.append({'check':name,'status':0,'reply_bytes':36})
                    xml=ET.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.03',
                        TargetName=routine['name'],TargetType='RLLContent',TargetSubType='RLL',ContainsContext='false')
                    content=ET.SubElement(xml,'RLLContent',Use='Create',OnlineEditType='Original')
                    ET.SubElement(ET.SubElement(content,'Rung',Type='N',RegionId='1'),'TextIOI').text='NOP();'
                    plain=ET.tostring(xml);packed=zlib.compress(plain)
                    source=struct.pack('<II',0x40000000|len(packed),len(plain))+packed
                    source+=bytes((-len(source))%4)
                    auxiliary=struct.pack('<II',1,8)+zlib.compress(b'research')
                    total=28+len(source)+((len(auxiliary)+3)//4)*4
                    block=struct.pack('<8I',total,28,len(source),28+len(source),len(auxiliary),0,total,0)+source+auxiliary
                    block+=bytes((-len(block))%4)
                    source_prefix=bytes((0x5C,len(target)//2))+target+struct.pack('<II',1,3)
                    client.fragment(0x101,len(block),source_prefix+block[:48])
                    checks.append({'check':'routine_source_first_fragment','status':0,'reply_bytes':36})
                    transfer=app.endpoint.state()['native_programming_lease']['edit_transfer']
                    assert transfer['received_bytes']==48 and transfer['code_bytes']==len(body) and transfer['component_kind']=='source'
                    assert not transfer['routine_installed'] and not transfer['complete']
                    client.fragment(0x201,48,block[48:])
                    checks.append({'check':'routine_source_validated_receipt','status':0,'reply_bytes':36})
                    transfer=app.endpoint.state()['native_programming_lease']['edit_transfer']
                    assert transfer['source_description']['execution_plan_validated']
                    record=bytes((0x5C,len(target)//2))+target+struct.pack('<5I',2,5,0,1,123)
                    response=client.transfer(record,control=8)
                    assert response==bytes.fromhex('dc000000')
                    checks.append({'check':'post_source_record_receipt','status':0,'reply_bytes':len(response)})
                    assert app.endpoint.state()['native_programming_lease']['edit_transfer']['post_source_record']['staged']
                    check('unimplemented_edit_completion_denied',bytes.fromhex('5902208e2401')+bytes(4),bytes.fromhex('d9000f00'))
                    assert not app.endpoint.state()['native_programming_lease']['edit_transfer']['accepted_edits']
        check('program_reservation_release',bytes((0x4C,len(semaphore)//2))+semaphore,bytes.fromhex('cc000000'))
        transfer=app.endpoint.state()['native_programming_lease']['edit_transfer']
        if transfer['post_source_record']['staged']:assert transfer['program_released']
        else:assert transfer['status']=='idle'
        assert app.endpoint.state()['native_programming_lease']['scan_inhibited']
        attrs=app.engine.project.program_configuration.attributes(row['name'],source_sha256=app.engine.project.sha256)
        if 19 in attrs:
            path=b'\x20\x68'+logical(0x24,row['id'])
            check('program_disabled_source',bytes((3,len(path)//2))+path+b'\1\0\x13\0',bytes.fromhex('83000000010013000000')+attrs[19])
    if app.native_tasks is not None:
        rows=app.endpoint.router.tasks()
        check('task_native_instance_list',bytes.fromhex('4b0220702400'),bytes.fromhex('cb000000')+
              b''.join(struct.pack('<I',row['id']) for row in rows))
        for row in rows:
            path=b'\x20\x70'+logical(0x24,row['id'])
            attrs=app.engine.project.task_configuration.attributes(row['name'],source_sha256=app.engine.project.sha256)
            attrs.update(app.engine.project.task_timing.attributes(row['name'],source_sha256=app.engine.project.sha256))
            if app.native_symbols is not None:
                attrs.update(app.engine.project.task_configuration.scheduled_attributes(
                    row['name'],source_sha256=app.engine.project.sha256,
                    source_acd_sha256=app.native_tasks.source_acd_sha256,program_ids=app.native_symbols.programs,
                    program_source_l5x_sha256=app.native_symbols.source_l5x_sha256,
                    program_source_acd_sha256=app.native_symbols.source_acd_sha256))
            if attrs:
                request=bytes((3,len(path)//2))+path+struct.pack('<H',len(attrs))
                expected=bytes.fromhex('83000000')+struct.pack('<H',len(attrs))
                for number,value in attrs.items():
                    request+=struct.pack('<H',number);expected+=struct.pack('<HH',number,0)+value
                check('task_source_settings',request,expected)
            if 19 in attrs:
                check('task_inhibit_source',bytes((0x0E,len(path)//2+1))+path+b'\x30\x13',
                      bytes.fromhex('8e000000')+attrs[19])
            for number in (1,12):
                if number in attrs:
                    check('task_programs_source' if number==1 else 'task_watchdog_source',
                          bytes((0x0E,len(path)//2+1))+path+b'\x30'+bytes((number,)),
                          bytes.fromhex('8e000000')+attrs[number])
            check('task_execution_slot_unavailable',bytes((0x0E,len(path)//2+1))+path+b'\x30\x10',
                  bytes.fromhex('8e001400'))
    if app.native_routines is not None:
        check('executable_legacy_class_revision',bytes.fromhex('0e03206d24003001'),bytes.fromhex('8e0000000100'))
        for program in app.endpoint.router.programs():
            prefix=b'\x20\x68'+logical(0x24,program['id'])+b'\x20\x6d'
            path=prefix+b'\x24\0'
            try:rows=app.endpoint.router.routines(program['id'])
            except CIPError as error:
                if error.status!=0x0C:raise
                check('executable_catalog_unavailable',bytes((0x4B,len(path)//2))+path,bytes.fromhex('cb000c00'))
                continue
            check('program_scoped_executable_list',bytes((0x4B,len(path)//2))+path,
                  b'\xcb\0\0\0'+b''.join(struct.pack('<I',row['id']) for row in rows))
            for row in rows:
                path=prefix+logical(0x24,row['id'])
                attrs=app.engine.project.executable_configuration.attributes(
                    program['name'],row['name'],source_sha256=app.engine.project.sha256)
                check('executable_legacy_description',bytes((0x0E,len(path)//2+1))+path+b'\x30\7',
                      b'\x8e\0\0\0'+attrs[7] if 7 in attrs else bytes.fromhex('8e001400'))
                check('executable_type_unavailable',bytes((0x0E,len(path)//2+1))+path+b'\x30\1',bytes.fromhex('8e001400'))
    check('edit_preparation_close',bytes.fromhex('5702208e2401'),bytes.fromhex('d7000000'))
    assert app.endpoint.state()['native_programming_lease']['edit_transfer']['status']=='idle'
    lease=app.endpoint.state()['native_programming_lease']
    assert not lease['scan_inhibited'] and lease['edit_preparation']['program_stack_preparations']==0
    assert not lease['edit_preparation']['active_stack_changed']
    check('edit_release',bytes.fromhex('4c04208e240120742401'),bytes.fromhex('cc000000'))
    image_receipt=None
    if payload is not None:
        if not 1<=len(payload)<=MAX_BUFFER_BYTES or not 1<=expanded<=2*1024*1024:
            raise ValueError('Device payload or expanded size exceeds the research bound')
        check('download_reservation',bytes.fromhex('4b04208e24012074240100'),bytes.fromhex('cb000000'))
        check('run_inhibit',bytes.fromhex('0402208e2401010007000100'),bytes.fromhex('84000000010007000000'))
        check('begin_preparation',bytes.fromhex('6002208e2401'),bytes.fromhex('e0000000'))
        check('transport_setup',bytes.fromhex('4b03210012042400')+struct.pack('<HHIII',1,1,1,MAX_BUFFER_BYTES,expanded),bytes.fromhex('cb000000'))
        offset=0
        while offset<len(payload):
            chunk=payload[offset:offset+4000];first=offset==0;last=offset+len(chunk)==len(payload)
            if first and last:raise ValueError('Device probe requires at least two fragments')
            client.fragment(0x101 if first else 0x201 if last else 1,len(payload) if first else offset,
                            DEVICE_HEADER+chunk if first else chunk)
            offset+=len(chunk)
        check('start_real_temporary_image',bytes.fromhex('0603210012042400'),bytes.fromhex('86000000'))
        transport=app.endpoint.programming_lease.transport;image=transport.download_image
        matches=historical=0
        for ordinal in range(image.records):
            result=image.read_preparation_effect(ordinal,image.source)
            if not result.matches:raise ValueError('Preparation result does not match temporary resources')
            if result.historical_transition:historical+=1
            else:matches+=1
        image_receipt={**image.description(),'current_resource_readbacks':matches,'historical_transitions':historical}
        check('unsupported_result_request',bytes.fromhex('4d03210012042400'),bytes.fromhex('cd000f00'))
        check('transport_delete',bytes.fromhex('0903210012042400'),bytes.fromhex('89000000'))
        check('end_preparation',bytes.fromhex('6202208e2401'),bytes.fromhex('e2000000'))
        check('clear_inhibit',bytes.fromhex('0402208e2401010007000000'),bytes.fromhex('84000000010007000000'))
        check('download_release',bytes.fromhex('4c04208e240120742401'),bytes.fromhex('cc000000'))
    return checks,image_receipt


def edit_case(load_request,target,value):
    """Use a second disposable app so transfer/inventory baselines stay intact."""
    with tempfile.TemporaryDirectory(prefix='logixlab-edit-research-') as folder:
        app=Application(folder)
        try:
            app.command('load',load_request)
            app.command('routine-edits-configure',{'allow_writes':True})
            app.endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True).start()
            result=replace_routine(app.endpoint,program=target[0],routine=target[1],tag=target[2],value=value)
            # A fresh independent session must see the same committed revision
            # and original value before the first scan of the new logic.
            original=app.engine.memory.read(target[2])
            with AnonymousClient(app.endpoint) as client:
                client.bind();path=symbol_path(target[2]);request=bytes((0x4C,len(path)//2))+path+b'\1\0'
                expected=bytes.fromhex('cc000000c400')+struct.pack('<i',original)
                if client.request(request)!=expected:raise ValueError('Post-edit reconnect value read differs')
            app.command('step',{'count':1})
            if app.engine.memory.read(target[2])!=value:raise ValueError('Edited routine did not execute on the next scan')
            inventory=collect_inventory(app.endpoint)
            matches=[row for scope in inventory['scopes'] if scope['program_instance'] is None
                     for row in scope['symbols'] or [] if any(field['attribute']==1 and isinstance(field['value'],str)
                                                               and field['value'].casefold()==target[2].casefold()
                                                               for field in row['metadata']['attributes'] or [])]
            if len(matches)!=1 or matches[0]['value']!=value:raise ValueError('Post-edit inventory value differs')
            exported=app.command('export-edited-l5x',{})
            with tempfile.TemporaryDirectory(prefix='logixlab-edit-reload-') as reload_folder:
                reload=Application(reload_folder)
                try:
                    reload.command('load',{'name':'edited.L5X','content':base64.b64encode(exported['content'].encode()).decode()})
                    if reload.engine.memory.read(target[2])!=original:raise ValueError('Edited export lost original initial values')
                    reload.command('step',{'count':1})
                    if reload.engine.memory.read(target[2])!=value:raise ValueError('Edited L5X reload did not reproduce execution')
                finally:reload.close()
            result.update(reconnect_value_read=True,next_scan_execution=True,inventory_requests=inventory['request_count'],
                          inventory_value=value,l5x_export_sha256=exported['sha256'],l5x_reload_execution=True,
                          original_initial_value_preserved=True,isolated_model_changed=True)
        finally:app.close()
    result['isolated_app_closed']=True
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--acd',type=Path,required=True);p.add_argument('--l5x',type=Path,required=True)
    p.add_argument('--device-payload',type=Path);p.add_argument('--expanded-bytes',type=int)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inventory',action='store_true',help='Read private Template/Task/Program/tag inventory through a fresh owned TCP session')
    p.add_argument('--edit-target',nargs=3,metavar=('PROGRAM','ROUTINE','DINT_TAG'),
                   help='Test supported replacement and execution in a second disposable emulator')
    p.add_argument('--edit-value',type=int,default=123,help='Signed DINT literal for the optional edit probe')
    args=p.parse_args()
    if not -(1<<31)<=args.edit_value<(1<<31):p.error('Edit value must fit a signed DINT')
    if bool(args.device_payload)!=(args.expanded_bytes is not None):p.error('Supply both payload and expanded size')
    if args.acd.suffix.lower()!='.acd' or args.l5x.suffix.lower()!='.l5x':p.error('Select an ACD and complete L5X export')
    for path in (args.acd,args.l5x):
        if not 1<=path.stat().st_size<=100_000_000:p.error('Project inputs must be at most 100 MB')
    if args.device_payload and not 1<=args.device_payload.stat().st_size<=MAX_BUFFER_BYTES:
        p.error('Device payload exceeds the bounded temporary transport')
    if args.output.resolve() in {args.acd.resolve(),args.l5x.resolve(),*([] if args.device_payload is None else [args.device_payload.resolve()])}:
        p.error('The report cannot overwrite an input')
    acd_hash=digest(args.acd);l5x_hash=digest(args.l5x)
    project=Project(args.l5x);configuration=project.task_configuration
    symbols=NativeSymbols.from_acd(args.acd,l5x_hash)
    tasks=None;task_error=None
    try:
        if not configuration.source_complete:raise ModelError('Complete v35 Task source is unavailable')
        tasks=NativeTasks.from_acd(args.acd,l5x_hash,configuration.names)
    except (ModelError,UnicodeError,OSError) as error:task_error=str(error)
    routines=None;routine_error=None
    try:
        config=project.executable_configuration
        if not config.source_complete:raise ModelError('Complete v35 Executable source is unavailable')
        expected=[{'program':program,'name':name} for program in config.program_names
                  for name in config.routine_names(program,source_sha256=l5x_hash)]
        routines=NativeRoutines.from_acd(args.acd,l5x_hash,expected,symbols)
    except (ModelError,UnicodeError,OSError) as error:routine_error=str(error)
    aois=None;aoi_error=None
    try:
        if project.aoi_catalog.metadata is None:raise ModelError('Complete AOI declarations are unavailable')
        aois=NativeAOIs.from_acd(args.acd,l5x_hash,[row.name for row in project.aoi_catalog.metadata])
    except (ModelError,UnicodeError,OSError) as error:aoi_error=str(error)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():p.error('Use a new private report path')
    with tempfile.TemporaryDirectory(prefix='logixlab-research-') as folder:
        app=Application(folder)
        try:
            load_request={'name':'research.L5X','content':base64.b64encode(args.l5x.read_bytes()).decode(),
                'native_project_identity':NativeProjectIdentity.from_acd(args.acd,l5x_hash).manifest(),
                'native_symbols':symbols.manifest(),
                'native_types':NativeTypes.from_acd(args.acd,l5x_hash).manifest(),
                **({'native_tasks':tasks.manifest()} if tasks is not None else {}),
                **({'native_routines':routines.manifest()} if routines is not None else {}),
                **({'native_aois':aois.manifest()} if aois is not None else {})}
            app.command('load',load_request)
            before=app.state()
            app.endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True).start()
            with AnonymousClient(app.endpoint) as client:
                checks,image=exercise(app,client,args.device_payload.read_bytes() if args.device_payload else None,args.expanded_bytes)
            inventory=collect_inventory(app.endpoint) if args.inventory else None
            deadline=time.monotonic()+3
            while app.endpoint.state()['active_tcp_clients'] and time.monotonic()<deadline:time.sleep(.02)
            after=app.state();lease=app.endpoint.state()['native_programming_lease']
            assert not lease['owned'] and lease['run_mode_inhibit']==0 and not lease['resilient_transport']['open']
            assert lease['resilient_transport']['download_image']['status']=='idle'
            assert app.endpoint.state()['active_tcp_clients']==0
            assert all(before[k]==after[k] for k in ('tags','routines','tasks','scan','ms','controller'))
            routine_edit=edit_case(load_request,args.edit_target,args.edit_value) if args.edit_target else None
            assert acd_hash==digest(args.acd) and l5x_hash==digest(args.l5x)
            report={'version':__version__,'status':'passed','transport':'owned loopback TCP',
                'ephemeral_client_key':True,'server_nonce_patched':False,'windows_services_used':False,
                'source_acd_sha256':acd_hash,'source_l5x_sha256':l5x_hash,'checks':checks,
                'native_task_binding':app.native_tasks.description() if app.native_tasks is not None else None,
                'native_task_binding_error':task_error,
                'native_routine_binding':app.native_routines.description() if app.native_routines is not None else None,
                'native_routine_binding_error':routine_error,
                'native_aoi_binding':app.native_aois.description() if app.native_aois is not None else None,
                'native_aoi_binding_error':aoi_error,
                'upload_inventory':inventory,
                'routine_edit_probe':routine_edit,
                'prepared_image':image,'cleanup_confirmed':True,'source_and_model_preserved':True,
                'native_sdk_acceptance':'NOT ASSESSED','studio_gui_acceptance':'NOT ASSESSED'}
            args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({'version':__version__,'checks':len(checks),'records':image['records_prepared'] if image else 0,
                              'inventory_requests':inventory['request_count'] if inventory else None,
                              'routine_edit_checks':len(routine_edit['checks']) if routine_edit else None,
                              'source_and_model_preserved':True,'report':str(args.output),'native_sdk_acceptance':'NOT ASSESSED'}))
        finally:app.close()


if __name__=='__main__':main()
