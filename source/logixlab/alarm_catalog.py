"""Empty instruction and tag-based alarm discovery from complete L5X source.

ALARM_DIGITAL and ALARM_ANALOG tags use Data@Format="Alarm" and
AlarmDigitalParameters / AlarmAnalogParameters (1756-RM014, chapter 6).
Nonempty catalogs, alarm configuration and alarm execution are not modeled.
"""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


CLASSES = (0x331, 0x332, 0x3A6, 0x3A7, 0x3A8)
# Successful empty lists observed under original Program parents in v35.
PROGRAM_CLASSES = (0x331, 0x332)


@dataclass(frozen=True)
class AlarmCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        # Include original controller/program/AOI declarations: unsupported
        # alarm types must not vanish when runtime tags are filtered out.
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if (node.get('DataType', '').upper().startswith('ALARM_')
                    or any(word in node.get('Format', '').lower()
                           for word in ('alarm', 'encoded', 'encrypted', 'protected'))
                    or any(word in name for word in ('alarm', 'encoded', 'encrypted', 'protected'))
                    or any(any(word in key.lower() for word in ('encoded', 'encrypted', 'protected'))
                           for key in node.attrib)):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'source': 'complete Controller L5X alarm tags and configuration',
                'class_ids': list(CLASSES),
                'program_class_ids': list(PROGRAM_CLASSES),
                'program_scope_requires': 'Matching original native identity and ordinary Standard Program; complete alarm-free project source',
                'instance_list': self.empty, 'alarm_configuration': False,
                'alarm_execution': False}
