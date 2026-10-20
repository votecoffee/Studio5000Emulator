"""Immutable ordinary Routine inventory and legacy Executable descriptions.

The installed plain v35 Executable ADF revisions 1--8 define attribute 7 as
a BITS16 length followed by STRING[128]. Revisions 9/10 omit that attribute;
this is a limited legacy read model, not a revision-10 implementation. No
Type enum, Executable UID, GSV slot or compiled address is inferred here.
"""
from dataclasses import dataclass, field
import re
import struct
from types import MappingProxyType
from typing import Mapping

from .tag_catalog import complete_tag_source


MAX_PROGRAMS=4096
MAX_ROUTINES=65535
MAX_DESCRIPTION=128
NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')
SHA256=re.compile(r'[0-9a-f]{64}\Z')
LANGUAGES=frozenset(('RLL','ST','FBD','SFC'))
HIDDEN=('encoded','encrypted','protected','protection','sourcekey','license')


def _valid_name(value):
    return isinstance(value,str) and NAME.fullmatch(value) is not None


def _alias(node,fields):
    return any(key not in fields and key.rsplit('}',1)[-1].casefold() in
               {field.casefold() for field in fields} for key in node.attrib)


def _hidden(node):
    """Protection markers withhold data even if ordinary text is also visible."""
    for child in node.iter():
        if any(word in child.tag.rsplit('}',1)[-1].casefold() for word in HIDDEN):return True
        if any(any(word in key.casefold() for word in HIDDEN) for key in child.attrib):return True
        if any(word in child.get('Format','').casefold() for word in HIDDEN):return True
    return False


def _description(routine):
    descriptions=[child for child in routine if child.tag.rsplit('}',1)[-1].casefold()=='description']
    if len(descriptions)!=1:return None
    node=descriptions[0]
    if node.tag!='Description' or node.attrib or len(node):return None
    try:data=(node.text or '').encode('ascii')
    except UnicodeEncodeError:return None
    return data if len(data)<=MAX_DESCRIPTION and b'\0' not in data else None


@dataclass(frozen=True)
class RoutineMetadata:
    name: str
    language: str
    description: bytes | None = None

    def __post_init__(self):
        if not _valid_name(self.name) or self.language not in LANGUAGES:
            raise ValueError('Invalid ordinary Routine declaration')
        value=self.description
        if value is not None and (not isinstance(value,bytes) or len(value)>MAX_DESCRIPTION
                                  or b'\0' in value or any(byte>127 for byte in value)):
            raise ValueError('Invalid Executable Description bytes')

    def attributes(self):
        return {} if self.description is None else {7:struct.pack('<H',len(self.description))+self.description}


@dataclass(frozen=True)
class ProgramMetadata:
    name: str
    routines: tuple[RoutineMetadata, ...] = ()
    _by_name: Mapping[str,RoutineMetadata] = field(init=False,repr=False,compare=False)

    def __post_init__(self):
        if (not _valid_name(self.name) or not isinstance(self.routines,tuple)
                or len(self.routines)>MAX_ROUTINES or any(not isinstance(row,RoutineMetadata) for row in self.routines)):
            raise ValueError('Invalid ordinary Program Routine inventory')
        rows={row.name.casefold():row for row in self.routines}
        if len(rows)!=len(self.routines):raise ValueError('Duplicate Routine declarations')
        object.__setattr__(self,'_by_name',MappingProxyType(rows))


