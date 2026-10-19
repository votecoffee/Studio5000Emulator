"""Source-checked discovery of empty motion object catalogs.

Motion groups are controller tags of type MOTION_GROUP. Their L5X configuration
uses Data@Format="MotionGroup" / MotionGroupParameters (1756-RM014, chapter 6).
Axis configuration uses AXIS_* tags and Data@Format="Axis" / AxisParameters.
Coordinate systems use COORDINATE_SYSTEM tags and CoordinateSystem parameters.
Nonempty catalogs and motion configuration/execution remain unsupported.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MotionCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        sections = controller.findall('Tags')
        complete = (root.get('ContainsContext') == 'false'
                    and controller.get('Use') in (None, 'Target')
                    and root.findall('Controller') == [controller]
                    and len(sections) == 1
                    and sections[0].get('Use') in (None, 'Target'))
        if not complete:
            return cls(False)
        for tag in sections[0]:
            if (tag.tag != 'Tag' or not tag.get('DataType')
                    or tag.get('Use') not in (None, 'Target')):
                return cls(False)
        # Inspect XML, not just parsed runtime tags: unsupported types and
        # protected data must not disappear from the discovery decision.
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if (node.get('DataType', '').upper() == 'MOTION_GROUP'
                    or node.get('DataType', '').upper() == 'COORDINATE_SYSTEM'
                    or node.get('DataType', '').upper().startswith('AXIS_')
                    or node.get('Format', '').lower() in ('motiongroup', 'axis', 'coordinatesystem')
                    or name.startswith(('motiongroup', 'axis', 'coordinatesystem'))
                    or name == 'tags' and node.tag != 'Tags'):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'source': 'complete Controller L5X tags and motion configuration',
                'instance_list': self.empty, 'motion_configuration': False,
                'motion_execution': False}
