"""Exercise the supported Program-mode replacement on an owned loopback app.

This synthetic source/container pair tests the custom execution model. It is
not a Studio compiler output, native edit acceptance or Test/Untest/Assemble.
The caller must enable routine edits on its disposable emulator explicitly.
"""
import copy
import hashlib
import struct
import time
import zlib
from xml.etree import ElementTree as ET

from .anonymous_client import AnonymousClient,ProbeError
from .upload_inventory import logical_path


def source_container(name,text):
    root=ET.Element('RSLogix5000Content',SchemaRevision='1.0',SoftwareRevision='35.03',
        TargetName=name,TargetType='RLLContent',TargetSubType='RLL',ContainsContext='false')
    content=ET.SubElement(root,'RLLContent',Use='Create',OnlineEditType='Original')
    ET.SubElement(ET.SubElement(content,'Rung',Type='N',RegionId='1'),'TextIOI').text=text
    plain=ET.tostring(root);packed=zlib.compress(plain)
    source=struct.pack('<II',0x40000000|len(packed),len(plain))+packed
    source+=bytes((-len(source))%4)
    auxiliary=struct.pack('<II',1,8)+zlib.compress(b'research')
    total=28+len(source)+((len(auxiliary)+3)//4)*4
    block=struct.pack('<8I',total,28,len(source),28+len(source),len(auxiliary),0,total,0)+source+auxiliary
    return block+bytes((-len(block))%4)


def replace_routine(endpoint,*,program,routine,tag,value=123):
    """Replace one routine with MOV(value, controller_DINT) through signed TCP.

    No scan runs here. Failures close this socket without retrying or guessing
    whether a commit succeeded. The caller owns and discards the temporary app.
    """
    client=AnonymousClient(endpoint)
    try:
        with client:
            app=endpoint.app;project=app.engine.project
            if not app.allow_routine_edits or app.controller_state()['mode']!='Program':
                raise ProbeError('Enable routine edits on a disposable Program-mode emulator')
            if type(value) is not int or not -(1<<31)<=value<(1<<31):
                raise ProbeError('Use a signed DINT replacement value')
            if any(not isinstance(name,str) for name in (program,routine,tag)):
                raise ProbeError('Supply explicit Program, Routine and controller tag names')
            if any(binding is None for binding in (app.native_symbols,app.native_types,app.native_routines)):
                raise ProbeError('Source-bound Symbol, Template and Routine catalogs are required')
            target=app.native_routines.lookup(program,routine)
            symbol=app.native_symbols.by_key.get(tag.casefold())
            declaration=project.tags.get(tag.casefold())
            if (target is None or symbol is None or symbol.program_instance or declaration is None or
                    declaration.scope or declaration.alias or declaration.constant or declaration.dtype!='DINT' or
                    type(declaration.value) is not int):
                raise ProbeError('Select a bound routine and writable scalar controller DINT')
            before=copy.deepcopy(app.state());base=before['routine_edits']['revision'];checks=[]
            def request(name,raw,expected,*,transfer=False):
                response=client.transfer(raw,control=8) if transfer else client.request(raw)
                if response!=expected:raise ProbeError(name+': unexpected signed reply '+response[:4].hex())
                checks.append({'check':name,'status':response[2],'reply_bytes':len(response)})
            def fragment(name,word,position,data):
                client.fragment(word,position,data)
                checks.append({'check':name,'status':0,'reply_bytes':36})
            client.bind()
            request('controller_reserve',bytes.fromhex('4b04208e24012074240101'),bytes.fromhex('cb000000'))
            request('edit_phase_open',bytes.fromhex('5502208e2401'),bytes.fromhex('d5000000'))
            semaphore=logical_path(0x74,1,target.program_instance)
            request('program_reserve',bytes((0x4B,len(semaphore)//2))+semaphore+b'\0',bytes.fromhex('cb000000'))
            path=logical_path(0x68,target.program_instance)
            request('zero_stack_prepare',bytes((4,len(path)//2))+path+b'\1\0\x1b\0'+bytes(4),
                    bytes.fromhex('8400000001001b000000'))
            path=logical_path(0x6D,target.instance,target.program_instance)
            header=bytes((0x5C,len(path)//2))+path
            elf=b'\x7fELF\x01\x01\x01'+bytes(45)
            code=struct.pack('<5I',9,0,0,0,len(elf))+elf
            fragment('code_first',0x101,len(code),header+struct.pack('<4I',3,1,0,0)+code[:32])
            fragment('code_last',0x201,32,code[32:])
            source=source_container(target.name,f'MOV({value},@107 {symbol.instance} 0 0 0 0@);')
            fragment('source_first',0x101,len(source),header+struct.pack('<II',1,3)+source[:48])
            fragment('source_last',0x201,48,source[48:])
            request('post_source_record',header+struct.pack('<5I',2,5,0,1,123),bytes.fromhex('dc000000'),transfer=True)
            commit=bytes.fromhex('5902208e2401')+bytes(4)
            request('commit_while_reserved_denied',commit,bytes.fromhex('d9000c00'))
            assert app.state()['routine_edits']['revision']==base
            request('program_release',bytes((0x4C,len(semaphore)//2))+semaphore,bytes.fromhex('cc000000'))
            request('routine_commit',commit,bytes.fromhex('d9000000'))
            after=app.state()
            if after['routine_edits']['revision']!=base+1:raise ProbeError('Commit did not advance the logic revision once')
            if not all(before[k]==after[k] for k in ('tags','scan','ms','controller','tasks')):
                raise ProbeError('Routine commit changed values or scan state')
            request('duplicate_commit_idempotent',commit,bytes.fromhex('d9000000'))
            if app.state()['routine_edits']['revision']!=base+1:raise ProbeError('Duplicate commit changed logic revision')
            request('edit_phase_close',bytes.fromhex('5702208e2401'),bytes.fromhex('d7000000'))
            request('controller_release',bytes.fromhex('4c04208e240120742401'),bytes.fromhex('cc000000'))
            result={'checks':checks,'revision_before':base,'revision_after':base+1,
                    'program':target.program,'routine':target.name,'tag':declaration.name,'value':value,
                    'source_container_sha256':hashlib.sha256(source).hexdigest(),
                    'values_and_scan_preserved_at_commit':True,'synthetic_compiled_container':True,
                    'native_code_executed':False,'native_sdk_acceptance':'NOT ASSESSED',
                    'test_untest_assemble':False}
    finally:
        deadline=time.monotonic()+.5
        while endpoint.state()['active_tcp_clients'] and time.monotonic()<deadline:time.sleep(.005)
    lease=endpoint.state()['native_programming_lease']
    if lease['owned'] or endpoint.state()['active_tcp_clients']:
        raise ProbeError('Routine probe connection or reservation did not close')
    result['cleanup_confirmed']=True
    return result
