"""Complete L5X assembled from checked native upload components and source context.

Controller/Task/type context remains source-bound. Actual uploaded controller
tags and entire Programs replace those source sections. No native ACD bytes,
compiled payloads or journal identities are copied into the assembled document.
"""
import copy
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from tools import upload_content


def _root(path,expected_hash):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 8<=path.stat().st_size<=upload_content.MAX_XML:
        raise ValueError('A bounded regular L5X component is required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_hash:raise ValueError('L5X component changed during assembly')
    try:
        text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
        if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ValueError('L5X entities and document types are unsupported')
        root=ET.fromstring(text)
    except (UnicodeError,ET.ParseError) as error:raise ValueError('Invalid L5X component') from error
    if root.tag!='RSLogix5000Content' or len(root.findall('Controller'))!=1:
        raise ValueError('An unambiguous L5X Controller context is required')
    return root


def _target(node):
    result=copy.deepcopy(node)
    for child in result.iter():child.attrib.pop('Use',None)
    # Only decorated current values are independently checked. Do not let a
    # conflicting unverified L5K/raw representation choose the imported value.
    tags=[result] if result.tag=='Tag' else result.findall('./Tags/Tag')
    for tag in tags:
        data=tag.findall("Data[@Format='Decorated']")
        if len(data)!=1:raise ValueError('Every uploaded tag requires complete decorated values')
        for child in list(tag):
            if child.tag=='Data' and child is not data[0]:tag.remove(child)
    return result


def assemble(source,l5x,upload):
    """Revalidate retained native evidence, then return a separate complete XML.

    The original ACD is used for provenance/type checks only. The returned XML
    is the native input when creating a fresh ACD with --from-uploaded-l5x.
    """
    from tools import rebuild_uploaded_acd as rebuild,upload_tag_definitions
    upload=Path(upload)
    manifest,expected,_=rebuild.prepare(source,l5x,upload)
    request=rebuild.read_json(upload/'request.json')
    if request.get('ExportUploadedTags') is not True:
        raise ValueError('L5X reconstruction requires the actual requested controller-tag export')
    receipt=rebuild.read_json(upload/'sdk-result.json')['uploadedContent']
    root=_root(l5x,expected['sourceL5xSha256'])
    if root.get('TargetType')!='Controller':raise ValueError('Complete original Controller context is required')
    controller=root.find('Controller')
    if len(controller.findall('Tags'))!=1 or len(controller.findall('Programs'))!=1:
        raise ValueError('Complete unambiguous source Tags and Programs are required')
    package=_root(upload/upload_tag_definitions.FILENAME,receipt['controllerTags']['sha256'])
    tags=ET.Element('Tags')
    for node in package.findall('./Controller/Tags/Tag'):tags.append(_target(node))
    old=controller.find('Tags');position=list(controller).index(old)
    controller.remove(old);controller.insert(position,tags)
    packages={p['name']:p for p in manifest['programs']}
    programs=ET.Element('Programs')
    for original in controller.findall('./Programs/Program'):
        entry=packages.pop(original.get('Name'))
        package=_root(upload/entry['fileName'],entry['sha256'])
        nodes=package.findall('./Controller/Programs/Program')
        if len(nodes)!=1 or nodes[0].get('Name')!=entry['name']:
            raise ValueError('Uploaded Program target changed')
        programs.append(_target(nodes[0]))
    if packages:raise ValueError('Uploaded Program coverage changed')
    old=controller.find('Programs');position=list(controller).index(old)
    controller.remove(old);controller.insert(position,programs)
    root.set('ContainsContext','false');root.set('TargetName',expected['controller'])
    payload=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    if len(payload)>upload_content.MAX_XML:raise ValueError('Reconstructed L5X exceeds the upload XML bound')
    return payload


def verify(path,expected,types):
    """Check the assembled complete document before a native project opens."""
    from tools.rebuild_uploaded_acd import source_schema
    content=upload_content.verify_serialized(path,expected,types)
    if (not content['verified'] or source_schema(upload_content.Project(path))!=expected['rebuildSourceSchema']):
        raise ValueError('Assembled complete L5X differs from uploaded values, source logic or context')
    return content
