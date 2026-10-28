"""Validate native controller-tag exports separately from Program dependencies."""
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from logixlab.download_values import encode_initial
from logixlab.model import ModelError
from tools.upload_content import MAX_XML, _ProgramValues, declaration_matches

FILENAME='uploaded-controller-tags.L5X'


def validate_options(operation,enabled,content_source,new_project=False):
    if type(enabled) is not bool:
        raise ValueError('Uploaded tag definitions require an explicit boolean')
    if enabled and (operation!='upload' or content_source is None or new_project):
        raise ValueError('--verify-uploaded-tag-definitions requires existing-project upload and --verify-uploaded-content')


def verify(folder,expected,native_types,receipt,source):
    """Check the complete targeted controller roots, not incidental context tags."""
    result=dict(verified=False,controller_tags_verified=0,serialized_values_verified=False)
    try:
        wanted={t['name'].casefold():t for t in expected['tags'] if not t['name'].casefold().startswith('program:')}
        if (not wanted or source.sha256!=expected['sourceL5xSha256'] or source.name!=expected['controller']
                or not isinstance(receipt,dict) or receipt.get('offlineOnly') is not True
                or receipt.get('sourceL5xSha256')!=expected['sourceL5xSha256']):return result
        entry=receipt.get('controllerTags')
        if not isinstance(entry,dict) or entry.get('fileName')!=FILENAME:return result
        path=Path(folder)/FILENAME
        if path.is_symlink() or not path.is_file() or not 8<=path.stat().st_size<=MAX_XML:return result
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):return result
        text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
        if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():return result
        root=ET.fromstring(text)
        if (root.tag!='RSLogix5000Content' or root.get('SchemaRevision')!='1.0' or root.get('TargetType')!='Tag'
                or root.get('TargetName','').casefold() not in wanted or root.get('ContainsContext')!='true'
                or not re.fullmatch(r'35\.[0-9]{2}',root.get('SoftwareRevision',''))
                or len(root.findall('Controller'))!=1):return result
        controller=root.find('Controller')
        if controller.get('Name')!=source.name or controller.get('Use')!='Context' or len(controller.findall('Tags'))!=1:return result
        nodes=controller.findall('./Tags/Tag')
        if len(nodes)!=len(wanted):return result
        values=_ProgramValues(controller)
        for node in nodes:
            planned=wanted[node.get('Name','').casefold()]
            if (node.get('Use')!='Target' or node.get('TagType')!='Base'
                    or node.get('Constant','false') not in ('true','false')
                    or node.get('Class','Standard')!='Standard'
                    or len(node.findall("Data[@Format='Decorated']"))!=1
                    or not declaration_matches(node,planned)):return result
            values._tag(node,'')
        if len(values.tags)!=len(nodes) or set(values.tags)!=set(wanted):return result
        for key,tag in wanted.items():
            actual=values.tags[key];original=source.tags[key]
            if (actual.problem or actual.alias or actual.tag_class!='Standard' or actual.constant!=tag['constant']
                    or actual.dtype.casefold()!=tag['dtype'].casefold() or actual.external_access!=original.external_access):return result
            code,dimensions,_,data=encode_initial(actual.dtype.upper(),actual.value,native_types)
            if code!=tag['typeCode'] or dimensions!=tuple(tag['dimensions']) or data.hex()!=tag['expectedHex']:return result
        result.update(verified=True,controller_tags_verified=len(wanted),serialized_values_verified=True,
                      definitions_verified=True,value_bytes=sum(len(t['expectedHex'])//2 for t in wanted.values()),
                      partial_export=True,native_acd_saved=False)
        return result
    except (OSError,ValueError,ModelError,TypeError,KeyError,AttributeError,IndexError,ET.ParseError):return result
