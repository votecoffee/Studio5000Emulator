"""Lease-local Task headers and source-checked configuration, without scheduling."""
from dataclasses import dataclass
import hashlib
import json
import struct
from types import MappingProxyType

from .download_image import ImageError
from .native_tasks import NativeTasks,MAX_TASKS
from .task_configuration import MAX_SCHEDULED_PROGRAMS
from .task_timing import microseconds
from .download_headers import reference_path
from .object_staging import NULL_REFERENCE

TASK_BASE=0x75000000
WIDTHS={1:'programs',2:4,4:'trigger',5:2,6:2,12:4,17:4,18:4,19:4}


def attributes(payload):
    if not isinstance(payload,bytes) or len(payload)<2:raise ImageError('download_task_attribute_extent')
    count=struct.unpack_from('<H',payload)[0];offset=2;values={}
    if count!=len(WIDTHS):raise ImageError('download_task_attribute_profile')
    for _ in range(count):
        if offset+2>len(payload):raise ImageError('download_task_attribute_extent')
        number=struct.unpack_from('<H',payload,offset)[0];offset+=2
        if number not in WIDTHS or number in values:raise ImageError('download_task_attribute_profile')
        size=WIDTHS[number]
        if not isinstance(size,int):
            if offset+2>len(payload):raise ImageError('download_task_attribute_extent')
            length=struct.unpack_from('<H',payload,offset)[0]
            if (number==1 and length>MAX_SCHEDULED_PROGRAMS or number==4 and length!=5):
                raise ImageError('download_task_attribute_count')
            size=2+length*(4 if number==1 else 1)
        if offset+size>len(payload):raise ImageError('download_task_attribute_extent')
        values[number]=payload[offset:offset+size];offset+=size
    if offset!=len(payload):raise ImageError('download_task_attribute_trailing')
    return values


