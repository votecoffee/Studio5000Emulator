"""Decode the observed source container without applying its object references.

The XML contains TextIOI, not neutral text with resolved tag names. Its auxiliary
data, RegionIds and IOI operands retain their native meaning; no code executes.
"""
from dataclasses import dataclass
import hashlib
import re
import struct
import zlib
from xml.etree import ElementTree as ET

MAX_EXPANDED=2*1024*1024
MAX_AUXILIARY=65536
MAX_RUNGS=4096
MAX_RUNG_TEXT=65536
NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')


class SourceError(ValueError):pass


def aligned(value):return (value+3)&~3


def source_header(data,total):
    if not isinstance(data,bytes) or len(data)<40:raise SourceError('routine_source_header_truncated')
    length,offset,size,aux_offset,aux_size,flags,end,pad=struct.unpack_from('<8I',data)
    if (total<64 or length!=total-4 or offset!=28 or size<12 or size%4 or aux_offset!=offset+size
            or not 8<aux_size<=MAX_AUXILIARY or flags or end!=length or pad
            or aligned(aux_offset+aux_size)!=length):
        raise SourceError('routine_source_header_invalid')
    stored,expanded=struct.unpack_from('<II',data,32)
    if (stored&0xC0000000!=0x40000000 or not 1<=expanded<=MAX_EXPANDED
            or aligned(8+(stored&0x3FFFFFFF))!=size):
        raise SourceError('routine_source_compression_header_invalid')
    return size,4+aux_offset,aux_size


def inflate(data,expected,limit):
    if not 1<=expected<=limit:raise SourceError('routine_source_expanded_limit')
    try:
        stream=zlib.decompressobj();result=stream.decompress(data,expected+1)
    except zlib.error as error:raise SourceError('routine_source_compression_invalid') from error
    if (len(result)!=expected or not stream.eof or stream.unused_data or stream.unconsumed_tail):
        raise SourceError('routine_source_compression_extent')
    return result


@dataclass(frozen=True)
class SourceRung:
    region_id:int
    text_ioi:str


@dataclass(frozen=True)
class RoutineSource:
    name:str
    rungs:tuple[SourceRung,...]
    xml_bytes:int
    xml_sha256:str
    auxiliary_bytes:int
    auxiliary_sha256:str

    def description(self):
        return {'decoded':True,'rungs':len(self.rungs),'xml_bytes':self.xml_bytes,'xml_sha256':self.xml_sha256,
                'auxiliary_bytes':self.auxiliary_bytes,'auxiliary_sha256':self.auxiliary_sha256,
                'ioi_operands':sum(len(re.findall(r'@[^@]*@',r.text_ioi)) for r in self.rungs),
                'operand_bindings_verified':False,'auxiliary_semantics_verified':False,
                'text_exposed':False,'source_applied':False}


def decode(data):
    if not isinstance(data,bytes):raise SourceError('routine_source_bytes_required')
    size,aux_offset,aux_size=source_header(data,len(data))
    stored,expanded=struct.unpack_from('<II',data,32);compressed=stored&0x3FFFFFFF
    if any(data[40+compressed:32+size]) or any(data[aux_offset+aux_size:]):
        raise SourceError('routine_source_padding_invalid')
    xml=inflate(data[40:40+compressed],expanded,MAX_EXPANDED)
    version,aux_expanded=struct.unpack_from('<II',data,aux_offset)
    if version!=1:raise SourceError('routine_source_auxiliary_profile')
    auxiliary=inflate(data[aux_offset+8:aux_offset+aux_size],aux_expanded,MAX_AUXILIARY)
    try:
        # This observed stream declares UTF-16 but carries UTF-8 text. Decode
        # the bounded bytes explicitly; do not let the declaration guess it.
        text=xml.decode('utf-8-sig')
        if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise SourceError('routine_source_xml_declaration')
        root=ET.fromstring(text)
    except (UnicodeError,ET.ParseError) as error:raise SourceError('routine_source_xml_invalid') from error
    if (root.tag!='RSLogix5000Content' or root.get('SchemaRevision')!='1.0'
            or not re.fullmatch(r'35\.[0-9]{2}',root.get('SoftwareRevision',''))
            or root.get('TargetType')!='RLLContent' or root.get('TargetSubType')!='RLL'
            or root.get('ContainsContext')!='false' or not NAME.fullmatch(root.get('TargetName',''))
            or set(root.attrib)-{'SchemaRevision','SoftwareRevision','TargetName','TargetType','TargetSubType',
                                      'ContainsContext','ExportDate','ExportOptions'}
            or len(root)!=1 or root[0].tag!='RLLContent'
            or root[0].attrib!={'Use':'Create','OnlineEditType':'Original'}):
        raise SourceError('routine_source_xml_profile')
    content=root[0]
    if (root.text or '').strip() or (content.text or '').strip() or (content.tail or '').strip():
        raise SourceError('routine_source_extra_text')
    if not 1<=len(content)<=MAX_RUNGS:raise SourceError('routine_source_rung_limit')
    rungs=[];ids=set()
    for rung in content:
        region=rung.get('RegionId','')
        if (rung.tag!='Rung' or set(rung.attrib)!={'Type','RegionId'} or rung.get('Type')!='N'
                or not re.fullmatch(r'[1-9][0-9]{0,9}',region) or int(region)>0xFFFFFFFF
                or int(region) in ids or len(rung)!=1 or rung[0].tag!='TextIOI' or rung[0].attrib or len(rung[0])):
            raise SourceError('routine_source_rung_profile')
        source=(rung[0].text or '').strip()
        if (rung.text or '').strip() or (rung.tail or '').strip() or (rung[0].tail or '').strip():
            raise SourceError('routine_source_extra_text')
        if not 1<=len(source)<=MAX_RUNG_TEXT:raise SourceError('routine_source_rung_text_limit')
        ids.add(int(region));rungs.append(SourceRung(int(region),source))
    return RoutineSource(root.get('TargetName'),tuple(rungs),len(xml),hashlib.sha256(xml).hexdigest(),
                         len(auxiliary),hashlib.sha256(auxiliary).hexdigest())


