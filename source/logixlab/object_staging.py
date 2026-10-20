"""Temporary native object descriptors and reference/coordination checks.

Names, compiled bodies, physical addresses and active memory are not created.
The observed batch profile is validated as a graph, never dispatched.
"""
from dataclasses import dataclass
import struct

NULL_REFERENCE=0xFFFF
MAX_INSTANCE=0xFFFE
MAX_SYMBOLS=1024
MAX_TABLES=1024
MAX_PROGRAMS=64
MAX_ROUTINES=512
MAX_ELEMENTS=65536
MAX_STORAGE_BYTES=1024*1024
ATOM_BYTES={0xC1:1,0xC2:1,0xC3:2,0xC4:4,0xC5:8,0xC6:1,0xC7:2,0xC8:4,0xC9:8,0xCA:4}
CLASSES=(0x68,0x6A,0x6B,0x6D,0x74)


class ObjectError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


def attributes(payload,widths):
    if len(payload)<2 or struct.unpack_from('<H',payload)[0]!=len(widths):raise ObjectError('invalid_object_attributes')
    offset=2;values={}
    for _ in widths:
        if offset+2>len(payload):raise ObjectError('invalid_object_attributes')
        attr=struct.unpack_from('<H',payload,offset)[0];offset+=2
        if attr not in widths or attr in values or offset+widths[attr]>len(payload):raise ObjectError('invalid_object_attributes')
        values[attr]=payload[offset:offset+widths[attr]];offset+=widths[attr]
    if offset!=len(payload):raise ObjectError('invalid_object_attributes')
    return values


def reference(value):
    if value!=NULL_REFERENCE and not 1<=value<=MAX_INSTANCE:raise ObjectError('invalid_object_reference')
    return value


@dataclass(frozen=True)
class Symbol:
    program:int
    instance:int
    table:int


@dataclass(frozen=True)
class Table:
    instance:int
    data_use:int
    type_code:int
    dimensions:tuple
    symbol:int
    elements:int
    storage_bytes:int


@dataclass(frozen=True)
class Routine:
    program:int
    instance:int
    create_word:int=0


def table(instance,payload,templates):
    values=attributes(payload,{6:2,2:2,1:12,8:4,9:2})
    use=int.from_bytes(values[6],'little');code=int.from_bytes(values[2],'little')
    dims=struct.unpack('<III',values[1]);symbol=reference(int.from_bytes(values[8],'little'))
    if use not in (4,0x6A) or values[9]!=b'\0\0':raise ObjectError('unsupported_table_flags')
    if (use==4)!=(symbol==NULL_REFERENCE):raise ObjectError('invalid_table_symbol_reference')
    rank=(code>>13)&3;elements=1
    if code&0x1000 or any(dims[i]==0 for i in range(rank)) or any(dims[rank:]):raise ObjectError('invalid_table_type_dimensions')
    for size in dims[:rank]:
        elements*=size
        if elements>MAX_ELEMENTS:raise ObjectError('table_element_limit')
    if code&0x8000:
        target=templates.get(code&0xFFF)
        if target is None:raise ObjectError('table_template_reference_required')
        width=target.attributes.structure_bytes
    else:
        width=ATOM_BYTES.get(code&0xFFF)
        if width is None:raise ObjectError('unsupported_table_type')
    size=width*elements
    if size>MAX_STORAGE_BYTES:raise ObjectError('object_storage_limit')
    return Table(instance,use,code,dims,symbol,elements,size)