class TaskBindings:
    def __init__(self,engine,namespace,native_tasks,identity,programs,auxiliary=None):
        self.engine=engine;self.namespace=namespace;self.tasks=native_tasks;self.identity=identity;self.programs=programs
        self.auxiliary=auxiliary

    def expected(self,instance):
        project=self.engine.project;source=self.namespace._source;native=self.tasks;symbols=self.programs;identity=self.identity
        if (not isinstance(native,NativeTasks) or identity is None or symbols is None
                or project.sha256!=source.l5x_sha256 or self.engine.mode!='project'
                or getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',())
                or any((obj.source_acd_sha256,obj.source_l5x_sha256)!=(source.acd_sha256,source.l5x_sha256)
                       for obj in (native,identity,symbols))):raise ImageError('download_task_source_required')
        config=project.task_configuration
        if not config.source_complete or {n.casefold() for n in config.names}!=set(native.tasks):
            raise ImageError('download_task_inventory_mismatch')
        if type(instance) is not int or instance not in native.task_ids:raise ImageError('download_task_identity_missing')
        row=next(t for t in native.rows if t.instance==instance);name=row.name
        fields=config.attributes(name,source_sha256=project.sha256)
        fields.update(project.task_timing.attributes(name,source_sha256=project.sha256))
        fields.update(native.configuration_attributes(project,name,identity,symbols))
        fields.update(config.scheduled_attributes(name,source_sha256=project.sha256,source_acd_sha256=source.acd_sha256,
            program_ids=symbols.programs,program_source_l5x_sha256=symbols.source_l5x_sha256,
            program_source_acd_sha256=symbols.source_acd_sha256))
        # The observed empty Create profile allocates ordinary Standard memory.
        if (config.memory_attributes(name,source_sha256=project.sha256)!={20:bytes(2)}
                or not WIDTHS.keys()<=fields.keys()):raise ImageError('download_task_configuration_required')
        stored=native.configurations.get(name.casefold())
        if stored is None or any(i not in self.namespace._image.programs for i in stored.programs):
            raise ImageError('download_task_retained_program_required')
        active=[t for t in project.tasks if t['name'].casefold()==name.casefold()]
        settings=config._tasks[name.casefold()];times=project.task_timing._tasks.get(name.casefold())
        if (len(active)!=1 or times is None or active[0]['class']!='Standard' or active[0]['type']!=times.kind
                or active[0]['inhibited']!=settings.inhibited
                or tuple(n.casefold() for n in active[0]['programs'])!=tuple(n.casefold() for n in settings.scheduled_programs)
                or times.rate_present and microseconds(active[0]['rate'])!=times.declared_rate_us):
            raise ImageError('download_task_runtime_source_changed')
        return name,tuple(sorted((n,fields[n]) for n in WIDTHS))

    def stamp(self):
        if not isinstance(self.tasks,NativeTasks):raise ImageError('download_task_source_required')
        fields=[(i,self.expected(i)) for i in sorted(self.tasks.task_ids)]
        raw=repr((id(self.engine.project),fields,self.engine.project.tasks,
            self.auxiliary.manifest() if self.auxiliary is not None else None)).encode()
        return hashlib.sha256(raw+json.dumps(self.tasks.manifest(),sort_keys=True).encode()).hexdigest()

    def symbol_target(self,instance):
        source=self.namespace._source;extra=self.auxiliary
        if (extra is None or (extra.source_acd_sha256,extra.source_l5x_sha256)!=(source.acd_sha256,source.l5x_sha256)
                or type(instance) is not int or self.namespace._image._symbols.get((0,instance))!=NULL_REFERENCE):
            raise ImageError('download_task_symbol_source_required')
        row=extra.by_instance.get((0,instance));updates=self.namespace._incremental
        if row is None or row.component_type!=256 or row.reference_name is None or not row.reference_name.startswith('Task:'):
            raise ImageError('download_task_symbol_source_required')
        target=self.tasks.lookup(row.reference_name[5:])
        self.expected(target)
        values=dict(updates._headers.get((0x6B,0,instance),())) if updates is not None else {}
        raw=row.reference_name.encode('ascii')
        if any(values.get(n)!=value for n,value in {
                1:struct.pack('<H',len(raw))+raw,2:struct.pack('<H',0x1070),3:bytes(4),13:b'\0'}.items()):
            raise ImageError('download_task_initial_symbol_required')
        return target


@dataclass(frozen=True)
class TaskHeader:
    instance:int
    address:int
    name:str
    source_attributes:tuple


@dataclass(frozen=True)
class TaskSymbol:
    task:int
    address:int
    logical_path:bytes


