"""Compare native uploaded offline values/routine exports with a pinned model.

This optional diagnostic neither saves an ACD nor substitutes source files for
native exports. Its plan and artifacts contain private engineering content.
"""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from logixlab.download_values import encode_initial
from logixlab.model import Project,Memory,ModelError,parse_rung,dimensions as declared_dimensions
from logixlab.native_types import NativeTypes
from logixlab.server import serialize_nodes

MAX_TAGS=32
MAX_ROUTINES=32
MAX_PROGRAMS=32
MAX_BYTES=1024*1024
MAX_XML=16_000_000
NAME=re.compile(r'[A-Za-z_][A-Za-z_0-9]{0,39}\Z')


def declaration_matches(node,tag):
    """Check declared logical dimensions separately from decorated value shape.

    Packed BOOL Table dimensions count words; L5X tag dimensions count bits.
    A decorated scalar can replace an array default during value parsing, so
    encoding those values alone cannot establish the tag's declaration.
    """
    logical=tuple(size for size in tag['dimensions'] if size)
    if tag['dtype'].upper()=='BOOL' and tag['typeCode']==0x20D3:
        if len(logical)!=1:return False
        logical=(logical[0]*32,)
    return declared_dimensions(node.get('Dimensions',''))==logical


def tag_declarations(controller):
    pairs=[(node.get('Name','').casefold(),node) for node in controller.findall('./Tags/Tag')]
    for program in controller.findall('./Programs/Program'):
        prefix='program:'+program.get('Name','').casefold()+'.'
        pairs.extend((prefix+node.get('Name','').casefold(),node) for node in program.findall('./Tags/Tag'))
    result=dict(pairs)
    if len(result)!=len(pairs):raise ValueError('Duplicate tag declaration')
    return result


