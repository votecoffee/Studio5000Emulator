"""Explicit v35 Task settings, without inferring native task identities."""
from dataclasses import dataclass, field
import re
import struct
from types import MappingProxyType
from typing import Mapping

from .tag_catalog import complete_tag_source
from .program_configuration import ORDINARY_ATTRIBUTES

MAX_TASKS = 32
MAX_PROGRAMS = 4096
MAX_SCHEDULED_PROGRAMS = 1028
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
MEMORY_FIELDS=frozenset(('Name','Class','Use','Type','Rate','Priority','Watchdog','DisableUpdateOutputs','InhibitTask'))


@dataclass(frozen=True)
class TaskSettings:
    name: str
    priority: int | None = None
    disable_output_update: bool | None = None
    inhibited: bool | None = None
    scheduled_programs: tuple[str, ...] | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not NAME.fullmatch(self.name):
            raise ValueError('Invalid Task name')
        if self.priority is not None and (type(self.priority) is not int or not 1 <= self.priority <= 15):
            raise ValueError('Invalid Task priority')
        if any(value is not None and type(value) is not bool
               for value in (self.disable_output_update, self.inhibited)):
            raise ValueError('Invalid Task boolean setting')
        if self.scheduled_programs is not None and (
                not isinstance(self.scheduled_programs, tuple) or len(self.scheduled_programs)>MAX_SCHEDULED_PROGRAMS
                or any(not isinstance(name,str) or not NAME.fullmatch(name) for name in self.scheduled_programs)
                or len({name.casefold() for name in self.scheduled_programs})!=len(self.scheduled_programs)):
            raise ValueError('Invalid Task program schedule')

    def attributes(self):
        values = {}
        if self.priority is not None:values[6] = struct.pack('<H', self.priority)
        if self.disable_output_update is not None:values[18] = struct.pack('<I', self.disable_output_update)
        if self.inhibited is not None:values[19] = struct.pack('<I', self.inhibited)
        return values


def _program_names(controller):
    programs=controller.findall('./Programs/Program')
    if len(programs)>MAX_PROGRAMS or controller.findall('.//Program')!=programs:return None
    result={}
    for program in programs:
        name=program.get('Name','')
        if (not NAME.fullmatch(name) or name.casefold() in result or
                any(key not in ('Name','Class','Use') and key.rsplit('}',1)[-1].casefold() in ('name','class','use')
                    for key in program.attrib)):
            return None
        result[name.casefold()]=(name,program.get('Class') in (None,'Standard') and
            program.get('Type') in (None,'Normal') and not program.attrib.keys()-ORDINARY_ATTRIBUTES and
            program.get('UseAsFolder') in (None,'false'))
    return result


def _scheduled_programs(task, programs):
    """An explicit list can establish zero entries; an omitted list cannot."""
    if programs is None:return None
    containers=task.findall('ScheduledPrograms')
    entries=task.findall('./ScheduledPrograms/ScheduledProgram')
    if (len(containers)!=1 or len(entries)>MAX_SCHEDULED_PROGRAMS
            or task.findall('.//ScheduledPrograms')!=containers or task.findall('.//ScheduledProgram')!=entries):
        return None
    for node in task.iter():
        local=node.tag.rsplit('}',1)[-1].casefold()
        if local not in ('scheduledprograms','scheduledprogram'):continue
        if node.tag!={'scheduledprograms':'ScheduledPrograms','scheduledprogram':'ScheduledProgram'}[local]:return None
        if node.get('Use') not in (None,'Target'):return None
        if any(key not in (('Use',) if local=='scheduledprograms' else ('Name','Use')) for key in node.attrib):return None
        if local=='scheduledprograms' and any(child.tag!='ScheduledProgram' for child in node):return None
        if local=='scheduledprograms' and ((node.text or '').strip() or any((child.tail or '').strip() for child in node)):return None
        if local=='scheduledprogram' and (len(node) or (node.text or '').strip()):return None
    names=[];seen=set()
    for entry in entries:
        name=entry.get('Name','')
        target=programs.get(name.casefold()) if isinstance(name,str) else None
        if not target or not target[1] or name.casefold() in seen:return None
        seen.add(name.casefold());names.append(target[0])
    return tuple(names)


