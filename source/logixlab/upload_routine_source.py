"""Read-only v35 Routine upload XML, separate from the edit/import profile.

Class, edit type, rung kinds, native RegionIds and TextIOI stay explicit. These
records cannot be passed to the edit resolver or candidate planner. No operand
bindings, active rung selection, auxiliary semantics or execution are inferred.
"""
from collections import Counter
from dataclasses import dataclass,field
import hashlib
import re
import struct
from xml.etree import ElementTree as ET

from . import routine_source as source

MAX_CONTAINER=4*1024*1024
Error=source.SourceError
PROFILES={('Standard','Original'),('Safety','Original'),('Standard','TestEdits')}


@dataclass(frozen=True)
class UploadRung:
    region_id:int
    kind:str
    text_ioi:str=field(repr=False)


@dataclass(frozen=True)
class UploadSource:
    name:str=field(repr=False)
    target_class:str
    edit_type:str
    records:tuple[UploadRung,...]=field(repr=False)
    container_bytes:int
    container_sha256:str
    xml_bytes:int
    xml_sha256:str
    auxiliary_bytes:int
    auxiliary_sha256:str

    def description(self):
        """Public metadata omits names, regions, operand values and source text."""
        kinds=Counter(row.kind for row in self.records)
        return dict(decoded=True,profile='upload-rll-v35',target_class=self.target_class,
                    online_edit_type=self.edit_type,rungs=len(self.records),rung_kinds=dict(sorted(kinds.items())),
                    paired_regions=sum(row.kind=='IR' for row in self.records),
                    container_bytes=self.container_bytes,container_sha256=self.container_sha256,
                    xml_bytes=self.xml_bytes,xml_sha256=self.xml_sha256,
                    auxiliary_bytes=self.auxiliary_bytes,auxiliary_sha256=self.auxiliary_sha256,
                    ioi_operands=sum(len(re.findall(r'@[^@]*@',row.text_ioi)) for row in self.records),
                    source_identity_verified=False,operand_bindings_verified=False,auxiliary_semantics_verified=False,
                    active_rungs_selected=False,execution_verified=False,text_exposed=False,source_applied=False)


def decode(data):
    """Decode one complete assembled source container without resolving IOIs."""
    if not isinstance(data,bytes):raise Error('upload_source_bytes_required')
    if len(data)>MAX_CONTAINER:raise Error('upload_source_container_limit')
    xml,auxiliary=source._container(data)
    try:
        # The observed container declares UTF-16 while carrying UTF-8 bytes.
        text=xml.decode('utf-8-sig')
        if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise Error('upload_source_xml_declaration')
        parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True,insert_pis=True))
        root=ET.fromstring(text,parser=parser)
    except (UnicodeError,ET.ParseError) as error:raise Error('upload_source_xml_invalid') from error
    if (root.tag!='RSLogix5000Content' or root.get('SchemaRevision')!='1.0'
            or not re.fullmatch(r'35\.[0-9]{2}',root.get('SoftwareRevision',''))
            or root.get('TargetType')!='RLLContent' or root.get('TargetSubType')!='RLL'
            or root.get('ContainsContext')!='false' or not source.NAME.fullmatch(root.get('TargetName',''))
            or set(root.attrib)-{'SchemaRevision','SoftwareRevision','TargetName','TargetType','TargetSubType',
                                  'ContainsContext','ExportDate','ExportOptions','TargetClass'}
            or len(root)!=1 or root[0].tag!='RLLContent'):
        raise Error('upload_source_xml_profile')
    content=root[0];target_class=root.get('TargetClass');edit_type=content.get('OnlineEditType')
    if (set(content.attrib)!={'Use','OnlineEditType'} or content.get('Use')!='Create'
            or (target_class,edit_type) not in PROFILES):raise Error('upload_source_class_edit_profile')
    if any((value or '').strip() for value in (root.text,content.text,content.tail)):
        raise Error('upload_source_extra_text')
    if not 1<=len(content)<=source.MAX_RUNGS:raise Error('upload_source_rung_limit')
    records=[];regions={}
    for index,rung in enumerate(content):
        region=rung.get('RegionId','');kind=rung.get('Type')
        allowed=('N','IR','R') if edit_type=='TestEdits' else ('N',)
        if (rung.tag!='Rung' or set(rung.attrib)!={'Type','RegionId'} or kind not in allowed
                or not re.fullmatch(r'[1-9][0-9]{0,9}',region) or int(region)>0xFFFFFFFF
                or len(rung)!=1 or rung[0].tag!='TextIOI' or rung[0].attrib or len(rung[0])):
            raise Error('upload_source_rung_profile')
        text_ioi=rung[0].text or ''
        if any((value or '').strip() for value in (rung.text,rung.tail,rung[0].tail)):
            raise Error('upload_source_extra_text')
        if not text_ioi.strip() or len(text_ioi)>source.MAX_RUNG_TEXT:raise Error('upload_source_rung_text_limit')
        # The observed test-edit profile repeats a RegionId only in adjacent
        # IR/R records. Preserve both and their order; choose neither as active.
        previous=regions.get(int(region))
        if previous is not None and (kind!='R' or previous!=(index-1,'IR')):
            raise Error('upload_source_region_profile')
        if kind=='R' and previous!=(index-1,'IR'):raise Error('upload_source_region_profile')
        if records and records[-1].kind=='IR' and (kind!='R' or records[-1].region_id!=int(region)):
            raise Error('upload_source_region_profile')
        regions[int(region)]=(index,kind);records.append(UploadRung(int(region),kind,text_ioi))
    if records[-1].kind=='IR':raise Error('upload_source_region_profile')
    return UploadSource(root.get('TargetName'),target_class,edit_type,tuple(records),len(data),
                        hashlib.sha256(data).hexdigest(),len(xml),hashlib.sha256(xml).hexdigest(),
                        len(auxiliary),hashlib.sha256(auxiliary).hexdigest())


def decode_assembly(assembly):
    """Require a complete Routine selector-(1,3) read, keeping its caller scope.

    Structural assembly is not MAC authentication. The caller owns session
    separation, integrity verification and any independent source association.
    """
    from .read_transport import Assembly
    from .ethernetip import decode_path,CIPError
    if type(assembly) is not Assembly or not assembly.complete:raise Error('upload_source_read_incomplete')
    inner=assembly.inner
    if not isinstance(inner,bytes) or len(inner)<2:raise Error('upload_source_read_profile')
    end=2+2*inner[1]
    if inner[0]!=0x5D or len(inner)!=end+8 or inner[end:]!=struct.pack('<II',1,3):
        raise Error('upload_source_read_profile')
    try:path=decode_path(inner[2:end])
    except CIPError as error:raise Error('upload_source_read_path') from error
    if (path.class_id!=0x6D or not path.instance or path.attribute is not None or path.symbols
            or (path.program_instance is None)==(path.aoi_instance is None)
            or path.io_map_instance is not None or path.controller_instance is not None):
        raise Error('upload_source_read_path')
    return decode(assembly.value())
