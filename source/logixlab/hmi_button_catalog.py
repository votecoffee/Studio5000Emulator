"""Empty HMI Button Control discovery backed by complete L5X source.

HMIBC tags use Data@Format="HMIBC" / HMIBCParameters (1756-RM014, chapter 6).
Nonempty catalogs and HMI button configuration/execution are not implemented.
"""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class HmiButtonCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if (node.get('DataType', '').upper() == 'HMIBC'
                    or node.get('Format', '').lower() == 'hmibc'
                    or name.startswith('hmibc')):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'source': 'complete Controller L5X HMIBC tags and configuration',
                'program_class_ids': [0x36E],
                'program_scope_requires': 'Matching original native identity and ordinary Standard Program; complete HMIBC-free project source',
                'instance_list': self.empty, 'button_configuration': False,
                'button_execution': False}