@dataclass(frozen=True)
class ExecutableConfiguration:
    source_sha256: str
    source_complete: bool = False
    _programs: Mapping[str,ProgramMetadata] = field(default_factory=dict,repr=False)
    unavailable_programs: int = 0

    def __post_init__(self):
        if not isinstance(self.source_sha256,str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Executable source hash')
        rows=dict(self._programs)
        if (len(rows)>MAX_PROGRAMS or any(not isinstance(value,ProgramMetadata)
                or key!=value.name.casefold() for key,value in rows.items())
                or sum(len(row.routines) for row in rows.values())>MAX_ROUTINES):
            raise ValueError('Invalid Executable configuration inventory')
        if type(self.source_complete) is not bool or (rows and not self.source_complete):
            raise ValueError('Executable configuration requires complete source')
        if type(self.unavailable_programs) is not int or not 0<=self.unavailable_programs<=MAX_PROGRAMS:
            raise ValueError('Invalid unavailable Program count')
        object.__setattr__(self,'_programs',MappingProxyType(rows))

    @classmethod
    def from_source(cls,root,controller,source_sha256):
        unavailable=cls(source_sha256)
        if (not complete_tag_source(root,controller) or controller.get('MajorRev')!='35'
                or _alias(root,{'TargetType','ContainsContext'}) or _alias(controller,{'MajorRev'})):
            return unavailable
        containers=controller.findall('Programs');programs=controller.findall('./Programs/Program')
        if (len(programs)>MAX_PROGRAMS or controller.findall('.//Programs')!=containers
                or controller.findall('.//Program')!=programs):return unavailable
        declarations={'programs':'Programs','program':'Program','routines':'Routines','routine':'Routine'}
        for node in controller.iter():
            local=node.tag.rsplit('}',1)[-1].casefold()
            if local in declarations and (node.tag!=declarations[local] or node.get('Use') not in (None,'Target')):
                return unavailable
            if local in ('program','routine') and _alias(node,{'Name','Class','Type','Use'}):return unavailable
        names=[program.get('Name','') for program in programs]
        if any(not _valid_name(name) for name in names) or len({name.casefold() for name in names})!=len(names):
            return unavailable
        # Protection of the complete controller/container could hide ordinary
        # declarations. Unrelated protected AOI bodies do not supply Routines.
        if any(any(word in key.casefold() for word in HIDDEN) for key in controller.attrib):return unavailable
        if any(any(any(word in key.casefold() for word in HIDDEN) for key in section.attrib)
               or any(word in section.get('Format','').casefold() for word in HIDDEN) for section in containers):
            return unavailable
        if any(any(word in node.tag.rsplit('}',1)[-1].casefold() for word in HIDDEN) for node in controller):
            return unavailable
        rows={};total=0
        for name,program in zip(names,programs):
            sections=program.findall('Routines');routines=program.findall('./Routines/Routine')
            if (len(sections)>1 or program.findall('.//Routines')!=sections
                    or program.findall('.//Routine')!=routines
                    or any(child.tag!='Routine' for section in sections for child in section)):
                return unavailable
            routine_names=[routine.get('Name','') for routine in routines]
            total+=len(routines)
            if (total>MAX_ROUTINES or any(not _valid_name(value) for value in routine_names)
                    or len({value.casefold() for value in routine_names})!=len(routine_names)):
                return unavailable
            if len(sections)!=1 or program.get('Class') not in (None,'Standard') or _hidden(program):continue
            eligible=True;metadata=[]
            for routine_name,routine in zip(routine_names,routines):
                language=routine.get('Type')
                if (language not in LANGUAGES or routine.get('Class') not in (None,'Standard')
                        or len(routine.findall(language+'Content'))!=1
                        or any(child.tag not in ('Description',language+'Content')
                               and child.tag.rsplit('}',1)[-1].casefold()!='description' for child in routine)):
                    eligible=False;break
                metadata.append(RoutineMetadata(routine_name,language,_description(routine)))
            if eligible:rows[name.casefold()]=ProgramMetadata(name,tuple(metadata))
        return cls(source_sha256,True,rows,len(programs)-len(rows))

    @property
    def program_names(self):
        return tuple(row.name for row in self._programs.values())

    def routine_names(self,program,*,source_sha256):
        if source_sha256!=self.source_sha256 or not self.source_complete or not isinstance(program,str):return None
        row=self._programs.get(program.casefold())
        return tuple(routine.name for routine in row.routines) if row is not None else None

    def attributes(self,program,routine,*,source_sha256):
        if (source_sha256!=self.source_sha256 or not self.source_complete
                or not isinstance(program,str) or not isinstance(routine,str)):return {}
        parent=self._programs.get(program.casefold())
        row=parent._by_name.get(routine.casefold()) if parent else None
        return row.attributes() if row else {}

    def description(self):
        routines=[routine for program in self._programs.values() for routine in program.routines]
        return {'source_complete':self.source_complete,'programs_available':len(self._programs),
                'programs_unavailable':self.unavailable_programs,'routines_available':len(routines),
                'description_attributes_available':sum(row.description is not None for row in routines),
                'attributes':[7],'encoding':'UINT16 byte count + ASCII bytes, maximum 128',
                'adf_scope':'Installed plain v35 Executable revisions 1 through 8; absent in revisions 9/10',
                'native_ids_inferred':False,'type_enum_inferred':False,'uid_inferred':False,
                'compiled_addresses':False,'native_writes':False,'native_upload_acceptance':False}
