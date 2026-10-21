"""Source-backed Program settings for complete v35 controller exports.

The installed plain v35 Program ADF defines attribute 19 as one BITS8 value.
Only an explicit canonical Program@Disabled boolean supplies that byte. This
reader does not infer an enabled program from a missing or malformed field,
change execution state, or provide native online-edit write authority.
Attribute 30 is the separate one-byte Program Type; ordinary user Programs
are 1, without inferring phase/sequence kinds or making Disable available.
"""
from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Mapping

from .tag_catalog import complete_tag_source


MAX_PROGRAMS = 4096
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
ATTRIBUTE = 19
ORDINARY_ATTRIBUTES = frozenset(('Name','Class','Type','Use','TestEdits','MainRoutineName',
    'FaultRoutineName','Disabled','UseAsFolder','SynchronizeRedundancyDataAfterExecution'))


def _nonredundant_l85e(controller):
    """Narrow model profile; never infer disabled redundancy from its absence."""
    processor=[key for key in controller.attrib
               if key.rsplit('}',1)[-1].casefold().startswith('processortype')]
    revision=[key for key in controller.attrib if key.rsplit('}',1)[-1].casefold().startswith('majorrev')]
    if (processor!=['ProcessorType'] or controller.get('ProcessorType')!='1756-L85E' or
            revision!=['MajorRev'] or controller.get('MajorRev')!='35'):return False
    nodes=[node for node in controller.iter() if node.tag.rsplit('}',1)[-1].casefold()=='redundancyinfo']
    if len(nodes)!=1 or nodes!=controller.findall('RedundancyInfo'):return False
    node=nodes[0]
    return (not len(node) and not (node.text or '').strip() and
            not node.attrib.keys()-{'Enabled','KeepTestEditsOnSwitchOver'} and
            node.get('Enabled')=='false' and node.get('KeepTestEditsOnSwitchOver') in (None,'true','false'))


