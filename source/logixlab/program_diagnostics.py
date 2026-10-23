"""Source proofs for absent Program output lists and untested plain RLL logic."""
from dataclasses import dataclass, field
from .program_configuration import NAME, SHA256, MAX_PROGRAMS
from .executable_configuration import _hidden
from .tag_catalog import complete_tag_source

OUTPUT_SECTIONS=frozenset(('Description','RedundancyInfo','Security','SafetyInfo',
    'DataTypes','Modules','AddOnInstructionDefinitions','Tags','Programs','Tasks',
    'CST','WallClockTime','Trends','DataLogs','TimeSynchronize','EthernetPorts'))


def no_output_connections(controller, io_map):
    if not io_map.empty or any(node.tag not in OUTPUT_SECTIONS for node in controller) or _hidden(controller):return False
    for node in controller.iter():
        local=node.tag.rsplit('}',1)[-1].casefold()
        if 'parameter' in local or 'connection' in local:return False
        if any(any(word in key.rsplit('}',1)[-1].casefold() for word in ('parameter','connection')) for key in node.attrib):return False
        if local not in ('tag','localtag'):continue
        if (node.get('TagType') not in (None,'Base') or node.get('Usage') not in (None,'Local') or
                any(key.rsplit('}',1)[-1].casefold().startswith(('aliasfor','usage','tagtype')) and
                    key not in ('Usage','TagType') for key in node.attrib)):
            return False
    return True


def untested_rll(program, executable, source_sha256):
    if (program.get('TestEdits')!='false' or _hidden(program) or
            executable.routine_names(program.get('Name'),source_sha256=source_sha256) is None):return False
    routines=program.findall('./Routines/Routine')
    if not routines:return False
    for routine in routines:
        if routine.get('Type')!='RLL':return False
        content=routine.find('RLLContent')
        if (content is None or content.attrib.keys()-{'Use'} or content.get('Use') not in (None,'Target') or
                (content.text or '').strip() or any(node.tag!='Rung' for node in content)):return False
        for rung in content:
            if (rung.get('Type')!='N' or rung.attrib.keys()-{'Type','Number','RegionId','Use'} or
                    rung.get('Use') not in (None,'Target') or (rung.text or '').strip() or
                    any(node.tag not in ('Text','Comment') or len(node) or node.attrib for node in rung)):return False
    for node in program.iter():
        if any('edit' in key.rsplit('}',1)[-1].casefold() and
               (key!='TestEdits' or node is not program) for key in node.attrib):return False
    return True


def signature_free(root):
    # Only a complete ordinary RLL declaration with canonical attributes can
    # establish absence. Unknown signature containers/aliases stay unavailable.
    for node in root.iter():
        if ('signature' in node.tag.rsplit('}',1)[-1].casefold() or
                any('signature' in key.casefold() for key in node.attrib)):return False
    return True


def empty_program(program, executable, source_sha256):
    """Prove an explicit empty declaration, rather than a missing named main."""
    sections=program.findall('Routines')
    return (program.get('TestEdits')=='false' and program.get('UseAsFolder')=='false'
            and program.get('Disabled') in ('true','false')
            and program.get('MainRoutineName') in (None,'')
            and program.get('FaultRoutineName') in (None,'')
            and executable.routine_names(program.get('Name'),source_sha256=source_sha256)==()
            and len(sections)==1 and not len(sections[0]) and not (sections[0].text or '').strip()
            and not sections[0].attrib.keys()-{'Use'} and sections[0].get('Use') in (None,'Target')
            and not any('edit' in key.rsplit('}',1)[-1].casefold()
                        and (key!='TestEdits' or node is not program)
                        for node in program.iter() for key in node.attrib))


def no_main_program(program, executable, source_sha256):
    """Known unassigned main, including stored ordinary uncalled RLL routines."""
    if empty_program(program,executable,source_sha256):return True
    sections=program.findall('Routines')
    return (program.get('UseAsFolder')=='false' and program.get('Disabled') in ('true','false')
            and program.get('MainRoutineName') in (None,'') and program.get('FaultRoutineName') in (None,'')
            and len(sections)==1 and not sections[0].attrib.keys()-{'Use'}
            and sections[0].get('Use') in (None,'Target') and not (sections[0].text or '').strip()
            and signature_free(program) and untested_rll(program,executable,source_sha256)
            and all(not routine.attrib.keys()-{'Name','Type','Class','Use'}
                    for routine in program.findall('./Routines/Routine')))