def resolve(source,project,symbols,routines,types,program):
    """Translate only observed, source-bound six-word symbolic/member paths.

    This returns neutral text for inspection. It does not validate execution,
    compare the ELF with source, change a project or commit controller edits.
    """
    from .model import parse_rung,Branch,ModelError
    catalogs=(symbols,routines,types)
    if any(c is None or c.source_l5x_sha256!=project.sha256 for c in catalogs):
        raise SourceError('ioi_source_bindings_unavailable')
    if len({c.source_acd_sha256 for c in catalogs})!=1:raise SourceError('ioi_acd_binding_mismatch')
    program_id=symbols.programs.get(program.casefold())
    if program_id is None:raise SourceError('ioi_program_unavailable')
    by_id={(s.program_instance,s.instance):s for s in symbols.by_key.values()}
    token=re.compile(r'@[0-9]{1,10}(?: [0-9]{1,10}){5}@')
    segment=token.pattern+r'(?:\[[0-9]{1,10}(?:,[0-9]{1,10}){0,2}\])?'
    reference=segment+r'(?:\.'+segment+r')*'

    def indexed(name,value,suffix):
        if not suffix:return name,value
        indices=tuple(map(int,suffix[1:-1].split(',')))
        for index in indices:
            if not isinstance(value,list) or not 0<=index<len(value):
                raise SourceError('ioi_array_subscript_unavailable')
            value=value[index]
        if isinstance(value,list):raise SourceError('ioi_array_rank_unsupported')
        return name+'['+','.join(map(str,indices))+']',value

    def argument(value,routine=False,expression=None):
        if expression and '@' in value:
            # Only CPT/CMP expression operands use this profile. Resolve complete
            # IOI/member chains individually, then check the existing bounded
            # grammar and require every tag reference to originate in a chain.
            from .expressions import Expression
            if len(value)>4096:raise SourceError('ioi_expression_limit')
            references=[]
            def substitute(match):
                name=argument(match.group());references.append(name.casefold());return name
            translated=re.sub(reference,substitute,value)
            if '@' in translated:raise SourceError('ioi_expression_profile_unsupported')
            try:parsed=Expression(translated,condition=expression=='CMP')
            except ModelError as error:raise SourceError('ioi_expression_syntax_unsupported') from error
            if sorted(ref.casefold() for ref in parsed.refs)!=sorted(references):
                raise SourceError('ioi_expression_reference_unsupported')
            return translated
        if '@' not in value or len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):return value
        if not re.fullmatch(reference,value):
            raise SourceError('ioi_argument_profile_unsupported')
        parts=list(re.finditer(segment,value));found=[token.match(part.group()) for part in parts]
        suffixes=[part.group()[len(match.group()):] for part,match in zip(parts,found)]
        words=[tuple(map(int,t.group()[1:-1].split())) for t in found]
        if any(n>0xFFFFFFFF for word in words for n in word):raise SourceError('ioi_integer_limit')
        first=words[0]
        if routine:
            if len(words)!=1 or suffixes[0] or first[:3]!=(0x68,program_id,0x6D) or first[4:]!=(0,0):
                raise SourceError('ioi_routine_scope_unsupported')
            row=routines.by_instance.get((program_id,first[3]))
            if row is None or (row.program+'/'+row.name).casefold() not in project.routines:
                raise SourceError('ioi_routine_unavailable')
            return row.name
        if first[0]==0x6B and first[2:]==(0,0,0,0):pair=(0,first[1])
        elif first[0]==0x68 and first[2]==0x6B and first[4:]==(0,0):pair=(first[1],first[3])
        else:raise SourceError('ioi_symbol_profile_unsupported')
        symbol=by_id.get(pair)
        if symbol is None or symbol.key not in project.tags:raise SourceError('ioi_symbol_unavailable')
        tag=project.tags[symbol.key]
        if tag.problem or tag.tag_class!='Standard':raise SourceError('ioi_symbol_source_unsupported')
        name=(symbol.name if not symbol.scope or symbol.scope.casefold()==program.casefold()
              else 'Program:'+symbol.scope+'.'+symbol.name)
        name,current=indexed(name,tag.value,suffixes[0]);dtype=tag.dtype
        for word,suffix in zip(words[1:],suffixes[1:]):
            if isinstance(current,list) or word[0]!=0x6C or word[2]!=0x84FE or word[4:]!=(0,0):
                raise SourceError('ioi_member_profile_unsupported')
            definition=types.types.get(dtype.casefold())
            if definition is None or types.type_ids.get(dtype.casefold())!=word[1]:
                raise SourceError('ioi_member_type_unavailable')
            # Native member paths in this profile are one-based; TagInfo's
            # checked Index/order is zero-based, including hidden members.
            if not 1<=word[3]<=len(definition.members):raise SourceError('ioi_member_index_unavailable')
            member=definition.members[word[3]-1]
            if member.hidden:raise SourceError('ioi_hidden_member_unsupported')
            keys=[key for key in current if key.casefold()==member.name.casefold()] if isinstance(current,dict) else []
            if len(keys)!=1:raise SourceError('ioi_member_source_unavailable')
            name,current=indexed(name+'.'+member.name,current[keys[0]],suffix);dtype=member.dtype
        return name

    def emit(nodes):
        result=[]
        for node in nodes:
            if isinstance(node,Branch):result.append('['+','.join(emit(path) for path in node.paths)+']')
            else:result.append(node.name+'('+','.join(argument(a,node.name=='JSR' and i==0,
                    node.name if (node.name=='CPT' and i==1 or node.name=='CMP' and i==0) else None)
                                                     for i,a in enumerate(node.args))+')')
        return ''.join(result)
    try:return tuple(emit(parse_rung(r.text_ioi))+';' for r in source.rungs)
    except ModelError as error:raise SourceError('ioi_ladder_syntax_unsupported') from error


