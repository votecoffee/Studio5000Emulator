"""Temporary Diagnostics Message definitions from a native device batch.

These descriptors do not install controller diagnostics or execute messages.
Only the observed Create profile is modeled; unrelated operations never dispatch.
"""
from dataclasses import dataclass
import re
import struct

CLASS_ID = 0x3B2
MAX_MESSAGES = 1024
MAX_ID_BYTES = 40
MAX_CODE_BYTES = 255
MAX_TEXT_BYTES = 65536


class DiagnosticError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


@dataclass(frozen=True)
class Message:
    instance:int
    message_id:bytes
    code:bytes
    revision:int


def create(instance,payload):
    """Three unique attributes, with short strings and an unsigned revision."""
    if not isinstance(payload,bytes) or len(payload)<2 or struct.unpack_from('<H',payload)[0]!=3:
        raise DiagnosticError('invalid_diagnostic_create')
    values={};offset=2
    for _ in range(3):
        if offset+2>len(payload):raise DiagnosticError('invalid_diagnostic_attributes')
        attr=struct.unpack_from('<H',payload,offset)[0];offset+=2
        if attr not in (1,2,3) or attr in values:raise DiagnosticError('invalid_diagnostic_attributes')
        if attr==3:
            if offset+2>len(payload):raise DiagnosticError('invalid_diagnostic_attributes')
            values[attr]=struct.unpack_from('<H',payload,offset)[0];offset+=2
        else:
            if offset>=len(payload):raise DiagnosticError('invalid_diagnostic_string')
            size=payload[offset];offset+=1;limit=MAX_ID_BYTES if attr==1 else MAX_CODE_BYTES
            if not 1<=size<=limit or offset+size>len(payload):raise DiagnosticError('invalid_diagnostic_string')
            value=payload[offset:offset+size];offset+=size
            if (attr==1 and re.fullmatch(rb'[A-Za-z_][A-Za-z_0-9]*',value) is None
                    or attr==2 and any(not 32<=c<127 for c in value)):
                raise DiagnosticError('unsupported_diagnostic_string')
            values[attr]=value
    if offset!=len(payload):raise DiagnosticError('invalid_diagnostic_attributes')
    return Message(instance,values[1],values[2],values[3])


class DiagnosticStaging:
    def __init__(self,messages=()):self.messages=tuple(messages)

    @classmethod
    def from_batch(cls,batch):
        messages=[];instances=set();names=set();size=0
        for record in batch:
            scope=record.scopes[-1]
            if scope.class_id!=CLASS_ID:continue
            if (len(record.scopes)!=1 or scope.attribute is not None or scope.symbolic
                    or not 1<=scope.instance<=0xFFFFFFFF):raise DiagnosticError('unsupported_diagnostic_path')
            if record.service!=8:continue
            message=create(scope.instance,record.request[2+2*record.request[1]:])
            if message.instance in instances or message.message_id in names:raise DiagnosticError('duplicate_diagnostic_message')
            size+=len(message.message_id)+len(message.code)
            if len(messages)>=MAX_MESSAGES or size>MAX_TEXT_BYTES:raise DiagnosticError('diagnostic_stage_full')
            instances.add(message.instance);names.add(message.message_id);messages.append(message)
        return cls(messages)

    def description(self):
        return {'status':'modeled' if self.messages else 'idle','messages':len(self.messages),
                'text_bytes':sum(len(m.message_id)+len(m.code) for m in self.messages),'records_modeled':len(self.messages),
                'max_messages':MAX_MESSAGES,'max_text_bytes':MAX_TEXT_BYTES,
                'definitions_exposed':False,'active_catalog_replaced':False,'commit':False}
