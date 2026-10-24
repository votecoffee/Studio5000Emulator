"""Private later-batch Routine components with source-equivalent ladder logic.

Compiled bytes are opaque retained artifacts. The simulator uses its source
model; this module never links or executes ELF code or installs a project.
"""
from dataclasses import dataclass
import hashlib
import struct
from types import MappingProxyType
from . import device_payload,routine_source
from .download_image import ImageError
from .download_properties import controller_profile
from .incremental_download import record_digest,UpdateResult
from .model import parse_rung

MAX_STORAGE=2*1024*1024
MAX_COMPONENT=262144


class RoutineBindings:
    def __init__(self,headers,types):self.headers=headers;self.types=types

    def stamp(self):
        h=self.headers;project=h.engine.project;source=h.source
        profile=controller_profile(project,source)
        if (self.types is None or self.types.source_acd_sha256!=source.acd_sha256
                or self.types.source_l5x_sha256!=source.l5x_sha256):raise ImageError('download_routine_types_required')
        body=tuple((key,row.kind,repr([r['nodes'] for r in row.rungs])) for key,row in sorted(project.routines.items()))
        return hashlib.sha256(repr((profile,h.stamp(h.namespace._image,source),self.types.binding_stamp(),body)).encode()).hexdigest()

    def source(self,target,blob):
        row=self.headers._routine(*target);project=self.headers.engine.project
        try:
            active=project.routines[(row.program+'/'+row.name).casefold()]
            decoded=routine_source.decode_download(blob,empty=not active.rungs and not active.problems)
            if decoded.name.casefold()!=row.name.casefold():raise ImageError('download_routine_source_target_mismatch')
            neutral=routine_source.resolve(decoded,project,self.headers.symbols,self.headers.routines,self.types,row.program)
            if len(neutral)!=len(active.rungs) or any(parse_rung(text)!=rung['nodes'] for text,rung in zip(neutral,active.rungs,strict=True)):
                raise ImageError('download_routine_source_logic_mismatch')
            routine_source.validate_plan(decoded,neutral,project,row.program)
        except routine_source.SourceError as error:raise ImageError(str(error)) from error
        return decoded


@dataclass(frozen=True)
class Components:
    marker:int
    code:bytes
    source:bytes
    attachment:bytes
    source_rungs:int


