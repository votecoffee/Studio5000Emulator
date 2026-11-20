"""Conservative AOI declarations, clean model state and source metadata reads.

Native UDI Definition objects (0x338) represent AOI definitions. Runtime AOI
parsing alone does not prove protected or unrecognized definitions are absent.
"""
from dataclasses import dataclass
from datetime import datetime
import re
import struct
from .tag_catalog import complete_tag_source
from .time_values import EPOCH
from .executable_configuration import RoutineMetadata,LANGUAGES,_description,_alias,_hidden


MAX_DEFINITIONS=1024
NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


@dataclass(frozen=True)
class DefinitionMetadata:
    name: str
    classification: str
    major_revision: int | None
    minor_revision: int | None
    revision_extension: str | None
    vendor: str | None
    last_edit_date: int | None
    protected: bool = False
    routines: tuple | None = None

    def attributes(self):
        # Keep the CIP catalog's widths and availability independent of GSV.
        fields = {} if self.protected else {1: bytes(2)}
        if self.major_revision is not None:
            fields[12] = struct.pack('<H', self.major_revision)
            fields[13] = struct.pack('<H', self.minor_revision)
        for field, value in ((19, self.revision_extension), (21, self.vendor)):
            if value is not None:
                fields[field] = struct.pack('<H', len(value)) + value.encode('ascii')
        return fields


def header_text(value):
    if value is not None and len(value) <= 40 and value.isascii() and '\0' not in value:
        return value
    return None


