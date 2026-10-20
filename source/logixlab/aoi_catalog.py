"""Discovery of an explicitly empty source Add-On Instruction definition set.

Native UDI Definition objects (0x338) represent AOI definitions. Runtime AOI
parsing alone does not prove protected or unrecognized definitions are absent.
"""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class AOICatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        sections = controller.findall('AddOnInstructionDefinitions')
        if (len(sections) != 1 or len(sections[0]) or (sections[0].text or '').strip()
                or set(sections[0].attrib) - {'Use'}
                or sections[0].get('Use') not in (None, 'Target')):
            return cls(False)
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if name.startswith(('addoninstruction', 'udidefinition')) and (
                    node is not sections[0] or node.tag != 'AddOnInstructionDefinitions'):
                return cls(False)
            if any(word in name for word in ('encoded', 'encrypted', 'protected')) or any(
                    any(word in key.lower() for word in ('encoded', 'encrypted', 'protected'))
                    for key in node.attrib) or any(word in node.get('Format', '').lower()
                                                 for word in ('encoded', 'encrypted', 'protected')):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty, 'class_id': 0x338,
                'instance_count': 0 if self.empty else None, 'instance_list': self.empty,
                'source': 'Complete L5X with an explicit empty AddOnInstructionDefinitions section',
                'definition_upload': False, 'native_aoi_execution': False}