@dataclass(frozen=True)
class ProgramDiagnostics:
    source_sha256: str
    _empty_outputs: frozenset[str] = field(default_factory=frozenset,repr=False)
    _untested: frozenset[str] = field(default_factory=frozenset,repr=False)
    _unsigned: frozenset[str] = field(default_factory=frozenset,repr=False)
    _empty_programs: frozenset[str] = field(default_factory=frozenset,repr=False)
    _no_main_programs: frozenset[str] = field(default_factory=frozenset,repr=False)

    def __post_init__(self):
        if not isinstance(self.source_sha256,str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Program diagnostic source hash')
        for attribute in ('_empty_outputs','_untested','_unsigned','_empty_programs','_no_main_programs'):
            names=getattr(self,attribute)
            if (not isinstance(names,(set,frozenset)) or len(names)>MAX_PROGRAMS or
                    any(not isinstance(n,str) or not NAME.fullmatch(n) or n!=n.casefold() for n in names)):
                raise ValueError('Invalid Program diagnostic inventory')
            object.__setattr__(self,attribute,frozenset(names))
        if not self._empty_programs<=self._untested:
            raise ValueError('Empty Programs require a known untested source')
        if not self._no_main_programs<=self._untested:
            raise ValueError('Unassigned main Routines require a known untested source')

    @classmethod
    def from_source(cls,root,controller,source_sha256,configuration,executable,io_map):
        if (not complete_tag_source(root,controller) or controller.get('MajorRev')!='35' or
                configuration.source_sha256!=source_sha256 or executable.source_sha256!=source_sha256):return cls(source_sha256)
        outputs=set();untested=set();unsigned=set();empty_names=set();no_main_names=set();empty=no_output_connections(controller,io_map)
        no_signatures=signature_free(root)
        for program in controller.findall('./Programs/Program'):
            name=program.get('Name')
            if not configuration.type_attributes(name,source_sha256=source_sha256):continue
            if empty:outputs.add(name.casefold())
            is_empty=empty_program(program,executable,source_sha256)
            if is_empty:empty_names.add(name.casefold())
            if is_empty or untested_rll(program,executable,source_sha256):
                untested.add(name.casefold())
                if is_empty or (no_signatures and no_main_program(program,executable,source_sha256)):
                    no_main_names.add(name.casefold())
                if no_signatures and all(not r.attrib.keys()-{'Name','Type','Class','Use'}
                        for r in program.findall('./Routines/Routine')):unsigned.add(name.casefold())
        return cls(source_sha256,outputs,untested,unsigned,empty_names,no_main_names)

    def is_empty(self,program,*,source_sha256):
        return (source_sha256==self.source_sha256 and isinstance(program,str)
                and program.casefold() in self._empty_programs)

    def has_no_main(self,program,*,source_sha256):
        return (source_sha256==self.source_sha256 and isinstance(program,str)
                and program.casefold() in self._no_main_programs)

    def output_attributes(self,program,*,source_sha256):
        if (source_sha256!=self.source_sha256 or not isinstance(program,str) or
                program.casefold() not in self._empty_outputs):return {}
        return {7:bytes(4)}

    def edit_attributes(self,program,*,source_sha256,idle):
        if (idle is not True or source_sha256!=self.source_sha256 or not isinstance(program,str) or
                program.casefold() not in self._untested):return {}
        return {11:bytes(2)}

    def signature_attributes(self,program,*,source_sha256):
        if (source_sha256!=self.source_sha256 or not isinstance(program,str) or
                program.casefold() not in self._unsigned):return {}
        return {28:bytes(4)}

    def description(self):
        return {'attributes':[7,11],'null_output_lists_available':len(self._empty_outputs),
                'untested_rll_programs_available':len(self._untested),'source_hash_required':True,
                'empty_programs_available':len(self._empty_programs),
                'unassigned_main_programs_available':len(self._no_main_programs),
                'unsigned_rll_programs_available':len(self._unsigned),'native_signature_verification':False,
                'source':'Complete ordinary v35 source; no output connections; explicit TestEdits=false and normal RLL rungs or a confirmed empty Program',
                'native_edits_idle_required':True,'nonzero_output_addresses':False,
                'test_untest_assemble':False,'native_writes':False}