class RoutineBatch:
    def __init__(self):
        self._values=MappingProxyType({});self._coordination=();self._effects=();self._binding=None
        self.records=0;self.record_sha256=None;self._digest=None

    def _effect(self):
        return hashlib.sha256(repr((tuple(sorted(self._values.items())),self._coordination,self._effects,
            self.records,self.record_sha256)).encode()).hexdigest()

    @classmethod
    def prepare(cls,batch,bindings):
        stamp=bindings.stamp();image=bindings.headers.namespace._image
        proposal=cls();pending={};held=set();coordination=[];effects=[];storage=0
        if not batch or len(batch)>device_payload.MAX_RECORDS:raise ImageError('download_routine_record_limit')
        for ordinal,row in enumerate(batch):
            if (type(row.request) is not bytes or len(row.request)<2 or not row.scopes
                    or row.service!=row.request[0] or 2+2*row.request[1]>len(row.request)):
                raise ImageError('download_routine_record_invalid')
            try:scopes=device_payload.record_path(row.request[2:2+2*row.request[1]])
            except device_payload.PayloadError as error:raise ImageError('download_routine_record_invalid') from error
            if scopes!=row.scopes:raise ImageError('download_routine_record_invalid')
            leaf=row.scopes[-1];body=row.request[2+2*row.request[1]:]
            if row.service in (0x4B,0x4C) and len(row.scopes)==2 and row.scopes[0].class_id==0x68 and leaf.class_id==0x74:
                if any(s.attribute is not None or s.symbolic for s in row.scopes) or leaf.instance!=1:
                    raise ImageError('download_routine_coordination_scope')
                program=row.scopes[0].instance;before=program in held
                if program not in image.programs:raise ImageError('download_routine_program_missing')
                if row.service==0x4B:
                    if body!=b'\0' or before:raise ImageError('download_routine_acquire_invalid')
                    held.add(program)
                else:
                    if body or not before:raise ImageError('download_routine_release_invalid')
                    held.remove(program)
                value=(program,before,program in held);key=(len(coordination),);coordination.append(value);kind='coordination'
            elif row.service==0x33 and row.scopes==(device_payload.Scope(2,1),):
                if len(body)<10:raise ImageError('download_routine_container_extent')
                version,size=struct.unpack_from('<II',body);inner=body[8:];end=2+2*inner[1]
                if version!=0x301 or end>len(inner) or inner[0]!=0x5C:raise ImageError('download_routine_container_profile')
                try:scopes=device_payload.record_path(inner[2:end])
                except device_payload.PayloadError as error:raise ImageError('download_routine_target_scope') from error
                if (len(scopes)!=2 or scopes[0].class_id!=0x68 or scopes[1].class_id!=0x6D
                        or any(s.attribute is not None or s.symbolic for s in scopes)):
                    raise ImageError('download_routine_target_scope')
                key=(scopes[0].instance,scopes[1].instance)
                if key[0] not in held:raise ImageError('download_routine_reservation_required')
                bindings.headers._routine(*key);data=inner[end:]
                if len(data)>MAX_COMPONENT:raise ImageError('download_routine_component_limit')
                entry=pending.setdefault(key,{})
                if data[:8]==struct.pack('<II',3,1):
                    if (entry or len(data)<88 or size!=len(data)-16 or data[12:16]!=bytes(4)
                            or data[8:12]==bytes(4)):raise ImageError('download_routine_code_profile')
                    code=data[16:]
                    if (code[:12]!=struct.pack('<III',9,0,0) or struct.unpack_from('<I',code,16)[0]!=len(code)-20
                            or code[20:24]!=b'\x7fELF'):raise ImageError('download_routine_code_container')
                    entry['marker']=struct.unpack_from('<I',data,8)[0];kind='code'
                elif data[:8]==struct.pack('<II',1,3):
                    if size!=len(data)-8:raise ImageError('download_routine_source_sequence')
                    decoded=bindings.source(key,data[8:])
                    if decoded.rungs:
                        if set(entry)!={'marker','code'}:raise ImageError('download_routine_source_sequence')
                    else:
                        if entry:raise ImageError('download_routine_empty_code_unexpected')
                        # This native empty target has no code component. Keep
                        # absence explicit; never fabricate an ELF or a NOP.
                        entry.update(marker=0,code=b'')
                    entry['source_rungs']=len(decoded.rungs);kind='source'
                else:
                    if set(entry)!={'marker','code','source','source_rungs'}:
                        raise ImageError('download_routine_attachment_profile')
                    if entry['source_rungs']==0:
                        valid=size==4 and data==struct.pack('<4I',2,5,0,0)
                    else:
                        valid=(size==8 and len(data)==20 and data[:16]==struct.pack('<4I',2,5,0,1)
                               and struct.unpack_from('<I',data,16)[0]==entry['marker'])
                    if not valid:
                        raise ImageError('download_routine_attachment_profile')
                    kind='attachment'
                entry[kind]=data;value=data;storage+=len(data)
                if storage>MAX_STORAGE:raise ImageError('download_routine_storage_limit')
            else:raise ImageError('download_routine_operation_unsupported')
            effects.append(UpdateResult(ordinal,hashlib.sha256(row.request).hexdigest(),kind,key,value))
        expected={(row.program,row.instance) for row in image.routines}
        if held or set(pending)!=expected or any(set(v)!={'marker','code','source','source_rungs','attachment'} for v in pending.values()):
            raise ImageError('download_routine_batch_incomplete')
        if bindings.stamp()!=stamp:raise ImageError('download_routine_source_changed')
        proposal._values=MappingProxyType({key:Components(**value) for key,value in pending.items()})
        proposal._coordination=tuple(coordination);proposal._effects=tuple(effects);proposal._binding=stamp
        proposal.records=len(effects);proposal.record_sha256=record_digest(batch);proposal._digest=proposal._effect()
        proposal.verify_effects(bindings)
        return proposal

    def verify_effects(self,bindings):
        if self._binding is None or bindings is None or bindings.stamp()!=self._binding:
            raise ImageError('download_routine_binding_changed')
        if self._effect()!=self._digest or len(self._effects)!=self.records:raise ImageError('download_routine_effect_changed')
        for ordinal,result in enumerate(self._effects):
            if result.ordinal!=ordinal:raise ImageError('download_routine_ledger_changed')
            value=(self._coordination[result.key[0]] if result.kind=='coordination'
                   else getattr(self._values[result.key],result.kind))
            if value!=result.expected:raise ImageError('download_routine_readback_mismatch')

    def read(self,program,routine,kind,bindings):
        self.verify_effects(bindings)
        if (type(program) is not int or type(routine) is not int or (program,routine) not in self._values
                or kind not in ('code','source','attachment')):raise ImageError('download_routine_read_unavailable')
        value=getattr(self._values[program,routine],kind)
        if kind=='code' and not value:raise ImageError('download_routine_code_unavailable')
        return value

    def description(self):
        return dict(records=self.records,routines=len(self._values),source_rungs=sum(v.source_rungs for v in self._values.values()),
            empty_routines=sum(v.source_rungs==0 for v in self._values.values()),
            storage_bytes=sum(len(v.code)+len(v.source)+len(v.attachment) for v in self._values.values()),
            source_logic_matched=self._binding is not None,compiled_code_verified=False,compiled_code_executed=False,
            active_project_changed=False,commit=False,payloads_exposed=False)
