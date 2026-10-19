"""Empty Digital/Analog Alarm discovery backed by complete L5X source.

ALARM_DIGITAL and ALARM_ANALOG tags use Data@Format="Alarm" and
AlarmDigitalParameters / AlarmAnalogParameters (1756-RM014, chapter 6).
Nonempty catalogs, alarm configuration and alarm execution are not modeled.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        tags = controller.findall('Tags')
        if (root.get('ContainsContext') != 'false'
                or root.findall('Controller') != [controller]
                or controller.get('Use') not in (None, 'Target')
                or len(tags) != 1 or len(controller.findall('Programs')) > 1):
            return cls(False)
        # Include original controller/program/AOI declarations: unsupported
        # alarm types must not vanish when runtime tags are filtered out.
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if name in ('tags', 'tag', 'localtags', 'localtag', 'programs', 'program'):
                if node.tag != {'tags':'Tags', 'tag':'Tag', 'localtags':'LocalTags',
                                'localtag':'LocalTag', 'programs':'Programs', 'program':'Program'}[name]:
                    return cls(False)
                if node.get('Use') not in (None, 'Target'):
                    return cls(False)
            if name == 'programs' and any(child.tag != 'Program' for child in node):
                return cls(False)
            if name == 'program' and len(node.findall('Tags')) != 1:
                return cls(False)
            if name in ('tags', 'localtags'):
                expected = 'Tag' if name == 'tags' else 'LocalTag'
                if any(child.tag != expected or not child.get('DataType') for child in node):
                    return cls(False)
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
