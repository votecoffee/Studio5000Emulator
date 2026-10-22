"""Read explicit source Task times in the Task object's microsecond units.

These immutable settings are not wall-clock measurements or scheduling control.
Continuous tasks have no inferred period. Missing/zero watchdog values do not
become a fabricated native default, and conversion never rounds a source value.
"""
from dataclasses import dataclass, field
import re
import struct
from types import MappingProxyType
from typing import Mapping

from .task_configuration import TaskConfiguration, NAME, SHA256, MAX_TASKS

MAX_TIME_US = 0x7FFFFFFF
MILLISECONDS = re.compile(r'(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,6})?\Z')
KINDS = {'Continuous':'Continuous', 'CONTINUOUS':'Continuous',
         'Periodic':'Periodic', 'PERIODIC':'Periodic', 'Event':'Event', 'EVENT':'Event'}
STORED_TYPE_CODES=MappingProxyType({'Continuous':4,'Periodic':2})


def microseconds(value):
    """Accept positive exact microseconds from bounded decimal milliseconds."""
    if not isinstance(value,str) or not MILLISECONDS.fullmatch(value):return None
    whole,_,fraction=value.partition('.')
    if any(digit!='0' for digit in fraction[3:]):return None
    converted=int(whole)*1000+int(fraction[:3].ljust(3,'0'))
    return converted if 0<converted<=MAX_TIME_US else None


@dataclass(frozen=True)
class TaskTimes:
    name: str
    kind: str
    rate_us: int | None = None
    watchdog_us: int | None = None
    declared_rate_us: int | None = None
    rate_present: bool = False

    def __post_init__(self):
        if not isinstance(self.name,str) or not NAME.fullmatch(self.name) or self.kind not in KINDS.values():
            raise ValueError('Invalid Task timing identity')
        for value in (self.rate_us,self.watchdog_us,self.declared_rate_us):
            if value is not None and (type(value) is not int or not 0<value<=MAX_TIME_US):
                raise ValueError('Invalid Task time')
        if self.rate_us is not None and self.kind!='Periodic':
            raise ValueError('Only an explicit periodic Task rate is supported')
        if type(self.rate_present) is not bool or self.declared_rate_us is not None and not self.rate_present:
            raise ValueError('Invalid explicit Task rate source')

    def attributes(self):
        values={}
        if self.rate_us is not None:values[2]=struct.pack('<I',self.rate_us)
        if self.watchdog_us is not None:values[12]=struct.pack('<I',self.watchdog_us)
        return values


@dataclass(frozen=True)
class TaskTiming:
    source_sha256: str
    source_complete: bool = False
    _tasks: Mapping[str,TaskTimes] = field(default_factory=dict,repr=False)

    def __post_init__(self):
        if not isinstance(self.source_sha256,str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Task timing source hash')
        rows=dict(self._tasks)
        if (type(self.source_complete) is not bool or len(rows)>MAX_TASKS
                or rows and not self.source_complete
                or any(not isinstance(row,TaskTimes) or name!=row.name.casefold() for name,row in rows.items())):
            raise ValueError('Invalid Task timing snapshot')
        object.__setattr__(self,'_tasks',MappingProxyType(rows))

    @classmethod
    def from_source(cls,root,controller,source_sha256,configuration=None):
        unavailable=cls(source_sha256)
        configuration=configuration or TaskConfiguration.from_source(root,controller,source_sha256)
        if not configuration.source_complete or configuration.source_sha256!=source_sha256:return unavailable
        fields={'Type','Rate','Watchdog'}
        rows={};eligible={name.casefold() for name in configuration.names}
        for task in controller.findall('./Tasks/Task'):
            if any(key not in fields and key.rsplit('}',1)[-1].casefold() in {field.casefold() for field in fields}
                   for key in task.attrib):return unavailable
            name=task.get('Name','');kind=KINDS.get(task.get('Type'))
            if name.casefold() not in eligible or kind is None:continue
            rate=microseconds(task.get('Rate')) if kind=='Periodic' else None
            rows[name.casefold()]=TaskTimes(name,kind,rate,microseconds(task.get('Watchdog')),
                microseconds(task.get('Rate')),'Rate' in task.attrib)
        return cls(source_sha256,True,rows)

    def attributes(self,task,*,source_sha256):
        if source_sha256!=self.source_sha256 or not isinstance(task,str):return {}
        row=self._tasks.get(task.casefold()) if self.source_complete else None
        return row.attributes() if row else {}

    def description(self):
        return {'source_complete':self.source_complete,'attributes':[2,12],
                'periodic_rates_available':sum(row.rate_us is not None for row in self._tasks.values()),
                'watchdogs_available':sum(row.watchdog_us is not None for row in self._tasks.values()),
                'source_unit':'decimal milliseconds','wire_unit':'microseconds',
                'conversion':'exact; no rounding or defaults','continuous_rate_inferred':False,
                'event_timeout_supported':False,'native_scheduler':False,'watchdog_enforced':False,
                'runtime_measurements':False,'native_writes':False}

    def matches_stored(self,task,*,source_sha256,kind_code,rate_us,watchdog_us):
        if source_sha256!=self.source_sha256 or not self.source_complete or not isinstance(task,str):return False
        row=self._tasks.get(task.casefold())
        if (row is None or row.kind not in STORED_TYPE_CODES or kind_code!=STORED_TYPE_CODES[row.kind]
                or row.watchdog_us!=watchdog_us or row.kind=='Periodic' and row.rate_us!=rate_us
                or row.rate_present and row.declared_rate_us!=rate_us):return False
        return True
