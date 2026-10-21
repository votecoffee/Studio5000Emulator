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


@dataclass(frozen=True)
class ProgramDiagnostics:
    source_sha256: str
    _empty_outputs: frozenset[str] = field(default_factory=frozenset,repr=False)
    _untested: frozenset[str] = field(default_factory=frozenset,repr=False)

    def __post_init__(self):
        if not isinstance(self.source_sha256,str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Program diagnostic source hash')
        for attribute in ('_empty_outputs','_untested'):
            names=getattr(self,attribute)
            if (not isinstance(names,(set,frozenset)) or len(names)>MAX_PROGRAMS or
                    any(not isinstance(n,str) or not NAME.fullmatch(n) or n!=n.casefold() for n in names)):
                raise ValueError('Invalid Program diagnostic inventory')
            object.__setattr__(self,attribute,frozenset(names))

    @classmethod
    def from_source(cls,root,controller,source_sha256,configuration,executable,io_map):
        if (not complete_tag_source(root,controller) or controller.get('MajorRev')!='35' or
                configuration.source_sha256!=source_sha256 or executable.source_sha256!=source_sha256):return cls(source_sha256)
        outputs=set();untested=set();empty=no_output_connections(controller,io_map)
        for program in controller.findall('./Programs/Program'):
            name=program.get('Name')
            if not configuration.type_attributes(name,source_sha256=source_sha256):continue
            if empty:outputs.add(name.casefold())
            if untested_rll(program,executable,source_sha256):untested.add(name.casefold())
        return cls(source_sha256,outputs,untested)

    def output_attributes(self,program,*,source_sha256):
        if (source_sha256!=self.source_sha256 or not isinstance(program,str) or
                program.casefold() not in self._empty_outputs):return {}
        return {7:bytes(4)}

    def edit_attributes(self,program,*,source_sha256,idle):
        if (idle is not True or source_sha256!=self.source_sha256 or not isinstance(program,str) or
                program.casefold() not in self._untested):return {}
        return {11:bytes(2)}

    def description(self):
        return {'attributes':[7,11],'null_output_lists_available':len(self._empty_outputs),
                'untested_rll_programs_available':len(self._untested),'source_hash_required':True,
                'source':'Complete ordinary v35 source; no output connections; explicit TestEdits=false and normal RLL rungs',
                'native_edits_idle_required':True,'nonzero_output_addresses':False,
                'test_untest_assemble':False,'native_writes':False}
