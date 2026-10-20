"""Temporary Template objects from the observed native device-batch dialect.

Definitions remain temporary bytes. Member structure is inspected separately;
this model does not install types, map storage or authorize batch execution.
"""
from dataclasses import dataclass
import struct
from .template_layout import Inspection

MAX_TEMPLATES = 1024
MAX_DEFINITION_BYTES = 65536
MAX_TOTAL_BYTES = 1024*1024
MAX_STRUCTURE_BYTES = 1024*1024
MAX_MEMBERS = 4096
MAX_WRITE_BYTES = 16384


class TemplateError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


@dataclass(frozen=True)
class Attributes:
    handle:int
    members:int
    structure_bytes:int
    family:int
    recon:int


@dataclass(frozen=True)
class Template:
    instance:int
    words:int
    attributes:Attributes
    definition:bytes


def create(payload):
    if len(payload)!=8 or payload[:4]!=b'\1\0\4\0':raise TemplateError('invalid_template_create')
    words=struct.unpack_from('<I',payload,4)[0]
    # The observed download profile includes three more padding bytes than
    # the documented read-size formula (4*words - 23).
    if not 20<4*words<=MAX_DEFINITION_BYTES+20:raise TemplateError('template_definition_limit')
    return words


def attributes(payload):
    widths={1:2,2:2,5:4,6:2,8:1};values={};offset=2
    if len(payload)<2 or struct.unpack_from('<H',payload)[0]!=len(widths):raise TemplateError('invalid_template_attributes')
    for _ in widths:
        if offset+2>len(payload):raise TemplateError('invalid_template_attributes')
        attr=struct.unpack_from('<H',payload,offset)[0];offset+=2
        if attr not in widths or attr in values or offset+widths[attr]>len(payload):raise TemplateError('invalid_template_attributes')
        values[attr]=int.from_bytes(payload[offset:offset+widths[attr]],'little');offset+=widths[attr]
    if offset!=len(payload):raise TemplateError('invalid_template_attributes')
    if not 1<=values[2]<=MAX_MEMBERS or not 1<=values[5]<=MAX_STRUCTURE_BYTES:raise TemplateError('template_attribute_limit')
    # Attributes 6/8 are preserved without assigning execution semantics.
    return Attributes(values[1],values[2],values[5],values[6],values[8])


class TemplateStaging:
    def __init__(self,templates=(),records=0,writes=0,unsupported=0):
        self.templates=tuple(templates);self.records=records;self.writes=writes;self.unsupported=unsupported
        self.layout_inspection=Inspection(self.templates)

    @classmethod
    def from_batch(cls,batch):
        """Build all supported objects atomically; unrelated records only count.

        Unknown operations are never dispatched. Even an entirely modeled
        batch still needs an independently implemented execution contract.
        """
        pending={};total=modeled=writes=unsupported=0
        for record in batch:
            scope=record.scopes[-1]
            if scope.class_id!=0x6C:unsupported+=1;continue
            if len(record.scopes)!=1 or scope.attribute is not None or scope.symbolic or not 1<=scope.instance<=0xFFF:
                raise TemplateError('unsupported_template_path')
            if record.service not in (8,4,0x4D):unsupported+=1;continue
            payload=record.request[2+2*record.request[1]:];instance=scope.instance
            if record.service==8:
                words=create(payload);size=4*words-20
                if instance in pending:raise TemplateError('duplicate_template_create')
                if len(pending)>=MAX_TEMPLATES or total+size>MAX_TOTAL_BYTES:raise TemplateError('template_stage_full')
                pending[instance]={'words':words,'size':size,'attributes':None,'data':bytearray()};total+=size
            else:
                if instance not in pending:raise TemplateError('template_create_required')
                row=pending[instance]
                if record.service==4:
                    if row['attributes'] is not None:raise TemplateError('duplicate_template_attributes')
                    row['attributes']=attributes(payload)
                else:
                    if row['attributes'] is None:raise TemplateError('template_attributes_required')
                    if len(payload)<6:raise TemplateError('invalid_template_write')
                    offset,size=struct.unpack_from('<IH',payload)
                    if not 1<=size<=MAX_WRITE_BYTES or len(payload)!=6+size:raise TemplateError('invalid_template_write')
                    if offset!=len(row['data']) or offset+size>row['size']:raise TemplateError('template_write_range')
                    row['data'].extend(payload[6:]);writes+=1
            modeled+=1
        if any(row['attributes'] is None or len(row['data'])!=row['size'] for row in pending.values()):
            raise TemplateError('incomplete_template_definition')
        return cls((Template(i,row['words'],row['attributes'],bytes(row['data'])) for i,row in pending.items()),modeled,writes,unsupported)

    def description(self):
        return {'status':'modeled' if self.records or self.unsupported else 'idle',
                'templates':len(self.templates),'definition_bytes':sum(len(t.definition) for t in self.templates),
                'write_fragments':self.writes,'records_modeled':self.records,'unsupported_records':self.unsupported,
                'max_templates':MAX_TEMPLATES,'max_definition_bytes':MAX_DEFINITION_BYTES,'max_total_bytes':MAX_TOTAL_BYTES,
                'layout_inspection':self.layout_inspection.description(),
                'definitions_exposed':False,'active_catalog_replaced':False,'commit':False}
