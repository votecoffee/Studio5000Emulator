"""Export edited Standard RLL logic into a separate complete L5X working copy.

Original imported tag initial values are retained. Runtime values, native ACD
correlation manifests and compiled transfer containers are never serialized.
"""
import hashlib
import re
from xml.etree import ElementTree as ET
from .model import ModelError


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
        # Preserve routine attributes and unrelated project XML. Only the edited
        # RLLContent is rebuilt from the active neutral source and comments.
        content=contents[0];content.text=None
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
