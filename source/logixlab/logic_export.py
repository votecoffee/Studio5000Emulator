"""Export edited Standard RLL logic into a separate complete L5X working copy.

Original imported tag initial values are retained. Runtime values, native ACD
correlation manifests and compiled transfer containers are never serialized.
"""
import hashlib
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from .model import ModelError, Project


def _update_draft_rungs(content, rows, origins):
    originals = content.findall('Rung')
    replacements = {}
    inserted = []
    for row, origin in zip(rows, origins, strict=True):
        if origin is None:
            rung = ET.Element('Rung', Number=row['number'], Type='N')
            ET.SubElement(rung, 'Text')
            inserted.append(rung)
        else:
            if not 0 <= origin < len(originals) or origin in replacements:
                raise ModelError('The source L5X no longer has the original Standard rung layout')
            rung = originals[origin]
            if (rung.get('Type', 'N') != 'N' or len(rung.findall('Text')) != 1
                    or len(rung.findall('Comment')) > 1):
                raise ModelError('The source L5X no longer has the original Standard rung layout')
            if rung.get('Number', str(origin)) != row['number']:
                rung.set('Number', row['number'])
            replacements[origin] = [*inserted, rung]
            inserted.clear()
        text = rung.find('Text')
        if text.text != row['text']:
            text.text = row['text']
        comment = rung.find('Comment')
        if comment is None and row['comment']:
            comment = ET.Element('Comment')
            rung.insert(list(rung).index(text), comment)
        if comment is not None and (comment.text or '') != row['comment']:
            comment.text = row['comment']

    # Reuse retained elements in their source order, keeping non-rung siblings.
    children = []
    origin = 0
    for child in content:
        if child.tag == 'Rung':
            children.extend(replacements.get(origin, ()))
            origin += 1
            if origin == len(originals):
                children.extend(inserted)
        else:
            children.append(child)
    if not originals:
        children.extend(inserted)
    content[:] = children


def export(engine):
    project=engine.project
    revision=getattr(project,'runtime_revision',0)
    keys=getattr(project,'runtime_edited_routines',())
    if type(revision) is not int or revision<=0 or not keys:
        raise ModelError('Apply supported routine edits before exporting edited logic')
    if not project.executable_configuration.source_complete or project.aois:
        raise ModelError('Edited logic export requires a complete ordinary project')
    try:raw=project.path.read_bytes()
    except OSError as error:raise ModelError('Original imported L5X is unavailable') from error
    if hashlib.sha256(raw).hexdigest()!=project.sha256:
        raise ModelError('Original imported L5X changed; edited logic was not exported')
    root=ET.fromstring(raw)
    found={}
    for program in root.findall('./Controller/Programs/Program'):
        for routine in program.findall('./Routines/Routine'):
            key=(program.get('Name','')+'/'+routine.get('Name','')).casefold()
            if key in keys:
                if key in found:raise ModelError('Ambiguous edited routine in original L5X')
                found[key]=routine
    if set(found)!=set(keys):raise ModelError('Edited routine is absent from original L5X')
    for key,node in found.items():
        routine=project.routines.get(key)
        contents=node.findall('RLLContent')
        if (routine is None or routine.kind!='RLL' or node.get('Type')!='RLL' or
                node.get('Class','Standard')!='Standard' or len(contents)!=1):
            raise ModelError('Only ordinary RLL source can be exported')
        content=contents[0]
        origins=getattr(project,'runtime_rung_origins',{}).get(key)
        if origins is not None:
            _update_draft_rungs(content,routine.rungs,origins)
            continue
        # Native replacements may change rung counts and numbering.
        content.text=None
        for child in list(content):content.remove(child)
        for index,row in enumerate(routine.rungs):
            rung=ET.SubElement(content,'Rung',Number=str(index),Type='N')
            if row['comment']:ET.SubElement(rung,'Comment').text=row['comment']
            ET.SubElement(rung,'Text').text=row['text']
    payload=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    name=re.sub(r'[^A-Za-z0-9_-]','_',project.name)[:80] or 'Controller'
    return {'filename':f'{name}-edited-r{revision}.L5X','content':payload.decode('utf-8'),
            'sha256':hashlib.sha256(payload).hexdigest(),'base_l5x_sha256':project.sha256,
            'logic_revision':revision,'logic_sha256':project.runtime_logic_sha256,
            'edited_routines':list(keys),'tag_values':'original_import',
            'native_acd_correlation':False,'native_studio_import':'not_verified'}


def verify_working_copy(engine):
    result = export(engine)
    with tempfile.TemporaryDirectory(prefix='logixlab-draft-check-') as directory:
        path = Path(directory) / result['filename']
        try:
            path.write_bytes(result['content'].encode('utf-8'))
            reimported = Project(path)
        except (ET.ParseError, OSError, ModelError) as error:
            raise ModelError(f'Edited L5X could not be reimported: {error}') from error
    project = engine.project
    if reimported.initial != project.initial:
        raise ModelError('Edited L5X would change imported tag initial values')
    for key in result['edited_routines']:
        restored = reimported.routines.get(key)
        if restored is None or restored.problems or restored.rungs != project.routines[key].rungs:
            raise ModelError(f'Edited L5X would change rung source or operands in {project.routines[key].key}')