def plan(project,native_types,state,*,allow_edited=False):
    """Complete bounded roots and source-bound Standard RLL routines."""
    edits=state.get('routine_edits',{});revision=edits.get('revision');changed=set()
    if type(allow_edited) is not bool:raise ValueError('Invalid edited-content option')
    if allow_edited:
        names=edits.get('edited_routines');retained=edits.get('native_source_readback',{})
        if (type(revision) is not int or revision<1 or edits.get('modified') is not True
                or type(names) not in (tuple,list) or not names or len(names)>MAX_ROUTINES
                or any(type(n) is not str or n!=n.casefold() or n not in project.routines for n in names)
                or len(set(names))!=len(names) or type(retained.get('retained_routines')) is not int
                or retained['retained_routines']!=len(names)
                or not re.fullmatch('[0-9a-f]{64}',edits.get('logic_sha256') or '')):
            raise ValueError('Edited-content check requires complete retained native RLL edits')
        changed=set(names)
    if (project.sha256!=state.get('connectivity',{}).get('source_l5x_sha256')
            or (revision!=0 and not allow_edited)
            or state.get('controller',{}).get('mode')!='Program'
            or state.get('controller',{}).get('running') is not False or project.aois
            or not NAME.fullmatch(project.name)):
        raise ValueError('Uploaded-content check requires unchanged ordinary source in stopped Program mode')
    memory=Memory(project);leaves=memory.leaves();current=state.get('tags',[])
    if len(leaves)!=len(current) or len({r['name'].casefold() for r in current})!=len(current):
        raise ValueError('Uploaded-content leaf coverage changed')
    by_name={row['name'].casefold():row for row in current}
    for original in leaves:
        row=by_name.get(original['name'].casefold())
        if (row is None or row.get('type')!=original['type'] or row.get('unknown') or row.get('problem')
                or row.get('aoi_local') or original.get('alias') or original.get('problem')
                or row.get('kind')!=original.get('kind')
                or row.get('alias')!=original.get('alias') or row.get('constant')!=original.get('constant')):
            raise ValueError('Uploaded-content source fields or values unavailable')
        # Constants are source values and cannot be assigned through Memory.
        if original['constant']:
            if row['value']!=original['value']:raise ValueError('Uploaded-content constant changed')
        else:memory.write(original['name'],row['value'])
    tags=[];total=0
    if not 1<=len(project.tags)<=MAX_TAGS:raise ValueError('Uploaded-content root count outside bound')
    for key,tag in sorted(project.tags.items()):
        if (tag.alias or tag.problem or tag.tag_class!='Standard' or not NAME.fullmatch(tag.name)
                or tag.scope and not NAME.fullmatch(tag.scope)):
            raise ValueError('Uploaded-content ordinary root required')
        code,dimensions,elements,data=encode_initial(tag.dtype.upper(),memory.values[key],native_types)
        total+=len(data)
        if not 1<=len(data)<=32768 or total>MAX_BYTES:raise ValueError('Uploaded-content value extent outside bound')
        prefix=f"Controller/Programs/Program[@Name='{tag.scope}']/" if tag.scope else 'Controller/'
        tags.append(dict(name=tag.key,xpath=prefix+f"Tags/Tag[@Name='{tag.name}']",typeCode=code,
            dimensions=dimensions,dtype=tag.dtype,constant=tag.constant,expectedHex=data.hex()))
    raw=project.path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=project.sha256:raise ValueError('Uploaded-content source changed')
    declarations=tag_declarations(ET.fromstring(raw).find('Controller'))
    if (set(declarations)!={t['name'].casefold() for t in tags}
            or any(not declaration_matches(declarations[t['name'].casefold()],t) for t in tags)):
        raise ValueError('Uploaded-content declared dimensions differ from source values')
    routines=[];actual={row['key'].casefold():row for row in state.get('routines',[])}
    if len(actual)!=len(state.get('routines',[])) or set(actual)!=set(project.routines) or len(actual)>MAX_ROUTINES:
        raise ValueError('Uploaded-content routine coverage changed')
    if allow_edited:
        current=[(key,row['kind'],[r['text'] for r in row['rungs']]) for key,row in sorted(actual.items())]
        if hashlib.sha256(json.dumps(current,separators=(',',':')).encode()).hexdigest()!=edits['logic_sha256']:
            raise ValueError('Uploaded-content active logic fingerprint changed')
    for key,routine in sorted(project.routines.items()):
        row=actual[key]
        if (routine.kind!='RLL' or routine.problems or not NAME.fullmatch(routine.name)
                or not NAME.fullmatch(routine.program) or project.programs[routine.program]['class']!='Standard'
                or row['kind']!='RLL' or key not in changed and
                    [r['nodes'] for r in row['rungs']]!=[serialize_nodes(r['nodes']) for r in routine.rungs]):
            raise ValueError('Uploaded-content complete unchanged Standard RLL source required')
        rungs=[r['text'] for r in routine.rungs]
        if key in changed:
            rungs=[r['text'] for r in row['rungs']]
            if any(serialize_nodes(parse_rung(text))!=r['nodes'] for text,r in zip(rungs,row['rungs'],strict=True)):
                raise ValueError('Uploaded-content active text and parsed logic differ')
        routines.append(dict(program=routine.program,name=routine.name,
            xpath=f"Controller/Programs/Program[@Name='{routine.program}']/Routines/Routine[@Name='{routine.name}']",
            fileName=f'uploaded-routine-{len(routines):04d}.L5X',expectedRungs=rungs))
        if allow_edited:
            comments=[r.get('comment','') for r in row['rungs']]
            if any(type(c) is not str or len(c)>65536 for c in comments):raise ValueError('Uploaded-content Comment extent outside bound')
            routines[-1]['expectedComments']=comments
    if (any(len(r['expectedRungs'])>10000 or any(len(text)>65536 for text in r['expectedRungs']) for r in routines)
            or sum(len(text) for r in routines for text in r['expectedRungs'])>2*MAX_BYTES):
        raise ValueError('Uploaded-content routine source extent outside bound')
    programs=[]
    if len(project.programs)>MAX_PROGRAMS:raise ValueError('Uploaded-content program count outside bound')
    for name,settings in sorted(project.programs.items()):
        if (not NAME.fullmatch(name) or settings['class']!='Standard' or settings['use_as_folder']
                or project.program_configuration.type_attributes(name,source_sha256=project.sha256)!={30:b'\1'}):
            raise ValueError('Uploaded-content ordinary Program required')
        programs.append(dict(name=name,xpath=f"Controller/Programs/Program[@Name='{name}']",
            fileName=f'uploaded-program-{len(programs):04d}.L5X',settings=settings))
    result=dict(sourceL5xSha256=project.sha256,controller=project.name,processor=project.processor,version=project.version,
        entryRoutines=state['entry_routines'],taskNames=list(project.task_configuration.names),tags=tags,routines=routines,programs=programs)
    if allow_edited:result.update(runtimeRevision=revision,runtimeLogicSha256=edits['logic_sha256'])
    return result