@dataclass(frozen=True)
class TaskConfiguration:
    source_sha256: str
    source_complete: bool = False
    _tasks: Mapping[str, TaskSettings] = field(default_factory=dict, repr=False)
    unavailable_tasks: int = 0
    _program_owners: Mapping[str,str] = field(default_factory=dict,repr=False)
    _unscheduled_programs: frozenset[str] = field(default_factory=frozenset,repr=False)
    _standard_memory_tasks: frozenset[str] = field(default_factory=frozenset,repr=False)

    def __post_init__(self):
        if not isinstance(self.source_sha256, str) or not SHA256.fullmatch(self.source_sha256):
            raise ValueError('Invalid Task source hash')
        rows = dict(self._tasks)
        if (len(rows) > MAX_TASKS or any(not isinstance(value, TaskSettings)
                or key != value.name.casefold() for key, value in rows.items())):
            raise ValueError('Invalid Task settings inventory')
        if type(self.source_complete) is not bool or (rows and not self.source_complete):
            raise ValueError('Task settings require complete source')
        if type(self.unavailable_tasks) is not int or not 0 <= self.unavailable_tasks <= MAX_TASKS:
            raise ValueError('Invalid unavailable Task count')
        object.__setattr__(self, '_tasks', MappingProxyType(rows))
        owners=dict(self._program_owners)
        claims={}
        for name,row in rows.items():
            for program in row.scheduled_programs or ():
                claims.setdefault(program.casefold(),[]).append(name)
        if (len(owners)>MAX_PROGRAMS or any(not isinstance(p,str) or not NAME.fullmatch(p) or p!=p.casefold()
                or not isinstance(t,str) or claims.get(p)!=[t] for p,t in owners.items())):
            raise ValueError('Invalid Program Task owners')
        unscheduled=self._unscheduled_programs
        if (not isinstance(unscheduled,(set,frozenset)) or len(unscheduled)>MAX_PROGRAMS or
                any(not isinstance(p,str) or not NAME.fullmatch(p) or p!=p.casefold() or p in claims for p in unscheduled)):
            raise ValueError('Invalid unscheduled Program inventory')
        if (owners or unscheduled) and (not self.source_complete or not all(row.scheduled_programs is not None for row in rows.values())):
            raise ValueError('Program owners require complete Task schedules')
        object.__setattr__(self,'_program_owners',MappingProxyType(owners))
        object.__setattr__(self,'_unscheduled_programs',frozenset(unscheduled))
        memory=self._standard_memory_tasks
        if (not isinstance(memory,(set,frozenset)) or not memory<=rows.keys() or memory and not self.source_complete):
            raise ValueError('Invalid Standard Task memory inventory')
        object.__setattr__(self,'_standard_memory_tasks',frozenset(memory))

    @classmethod
    def from_source(cls, root, controller, source_sha256):
        unavailable = cls(source_sha256)
        if not complete_tag_source(root, controller) or controller.get('MajorRev') != '35':
            return unavailable
        containers = controller.findall('Tasks')
        tasks = controller.findall('./Tasks/Task')
        if (len(containers) > 1 or len(tasks) > MAX_TASKS or controller.findall('.//Task') != tasks
                or controller.findall('.//Tasks') != containers):
            return unavailable
        fields = {'Name', 'Class', 'Priority', 'DisableUpdateOutputs', 'InhibitTask', 'Use'}
        for node in controller.iter():
            local = node.tag.rsplit('}', 1)[-1].casefold()
            if local not in ('tasks', 'task'):continue
            if node.tag != {'tasks':'Tasks', 'task':'Task'}[local] or node.get('Use') not in (None, 'Target'):
                return unavailable
            if local == 'tasks' and any(child.tag != 'Task' for child in node):return unavailable
            if any(key not in fields and key.rsplit('}', 1)[-1].casefold() in {f.casefold() for f in fields}
                   for key in node.attrib):return unavailable
        names = [task.get('Name', '') for task in tasks]
        if (any(not NAME.fullmatch(name) for name in names)
                or len({name.casefold() for name in names}) != len(names)):
            return unavailable
        schedule_nodes={node for task in tasks for node in
                        task.findall('ScheduledPrograms')+task.findall('./ScheduledPrograms/ScheduledProgram')}
        canonical_schedule_scope=all(node in schedule_nodes for node in controller.iter()
            if node.tag.rsplit('}',1)[-1].casefold() in ('scheduledprograms','scheduledprogram'))
        programs=_program_names(controller) if canonical_schedule_scope else None
        schedules={name.casefold():_scheduled_programs(task,programs) for task,name in zip(tasks,names)
                   if task.get('Class') in (None,'Standard')}
        owners={};conflicts=set()
        for task_name,schedule in schedules.items():
            for program in schedule or ():
                key=program.casefold()
                if key in owners:conflicts.update((task_name,owners[key]))
                else:owners[key]=task_name
        for task_name in conflicts:schedules[task_name]=None
        values = {}
        for task, name in zip(tasks, names):
            if task.get('Class') not in (None, 'Standard'):continue
            raw = task.get('Priority', '')
            priority = int(raw) if re.fullmatch(r'[1-9][0-9]?', raw) and 1 <= int(raw) <= 15 else None
            booleans = [None if task.get(field) not in ('true', 'false') else task.get(field) == 'true'
                        for field in ('DisableUpdateOutputs', 'InhibitTask')]
            values[name.casefold()] = TaskSettings(name, priority, *booleans,schedules.get(name.casefold()))
        missing = len(tasks) - sum(bool(row.attributes()) for row in values.values())
        proven_owners={};unscheduled=frozenset()
        if len(values)==len(tasks) and all(row.scheduled_programs is not None for row in values.values()):
            proven_owners={program.casefold():name for name,row in values.items() for program in row.scheduled_programs}
            unscheduled=frozenset(n for n,(_,ordinary) in (programs or {}).items() if ordinary and n not in proven_owners)
        memory=frozenset(task.get('Name').casefold() for task in tasks
            if task.get('Name').casefold() in values and not task.attrib.keys()-MEMORY_FIELDS
            and task.get('Type') in ('Continuous','CONTINUOUS','Periodic','PERIODIC')
            and all(node.tag in ('Description','ScheduledPrograms') for node in task))
        return cls(source_sha256, True, values, missing,proven_owners,unscheduled,memory)

    @property
    def names(self):
        return tuple(row.name for row in self._tasks.values())

    def attributes(self, task, *, source_sha256):
        if source_sha256 != self.source_sha256 or not isinstance(task, str):return {}
        row = self._tasks.get(task.casefold()) if self.source_complete else None
        return row.attributes() if row else {}

    def memory_attributes(self,task,*,source_sha256):
        if (source_sha256!=self.source_sha256 or not self.source_complete or not isinstance(task,str) or
                task.casefold() not in self._standard_memory_tasks):return {}
        return {20:bytes(2)}

    def measurement_supported(self,task,*,source_sha256):
        if not self.memory_attributes(task,source_sha256=source_sha256):return False
        row=self._tasks.get(task.casefold())
        return (row is not None and row.scheduled_programs is not None and row.priority is not None
                and row.disable_output_update is not None and row.inhibited is False)

    def scheduled_attributes(self, task, *, source_sha256, source_acd_sha256, program_ids,
                             program_source_l5x_sha256, program_source_acd_sha256):
        """Bind the ordered source list to actual same-source native Program IDs.

        The expected ACD hash belongs to the independently bound Task catalog.
        A missing or conflicting Program binding withholds the entire list.
        Task IDs and source ordering never manufacture a Program ID.
        """
        if (source_sha256!=self.source_sha256 or program_source_l5x_sha256!=self.source_sha256
                or not isinstance(source_acd_sha256,str) or not SHA256.fullmatch(source_acd_sha256)
                or program_source_acd_sha256!=source_acd_sha256 or not isinstance(task,str)
                or not isinstance(program_ids,Mapping) or len(program_ids)>MAX_PROGRAMS):
            return {}
        row=self._tasks.get(task.casefold()) if self.source_complete else None
        if row is None or row.scheduled_programs is None:return {}
        bindings={};instances=set()
        for name,instance in dict(program_ids).items():
            if (not isinstance(name,str) or not NAME.fullmatch(name) or name.casefold() in bindings
                    or type(instance) is not int or not 1<=instance<=0xFFFFFFFF or instance in instances):
                return {}
            bindings[name.casefold()]=instance;instances.add(instance)
        if any(name.casefold() not in bindings for name in row.scheduled_programs):return {}
        ids=[bindings[name.casefold()] for name in row.scheduled_programs]
        return {1:struct.pack('<H',len(ids))+b''.join(struct.pack('<I',instance) for instance in ids)}

    def description(self):
        return {'source_complete':self.source_complete, 'attributes':[1, 6, 18, 19, 20],
                'tasks_available':sum(bool(row.attributes()) for row in self._tasks.values()),
                'tasks_unavailable':self.unavailable_tasks, 'missing_values_defaulted':False,
                'source':'Explicit Task priority, output-update and inhibit settings in complete v35 source',
                'source_schedules_available':sum(row.scheduled_programs is not None for row in self._tasks.values()),
                'scheduled_program_targets':sum(len(row.scheduled_programs or ()) for row in self._tasks.values()),
                'program_list_binding_required':True,'task_instance_readback':False,
                'program_owner_attribute':13,'program_owners_available':len(self._program_owners),
                'source_unscheduled_programs':len(self._unscheduled_programs),
                'standard_memory_tasks_available':len(self._standard_memory_tasks),'standard_memory_code':0,
                'safety_memory_modeled':False,
                'native_id_inferred':False, 'native_writes':False, 'execution_state_changed':False}

    def owner_attributes(self,program,*,source_sha256,source_acd_sha256,task_ids,
                         task_source_l5x_sha256,task_source_acd_sha256):
        if (source_sha256!=self.source_sha256 or task_source_l5x_sha256!=self.source_sha256 or
                not isinstance(source_acd_sha256,str) or not SHA256.fullmatch(source_acd_sha256) or
                task_source_acd_sha256!=source_acd_sha256 or not self.source_complete or
                not isinstance(program,str) or (program.casefold() not in self._program_owners and
                    program.casefold() not in self._unscheduled_programs) or
                not isinstance(task_ids,Mapping) or len(task_ids)>MAX_TASKS):return {}
        bindings={};ids=set()
        for name,instance in dict(task_ids).items():
            if (not isinstance(name,str) or not NAME.fullmatch(name) or name.casefold() in bindings or
                    type(instance) is not int or not 1<=instance<=0xFFFF or instance in ids):return {}
            bindings[name.casefold()]=instance;ids.add(instance)
        if bindings.keys()!=self._tasks.keys():return {}
        owner=self._program_owners.get(program.casefold())
        return {13:struct.pack('<I',bindings[owner] if owner is not None else 0)}