def last_edit_date(node):
    fields = [key for key in node.attrib if key.rsplit('}', 1)[-1].casefold() == 'editeddate']
    if fields != ['EditedDate']:
        return None
    value = node.get('EditedDate')
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z', value):
        return None
    try:
        elapsed = datetime.fromisoformat(value[:-1]) - EPOCH
    except ValueError:
        return None
    return (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds


def routine_metadata(node,classification):
    """Unknown, protected or partial children remain unavailable, never empty."""
    sections=node.findall('Routines');routines=node.findall('./Routines/Routine')
    allowed={*(id(section) for section in sections),*(id(routine) for routine in routines)}
    if any(child.tag.rsplit('}',1)[-1].casefold() in ('routines','routine') and id(child) not in allowed
           for child in node.iter()):return None
    if (len(sections)!=1 or node.findall('.//Routines')!=sections or node.findall('.//Routine')!=routines
            or len(routines)>16384 or _hidden(sections[0]) or set(sections[0].attrib)-{'Use'}
            or sections[0].get('Use') not in (None,'Target') or (sections[0].text or '').strip()
            or any(child.tag!='Routine' for child in sections[0])):return None
    rows=[];names=set()
    for routine in routines:
        name=routine.get('Name','');language=routine.get('Type')
        if (not NAME.fullmatch(name) or name.casefold() in names or language not in LANGUAGES
                or routine.get('Use') not in (None,'Target') or routine.get('Class') not in (None,classification)
                or _alias(routine,{'Name','Type','Class','Use'}) or _hidden(routine)
                or (routine.text or '').strip() or (routine.tail or '').strip()
                or len(routine.findall(language+'Content'))!=1
                or any(child.tag not in ('Description',language+'Content') for child in routine)):
            return None
        names.add(name.casefold());rows.append(RoutineMetadata(name,language,_description(routine)))
    return tuple(rows)


def source_metadata(root,controller):
    """Read AOI declarations independently of unrelated tag/runtime support."""
    if (controller is None or root.tag!='RSLogix5000Content' or root.get('SchemaRevision')!='1.0'
            or not re.fullmatch(r'35\.[0-9]{2}',root.get('SoftwareRevision','')) or root.get('TargetType')!='Controller'
            or root.get('ContainsContext')!='false' or root.findall('Controller')!=[controller]
            or controller.get('Use') not in (None,'Target') or controller.get('MajorRev')!='35'):
        return None
    sections=controller.findall('AddOnInstructionDefinitions')
    if (len(sections)!=1 or set(sections[0].attrib)-{'Use'} or sections[0].get('Use') not in (None,'Target')
            or (sections[0].text or '').strip() or not 1<=len(sections[0])<=MAX_DEFINITIONS):return None
    section=sections[0];allowed={id(section),*(id(node) for node in section)}
    for node in controller.iter():
        name=node.tag.rsplit('}',1)[-1].casefold()
        if name in ('addoninstructiondefinitions','addoninstructiondefinition','udidefinition') and id(node) not in allowed:
            return None
        if node.get('EncodedType','').casefold() in ('addoninstructiondefinition','udidefinition') and id(node) not in allowed:
            return None
    result=[];names=set()
    for node in section:
        name=node.get('Name','');classification=node.get('Class');protected=node.tag=='EncodedData'
        if (node.tag not in ('AddOnInstructionDefinition','EncodedData') or not NAME.fullmatch(name) or name.casefold() in names
                or classification not in ('Standard','Safety') or node.get('Use') not in (None,'Target')
                or not protected and (node.text or '').strip() or (node.tail or '').strip()):return None
        if protected and node.get('EncodedType')!='AddOnInstructionDefinition':return None
        for key in ('Name','Class','Use','Revision','RevisionExtension','Vendor'):
            variants=[field for field in node.attrib if field.rsplit('}',1)[-1].casefold()==key.casefold()]
            if variants and variants!=[key]:return None
        for child in (() if protected else node.iter()):
            local=child.tag.rsplit('}',1)[-1].casefold()
            if (any(word in local for word in ('encoded','encrypted','protected'))
                    or any(any(word in key.casefold() for word in ('encoded','encrypted','protected')) for key in child.attrib)
                    or any(word in child.get('Format','').casefold() for word in ('encoded','encrypted','protected'))
                    or child.get('OnlineEditType') not in (None,'Original')):return None
        major = minor = None
        revision = node.get('Revision', '')
        if re.fullmatch(r'[0-9]{1,5}\.[0-9]{1,5}', revision):
            major, minor = map(int, revision.split('.'))
            if max(major, minor) > 65535:
                major = minor = None
        names.add(name.casefold())
        result.append(DefinitionMetadata(
            name, classification, major, minor, header_text(node.get('RevisionExtension')),
            header_text(node.get('Vendor')), None if protected else last_edit_date(node),
            protected=protected, routines=None if protected else routine_metadata(node, classification),
        ))
    return tuple(result)


@dataclass(frozen=True)
class AOICatalog:
    empty: bool
    metadata: tuple | None = None

    @classmethod
    def from_source(cls, root, controller):
        metadata=source_metadata(root,controller)
        if not complete_tag_source(root, controller):
            return cls(False,metadata)
        sections = controller.findall('AddOnInstructionDefinitions')
        if (len(sections) != 1 or len(sections[0]) or (sections[0].text or '').strip()
                or set(sections[0].attrib) - {'Use'}
                or sections[0].get('Use') not in (None, 'Target')):
            return cls(False,metadata)
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if name.startswith(('addoninstruction', 'udidefinition')) and (
                    node is not sections[0] or node.tag != 'AddOnInstructionDefinitions'):
                return cls(False,metadata)
            if any(word in name for word in ('encoded', 'encrypted', 'protected')) or any(
                    any(word in key.lower() for word in ('encoded', 'encrypted', 'protected'))
                    for key in node.attrib) or any(word in node.get('Format', '').lower()
                                                 for word in ('encoded', 'encrypted', 'protected')):
                return cls(False,metadata)
        return cls(True,())

    def description(self):
        return {'empty_catalog_available': self.empty, 'class_id': 0x338,
                'instance_count': 0 if self.empty else None, 'instance_list': self.empty,
                'source': 'Explicit complete L5X AOI declarations; original IDs require a separate ACD binding',
                'source_metadata_available':self.metadata is not None,
                'source_definition_count':len(self.metadata) if self.metadata is not None else None,
                'protected_declarations':sum(row.protected for row in self.metadata) if self.metadata is not None else None,
                'source_metadata_attributes':[1,12,13,19,21],
                'source_routine_parents_available':sum(row.routines is not None for row in self.metadata) if self.metadata is not None else None,
                'source_routines_available':sum(len(row.routines or ()) for row in self.metadata) if self.metadata is not None else None,
                'bound_inventory_supported':True,'native_identity_binding_required':not self.empty,
                'definition_upload': False, 'native_aoi_execution': False}