def prepare(operation,new_project,l5x,acd,state,*,allow_edited=False):
    if l5x is None:return None
    if operation!='upload' or new_project:raise ValueError('Uploaded-content check requires existing-project upload')
    source=Path(l5x).resolve(strict=True)
    if source.suffix.lower()!='.l5x' or source.stat().st_size>MAX_XML:
        raise ValueError('Uploaded-content source must be a bounded complete L5X')
    project=Project(source)
    return plan(project,NativeTypes.from_acd(acd,project.sha256),state,allow_edited=allow_edited)


def verify(folder,expected,receipt):
    """Require exact SDK value receipts and independently parse native exports."""
    result=dict(verified=False,offline_values_verified=False,routine_exports_verified=False)
    try:
        if (not isinstance(receipt,dict) or receipt.get('offlineOnly') is not True
                or receipt.get('sourceL5xSha256')!=expected['sourceL5xSha256']):return result
        values=receipt.get('tags');exports=receipt.get('routines')
        if (not isinstance(values,list) or len(values)!=len(expected['tags'])
                or not isinstance(exports,list) or len(exports)!=len(expected['routines'])):return result
        for entry,tag in zip(values,expected['tags'],strict=True):
            if (entry.get('name')!=tag['name'] or entry.get('xpath')!=tag['xpath']
                    or entry.get('actualHex')!=tag['expectedHex']):return result
        result['offline_values_verified']=True
        for entry,routine in zip(exports,expected['routines'],strict=True):
            path=Path(folder)/routine['fileName']
            if (entry.get('fileName')!=routine['fileName'] or path.is_symlink()
                    or not path.is_file() or not 8<=path.stat().st_size<=MAX_XML):return result
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):return result
            text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
            if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():return result
            root=ET.fromstring(text)
            if root.tag!='RSLogix5000Content' or root.get('TargetType')!='Routine' or root.get('TargetName')!=routine['name']:return result
            controllers=root.findall('Controller')
            if len(controllers)!=1:return result
            programs=[p for p in controllers[0].findall('./Programs/Program') if p.get('Name')==routine['program']]
            if len(programs)!=1:return result
            targets=[r for r in programs[0].findall('./Routines/Routine') if r.get('Name')==routine['name']]
            if len(targets)!=1 or targets[0].get('Type')!='RLL':return result
            content=targets[0].findall('RLLContent')
            if len(content)!=1 or any(n.tag!='Rung' for n in content[0]):return result
            actual=[];comments=[]
            for rung in content[0]:
                nodes=rung.findall('Text')
                if len(nodes)!=1 or len(nodes[0]) or nodes[0].text is None:return result
                actual.append(serialize_nodes(parse_rung(nodes[0].text)))
                values_comment=rung.findall('Comment')
                if len(values_comment)>1 or any(len(c) for c in values_comment):return result
                comments.append((values_comment[0].text or '') if values_comment else '')
            wanted=[serialize_nodes(parse_rung(text)) for text in routine['expectedRungs']]
            if actual!=wanted:return result
            if 'expectedComments' in routine and comments!=routine['expectedComments']:return result
        result.update(verified=True,routine_exports_verified=True,tags=len(values),
            value_bytes=sum(len(t['expectedHex'])//2 for t in expected['tags']),
            routines=len(exports),rungs=sum(len(r['expectedRungs']) for r in expected['routines']))
        return result
    except (OSError,ValueError,ModelError,TypeError,KeyError,AttributeError):return result


def verify_saved(folder,expected,native_types,receipt):
    """Check the native reopened full export, not just an ACD success/hash."""
    from tools.probe_native_sdk import saved_uploaded_acd_effect
    result=dict(verified=False,serialized_values_verified=False,serialized_logic_verified=False)
    if not saved_uploaded_acd_effect(Path(folder),receipt):return result
    result=verify_serialized(Path(folder)/'uploaded.L5X',expected,native_types)
    if result['verified']:result['native_acd_reopened']=True
    return result


def verify_serialized(path,expected,native_types):
    """Check complete exported values/logic without claiming a native reopen."""
    from logixlab.runtime import Engine
    result=dict(verified=False,serialized_values_verified=False,serialized_logic_verified=False)
    try:
        project=Project(path)
        if (project.name!=expected['controller'] or project.processor!=expected['processor'] or project.version!=expected['version']
                or set(project.tags)!={t['name'].casefold() for t in expected['tags']}
                or list(project.task_configuration.names)!=expected['taskNames']):return result
        if 'programs' in expected and project.programs!={p['name']:p['settings'] for p in expected['programs']}:return result
        declarations=tag_declarations(ET.fromstring(Path(path).read_bytes()).find('Controller'))
        for tag in expected['tags']:
            key=tag['name'].casefold();actual=project.tags[key]
            if (actual.problem or actual.alias or actual.tag_class!='Standard' or actual.constant!=tag['constant']
                    or actual.dtype.casefold()!=tag['dtype'].casefold()
                    or not declaration_matches(declarations[key],tag)):return result
            code,dimensions,elements,data=encode_initial(actual.dtype.upper(),project.initial[key],native_types)
            if code!=tag['typeCode'] or dimensions!=tuple(tag['dimensions']) or data.hex()!=tag['expectedHex']:return result
        result['serialized_values_verified']=True
        if set(project.routines)!={(r['program']+'/'+r['name']).casefold() for r in expected['routines']}:return result
        for routine in expected['routines']:
            actual=project.routines[(routine['program']+'/'+routine['name']).casefold()]
            if (actual.kind!='RLL' or actual.problems
                    or [serialize_nodes(r['nodes']) for r in actual.rungs]!=[serialize_nodes(parse_rung(text)) for text in routine['expectedRungs']]):return result
        engine=Engine(project,defer_prescan=True)
        if engine.blockers or engine.fault or engine.entries!=expected['entryRoutines']:return result
        result.update(verified=True,serialized_logic_verified=True,tags=len(expected['tags']),
            value_bytes=sum(len(t['expectedHex'])//2 for t in expected['tags']),routines=len(expected['routines']),
            rungs=sum(len(r['expectedRungs']) for r in expected['routines']))
        return result
    except (OSError,ValueError,ModelError,TypeError,KeyError,AttributeError):return result


class _ProgramValues:
    """Reuse decorated-value parsing without treating a partial export as full."""
    default=Project.default
    string_capacity=Project.string_capacity
    decorated=Project.decorated
    _tag=Project._tag

    def __init__(self,controller):
        types=controller.findall('./DataTypes/DataType')
        self.udts={d.get('Name','').casefold():d for d in types}
        if len(self.udts)!=len(types):raise ValueError('Duplicate exported data type')
        self.tags={}


def verify_programs(folder,expected,native_types,receipt):
    """Check actual native Program packages independently of routine exports.

    Context objects are dependencies, not evidence of a complete Controller
    export. Check the target Program's settings, full routine set and local
    tag declarations/current values; controller roots have separate SDK reads.
    """
    result=dict(verified=False,programs_verified=0,routines_verified=0,local_tags_verified=0)
    try:
        if (not isinstance(receipt,dict) or receipt.get('offlineOnly') is not True
                or receipt.get('sourceL5xSha256')!=expected['sourceL5xSha256']):return result
        exports=receipt.get('programs')
        if not isinstance(exports,list) or len(exports)!=len(expected['programs']):return result
        for entry,program in zip(exports,expected['programs'],strict=True):
            path=Path(folder)/program['fileName']
            if (entry.get('fileName')!=program['fileName'] or path.is_symlink() or not path.is_file()
                    or not 8<=path.stat().st_size<=MAX_XML):return result
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):return result
            text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
            if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():return result
            root=ET.fromstring(text)
            if (root.tag!='RSLogix5000Content' or root.get('TargetType')!='Program'
                    or root.get('TargetName')!=program['name'] or len(root.findall('Controller'))!=1):return result
            targets=root.findall('./Controller/Programs/Program')
            if len(targets)!=1 or targets[0].get('Name')!=program['name'] or targets[0].get('Type','Normal')!='Normal':return result
            target=targets[0]
            if any(target.get(field,'false') not in ('true','false') for field in ('Disabled','UseAsFolder')):return result
            settings=dict(main=target.get('MainRoutineName',''),**{'class':target.get('Class','Standard')},
                disabled=target.get('Disabled','false')=='true',use_as_folder=target.get('UseAsFolder','false')=='true')
            if settings!=program['settings']:return result
            wanted=[r for r in expected['routines'] if r['program']==program['name']]
            nodes=target.findall('./Routines/Routine');routines={r.get('Name'):r for r in nodes}
            if len(routines)!=len(nodes) or set(routines)!={r['name'] for r in wanted}:return result
            for routine in wanted:
                value=routines[routine['name']];blocks=value.findall('RLLContent')
                if value.get('Type')!='RLL' or len(blocks)!=1:return result
                parsed=[]
                for rung in blocks[0]:
                    texts=rung.findall('Text')
                    if (rung.tag!='Rung' or rung.get('Type','N')!='N' or len(texts)!=1
                            or len(texts[0]) or texts[0].text is None):return result
                    parsed.append(serialize_nodes(parse_rung(texts[0].text)))
                if parsed!=[serialize_nodes(parse_rung(text)) for text in routine['expectedRungs']]:return result
            prefix='program:'+program['name'].casefold()+'.'
            tags=[t for t in expected['tags'] if t['name'].casefold().startswith(prefix)]
            values=_ProgramValues(root.find('Controller'));nodes=target.findall('./Tags/Tag')
            for node in nodes:values._tag(node,program['name'])
            local=values.tags
            if len(local)!=len(nodes):return result
            if set(local)!={t['name'].casefold() for t in tags}:return result
            declarations={prefix+node.get('Name','').casefold():node for node in nodes}
            for tag in tags:
                key=tag['name'].casefold();value=local[key]
                if (value.problem or value.alias or value.tag_class!='Standard' or value.constant!=tag['constant']
                        or value.dtype.casefold()!=tag['dtype'].casefold()
                        or not declaration_matches(declarations[key],tag)):return result
                code,dimensions,elements,data=encode_initial(value.dtype.upper(),value.value,native_types)
                if code!=tag['typeCode'] or dimensions!=tuple(tag['dimensions']) or data.hex()!=tag['expectedHex']:return result
            result['programs_verified']+=1;result['routines_verified']+=len(wanted);result['local_tags_verified']+=len(tags)
        result['verified']=True
        return result
    except (OSError,ValueError,ModelError,TypeError,KeyError,AttributeError):return result
