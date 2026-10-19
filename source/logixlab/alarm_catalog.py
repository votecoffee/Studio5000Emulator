"""Empty Digital/Analog Alarm discovery backed by complete L5X source.

ALARM_DIGITAL and ALARM_ANALOG tags use Data@Format="Alarm" and
AlarmDigitalParameters / AlarmAnalogParameters (1756-RM014, chapter 6).
Nonempty catalogs, alarm configuration and alarm execution are not modeled.
"""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


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
            if (node.get('DataType', '').upper() in ('ALARM_DIGITAL', 'ALARM_ANALOG')
                    or node.get('Format', '').lower() == 'alarm'
                    or name in ('alarmdigitalparameters', 'alarmanalogparameters', 'alarmconfig')):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'source': 'complete Controller L5X alarm tags and configuration',
                'instance_list': self.empty, 'alarm_configuration': False,
                'alarm_execution': False}
