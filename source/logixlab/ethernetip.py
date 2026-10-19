"""Experimental local EtherNet/IP explicit-message target.

This is a protocol research endpoint, not a complete Logix controller. Unknown
services return CIP errors and are traced; no upload/download is acknowledged.
The wire implementation uses only Python's standard library.
"""
from __future__ import annotations

import copy
import math
import re
import secrets
import socket
import socketserver
import struct
import sys
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from .model import ModelError
from .identity import Identity
from .templates import Catalog, MAX_BYTES
from .catalog_revision import CatalogRevision
from .network_objects import interface_snapshot, port_attributes, cip_string
from .broadcast_discovery import prepare_broadcasts
from . import file_manager, key_exchange

HEADER = struct.Struct('<HHII8sI')
TYPES = {'BOOL':(0xC1,'B'), 'SINT':(0xC2,'b'), 'INT':(0xC3,'h'),
         'DINT':(0xC4,'i'), 'LINT':(0xC5,'q'), 'USINT':(0xC6,'B'),
         'UINT':(0xC7,'H'), 'UDINT':(0xC8,'I'), 'ULINT':(0xC9,'Q'), 'REAL':(0xCA,'f')}
REPLY_LIMIT = 480


class CIPError(Exception):
    def __init__(self,status,detail):self.status=status;super().__init__(detail)


def need(data,size):
    if len(data)<size:raise CIPError(0x13,'Request data is too short')


def exact(data,size):
    need(data,size)
    if len(data)!=size:raise CIPError(0x15,'Request data has trailing bytes')


def reply(service,status=0,data=b''):return bytes((service|0x80,0,status,0))+data


def logical(kind,value):
    if value<256:return bytes((kind,value))
    if value<65536:return bytes((kind+1,0))+struct.pack('<H',value)
    return bytes((kind+2,0))+struct.pack('<I',value)


def symbol_path(name):
    """Client/test helper. Production parsing does not trust this encoder."""
    result=b''
    for part in name.split('.'):
        match=re.fullmatch(r'([A-Za-z_][\w:]*)(?:\[([\d,]+)\])?',part)
        if not match:raise ValueError('Static symbolic name required')
        text=match[1].encode('ascii');result+=bytes((0x91,len(text)))+text+b'\0'*(len(text)%2)
        if match[2]:
            for index in match[2].split(','):result+=logical(0x28,int(index))
    return result


@dataclass
class Path:
    class_id:int|None=None
    instance:int|None=None
    attribute:int|None=None
    symbols:list=field(default_factory=list)

    def reference(self,base=''):
        result=base;indices=[]
        def flush():
            nonlocal result
            if indices:result+='['+','.join(map(str,indices))+']';indices.clear()
        for part in self.symbols:
            if isinstance(part,int):indices.append(part)
            else:flush();result+=('.' if result else '')+part
        flush();return result


def decode_path(raw):
    p=Path();pos=0
    while pos<len(raw):
        code=raw[pos];pos+=1
        if code==0x91:
            need(raw[pos:],1);size=raw[pos];pos+=1;need(raw[pos:],size+size%2)
            try:name=raw[pos:pos+size].decode('ascii')
            except UnicodeDecodeError:raise CIPError(4,'Non-ASCII symbol')
            if not re.fullmatch(r'[A-Za-z_][\w:]*',name):raise CIPError(4,'Invalid symbol')
            if size%2 and raw[pos+size]!=0:raise CIPError(4,'Nonzero symbolic padding')
            p.symbols.append(name);pos+=size+size%2
        elif code in (0x20,0x21,0x22,0x24,0x25,0x26,0x28,0x29,0x2A,0x30,0x31,0x32):
            width=(1,2,4)[code&3]
            if width>1:
                need(raw[pos:],1)
                if raw[pos]!=0:raise CIPError(4,'Nonzero logical padding')
                pos+=1
            need(raw[pos:],width);value=int.from_bytes(raw[pos:pos+width],'little');pos+=width
            kind=code&0xFC
            if kind==0x28:p.symbols.append(value)
            else:
                attr={0x20:'class_id',0x24:'instance',0x30:'attribute'}[kind]
                if getattr(p,attr) is not None:raise CIPError(4,'Duplicate logical segment')
                setattr(p,attr,value)
        else:raise CIPError(4,f'Unsupported path segment 0x{code:02X}')
    if p.attribute is not None and p.class_id is None:raise CIPError(4,'Attribute without class')
    return p


def route_ok(raw,router=False):
    # One modeled backplane route: port 1, slot 0. Never forward externally.
    if raw.startswith(b'\x01\x00'):raw=raw[2:]
    if router:
        if raw!=b'\x20\x02\x24\x01':raise CIPError(5,'Class 3 connection must end at Message Router instance 1')
        return
    if raw:raise CIPError(5,'Only local backplane slot 0 is modeled')


@dataclass
class Connection:
    incoming:int
    outgoing:int
    identity:bytes
    incoming_size:int=500
    outgoing_size:int=500
    last_sequence:int|None=None
    last_request:bytes=b''
    last_reply:bytes=b''


@dataclass
class Session:
    handle:int=0
    generation:int=0
    connections:dict=field(default_factory=dict)
    peer:str=''