def candidate_project(source,neutral,project,program):
    """Build an independent routine table; preserve original artifact bindings."""
    import copy
    if len(neutral)!=len(source.rungs):raise SourceError('ioi_candidate_rung_count_mismatch')
    key=(program+'/'+source.name).casefold()
    if key not in project.routines:raise SourceError('ioi_candidate_routine_unavailable')
    candidate=copy.copy(project);candidate.routines=dict(project.routines)
    node=ET.Element('Routine',Name=source.name,Type='RLL');content=ET.SubElement(node,'RLLContent')
    for index,text in enumerate(neutral):ET.SubElement(ET.SubElement(content,'Rung',Type='N',Number=str(index)),'Text').text=text
    candidate.routines[key]=candidate._routine(node,program,count=False)
    old=list(project.routines[key].rungs)
    for rung in candidate.routines[key].rungs:
        match=next((i for i,item in enumerate(old) if item['nodes']==rung['nodes']),None)
        if match is not None:rung['comment']=old.pop(match)['comment']
    return candidate,key


def validate_plan(source,neutral,project,program):
    """Check a detached candidate using existing parser/planner and preview prescan."""
    from .runtime import Engine
    from .model import ModelError
    candidate,key=candidate_project(source,neutral,project,program)
    try:
        engine=Engine(candidate,defer_prescan=True)
        if key not in engine.active:
            engine.active.add(key);engine._plan()
        if engine.blockers:raise SourceError('ioi_candidate_execution_plan_unsupported')
    except ModelError as error:raise SourceError('ioi_candidate_execution_plan_invalid') from error