class DownloadTasks:
    def __init__(self):
        self._headers=();self._attributes=MappingProxyType({});self._binding=None;self._effect_stamp=None
        self._symbols=MappingProxyType({})

    def _digest(self):
        return hashlib.sha256(repr((self._headers,tuple(sorted(self._attributes.items())),tuple(sorted(self._symbols.items())))).encode()).hexdigest()

    def validate(self,bindings):
        if self._binding is None:
            if self._headers or self._attributes or self._symbols:raise ImageError('download_task_effect_changed')
            return
        if bindings is None or bindings.stamp()!=self._binding:raise ImageError('download_task_binding_changed')
        if self._digest()!=self._effect_stamp:raise ImageError('download_task_effect_changed')
        for row in self._headers:
            name,expected=bindings.expected(row.instance)
            if (row.name!=name or row.source_attributes!=expected
                    or row.address!=TASK_BASE+32*sorted(bindings.tasks.task_ids).index(row.instance)
                    or row.instance in self._attributes and self._attributes[row.instance]!=expected):
                raise ImageError('download_task_effect_changed')
        for instance,row in self._symbols.items():
            task=bindings.symbol_target(instance)
            header=next((h for h in self._headers if h.instance==task),None)
            if header is None or row.task!=task:raise ImageError('download_task_symbol_effect_changed')
            logical=reference_path(row.logical_path)
            if (logical and (logical!=((0x70,task),) or row.address!=header.address)
                    or not logical and row.address not in (0,header.address)):
                raise ImageError('download_task_symbol_effect_changed')

    def create(self,instance,bindings):
        self.validate(bindings);stamp=bindings.stamp();name,expected=bindings.expected(instance)
        if any(r.instance==instance for r in self._headers):raise ImageError('download_task_already_created')
        if len(self._headers)>=MAX_TASKS:raise ImageError('download_task_count_limit')
        address=TASK_BASE+32*sorted(bindings.tasks.task_ids).index(instance)
        row=TaskHeader(instance,address,name,expected)
        if bindings.stamp()!=stamp:raise ImageError('download_task_binding_changed')
        self._headers=(*self._headers,row);self._binding=stamp;self._effect_stamp=self._digest()
        self.validate(bindings)
        return struct.pack('<II',instance,address)

    def configure(self,instance,payload,bindings):
        self.validate(bindings)
        row=next((r for r in self._headers if type(instance) is int and r.instance==instance),None)
        if row is None:raise ImageError('download_task_create_required')
        values=attributes(payload);expected=bindings.expected(instance)[1]
        if tuple(sorted(values.items()))!=expected:raise ImageError('download_task_configuration_mismatch')
        updated=dict(self._attributes);updated[instance]=expected
        if bindings.stamp()!=self._binding:raise ImageError('download_task_binding_changed')
        self._attributes=MappingProxyType(updated);self._effect_stamp=self._digest()
        self.validate(bindings)
        return struct.pack('<H',len(values))+b''.join(struct.pack('<HH',n,0) for n in values)

    def require_configured(self,bindings):
        self.validate(bindings)
        if not self._headers or bindings is None or set(self._attributes)!=set(bindings.tasks.task_ids):
            raise ImageError('complete_download_task_configuration_required')

    def link_symbol(self,instance,payload,bindings):
        self.validate(bindings);target=bindings.symbol_target(instance)
        header=next((h for h in self._headers if h.instance==target),None)
        if header is None:raise ImageError('download_task_create_required')
        if not isinstance(payload,bytes) or len(payload)<2:raise ImageError('download_task_symbol_extent')
        count=struct.unpack_from('<H',payload)[0];offset=2;values={}
        if count not in (1,2):raise ImageError('download_task_symbol_profile')
        for _ in range(count):
            if offset+2>len(payload):raise ImageError('download_task_symbol_extent')
            number=struct.unpack_from('<H',payload,offset)[0];offset+=2
            if number not in (3,13) or number in values:raise ImageError('download_task_symbol_profile')
            if offset>=len(payload):raise ImageError('download_task_symbol_extent')
            size=4 if number==3 else 1+2*payload[offset]
            if offset+size>len(payload):raise ImageError('download_task_symbol_extent')
            values[number]=payload[offset:offset+size];offset+=size
        if offset!=len(payload):raise ImageError('download_task_symbol_extent')
        if set(values)=={13} and values[13]==b'\0':
            previous=self._symbols.get(instance);address=previous.address if previous is not None else 0
        elif set(values)=={3,13} and reference_path(values[13])==((0x70,target),):
            address=int.from_bytes(values[3],'little')
            if address!=header.address:raise ImageError('download_task_symbol_address_mismatch')
        else:raise ImageError('download_task_symbol_profile')
        if bindings.stamp()!=self._binding:raise ImageError('download_task_binding_changed')
        updated=dict(self._symbols);updated[instance]=TaskSymbol(target,address,values[13])
        self._symbols=MappingProxyType(updated);self._effect_stamp=self._digest();self.validate(bindings)
        return struct.pack('<H',count)+b''.join(struct.pack('<HH',n,0) for n in values)

    def description(self):
        return dict(created=len(self._headers),configured=len(self._attributes),
            symbol_updates=len(self._symbols),symbol_links=sum(r.logical_path!=b'\0' for r in self._symbols.values()),
            configuration_attributes=sum(len(v) for v in self._attributes.values()),
            source_bound=self._binding is not None,modeled_handles=True,physical_addresses=False,
            active_scheduler_changed=False,active_catalog_replaced=False,commit=False,payloads_exposed=False)
