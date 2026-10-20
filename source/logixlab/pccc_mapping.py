"""Source-checked empty PLC message mapping metadata; no PCCC execution."""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class PcccMapping:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        # Native full-project exports put these attributes on ProduceInfo,
        # including tags that exist only for PLC message mapping.
        allowed = set(controller.findall('./Tags/Tag/ProduceInfo'))
        for tag in controller.iter('Tag'):
            if len(tag.findall('ProduceInfo')) > 1:
                return cls(False)
        keys = {'PLC2Mapping', 'PLCMappingFile'}
        related = ('plc2mapping', 'plcmappingfile')
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if name.startswith(related) or name == 'produceinfo' and node.tag != 'ProduceInfo':
                return cls(False)
            for key, value in node.attrib.items():
                local = key.rsplit('}', 1)[-1].lower()
                if not local.startswith(related):
                    continue
                if node not in allowed or key not in keys:
                    return cls(False)
                # File zero, blank, UID-only and malformed references are not
                # evidence of an empty mapping. Only an explicit disabled
                # PLC-2 flag or absence in complete source establishes empty.
                if key == 'PLCMappingFile' or value not in ('0', 'false'):
                    return cls(False)
        return cls(True)

    def attributes(self):
        return {1: bytes(2), 2: bytes(4)} if self.empty else {}

    def description(self):
        return {'object_revision': 1, 'empty_mapping_available': self.empty,
                'plc2_file': 0 if self.empty else None,
                'mapping_value': 0 if self.empty else None,
                'source': 'complete Controller L5X ProduceInfo PLC2Mapping/PLCMappingFile',
                'configured_mapping_upload': False, 'pccc_commands': False,
                'mapping_execution': False, 'compiled_addresses': False}
