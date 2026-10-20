"""Read-only Time Sync settings from L5X, without a PTP clock implementation."""
from dataclasses import dataclass
import re
from .tag_catalog import complete_tag_source


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
        # Dynamic clock, port and vendor fields require a separate PTP model.
        values = ((1, self.ptp_enabled), (16, self.priority1), (17, self.priority2))
        return {number: bytes((value,)) for number, value in values if value is not None}

    def description(self):
        return {'object_revision': 1, 'ptp_enabled': self.ptp_enabled,
                'priority1': self.priority1, 'priority2': self.priority2,
                'source': 'Controller/TimeSynchronize PTPEnable/Priority1/Priority2',
                'available_attributes': list(self.attributes()), 'settings_writable': False,
                'ptp_engine': False, 'clock_measurements': False, 'port_metadata': False}
