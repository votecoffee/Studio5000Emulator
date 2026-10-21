"""Read-only logical Program relations; never compiled addresses or scheduling."""
from dataclasses import dataclass, field
import struct
from types import MappingProxyType
from typing import Mapping
from .program_configuration import NAME, SHA256, MAX_PROGRAMS
from .tag_catalog import complete_tag_source

MAX_CHILDREN = 1000


def valid_graph(rows):
    """The Logical Organizer is an ordered forest: one parent and no cycles."""
    if len(rows)>MAX_PROGRAMS:return False
    parent={}
    for name,children in rows.items():
        if (not isinstance(name,str) or not NAME.fullmatch(name) or name!=name.casefold() or
                not isinstance(children,tuple) or len(children)>MAX_CHILDREN):return False
        for child in children:
            if not isinstance(child,str) or child not in rows or child in parent:return False
            parent[child]=name
    complete=set()
    for name in rows:
        path=set();current=name
        while current not in complete:
            if current in path:return False
            path.add(current)
            if current not in parent:break
            current=parent[current]
        complete.update(path)
    return True


def source_children(controller, programs):
    expected=set();rows={}
    for program in programs:
        if (program.text or '').strip() or any((child.tail or '').strip() for child in program):return {}
        groups=program.findall('ChildPrograms')
        if len(groups)>1:return {}
        children=[]
        if groups:
            group=groups[0];expected.add(group)
            if (group.attrib.keys()-{'Use'} or group.get('Use') not in (None,'Target') or
                    (group.text or '').strip() or len(group)>MAX_CHILDREN):return {}
            for entry in group:
                expected.add(entry)
                name=entry.get('Name','')
                if (entry.tag!='ChildProgram' or entry.attrib.keys()-{'Name','Use'} or
                        entry.get('Use') not in (None,'Target') or len(entry) or
                        (entry.text or '').strip() or (entry.tail or '').strip() or not NAME.fullmatch(name)):return {}
                children.append(name.casefold())
        rows[program.get('Name').casefold()]=tuple(children)
    for node in controller.iter():
        if node.tag.rsplit('}',1)[-1].casefold().startswith('childprogram') and node not in expected:return {}
    return rows if valid_graph(rows) else {}


@dataclass(frozen=True)
class ProgramHierarchy:
    source_sha256: str
    _children: Mapping[str,tuple[str,...]] = field(default_factory=dict,repr=False)
    _null_faults: frozenset[str] = field(default_factory=frozenset,repr=False)

    def __post_init__(self):
        if not isinstance(self.source_sha256,str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Program hierarchy source hash')
        rows=dict(self._children)
        if not valid_graph(rows):raise ValueError('Invalid Program child graph')
        if (not isinstance(self._null_faults,(set,frozenset)) or len(self._null_faults)>MAX_PROGRAMS or
                any(not isinstance(n,str) or not NAME.fullmatch(n) or n!=n.casefold() for n in self._null_faults)):
            raise ValueError('Invalid null Program fault inventory')
        object.__setattr__(self,'_children',MappingProxyType(rows))
        object.__setattr__(self,'_null_faults',frozenset(self._null_faults))

    @classmethod
    def from_source(cls,root,controller,source_sha256,configuration):
        if (not complete_tag_source(root,controller) or controller.get('MajorRev')!='35' or
                configuration.source_sha256!=source_sha256 or not configuration.source_complete):return cls(source_sha256)
        programs=controller.findall('./Programs/Program')
        groups=controller.findall('Programs')
        if (len(groups)!=1 or controller.findall('.//Programs')!=groups or groups[0].attrib.keys()-{'Use'} or
                groups[0].get('Use') not in (None,'Target') or (groups[0].text or '').strip() or
                any((p.tail or '').strip() for p in programs)):return cls(source_sha256)
        ordinary=[p for p in programs if configuration.type_attributes(p.get('Name'),source_sha256=source_sha256)
                  and not (p.text or '').strip() and not any((c.tail or '').strip() for c in p)]
        nulls=frozenset(p.get('Name').casefold() for p in ordinary if not p.get('FaultRoutineName'))
        children=source_children(controller,programs) if len(ordinary)==len(programs) else {}
        return cls(source_sha256,children,nulls)

    def attributes(self,program,*,source_sha256):
        if (source_sha256!=self.source_sha256 or not isinstance(program,str) or
                program.casefold() not in self._null_faults):return {}
        return {9:bytes(4)}

    def child_attributes(self,program,*,source_sha256,source_acd_sha256,program_ids,
                         program_source_l5x_sha256,program_source_acd_sha256):
        if (source_sha256!=self.source_sha256 or program_source_l5x_sha256!=self.source_sha256 or
                not isinstance(source_acd_sha256,str) or not SHA256.fullmatch(source_acd_sha256) or
                program_source_acd_sha256!=source_acd_sha256 or not isinstance(program,str) or
                program.casefold() not in self._children or not isinstance(program_ids,Mapping) or
                len(program_ids)>MAX_PROGRAMS):return {}
        bindings={};ids=set()
        for name,instance in dict(program_ids).items():
            if (not isinstance(name,str) or not NAME.fullmatch(name) or name.casefold() in bindings or
                    type(instance) is not int or not 1<=instance<=0xFFFFFFFF or instance in ids):return {}
            bindings[name.casefold()]=instance;ids.add(instance)
        if bindings.keys()!=self._children.keys():return {}
        children=self._children[program.casefold()]
        return {32:struct.pack('<H',len(children))+b''.join(struct.pack('<I',bindings[n]) for n in children)}

    def description(self):
        return {'attributes':[9,32],'source':'Complete canonical ordinary v35 Program declarations',
                'child_lists_available':len(self._children),'child_targets':sum(map(len,self._children.values())),
                'null_fault_routines_available':len(self._null_faults),'same_source_native_ids_required':True,
                'configured_fault_addresses':False,'fault_execution':False,'logical_organizer_writes':False,
                'execution_schedule_changed':False}