@dataclass(frozen=True)
class ProgramConfiguration:
    source_sha256: str
    source_complete: bool = False
    _disabled: Mapping[str, bool] = field(default_factory=dict, repr=False)
    unavailable_programs: int = 0
    _ordinary: frozenset[str] = field(default_factory=frozenset, repr=False)
    _synchronize: Mapping[str, bool] = field(default_factory=dict, repr=False)
    _can_schedule: Mapping[str, bool] = field(default_factory=dict, repr=False)
    _synchronize_defaulted: frozenset[str] = field(default_factory=frozenset, repr=False)

    def __post_init__(self):
        if not isinstance(self.source_sha256, str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Program configuration source hash')
        rows = dict(self._disabled)
        if (len(rows) > MAX_PROGRAMS or any(not isinstance(name, str) or not NAME.fullmatch(name)
                or name.casefold() != name or type(value) is not bool for name, value in rows.items())):
            raise ValueError('Invalid Program configuration values')
        if type(self.source_complete) is not bool or (rows and not self.source_complete):
            raise ValueError('Program configuration requires complete source')
        if type(self.unavailable_programs) is not int or not 0 <= self.unavailable_programs <= MAX_PROGRAMS:
            raise ValueError('Invalid unavailable Program count')
        if not isinstance(self._ordinary,(set,frozenset)):
            raise ValueError('Invalid ordinary Program inventory')
        ordinary = frozenset(self._ordinary)
        if (len(ordinary) > MAX_PROGRAMS or ordinary and not self.source_complete or
                any(not isinstance(name,str) or not NAME.fullmatch(name) or name.casefold()!=name for name in ordinary)):
            raise ValueError('Invalid ordinary Program inventory')
        object.__setattr__(self, '_disabled', MappingProxyType(rows))
        object.__setattr__(self, '_ordinary', ordinary)
        for attribute in ('_synchronize','_can_schedule'):
            flags=dict(getattr(self,attribute))
            if any(name not in ordinary or type(value) is not bool for name,value in flags.items()):
                raise ValueError('Invalid ordinary Program flags')
            object.__setattr__(self,attribute,MappingProxyType(flags))
        defaults=self._synchronize_defaulted
        if (not isinstance(defaults,(set,frozenset)) or
                any(name not in self._synchronize or self._synchronize[name] is not True for name in defaults)):
            raise ValueError('Invalid defaulted Program synchronization inventory')
        object.__setattr__(self,'_synchronize_defaulted',frozenset(defaults))

    @classmethod
    def from_source(cls, root, controller, source_sha256):
        unavailable = cls(source_sha256)
        if not complete_tag_source(root, controller) or controller.get('MajorRev') != '35':
            return unavailable
        programs = controller.findall('./Programs/Program')
        # Nested or shadow declarations must never share the visible inventory.
        if len(programs) > MAX_PROGRAMS or controller.findall('.//Program') != programs:
            return unavailable
        names = [program.get('Name', '') for program in programs]
        if (any(not isinstance(name, str) or not NAME.fullmatch(name) for name in names)
                or len({name.casefold() for name in names}) != len(names)):
            return unavailable
        values = {};ordinary = set();synchronize={};can_schedule={};defaulted=set()
        model_default=_nonredundant_l85e(controller)
        for name, program in zip(names, programs):
            fields = ('Name', 'Class', 'Disabled')
            aliases = [key for key in program.attrib
                       if key.rsplit('}', 1)[-1].casefold() in {item.casefold() for item in fields}
                       and key not in fields]
            if aliases:
                return unavailable
            # Native ordinary-program exports may omit Class. This reader does
            # not manufacture its value: the Router must still apply its bound
            # Standard-program eligibility check before asking for attributes.
            if program.get('Class') not in (None, 'Standard'):
                continue
            # Canonical Programs/Program is the ordinary user-program form.
            # Kind overrides must not turn phases or sequences into user Programs.
            if (not program.attrib.keys()-ORDINARY_ATTRIBUTES and program.get('Type') in (None,'Normal')
                    and all(child.tag in ('Description','Tags','Routines','ChildPrograms') for child in program)):
                ordinary.add(name.casefold())
                value=program.get('SynchronizeRedundancyDataAfterExecution')
                if value in ('true','false'):synchronize[name.casefold()]=value=='true'
                elif value is None and model_default and program.get('UseAsFolder')=='false':
                    # Studio omits this inactive option on nonredundant exports.
                    # Initialize our model's documented new-Program default;
                    # this does not recover a checkbox from the original ACD.
                    synchronize[name.casefold()]=True;defaulted.add(name.casefold())
                value=program.get('UseAsFolder')
                if value in ('true','false'):can_schedule[name.casefold()]=value=='false'
            value = program.get('Disabled')
            if value not in ('true', 'false'):
                continue
            values[name.casefold()] = value == 'true'
        return cls(source_sha256, True, values, len(programs) - len(values), frozenset(ordinary),synchronize,can_schedule,frozenset(defaulted))

    def attributes(self, program, *, source_sha256):
        if source_sha256 != self.source_sha256 or not isinstance(program, str):
            return {}
        name = program.casefold()
        if not self.source_complete or name not in self._disabled:
            return {}
        return {ATTRIBUTE: bytes((int(self._disabled[name]),))}

    def description(self):
        return {'source_complete': self.source_complete, 'attributes': [ATTRIBUTE,26,29,30,31],
                'source': 'Explicit Program@Disabled in complete v35 program declarations',
                'encoding': 'BITS8; false=0, true=1', 'programs_available': len(self._disabled),
                'programs_unavailable': self.unavailable_programs, 'missing_values_defaulted': bool(self._synchronize_defaulted),
                'ordinary_programs_available':len(self._ordinary),'ordinary_program_type':1,
                'program_type_source':'Complete v35 Programs/Program; Standard or omitted Class; Normal or omitted Type; canonical fields only',
                'phase_sequence_types':False,
                'standard_memory_programs_available':len(self._ordinary),'standard_memory_code':0,
                'safety_memory_modeled':False,
                'synchronize_flags_available':len(self._synchronize),'can_schedule_flags_available':len(self._can_schedule),
                'synchronize_source_values':len(self._synchronize)-len(self._synchronize_defaulted),
                'synchronize_model_defaults':len(self._synchronize_defaulted),
                'synchronize_default_profile':'Complete ordinary v35 L85E; explicit disabled redundancy; explicit nonfolder; omitted synchronization only',
                'synchronize_default_recovers_original_acd_setting':False,
                'flag_source':'Explicit canonical L5X booleans; narrowly identified nonredundant synchronization model defaults',
                'redundancy_execution':False,
                'execution_state_changed': False, 'native_writes': False, 'online_edit_acceptance': False}

    def flag_attributes(self, program, *, source_sha256):
        if source_sha256!=self.source_sha256 or not self.source_complete or not isinstance(program,str):return {}
        name=program.casefold();values={}
        for number,flags in ((29,self._synchronize),(31,self._can_schedule)):
            if name in flags:values[number]=bytes((int(flags[name]),))
        return values

    def type_attributes(self, program, *, source_sha256):
        if (source_sha256!=self.source_sha256 or not self.source_complete or
                not isinstance(program,str) or program.casefold() not in self._ordinary):return {}
        return {30:b'\1'}

    def memory_attributes(self,program,*,source_sha256):
        if not self.type_attributes(program,source_sha256=source_sha256):return {}
        return {26:bytes(2)}
