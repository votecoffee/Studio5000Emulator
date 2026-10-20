"""Explicit v35 Task settings, without inferring native task identities."""
from dataclasses import dataclass, field
import re
import struct
from types import MappingProxyType
from typing import Mapping

from .tag_catalog import complete_tag_source

MAX_TASKS = 32
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,39}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True)
class TaskSettings:
    name: str
    priority: int | None = None
    disable_output_update: bool | None = None
    inhibited: bool | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not NAME.fullmatch(self.name):
            raise ValueError('Invalid Task name')
        if self.priority is not None and (type(self.priority) is not int or not 1 <= self.priority <= 15):
            raise ValueError('Invalid Task priority')
        if any(value is not None and type(value) is not bool
               for value in (self.disable_output_update, self.inhibited)):
            raise ValueError('Invalid Task boolean setting')

    def attributes(self):
        values = {}
        if self.priority is not None:values[6] = struct.pack('<H', self.priority)
        if self.disable_output_update is not None:values[18] = struct.pack('<I', self.disable_output_update)
        if self.inhibited is not None:values[19] = struct.pack('<I', self.inhibited)
        return values


@dataclass(frozen=True)
class TaskConfiguration:
    source_sha256: str
    source_complete: bool = False
    _tasks: Mapping[str, TaskSettings] = field(default_factory=dict, repr=False)
    unavailable_tasks: int = 0

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
        values = {}
        for task, name in zip(tasks, names):
            if task.get('Class') not in (None, 'Standard'):continue
            raw = task.get('Priority', '')
            priority = int(raw) if re.fullmatch(r'[1-9][0-9]?', raw) and 1 <= int(raw) <= 15 else None
            booleans = [None if task.get(field) not in ('true', 'false') else task.get(field) == 'true'
                        for field in ('DisableUpdateOutputs', 'InhibitTask')]
            values[name.casefold()] = TaskSettings(name, priority, *booleans)
        missing = len(tasks) - sum(bool(row.attributes()) for row in values.values())
        return cls(source_sha256, True, values, missing)

    @property
    def names(self):
        return tuple(row.name for row in self._tasks.values())

    def attributes(self, task, *, source_sha256):
        if source_sha256 != self.source_sha256 or not isinstance(task, str):return {}
        row = self._tasks.get(task.casefold()) if self.source_complete else None
        return row.attributes() if row else {}

    def description(self):
        return {'source_complete':self.source_complete, 'attributes':[6, 18, 19],
                'tasks_available':sum(bool(row.attributes()) for row in self._tasks.values()),
                'tasks_unavailable':self.unavailable_tasks, 'missing_values_defaulted':False,
                'source':'Explicit Task priority, output-update and inhibit settings in complete v35 source',
                'native_id_inferred':False, 'native_writes':False, 'execution_state_changed':False}
