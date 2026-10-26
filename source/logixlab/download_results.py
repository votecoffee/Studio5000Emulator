"""Preparation results and the observed completed-batch execution-status profile.

The private ledger retains typed model effects and ordered request fingerprints.
Its per-operation outcomes have no native encoding. The separate seven-byte
progress profile reports coverage of a completed temporary batch only.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import struct

from . import diagnostic_staging,object_staging,template_staging

MAX_PAGE_RECORDS=64
MAX_RESULTS=4096


class ResultError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


@dataclass(frozen=True)
class ExecutionStatus:
    """Observed seven-byte progress profile; trailing-word semantics stay opaque."""
    state:int
    processed_bytes:int

    @property
    def complete(self):return self.state==0

    @classmethod
    def decode(cls,data,expected_bytes):
        if (type(expected_bytes) is not int or not 1<=expected_bytes<=0xFFFFFFFF
                or not isinstance(data,bytes) or len(data)!=7):
            raise ResultError('download_execution_status_layout')
        state,processed,detail=struct.unpack('<BIH',data)
        if state not in (0,6) or detail or processed>expected_bytes or state==0 and processed!=expected_bytes:
            raise ResultError('download_execution_status_profile')
        return cls(state,processed)

    def encode(self,expected_bytes):
        if (type(self.state) is not int or type(self.processed_bytes) is not int
                or not 0<=self.state<=255 or not 0<=self.processed_bytes<=0xFFFFFFFF):
            raise ResultError('download_execution_status_profile')
        raw=struct.pack('<BIH',self.state,self.processed_bytes,0)
        self.decode(raw,expected_bytes)
        return raw


@dataclass(frozen=True)
class TemplateCreate:
    words:int
    definition_bytes:int


@dataclass(frozen=True)
class TemplateAttributes:
    attributes:template_staging.Attributes


@dataclass(frozen=True)
class TemplateWrite:
    offset:int
    count:int
    data_sha256:str


@dataclass(frozen=True)
class DiagnosticCreate:
    revision:int
    message_id_bytes:int
    message_id_sha256:str
    code_bytes:int
    code_sha256:str


@dataclass(frozen=True)
class SymbolCreate:
    table:int|tuple
    safety:int=0


@dataclass(frozen=True)
class TableCreate:
    data_use:int
    type_code:int
    dimensions:tuple
    symbol:int
    elements:int
    storage_bytes:int
    allocation_sha256:str


@dataclass(frozen=True)
class ProgramCreate:
    retained:bool=True


@dataclass(frozen=True)
class RoutineCreate:
    create_word:int


@dataclass(frozen=True)
class CoordinationChange:
    held_before:bool
    held_after:bool


Effect=TemplateCreate|TemplateAttributes|TemplateWrite|DiagnosticCreate|SymbolCreate|TableCreate|ProgramCreate|RoutineCreate|CoordinationChange


@dataclass(frozen=True)
class OperationResult:
    ordinal:int
    service:int
    scopes:tuple
    request_bytes:int
    request_sha256:str
    effect:Effect


@dataclass(frozen=True)
class OperationCount:
    service:int
    class_id:int
    count:int


@dataclass(frozen=True)
class EffectReadback:
    result:OperationResult
    observed:Effect
    matches:bool
    historical_transition:bool=False


def _hash(raw):return hashlib.sha256(raw).hexdigest()


def _template(image,instance):
    row=next((t for t in image.templates if t.instance==instance),None)
    if row is None:raise ResultError('download_result_template_unavailable')
    return row


def _diagnostic(image,instance):
    row=next((d for d in image.diagnostics if d.instance==instance),None)
    if row is None:raise ResultError('download_result_diagnostic_unavailable')
    return DiagnosticCreate(row.revision,len(row.message_id),_hash(row.message_id),len(row.code),_hash(row.code))


def _table(image,instance):
    row=image._tables[instance];region=image._regions[instance]
    if row.key!=instance or (row.program,row.instance)!=(region.program,region.instance):
        raise ResultError('download_result_table_scope_mismatch')
    return TableCreate(row.data_use,row.type_code,row.dimensions,row.symbol,row.elements,
                       len(region.data),_hash(region.data))


def _observed(image,result):
    cls,instance=result.scopes[-1];program=result.scopes[0][1] if len(result.scopes)==2 else 0
    effect=result.effect
    if isinstance(effect,TemplateCreate):
        row=_template(image,instance);return TemplateCreate(row.words,len(row.definition))
    if isinstance(effect,TemplateAttributes):return TemplateAttributes(_template(image,instance).attributes)
    if isinstance(effect,TemplateWrite):
        data=_template(image,instance).definition[effect.offset:effect.offset+effect.count]
        return TemplateWrite(effect.offset,len(data),_hash(data))
    if isinstance(effect,DiagnosticCreate):return _diagnostic(image,instance)
    if isinstance(effect,SymbolCreate):return SymbolCreate(image._symbols[program,instance])
    if isinstance(effect,TableCreate):return _table(image,object_staging.table_key(program,instance))
    if isinstance(effect,ProgramCreate):return ProgramCreate(instance in image.programs)
    if isinstance(effect,RoutineCreate):
        row=next((r for r in image.routines if (r.program,r.instance)==(program,instance)),None)
        if row is None:raise ResultError('download_result_routine_unavailable')
        return RoutineCreate(row.create_word)
    if isinstance(effect,CoordinationChange):return effect
    raise ResultError('download_result_effect_unavailable')


@dataclass(frozen=True)
class ResultLedger:
    results:tuple=()
    counts:tuple=()
    record_sha256:str|None=None
    source_acd_sha256:str|None=None
    source_l5x_sha256:str|None=None

    @classmethod
    def from_image(cls,batch,image):
        if not 1<=len(batch)<=MAX_RESULTS:raise ResultError('download_result_count_limit')
        results=[];held=set();coordination=0;digest=hashlib.sha256()
        try:
            for ordinal,record in enumerate(batch):
                scopes=tuple((s.class_id,s.instance) for s in record.scopes)
                cls_id,instance=scopes[-1];program=scopes[0][1] if len(scopes)==2 else 0
                payload=record.request[2+2*record.request[1]:];service=record.service
                if cls_id==0x6C:
                    row=_template(image,instance)
                    if service==8:
                        if payload!=b'\1\0\4\0'+struct.pack('<I',row.words):raise ResultError('download_result_effect_mismatch')
                        effect=TemplateCreate(row.words,len(row.definition))
                    elif service==4:
                        if template_staging.attributes(payload)!=row.attributes:raise ResultError('download_result_effect_mismatch')
                        effect=TemplateAttributes(row.attributes)
                    elif service==0x4D:
                        offset,count=struct.unpack_from('<IH',payload)
                        data=row.definition[offset:offset+count]
                        if len(payload)!=count+6 or data!=payload[6:]:raise ResultError('download_result_effect_mismatch')
                        effect=TemplateWrite(offset,count,_hash(data))
                    else:raise ResultError('download_result_operation_unavailable')
                elif cls_id==0x3B2 and service==8:
                    expected=diagnostic_staging.create(instance,payload)
                    row=next((d for d in image.diagnostics if d.instance==instance),None)
                    if expected!=row:raise ResultError('download_result_effect_mismatch')
                    effect=_diagnostic(image,instance)
                elif cls_id==0x6B and service==8:
                    fields=object_staging.attributes(payload,{12:4,9:1})
                    table=object_staging.table_key(program,int.from_bytes(fields[12],'little'))
                    if image._symbols[program,instance]!=table or fields[9]!=b'\0':raise ResultError('download_result_effect_mismatch')
                    effect=SymbolCreate(table)
                elif cls_id==0x6A and service==8:
                    expected=object_staging.table(instance,payload,{t.instance:t for t in image.templates},program)
                    key=object_staging.table_key(program,instance)
                    if expected!=image._tables[key]:raise ResultError('download_result_effect_mismatch')
                    effect=_table(image,key)
                    if effect.storage_bytes!=expected.storage_bytes:raise ResultError('download_result_effect_mismatch')
                elif cls_id==0x68 and service==8:
                    if payload or instance not in image.programs:raise ResultError('download_result_effect_mismatch')
                    effect=ProgramCreate()
                elif cls_id==0x6D and service==8:
                    row=next((r for r in image.routines if (r.program,r.instance)==(program,instance)),None)
                    if row is None or payload!=struct.pack('<H',row.create_word):raise ResultError('download_result_effect_mismatch')
                    effect=RoutineCreate(row.create_word)
                elif cls_id==0x74 and service in (0x4B,0x4C):
                    acquire=service==0x4B;before=program in held
                    if (not program or instance!=1 or program not in image.programs or before==acquire
                            or payload!=(b'\1' if acquire else b'')):
                        raise ResultError('download_result_coordination_mismatch')
                    if acquire:held.add(program)
                    else:held.remove(program)
                    effect=CoordinationChange(before,acquire);coordination+=1
                else:raise ResultError('download_result_operation_unavailable')
                digest.update(struct.pack('<I',len(record.request)));digest.update(record.request)
                results.append(OperationResult(ordinal,service,scopes,len(record.request),_hash(record.request),effect))
        except (KeyError,struct.error,template_staging.TemplateError,diagnostic_staging.DiagnosticError,object_staging.ObjectError) as error:
            raise ResultError('download_result_resource_mismatch') from error
        if held:raise ResultError('download_result_coordination_incomplete')
        if coordination!=image._coordination_records:raise ResultError('download_result_coordination_mismatch')
        actual_digest=digest.hexdigest()
        if actual_digest!=image.record_sha256 or len(results)!=image.records:raise ResultError('download_result_record_binding_mismatch')
        counts=Counter((r.service,r.scopes[-1][0]) for r in results)
        return cls(tuple(results),tuple(OperationCount(s,c,n) for (s,c),n in sorted(counts.items())),actual_digest,
                   image.source.acd_sha256,image.source.l5x_sha256)

    def page(self,offset,count):
        if (type(offset) is not int or type(count) is not int or not 0<=offset<=len(self.results)
                or not 1<=count<=MAX_PAGE_RECORDS):raise ResultError('download_result_page_range')
        return self.results[offset:offset+count]

    def readback(self,image,ordinal):
        if type(ordinal) is not int or not 0<=ordinal<len(self.results):raise ResultError('download_result_ordinal_range')
        result=self.results[ordinal]
        try:observed=_observed(image,result)
        except KeyError as error:raise ResultError('download_result_resource_unavailable') from error
        return EffectReadback(result,observed,observed==result.effect,isinstance(result.effect,CoordinationChange))

    def description(self):
        return {'status':'available' if self.results else 'idle','records':len(self.results),'immutable':True,
                'max_records':MAX_RESULTS,'max_page_records':MAX_PAGE_RECORDS,
                'operations':[{'service':c.service,'class_id':c.class_id,'count':c.count} for c in self.counts],
                'private_internal_only':True,'wire_encoding_supported':False,'vendor_status_exposed':False,
                'request_bytes_exposed':False,'object_identifiers_exposed':False}
