"""Source Time Sync settings and local software-clock capability metadata."""
from dataclasses import dataclass
import re
from .tag_catalog import complete_tag_source
from . import controller_schemas, software_clock


@dataclass(frozen=True)
class TimeSync:
    ptp_enabled: bool | None = None
    priority1: int | None = None
    priority2: int | None = None

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls()
        nodes = [node for node in controller.iter()
                 if node.tag.rsplit('}', 1)[-1].lower().startswith('timesynchronize')]
        if len(nodes) != 1 or nodes != controller.findall('TimeSynchronize'):
            return cls()
        node = nodes[0]
        if node.get('Use') not in (None, 'Target') or len(node) or (node.text or '').strip():
            return cls()
        fields = {'PTPEnable', 'Priority1', 'Priority2'}
        related = tuple(name.lower() for name in fields)
        for name in node.attrib:
            local = name.rsplit('}', 1)[-1].lower()
            if local.startswith(related) and name not in fields:
                return cls()
        def priority(name):
            text = node.get(name, '')
            return int(text) if re.fullmatch(r'[0-9]{1,3}', text) and int(text) <= 255 else None
        return cls({'true': True, 'false': False}.get(node.get('PTPEnable')),
                   priority('Priority1'), priority('Priority2'))

    def attributes(self):
        # v35 Time Synchronize uses one byte for each of these settings.
        # Runtime clock and empty port state are supplied independently.
        values = ((1, self.ptp_enabled), (16, self.priority1), (17, self.priority2))
        return {number: bytes((value,)) for number, value in values if value is not None}

    def description(self, *, instance_id=None, native_compatibility=False):
        clock = software_clock.description(instance_id=instance_id)
        return {'object_revision': controller_schemas.object_revision(0x43,native_compatibility=native_compatibility),
                'ptp_enabled': self.ptp_enabled,
                'priority1': self.priority1, 'priority2': self.priority2,
                'source': 'Controller/TimeSynchronize PTPEnable/Priority1/Priority2',
                'source_attributes': list(self.attributes()),
                'available_attributes': sorted(set(self.attributes()) | set(clock['static_attributes'])),
                'dynamic_attributes': list(software_clock.TIME_ATTRIBUTES), 'settings_writable': False,
                'ptp_engine': False, 'clock_measurements': True, 'port_metadata': True,
                'software_clock': clock}