class Router:
    def __init__(self,app,endpoint):
        self.app=app;self.endpoint=endpoint;self._catalog=None

    def templates(self):
        project=self.app.engine.project
        if self._catalog is None or self._catalog.project is not project:self._catalog=Catalog(project)
        return self._catalog

    def identity_attributes(self):
        return self.endpoint.identity.attributes()

    def identity(self):return self.endpoint.identity.all_attributes()

    def network_interface(self):
        if not self.endpoint.interface_queried:
            snapshot,error=interface_snapshot(self.endpoint.bind_address)
            with self.endpoint.lock:
                self.endpoint.interface=snapshot;self.endpoint.interface_error=error;self.endpoint.interface_queried=True
        return self.endpoint.interface

    def attribute_read(self,service,path,data,attributes):
        if service==0x0E:
            exact(data,0)
            if path.attribute not in attributes:raise CIPError(0x14,'Unsupported attribute')
            return 0,attributes[path.attribute]
        if service==3 and path.attribute is None:
            need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
            if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
            result=struct.pack('<H',count);failed=False
            for number in struct.unpack_from('<'+'H'*count,data,2):
                value=attributes.get(number);status=0 if value is not None else 0x14
                failed|=status!=0;result+=struct.pack('<HH',number,status)+(value if value is not None else b'')
            return 0x0A if failed else 0,result
        raise CIPError(8,'Unsupported attribute service')

    def symbols(self,scope=''):
        result=[];engine=self.app.engine
        if not engine:return result
        for tag in sorted(engine.project.tags.values(),key=lambda t:t.key.lower()):
            if tag.scope.lower()!=scope.lower() or tag.problem or tag.tag_class!='Standard':continue
            try:
                self.access(tag.key)
                key,parts,dtype=engine.memory.resolve(tag.key);value=engine.memory.values[key]
                for part in parts:
                    if isinstance(part,tuple):value=None;break
                    value=value[part]
                dims=[]
                while isinstance(value,list):dims.append(len(value));value=value[0] if value else None
                template=self.templates().for_type(dtype) if dtype not in TYPES else None
                if dtype not in TYPES and template is None or dtype=='BOOL' and dims or len(dims)>3:continue
                try:self.access(tag.key,True);access=0
                except (CIPError,ModelError):access=2
                code=(0x8000|template.instance) if template else TYPES[dtype][0]
                result.append({'id':len(result)+1,'name':tag.name,'ref':tag.key,'type':code|(len(dims)<<13),
                               'dimensions':(dims+[0,0,0])[:3],'external_access':access})
            except ModelError:continue
            except CIPError:continue
        return result

    def access(self,ref,write=False,seen=()):
        """Honor root, alias target, member and AOI external-access restrictions."""
        memory=self.app.engine.memory;project=self.app.engine.project
        match=re.match(r'^(?:Program:([\w]+)\.)?([A-Za-z_][\w:]*)(.*)$',ref,re.I)
        if not match:raise CIPError(4,'Invalid static tag path')
        scope,name,tail=match.groups();key=(f'Program:{scope}.{name}' if scope else name).lower()
        if scope:
            program=next((p for n,p in project.programs.items() if n.lower()==scope.lower()),None)
            if program is None:raise CIPError(5,'Unknown program scope')
            if program['class']!='Standard':raise CIPError(0x0F,'Program is not externally accessible')
        tag=project.tags.get(key)
        if tag is None:raise CIPError(5,'Unknown tag')
        if key in seen:raise CIPError(5,'Alias cycle')
        if tag.external_access not in ('Read/Write','Read Only') or tag.tag_class!='Standard':raise CIPError(0x0F,'Tag is not externally accessible')
        if write and (tag.external_access!='Read/Write' or tag.constant):raise CIPError(0x0F,'Tag is externally read-only')
        if tag.alias:
            alias=tag.alias
            if tag.scope and not alias.lower().startswith('program:'):
                root=re.match(r'[A-Za-z_][\w:]*',alias)[0]
                if (f'Program:{tag.scope}.{root}').lower() in project.tags:alias=f'Program:{tag.scope}.'+alias
            return self.access(alias+tail,write,seen+(key,))
        dtype=tag.dtype
        for item in re.findall(r'\.([A-Za-z_][\w]*)',tail):
            if dtype.upper() in ('TIMER','COUNTER','STRING'):
                dtype='DINT' if item.upper() in ('LEN','PRE','ACC') else 'SINT' if item.upper()=='DATA' else 'BOOL';continue
            udt=project.udts.get(dtype.lower())
            member=next((m for m in udt.findall('./Members/Member') if m.get('Name','').lower()==item.lower()),None) if udt is not None else None
            if member is None:raise CIPError(5,'Unknown member')
            access=member.get('ExternalAccess','Read/Write')
            if member.get('Hidden','false').lower()=='true' or member.get('AOILocal','false')=='true' or access not in ('Read/Write','Read Only'):raise CIPError(0x0F,'Member is not externally accessible')
            if write and access!='Read/Write':raise CIPError(0x0F,'Member is externally read-only')
            dtype=member.get('DataType','')
        return memory.resolve(ref)

    def reference(self,path):
        if path.attribute is not None:raise CIPError(4,'Tag service does not take an attribute')
        if path.class_id==0x6B:
            scope='';parts=path.symbols
            if parts and isinstance(parts[0],str) and parts[0].lower().startswith('program:'):
                scope=parts[0][8:];parts=parts[1:]
            symbol=next((s for s in self.symbols(scope) if s['id']==path.instance),None)
            if symbol is None:raise CIPError(5,'Unknown symbol instance')
            return Path(symbols=parts).reference(symbol['ref'])
        if path.class_id is not None or path.instance is not None:raise CIPError(4,'Unsupported logical tag path')
        return path.reference()

    def region(self,ref,count,write=False):
        if not 1<=count<=4096:raise CIPError(3,'Element count must be 1..4096')
        key,parts,dtype=self.access(ref,write);memory=self.app.engine.memory
        if key is None or dtype not in TYPES:raise CIPError(8,'Only atomic data and atomic members are implemented')
        if dtype=='BOOL':
            value=memory.read(ref) if any(isinstance(p,tuple) for p in parts) else memory.at(key,parts)
            if count!=1 or isinstance(value,list):raise CIPError(8,'Packed BOOL arrays are not implemented')
            return dtype,[ref]
        value=memory.at(key,parts)
        if count==1 and not isinstance(value,list):return dtype,[ref]
        start=ref
        while isinstance(value,list):
            if not value:raise CIPError(0x0C,'Empty atomic array')
            start+='[0]';value=value[0]
        key,paths,dtype=memory.region(start,count)
        return dtype,[memory.address(key,p) for p in paths]

    def read_tag(self,path,data,fragment=False,limit=REPLY_LIMIT):
        exact(data,6 if fragment else 2);count=struct.unpack_from('<H',data)[0]
        if not 1<=count<=4096:raise CIPError(3,'Element count must be 1..4096')
        ref=self.reference(path);_,_,dtype=self.access(ref)
        template=self.templates().for_type(dtype) if dtype not in TYPES else None
        if template:
            memory=self.app.engine.memory;refs=self.structure_region(ref,count,template)
            def read_member(member_ref):
                self.access(member_ref)
                return memory.read(member_ref)
            encoded=b''.join(self.templates().encode(template,item,read_member) for item in refs)
            type_data=struct.pack('<HH',0x02A0,template.handle)
        else:
            dtype,refs=self.region(ref,count)
            fmt='<'+TYPES[dtype][1];encoded=b''
            for ref in refs:
                value=self.app.engine.memory.read(ref)
                if value is None or isinstance(value,(dict,list)):raise CIPError(0x0C,'Unknown or aggregate data')
                encoded+=struct.pack(fmt,int(value) if dtype=='BOOL' else value)
            type_data=struct.pack('<H',TYPES[dtype][0])
        offset=struct.unpack_from('<I',data,2)[0] if fragment else 0
        if offset>=len(encoded):raise CIPError(0x20,'Fragment offset outside data')
        capacity=limit-4-len(type_data)
        if capacity<1:raise CIPError(0x1B,'Response cannot hold a tag data byte')
        chunk=encoded[offset:offset+capacity]
        return 6 if offset+len(chunk)<len(encoded) else 0,type_data+chunk

    def structure_region(self,ref,count,template,write=False):
        if not 1<=count<=4096:raise CIPError(3,'Element count must be 1..4096')
        if count*template.size>MAX_BYTES:raise CIPError(3,'Structured transfer exceeds 32768 bytes')
        key,parts,_=self.access(ref,write);memory=self.app.engine.memory;value=memory.at(key,parts)
        if isinstance(value,dict) and (not parts or not isinstance(parts[-1],int)):
            if count!=1:raise CIPError(3,'Scalar structure count must be one')
            paths=[parts]
        else:
            start=ref
            while isinstance(value,list):
                if not value:raise CIPError(0x0C,'Empty structured array')
                start+='[0]';value=value[0]
            key,paths,_=memory.region(start,count)
        return [memory.address(key,p) for p in paths]

    def template_service(self,service,path,data,limit):
        if path.symbols:raise CIPError(4,'Template paths do not take symbols')
        scopes=['']+[n for n,p in self.app.engine.project.programs.items() if p['class']=='Standard']
        instances={s['type']&0xFFF for scope in scopes for s in self.symbols(scope) if s['type']&0x8000}
        template=self.templates().closure(instances).get(path.instance)
        if template is None:raise CIPError(5,'Unknown or unexposed template instance')
        if service in (3,0x0E):return self.attribute_read(service,path,data,template.attributes())
        if service!=0x4C:raise CIPError(8,'Unsupported template service')
        if path.attribute is not None:raise CIPError(4,'Template reads do not take an attribute')
        exact(data,6);offset,count=struct.unpack('<IH',data)
        if not count:raise CIPError(3,'Template byte count must be positive')
        if offset>=len(template.definition):raise CIPError(0x20,'Template offset outside definition')
        if limit<=4:raise CIPError(0x1B,'Response cannot hold a template data byte')
        end=min(offset+count,len(template.definition));chunk=template.definition[offset:min(end,offset+limit-4)]
        return 6 if offset+len(chunk)<end else 0,chunk

    def store_atomic(self,dtype,refs,values):
        if dtype=='BOOL' and any(v not in (0,1) for v in values):raise CIPError(9,'BOOL value must be 0 or 1')
        self.store_values([(ref,bool(value) if dtype=='BOOL' else value) for ref,value in zip(refs,values)])

    def store_values(self,values):
        memory=self.app.engine.memory;before=copy.deepcopy(memory.values)
        try:
            for ref,value in values:memory.write(ref,value)
        except Exception:
            memory.values=before;raise

    def write_tag(self,path,data,fragment=False):
        if not self.endpoint.allow_writes:raise CIPError(0x0F,'Network writes are disabled')
        ref=self.reference(path);_,_,declared=self.access(ref,True)
        if declared not in TYPES:
            template=self.templates().for_type(declared)
            if template is None:raise CIPError(8,'Unsupported structured wire layout')
            return self.write_structure(ref,template,data,fragment)
        header=8 if fragment else 4;need(data,header);type_code,count=struct.unpack_from('<HH',data)
        dtype,refs=self.region(ref,count,True)
        if type_code!=TYPES[dtype][0]:raise CIPError(0xFF,'Tag type does not match declared type')
        fmt='<'+TYPES[dtype][1];size=struct.calcsize(fmt)
        offset=struct.unpack_from('<I',data,4)[0] if fragment else 0;payload=data[header:]
        if not fragment:exact(data,header+count*size)
        if not payload:raise CIPError(0x13,'Fragment contains no data')
        if offset>=count*size or len(payload)>count*size-offset:raise CIPError(0x20,'Fragment exceeds requested atomic region')
        first=offset//size;last=(offset+len(payload)-1)//size;values=[]
        for index in range(first,last+1):
            start=max(offset,index*size);end=min(offset+len(payload),(index+1)*size)
            lo=start-index*size;hi=end-index*size;chunk=payload[start-offset:end-offset]
            if lo==0 and hi==size:raw=chunk
            else:
                # Partial atoms preserve known backing bytes. Unknown bytes are
                # never filled with zeros just to accept an incomplete write.
                old=self.app.engine.memory.read(refs[index])
                raw=bytearray(struct.pack(fmt,int(old) if dtype=='BOOL' else old));raw[lo:hi]=chunk
            values.append(struct.unpack(fmt,raw)[0])
        self.store_atomic(dtype,refs[first:last+1],values)
        return 0,b''

    def write_structure(self,ref,template,data,fragment=False):
        header=10 if fragment else 6;need(data,header)
        type_code,handle,count=struct.unpack_from('<HHH',data)
        if type_code!=0x02A0 or handle!=template.handle:raise CIPError(0xFF,'Structure type or handle does not match the template')
        refs=self.structure_region(ref,count,template,True);total=count*template.size
        offset=struct.unpack_from('<I',data,6)[0] if fragment else 0;payload=data[header:]
        if not fragment:exact(data,header+total)
        if not payload:raise CIPError(0x13,'Fragment contains no data')
        if offset>=total or len(payload)>total-offset:raise CIPError(0x20,'Fragment exceeds requested structured region')
        end=offset+len(payload);values=[];memory=self.app.engine.memory;covered=bytearray(len(payload))
        first=offset//template.size;last=(end-1)//template.size
        for index in range(first,last+1):
            for member_offset,dtype,member_ref,bit in self.templates().leaves(template,refs[index],index*template.size):
                if bit is not None:
                    if offset<=member_offset<end:
                        self.access(member_ref,True)
                        mask=1<<bit;position=member_offset-offset;covered[position]|=mask
                        values.append((member_ref,bool(payload[position]&mask)))
                    continue
                fmt='<'+TYPES[dtype][1];size=struct.calcsize(fmt)
                start=max(offset,member_offset);stop=min(end,member_offset+size)
                if start>=stop:continue
                self.access(member_ref,True)
                chunk=payload[start-offset:stop-offset];covered[start-offset:stop-offset]=b'\xFF'*(stop-start)
                if stop-start==size:raw=chunk
                else:
                    # Preserve known bytes in split atoms; untouched members may
                    # remain unknown and are never read merely to fill a packet.
                    raw=bytearray(struct.pack(fmt,memory.read(member_ref)))
                    raw[start-member_offset:stop-member_offset]=chunk
                values.append((member_ref,struct.unpack(fmt,raw)[0]))
        if any(value&(~used&0xFF) for value,used in zip(payload,covered)):
            raise CIPError(9,'Reserved layout padding and unused host bits must be zero')
        if values:self.store_values(values)
        return 0,b''

    def read_modify_write(self,path,data):
        if not self.endpoint.allow_writes:raise CIPError(0x0F,'Network writes are disabled')
        need(data,2);mask_size=struct.unpack_from('<H',data)[0]
        dtype,refs=self.region(self.reference(path),1,True)
        if dtype in ('BOOL','REAL'):raise CIPError(8,'Read Modify Write supports integer atoms only')
        fmt='<'+TYPES[dtype][1];size=struct.calcsize(fmt)
        if mask_size not in (1,2,4,8) or mask_size>size:raise CIPError(3,'Mask size exceeds the integer atom')
        exact(data,2+2*mask_size)
        or_mask=int.from_bytes(data[2:2+mask_size],'little');and_mask=int.from_bytes(data[2+mask_size:],'little')
        old=self.app.engine.memory.read(refs[0]);low_mask=(1<<(mask_size*8))-1
        value=((old&~low_mask)|(((old&low_mask)|or_mask)&and_mask))&((1<<(size*8))-1)
        value=struct.unpack(fmt,value.to_bytes(size,'little'))[0]
        self.store_atomic(dtype,refs,[value])
        return 0,b''

    def symbol_scope(self,path):
        scope=''
        if path.symbols:
            if len(path.symbols)!=1 or not isinstance(path.symbols[0],str) or not path.symbols[0].lower().startswith('program:'):raise CIPError(4,'Unsupported symbol enumeration path')
            scope=path.symbols[0][8:]
            program=next((p for n,p in self.app.engine.project.programs.items() if n.lower()==scope.lower()),None)
            if program is None:raise CIPError(5,'Unknown program scope')
            if program['class']!='Standard':raise CIPError(0x0F,'Program is not externally accessible')
        return scope

    def symbol_attributes(self,symbol):
        name=symbol['name'].encode('ascii')
        return {1:struct.pack('<H',len(name))+name,2:struct.pack('<H',symbol['type']),
                8:struct.pack('<III',*symbol['dimensions']),10:bytes((symbol['external_access'],))}

    def enumerate_symbols(self,path,data,limit=REPLY_LIMIT):
        scope=self.symbol_scope(path)
        if path.attribute is not None:raise CIPError(4,'Enumeration path does not take an attribute')
        need(data,2);n=struct.unpack_from('<H',data)[0];exact(data,2+2*n)
        attrs=struct.unpack_from('<'+'H'*n,data,2)
        if not n or n>16 or any(a not in (1,2,8,10) for a in attrs):raise CIPError(0x14,'Only symbol attributes 1, 2, 8 and 10 are implemented')
        out=b''
        for symbol in self.symbols(scope):
            if symbol['id']<(path.instance or 0):continue
            values=self.symbol_attributes(symbol)
            row=struct.pack('<I',symbol['id'])+b''.join(values[a] for a in attrs)
            if len(out)+len(row)>limit-4:
                if not out:raise CIPError(0x1B,'One symbol row exceeds negotiated response size')
                return 6,out
            out+=row
        return 0,out

    def forward_open(self,data,session,large=False):
        fixed=40 if large else 36;need(data,fixed)
        path_size=data[fixed-1]*2;exact(data,fixed+path_size);route_ok(data[fixed:],True)
        if data[fixed-2]!=0xA3:raise CIPError(8,'Only point-to-point Class 3 explicit connections are modeled')
        params=[struct.unpack_from('<I' if large else '<H',data,i)[0] for i in ((26,34) if large else (26,32))]
        for param in params:
            flags=param>>16 if large else param
            size=param&(0xFFFF if large else 0x1FF)
            if flags&0x6000!=0x4000 or not 16<=size<=4000:raise CIPError(1,'Only bounded point-to-point explicit connection sizes are supported')
        if len(session.connections)>=8:raise CIPError(2,'Connection limit reached')
        # Originator identity is retained verbatim for Forward Close matching.
        ident=data[10:18]
        if any(c.identity==ident for c in session.connections.values()):raise CIPError(1,'Duplicate connection serial/originator')
        incoming=secrets.randbits(32) or 1;outgoing=struct.unpack_from('<I',data,6)[0] or (secrets.randbits(32) or 2)
        while incoming in session.connections:incoming=secrets.randbits(32) or 1
        sizes=[p&(0xFFFF if large else 0x1FF) for p in params]
        session.connections[incoming]=Connection(incoming,outgoing,ident,*sizes)
        rpi1=data[22:26];rpi2=data[30:34] if large else data[28:32]
        return 0,struct.pack('<II',incoming,outgoing)+ident+rpi1+rpi2+b'\x00\x00'

    def forward_close(self,data,session):
        need(data,12);exact(data,12+data[10]*2)
        if data[11]:raise CIPError(4,'Nonzero close-path padding')
        route_ok(data[12:],True);ident=data[2:10]
        key=next((k for k,c in session.connections.items() if c.identity==ident),None)
        if key is None:raise CIPError(1,'Unknown connection identity')
        del session.connections[key];return 0,ident+b'\x00\x00'

    def dispatch(self,raw,session,depth=0,limit=REPLY_LIMIT,budget=None):
        if depth>4:raise CIPError(8,'Nested message depth limit')
        need(raw,2);service=raw[0];end=2+raw[1]*2;need(raw,end)
        path=decode_path(raw[2:end]);data=raw[end:]
        if path.class_id==6 and path.instance==1 and not path.symbols and path.attribute is None:
            if service in (0x54,0x5B):return self.forward_open(data,session,service==0x5B)
            if service==0x4E:return self.forward_close(data,session)
            if service==0x52:
                need(data,4);size=struct.unpack_from('<H',data,2)[0];need(data,4+size+size%2+2)
                pos=4+size+size%2
                if size%2 and data[4+size]:raise CIPError(4,'Nonzero message padding')
                if data[pos+1]:raise CIPError(4,'Nonzero route padding')
                exact(data,pos+2+data[pos]*2);route_ok(data[pos+2:])
                # Successful UCMM replies contain the embedded service response.
                return self.handle(data[4:4+size],session,depth+1,limit,budget),None
        if path.class_id==1 and not path.symbols:
            if path.instance==1:
                if service==0x4B:
                    if path.attribute is not None:raise CIPError(4,'Flash LEDs does not take an attribute')
                    exact(data,1)
                    self.endpoint.flash_leds(data[0])
                    return 0,b''
                if service==1 and path.attribute is None:exact(data,0);return 0,self.identity()
                return self.attribute_read(service,path,data,self.identity_attributes())
            elif path.instance in (None,0):
                return self.attribute_read(service,path,data,{1:b'\1\0',2:b'\1\0',3:b'\1\0',6:b'\7\0',7:b'\x08\x00'})
            raise CIPError(5,'Unknown Identity object instance')
        if path.class_id==2 and path.instance==1 and not path.symbols and service in (1,3,0x0E):
            classes=struct.pack('<12H',11,1,2,6,0x64,0x6B,0x6C,0xAC,0xF4,0xF5,0xF6,0x31A)
            if service==1 and path.attribute is None:exact(data,0);return 0,classes
            return self.attribute_read(service,path,data,{1:classes})
        if path.class_id in (0xF4,0xF5,0xF6):
            if path.symbols:raise CIPError(4,'Network object paths do not take symbols')
            instance=path.instance
            if instance is None:raise CIPError(4,'Network object path requires an instance')
            if path.class_id==0xF4:
                try:attributes=port_attributes(instance,self.endpoint.bind_address)
                except KeyError:raise CIPError(5,'Unknown Port object instance')
                if service==1 and path.attribute is None:
                    exact(data,0);return 0,b''.join(attributes.values())
            elif instance==0:
                attributes={1:b'\1\0',2:b'\1\0',3:b'\1\0'}
                if service==1 and path.attribute is None:
                    exact(data,0);return 0,b''.join(attributes.values())
            elif instance==1 and path.class_id==0xF6:
                attributes={}
                if service==0x0E:exact(data,0)
                requested=service==0x0E and path.attribute==3
                if service==3 and path.attribute is None:
                    need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
                    if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
                    requested=3 in struct.unpack_from('<'+'H'*count,data,2)
                if requested:
                    snapshot=self.network_interface()
                    if snapshot is None or snapshot.mac is None:raise CIPError(0x0C,'Ethernet MAC address is unavailable on this interface')
                    attributes[3]=snapshot.mac
            elif instance==1:
                if service==0x0E:exact(data,0)
                attributes={6:cip_string(socket.gethostname())}
                # Query the local OS only when the caller needs this attribute.
                # Unknown interface data is an error, never a guessed /24 or MAC.
                requested=service==0x0E and path.attribute in (4,5)
                if service==3 and path.attribute is None:
                    need(data,2);count=struct.unpack_from('<H',data)[0];exact(data,2+2*count)
                    if not 1<=count<=32:raise CIPError(3,'Attribute count must be 1..32')
                    requested=bool({4,5}.intersection(struct.unpack_from('<'+'H'*count,data,2)))
                if requested:
                    snapshot=self.network_interface()
                    attributes[4]=b'\2\0\x20\xF6\x24\1' if snapshot is not None and snapshot.mac else b'\0\0'
                    if snapshot is not None:attributes[5]=snapshot.configuration()
                    elif path.attribute==5 or service==3:raise CIPError(0x0C,'Local IPv4 configuration is unavailable')
            else:raise CIPError(5,'Unknown TCP/IP Interface object instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x31A:
            if path.symbols:raise CIPError(4,'File Manager paths do not take symbols')
            if path.instance!=0:raise CIPError(5,'No File Manager storage instances are modeled')
            return self.attribute_read(service,path,data,file_manager.class_attributes())
        if path.class_id==0xAC:
            if path.symbols:raise CIPError(4,'Controller metadata paths do not take symbols')
            if path.instance==0:
                # Common class metadata describes this implementation's revision
                # and its one modeled instance, not native firmware signatures.
                attributes={1:b'\1\0',2:b'\1\0',3:b'\1\0'}
            elif path.instance==1:
                attributes=CatalogRevision.from_source(self.app.engine.project.sha256).attributes()
            else:raise CIPError(5,'Unknown controller metadata instance')
            return self.attribute_read(service,path,data,attributes)
        if path.class_id==0x64 and path.instance==1 and not path.symbols and path.attribute is None and service==1:
            exact(data,0);name=self.app.engine.project.name.encode('ascii')
            if len(name)>255:raise CIPError(0x1B,'Controller project name exceeds supported size')
            return 0,struct.pack('<H',len(name))+name
        if path.class_id==0x64 and path.instance==1 and service==0x4B:
            if path.symbols or path.attribute is not None:raise CIPError(4,'Key challenge requires an object instance path')
            try:return 0,key_exchange.challenge(data)
            except key_exchange.OfferError as error:raise CIPError(error.status,str(error)) from error
        if path.class_id==2 and path.instance==1 and service==0x0A and not path.symbols and path.attribute is None:
            need(data,2);count=struct.unpack_from('<H',data)[0]
            if not 1<=count<=16:raise CIPError(3,'Multiple Service Packet limit is 16')
            need(data,2+2*count);offsets=list(struct.unpack_from('<'+'H'*count,data,2))
            if offsets[0]!=2+2*count or offsets!=sorted(set(offsets)) or offsets[-1]>=len(data):raise CIPError(0x13,'Invalid multiple-service offsets')
            results=[self.handle(data[a:b],session,depth+1,limit,budget) for a,b in zip(offsets,offsets[1:]+[len(data)])]
            base=2+2*count;positions=[]
            for r in results:positions.append(base);base+=len(r)
            if base>limit-4:raise CIPError(0x1B,'Multiple-service response exceeds model limit')
            return (0x1E if any(r[2] for r in results) else 0),struct.pack('<H'+'H'*count,count,*positions)+b''.join(results)
        if path.class_id==0x6B and service==0x55:return self.enumerate_symbols(path,data,limit)
        if path.class_id==0x6C:return self.template_service(service,path,data,limit)
        if path.class_id==0x6B and service in (3,0x0E):
            scope=self.symbol_scope(path)
            symbol=next((s for s in self.symbols(scope) if s['id']==path.instance),None)
            if symbol is None:raise CIPError(5,'Unknown symbol instance')
            return self.attribute_read(service,path,data,self.symbol_attributes(symbol))
        if service in (0x4C,0x52,0x4D,0x53,0x4E) and path.class_id in (None,0x6B):
            if service in (0x4D,0x53):return self.write_tag(path,data,service==0x53)
            if service==0x4E:return self.read_modify_write(path,data)
            return self.read_tag(path,data,service==0x52,limit)
        raise CIPError(8,f'Unsupported service 0x{service:02X} class {path.class_id}')

    def handle(self,raw,session,depth=0,limit=REPLY_LIMIT,budget=None):
        service=raw[0] if raw else 0;detail='';path=''
        try:
            if budget is None:budget=[128]
            budget[0]-=1
            if budget[0]<0:raise CIPError(2,'CIP dispatch budget exceeded')
            if len(raw)>=2:path=repr(decode_path(raw[2:2+raw[1]*2]))
            with self.app.lock:
                if session.handle and session.generation!=self.app.generation:raise CIPError(0x10,'Project generation changed; reconnect')
                if self.app.busy:raise CIPError(0x10,'Project import is in progress')
                if self.app.engine is None:raise CIPError(0x10,'No project loaded')
                status,data=self.dispatch(raw,session,depth,limit,budget)
            result=status if isinstance(status,bytes) and data is None else reply(service,status,data)
            if len(result)>limit:raise CIPError(0x1B,'Response exceeds negotiated connection size')
        except CIPError as e:result=reply(service,e.status);detail=str(e)
        except ModelError as e:result=reply(service,0x0C);detail=str(e)
        except (ValueError,TypeError,IndexError,KeyError,struct.error,OverflowError) as e:result=reply(service,0x13);detail=str(e)
        self.endpoint.record('cip',request=raw,response=result,service=f'0x{service:02X}',path=path,status=result[2],detail=detail,
                             peer=session.peer,session=session.handle,generation=session.generation)
        return result


def cpf(items):return struct.pack('<IHH',0,0,len(items))+b''.join(struct.pack('<HH',kind,len(data))+data for kind,data in items)


def decode_cpf(data):
    need(data,8);interface,_,count=struct.unpack_from('<IHH',data)
    if interface or count!=2:raise CIPError(0x13,'Only two-item CIP CPF is supported')
    result=[];pos=8
    for _ in range(count):
        need(data[pos:],4);kind,size=struct.unpack_from('<HH',data,pos);pos+=4;need(data[pos:],size)
        result.append((kind,data[pos:pos+size]));pos+=size
    exact(data,pos);return result


class Endpoint:
    def __init__(self,app,port=44818,allow_writes=False,profile='research',bind_address='127.0.0.1'):
        from ipaddress import IPv4Address
        try:
            if not isinstance(bind_address,str):raise ValueError('Expected IPv4 text')
            address=IPv4Address(bind_address)
            if address.packed[0]==0 or address.is_multicast or address.is_reserved:
                raise ValueError('Expected a specific unicast address')
        except ValueError as error:
            raise ModelError('Bind IP must be a specific unicast IPv4 address assigned to this PC') from error
        if isinstance(port,bool) or not isinstance(port,int) or not 0<=port<=65535:raise ModelError('EtherNet/IP port must be 0..65535')
        if not isinstance(allow_writes,bool):raise ModelError('allow_writes must be boolean')
        self.bind_address=str(address)
        self.app=app;self.allow_writes=allow_writes;self.port=port;self.router=Router(app,self)
        if app.engine is None:raise ModelError('Load a project before selecting an identity')
        self.profile=profile;self.identity=Identity.from_project(profile,app.engine.project)
        self.source_sha256=app.engine.project.sha256
        self.lock=threading.RLock();self.events=deque(maxlen=1000);self.counts=Counter();self.unsupported=Counter()
        self.connections=set();self.threads=[];self.tcp=None;self.udp=None;self.enabled=False;self.slots=threading.BoundedSemaphore(16)
        self._locator_clock=time.monotonic;self._locator_until=0.0;self._locator_started=0.0;self._locator_request=None
        self.interface=None;self.interface_error=None;self.interface_queried=False
        self.broadcast_servers=[]
        self.discovery_status={'broadcast_enabled':False,'broadcast_addresses':[],'interface':None,'reason':'Endpoint is stopped'}

    def flash_leds(self,seconds):
        # Identification is independent of application tag-write permission.
        if isinstance(seconds,bool) or not isinstance(seconds,int) or not (seconds==0 or 9<=seconds<=255):
            raise CIPError(3,'Flash LEDs time must be zero or 9..255 seconds')
        with self.lock:
            if not self.enabled:raise CIPError(0x10,'Endpoint is stopped')
            now=self._locator_clock();self._locator_started=now
            self._locator_until=now+seconds if seconds else 0.0
            self._locator_request=secrets.token_hex(8)
            self.record('locator',duration_seconds=seconds)

    def locator_state(self):
        # Caller holds endpoint.lock; no app lock or wall-clock dependency.
        now=self._locator_clock();remaining=max(0.0,self._locator_until-now) if self.enabled else 0.0
        return {'active':remaining>0,'remaining_ms':math.ceil(remaining*1000),
                'elapsed_ms':max(0,int((now-self._locator_started)*1000)) if remaining else 0,
                'request_id':self._locator_request}

    def record(self,kind,request=b'',response=b'',**fields):
        with self.lock:
            self.counts[kind]+=1
            if kind=='cip' and fields.get('status') in (8,0x0A,0x14):
                key=fields.get('service','')+' '+fields.get('path','')
                self.unsupported[key if key in self.unsupported or len(self.unsupported)<128 else 'Other unsupported requests']+=1
            self.events.append({'time':time.time(),'kind':kind,**fields,'request_hex':request[:1024].hex(),
                                'response_hex':response[:1024].hex(),'truncated':len(request)>1024 or len(response)>1024})

    def state(self,trace=False):
        with self.lock:
            result={'enabled':self.enabled,'address':f'{self.bind_address}:{self.port}','bind_address':self.bind_address,'allow_writes':self.allow_writes,
                    'identity':self.identity.description(),'profile':self.profile,'source_l5x_sha256':self.source_sha256,
                    'catalog_revision':CatalogRevision.from_source(self.source_sha256).description() if self.enabled else None,
                    'file_manager':file_manager.description() if self.enabled else None,
                    'key_exchange':key_exchange.description() if self.enabled else None,
                    'locator':self.locator_state(),
                    'network_interface':self.interface.description() if self.interface else None,
                    'network_interface_error':self.interface_error,'network_interface_queried':self.interface_queried,
                    'discovery':{**self.discovery_status,'broadcast_enabled':self.enabled and bool(self.broadcast_servers)},
                    'active_tcp_clients':len(self.connections),'counts':dict(self.counts),
                    'unsupported':[{'request':k,'count':v} for k,v in self.unsupported.most_common(20)],
                    'studio_go_online':'NOT IMPLEMENTED OR VERIFIED','trace_events':len(self.events)}
            if trace:result['events']=list(self.events)
            return result

    def discovery(self,command):
        if command==0x63:
            addr=struct.pack('>HH4s8s',2,self.port,socket.inet_aton(self.bind_address),b'\0'*8)
            with self.lock:identity=self.identity
            item=struct.pack('<H',1)+addr+identity.all_attributes()+identity.attributes()[8]
            return struct.pack('<HHH',1,0x0C,len(item))+item
        if command==4:
            item=struct.pack('<HH',1,0x20)+b'Communications'.ljust(16,b'\0')
            return struct.pack('<HHH',1,0x100,len(item))+item
        if command==0x64:return b'\x00\x00'
        raise CIPError(8,'Unknown discovery command')

    def packet(self,raw,session,udp=False):
        if len(raw)<24:return None
        command,size,handle,status,context,options=HEADER.unpack_from(raw)
        # A nonzero status is an encapsulation error reply from the peer.
        # Reflecting another error can make two implementations reply forever.
        if status:
            self.record('peer_error',request=raw,command=f'0x{command:04X}',status=status,
                        transport='udp' if udp else 'tcp',peer=session.peer,session=handle)
            return None
        result=b'';error=0;out_handle=handle
        if size!=len(raw)-24 or options:error=3
        elif command in (4,0x63,0x64):
            if size:error=3
            else:result=self.discovery(command)
        elif udp:error=1
        elif command==0x65:
            if raw[24:]!=b'\x01\x00\x00\x00' or handle:error=0x69
            elif session.handle:error=3
            else:
                session.handle=secrets.randbits(32) or 1;session.generation=self.app.generation
                out_handle=session.handle;result=raw[24:]
        elif command in (0x66,0x6F,0x70):
            if not session.handle or handle!=session.handle or session.generation!=self.app.generation:error=0x64
            elif command==0x66:
                if size:error=3
                else:session.handle=0;session.connections.clear();return None
            else:
                try:
                    items=decode_cpf(raw[24:])
                    if command==0x6F:
                        if items[0]!=(0,b'') or items[1][0]!=0xB2:raise CIPError(0x13,'Invalid unconnected CPF')
                        result=cpf([(0,b''),(0xB2,self.router.handle(items[1][1],session))])
                    else:
                        if items[0][0]!=0xA1 or len(items[0][1])!=4 or items[1][0]!=0xB1:raise CIPError(0x13,'Invalid connected CPF')
                        conn=session.connections.get(struct.unpack('<I',items[0][1])[0]);data=items[1][1];need(data,4)
                        if conn is None:raise CIPError(1,'Unknown connected address')
                        if len(data)>conn.incoming_size:raise CIPError(0x13,'Request exceeds negotiated connection size')
                        seq=struct.unpack_from('<H',data)[0]
                        if conn.last_sequence==seq:
                            if conn.last_request!=data:raise CIPError(1,'Sequence reused with different message')
                            response=conn.last_reply
                        else:
                            if conn.last_sequence is not None and not 0<(seq-conn.last_sequence)&0xFFFF<0x8000:raise CIPError(1,'Stale connected sequence')
                            response=data[:2]+self.router.handle(data[2:],session,limit=min(REPLY_LIMIT,conn.outgoing_size-2))
                            conn.last_sequence,conn.last_request,conn.last_reply=seq,data,response
                        result=cpf([(0xA1,struct.pack('<I',conn.outgoing)),(0xB1,response)])
                except CIPError as e:error=3;self.record('cpf_error',request=raw,status=e.status,detail=str(e))
        elif command==0:return None
        else:error=1
        response=HEADER.pack(command,len(result),out_handle,error,context,0)+result
        self.record('encapsulation',request=raw,response=response,command=f'0x{command:04X}',status=error,transport='udp' if udp else 'tcp',peer=session.peer,session=out_handle)
        return response

    def start(self):
        endpoint=self
        class TCP(socketserver.ThreadingTCPServer):
            daemon_threads=True;block_on_close=False
            # Linux requires this on both old and new sockets to restart after
            # a server-closed connection enters TIME_WAIT. SO_REUSEPORT is not
            # enabled: another active listener must still make startup fail.
            allow_reuse_address=sys.platform=='linux'
            def process_request(self,request,address):
                if not endpoint.slots.acquire(False):request.close();return
                try:super().process_request(request,address)
                except Exception:endpoint.slots.release();raise
            def process_request_thread(self,request,address):
                try:super().process_request_thread(request,address)
                finally:endpoint.slots.release()
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                conn=self.request;conn.settimeout(30);session=Session(peer=str(self.client_address))
                with endpoint.lock:endpoint.connections.add(conn)
                endpoint.record('client_open',peer=str(self.client_address))
                def read(size):
                    data=b''
                    while len(data)<size:
                        chunk=conn.recv(size-len(data))
                        if not chunk:return None
                        data+=chunk
                    return data
                try:
                    while endpoint.enabled:
                        header=read(24)
                        if header is None:break
                        size=HEADER.unpack(header)[1]
                        if size>32768:endpoint.record('frame_rejected',detail='Frame exceeds 32768 bytes');break
                        body=read(size)
                        if body is None:break
                        response=endpoint.packet(header+body,session)
                        if response is not None:conn.sendall(response)
                except (OSError,ValueError) as e:endpoint.record('client_closed',detail=str(e))
                finally:
                    with endpoint.lock:endpoint.connections.discard(conn)
        class UDPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                raw,sock=self.request
                if len(raw)>32792:return
                response=endpoint.packet(raw,Session(peer=str(self.client_address)),True)
                if response is not None:sock.sendto(response,self.client_address)
        requested_port=self.port;attempts=8 if requested_port==0 else 1
        for attempt in range(attempts):
            try:
                transport='TCP'
                self.tcp=TCP((self.bind_address,requested_port),Handler);self.port=self.tcp.server_address[1]
                transport='UDP'
                self.udp=socketserver.UDPServer((self.bind_address,self.port),UDPHandler)
                break
            except OSError as e:
                failed_port=self.port
                for server in (self.tcp,self.udp):
                    if server:server.server_close()
                self.tcp=self.udp=None;self.port=requested_port
                if attempt+1==attempts:
                    raise ModelError(f'Cannot bind EtherNet/IP {transport} at {self.bind_address}:{failed_port}: {e}. '
                        'Use an IP assigned to this PC and a free TCP/UDP port. A listener on 0.0.0.0 may also reserve this port.') from e
        self.broadcast_servers,self.discovery_status=prepare_broadcasts(self.bind_address,self.port,
            lambda raw,peer:self.packet(raw,Session(peer=str(peer)),True),self.record)
        self.enabled=True
        for server in (self.tcp,self.udp,*self.broadcast_servers):
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True);thread.start();self.threads.append(thread)
        self.record('started',detail='Local research endpoint; Studio Go Online is unverified')
        return self

    def stop(self):
        with self.lock:self.enabled=False;self._locator_until=0.0
        with self.lock:clients=list(self.connections)
        for conn in clients:
            try:conn.shutdown(socket.SHUT_RDWR);conn.close()
            except OSError:pass
        for server in (self.tcp,self.udp,*self.broadcast_servers):
            if server:server.shutdown();server.server_close()
        self.record('stopped')
