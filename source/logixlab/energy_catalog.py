"""Bounded empty energy inventory for the software controller.

The model has no energy meters, proxies or controls. Empty discovery is offered
only for complete ordinary-tag projects with no custom types/AOIs or external
modules. Unknown source configurations remain unavailable; no readings are
substituted for unsupported energy objects.
"""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source

CLASSES = (0x4E, 0x4F, 0x50)  # Base, Electrical, Non-Electrical Energy
ORDINARY_TYPES = frozenset(('BOOL', 'SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT',
                            'UDINT', 'ULINT', 'REAL', 'TIMER', 'COUNTER', 'STRING'))
CONTROLLER_SECTIONS = frozenset(('Description', 'RedundancyInfo', 'Security', 'SafetyInfo',
    'DataTypes', 'Modules', 'AddOnInstructionDefinitions', 'Tags', 'Programs', 'Tasks',
    'CST', 'WallClockTime', 'Trends', 'DataLogs', 'TimeSynchronize', 'EthernetPorts'))


@dataclass(frozen=True)
class EnergyCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        if any(node.tag not in CONTROLLER_SECTIONS for node in controller):
            return cls(False)
        for section in ('DataTypes', 'AddOnInstructionDefinitions'):
            containers = controller.findall(section)
            if len(containers) > 1 or any(len(node) or node.get('Use') not in (None, 'Target') for node in containers):
                return cls(False)
        containers = controller.findall('Modules')
        if len(containers) > 1 or any(node.get('Use') not in (None, 'Target') for node in containers):
            return cls(False)
        modules = list(containers[0]) if containers else []
        if modules and not controller.get('ProcessorType'):
            return cls(False)
        if len(modules) > 1 or any(node.tag != 'Module'
                or node.get('CatalogNumber') != controller.get('ProcessorType')
                or node.get('Use') not in (None, 'Target') for node in modules):
            return cls(False)
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if name in ('datatypes', 'addoninstructiondefinitions', 'modules', 'module') and node.tag.startswith('{'):
                return cls(False)
            if 'energy' in name:
                return cls(False)
            if name in ('tag', 'localtag', 'parameter') and node.get('DataType', '').upper() not in ORDINARY_TYPES:
                return cls(False)
            if name == 'data' and node.get('Format') not in (None, 'Decorated', 'L5K', 'String'):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'classes': list(CLASSES),
                'source': 'ordinary tags and software-controller-only module layout',
                'physical_inventory': False, 'energy_measurement': False,
                'energy_aggregation': False, 'energy_control': False}