class ObjectStaging:
    def __init__(self,symbols=(),tables=(),programs=(),routines=(),coordination=0,records=0):
        self.symbols=tuple(symbols);self.tables=tuple(tables);self.programs=tuple(programs);self.routines=tuple(routines)
        self.coordination=coordination;self.records=records

    @classmethod
    def from_batch(cls,batch,templates=()):
        types={t.instance:t for t in templates};symbols={};tables={};programs=set();routines={};held=set()
        modeled=coordination=storage=0
        for record in batch:
            leaf=record.scopes[-1]
            if leaf.class_id not in CLASSES:continue
            if any(s.attribute is not None or s.symbolic or not 1<=s.instance<=MAX_INSTANCE for s in record.scopes):
                raise ObjectError('unsupported_object_path')
            program=0
            if len(record.scopes)==2 and record.scopes[0].class_id==0x68 and leaf.class_id in (0x6B,0x6D,0x74):
                program=record.scopes[0].instance
                if program not in programs:raise ObjectError('object_program_required')
            elif len(record.scopes)!=1 or leaf.class_id in (0x6D,0x74):raise ObjectError('unsupported_object_scope')
            if record.service!=8 and not (leaf.class_id==0x74 and record.service in (0x4B,0x4C)):continue
            payload=record.request[2+2*record.request[1]:];instance=leaf.instance
            if leaf.class_id==0x74:
                if instance!=1:raise ObjectError('unsupported_program_coordination')
                if record.service==0x4B:
                    if payload!=b'\1' or program in held:raise ObjectError('invalid_program_acquire')
                    held.add(program)
                elif record.service==0x4C:
                    if payload or program not in held:raise ObjectError('invalid_program_release')
                    held.remove(program)
                else:continue
                coordination+=1
            elif leaf.class_id==0x68:
                if payload:raise ObjectError('invalid_program_create')
                if instance in programs:raise ObjectError('duplicate_program_create')
                if len(programs)>=MAX_PROGRAMS:raise ObjectError('object_stage_full')
                programs.add(instance)
            elif leaf.class_id==0x6B:
                if program and program not in held:raise ObjectError('program_coordination_required')
                values=attributes(payload,{12:4,9:1});ref=reference(int.from_bytes(values[12],'little'))
                if values[9]!=b'\0' or program and ref!=NULL_REFERENCE:raise ObjectError('unsupported_symbol_profile')
                key=(program,instance)
                if key in symbols:raise ObjectError('duplicate_symbol_create')
                if len(symbols)>=MAX_SYMBOLS:raise ObjectError('object_stage_full')
                symbols[key]=Symbol(program,instance,ref)
            elif leaf.class_id==0x6A:
                if instance in tables:raise ObjectError('duplicate_table_create')
                if len(tables)>=MAX_TABLES:raise ObjectError('object_stage_full')
                row=table(instance,payload,types);storage+=row.storage_bytes
                if storage>MAX_STORAGE_BYTES:raise ObjectError('object_storage_limit')
                tables[instance]=row
            else:
                if program not in held:raise ObjectError('program_coordination_required')
                if payload!=b'\0\0':raise ObjectError('unsupported_routine_create')
                key=(program,instance)
                if key in routines:raise ObjectError('duplicate_routine_create')
                if len(routines)>=MAX_ROUTINES:raise ObjectError('object_stage_full')
                routines[key]=Routine(program,instance)
            modeled+=1
        if held:raise ObjectError('incomplete_program_coordination')
        for row in symbols.values():
            if row.table!=NULL_REFERENCE and (row.table not in tables or tables[row.table].symbol!=row.instance):
                raise ObjectError('symbol_table_reference_mismatch')
        for row in tables.values():
            if row.symbol!=NULL_REFERENCE and ((0,row.symbol) not in symbols or symbols[0,row.symbol].table!=row.instance):
                raise ObjectError('table_symbol_reference_mismatch')
        return cls(symbols.values(),tables.values(),sorted(programs),routines.values(),coordination,modeled)

    def description(self):
        return {'status':'modeled' if self.records else 'idle','symbols':len(self.symbols),'tables':len(self.tables),
                'programs':len(self.programs),'routines':len(self.routines),'coordination_records':self.coordination,
                'records_modeled':self.records,'storage_bytes':sum(t.storage_bytes for t in self.tables),
                'references_validated':bool(self.records),'open_coordination':0,
                'max_symbols':MAX_SYMBOLS,'max_tables':MAX_TABLES,'max_programs':MAX_PROGRAMS,'max_routines':MAX_ROUTINES,
                'max_elements':MAX_ELEMENTS,'max_storage_bytes':MAX_STORAGE_BYTES,
                'definitions_exposed':False,'active_catalog_replaced':False,'commit':False}
