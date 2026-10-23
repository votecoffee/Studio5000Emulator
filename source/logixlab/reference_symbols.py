"""Original native Program/Task reference symbols, separate from tag values."""
from dataclasses import dataclass
import re
import struct
from types import MappingProxyType

from .model import ModelError


@dataclass(frozen=True)
class ReferenceSymbol:
    instance: int
    name: str
    kind: str
    target: str
    target_instance: int

    def __post_init__(self):
        if (type(self.instance) is not int or not 1<=self.instance<65535 or
                type(self.target_instance) is not int or not 1<=self.target_instance<=65535 or
                self.kind not in ('program','task') or not isinstance(self.target,str) or
                not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,39}',self.target) or
                self.name!=self.kind.title()+':'+self.target):
            raise ModelError('Invalid reference Symbol descriptor')

    @property
    def type_code(self):return {'program':0x1068,'task':0x1070}[self.kind]

    def attributes(self,value_address,header_address):
        name=self.name.encode('ascii')
        return {1:struct.pack('<H',len(name))+name,2:struct.pack('<H',self.type_code),
                3:struct.pack('<I',value_address),5:struct.pack('<I',header_address),6:bytes(4),
                7:bytes(2),8:bytes(12),9:b'\0',10:b'\0',11:b'\0',12:struct.pack('<I',0xFFFF),14:bytes(4)}


@dataclass(frozen=True,init=False)
class ReferenceSymbols:
    source_l5x_sha256: str
    rows: tuple[ReferenceSymbol,...]
    by_instance: object
    _bindings: tuple

    def __init__(self,project,identity,symbols,tasks,auxiliary,rows):
        object.__setattr__(self,'source_l5x_sha256',project.sha256)
        object.__setattr__(self,'rows',tuple(sorted(rows,key=lambda row:row.instance)))
        object.__setattr__(self,'by_instance',MappingProxyType({row.instance:row for row in rows}))
        object.__setattr__(self,'_bindings',(identity,symbols,tasks,auxiliary))

    @classmethod
    def from_source(cls,project,identity,symbols,tasks,auxiliary):
        # Old optional manifests need not contain reference data names. They
        # remain comparison-only and never supply guessed public references.
        candidates=[row for row in auxiliary.rows if row.reference_name is not None and row.program_instance==0] if auxiliary else []
        if not candidates:return None
        if any(binding is None for binding in (identity,symbols,tasks)):
            return None
        if (any((binding.source_l5x_sha256,binding.source_acd_sha256)!=(project.sha256,identity.source_acd_sha256)
                for binding in (identity,symbols,tasks,auxiliary))):
            raise ModelError('Reference Symbol source differs from the native Project bindings')
        auxiliary.require_parents(symbols)
        config=project.program_configuration;task_config=project.task_configuration
        if not config.source_complete or not task_config.source_complete:return None
        programs={name.casefold():name for name in project.programs}
        declared_tasks={row['name'].casefold():row['name'] for row in project.tasks}
        if len(programs)!=len(project.programs) or len(declared_tasks)!=len(project.tasks):return None
        expected={('program',key) for key,name in programs.items()
                  if config.type_attributes(name,source_sha256=project.sha256) and
                  config.flag_attributes(name,source_sha256=project.sha256).get(31)==b'\1'}
        expected|={('task',key) for key,name in declared_tasks.items()
                   if task_config.memory_attributes(name,source_sha256=project.sha256).get(20)==bytes(2)}
        found=set();rows=[];ids=set();names=set()
        root_ids={row.instance for row in symbols.by_key.values() if not row.scope}
        root_names={tag.name.casefold() for tag in project.tags.values() if not tag.scope}
        for source in candidates:
            prefix,target=source.reference_name.split(':',1);kind=prefix.casefold();key=target.casefold()
            declarations=programs if kind=='program' else declared_tasks
            if key not in declarations:raise ModelError('Reference Symbol target is absent from source')
            if (kind,key) not in expected:continue  # Safety/opaque/folder/event kinds are not promoted.
            target_id=symbols.programs.get(key) if kind=='program' else tasks.lookup(target)
            if target_id is None:return None
            name=prefix+':'+declarations[key]
            if ((kind,key) in found or source.instance in ids or name.casefold() in names or
                    source.instance in root_ids or name.casefold() in root_names):
                raise ModelError('Duplicate or colliding reference Symbol identity')
            found.add((kind,key));ids.add(source.instance);names.add(name.casefold())
            rows.append(ReferenceSymbol(source.instance,name,kind,declarations[key],target_id))
        if found!=expected:return None
        return cls(project,identity,symbols,tasks,auxiliary,rows)

    def current(self,project,identity,symbols,tasks,auxiliary):
        bound=(project.sha256==self.source_l5x_sha256 and
                all(old is new for old,new in zip(self._bindings,(identity,symbols,tasks,auxiliary))) and
                all((binding.source_l5x_sha256,binding.source_acd_sha256)==(project.sha256,identity.source_acd_sha256)
                    for binding in (identity,symbols,tasks,auxiliary)) and
                all((symbols.programs.get(row.target.casefold()) if row.kind=='program' else tasks.lookup(row.target))
                    ==row.target_instance for row in self.rows))
        if not bound or symbols.program_inventory_error is not None:return False
        root_ids={row.instance for row in symbols.by_key.values() if not row.scope}
        root_names={tag.name.casefold() for tag in project.tags.values() if not tag.scope}
        for row in self.rows:
            if row.instance in root_ids or row.name.casefold() in root_names:return False
            if row.kind=='program':
                target=next((p for name,p in project.programs.items() if name.casefold()==row.target.casefold()),None)
                if target is None or target['class']!='Standard' or target.get('use_as_folder'):return False
            else:
                target=next((p for p in project.tasks if p['name'].casefold()==row.target.casefold()),None)
                if target is None or target['class']!='Standard' or target['type'] not in ('Continuous','Periodic'):return False
        return True

    def description(self):
        return {'bound':True,'symbols':len(self.rows),'programs':sum(row.kind=='program' for row in self.rows),
                'tasks':sum(row.kind=='task' for row in self.rows),'types':[0x1068,0x1070],
                'source':'Original ACD format-63 reference data names and matching native Program/Task identities',
                'value_storage':False,'data_tables':False,'read_write_tags':False,'physical_addresses':False,
                'native_transfer_acceptance':False}
