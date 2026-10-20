"""Read-only I/O force/LED status when the complete source has no I/O modules."""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class IOMap:
    empty: bool = False

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls()
        sections = controller.findall('Modules')
        if len(sections) != 1 or sections[0].get('Use') not in (None, 'Target'):
            return cls()
        modules = list(sections[0])
        if any(module.tag != 'Module' for module in modules):
            return cls()
        for node in controller.iter():
            local = node.tag.rsplit('}', 1)[-1].lower()
            if local in ('module', 'modules') and (node.tag not in ('Module', 'Modules')
                    or node.get('Use') not in (None, 'Target')
                    or node.tag == 'Modules' and node is not sections[0]
                    or node.tag == 'Module' and node not in modules):
                return cls()
            if 'force' in local or node.tag in ('Tag', 'LocalTag') and (
                    ':' in node.get('Name', '') or node.get('DataType', '').upper() == 'MODULE'):
                return cls()
            if any(any(word in name.lower() for word in ('force', 'encoded', 'encrypted', 'protected'))
                   for name in node.attrib):
                return cls()
        if modules:
            # A native full-controller export includes its own Local module.
            # It is not an I/O Map connection to an external module.
            if len(modules) != 1:
                return cls()
            module = modules[0]
            expected = {'Name':'Local', 'ParentModule':'Local', 'Vendor':'1',
                        'ProductType':'14', 'CatalogNumber':'1756-L85E'}
            if controller.get('ProcessorType') != '1756-L85E' or any(module.get(k) != v for k,v in expected.items()):
                return cls()
            if any(child.tag not in ('Module', 'EKey', 'Key', 'Ports', 'Port', 'Bus', 'Description')
                   for child in module.iter()):
                return cls()
        return cls(True)

    def attributes(self):
        # No installed/enabled I/O forces; LED 0 means no Module objects.
        return {9:bytes(2), 11:bytes(2)} if self.empty else {}

    def description(self):
        return {'empty_status_available':self.empty, 'force_status':0 if self.empty else None,
                'led_status':0 if self.empty else None, 'source':'Complete L5X with no external I/O modules',
                'module_connections':False, 'force_writes':False, 'physical_io_state_imported':False}
