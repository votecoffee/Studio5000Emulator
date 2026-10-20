"""Read-only empty I/O status and bounded root connection-class metadata."""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class IOMap:
    empty: bool = False
    root_link_address: int|None = None

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
        root_link_address=None
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
            # The supported endpoint's backplane route is fixed at slot zero.
            # Read it only from a canonical Local ICP port, never from a
            # guessed address, hardware status word or model memory pointer.
            ports=module.findall('Ports')
            candidates=module.findall('./Ports/Port[@Id="1"]')
            if (len(ports)==1 and len(candidates)==1 and candidates[0].get('Address')=='0'
                    and len([node for node in module.iter() if node.tag=='Ports'])==1
                    and len([node for node in module.iter() if node.tag=='Port' and node.get('Id')=='1'])==1
                    and candidates[0].get('Type')=='ICP' and candidates[0].get('Upstream')=='false'
                    and module.get('ParentModPortId')=='1'):
                root_link_address=0
        return cls(True,root_link_address)

    def attributes(self):
        # No installed/enabled I/O forces; LED 0 means no Module objects.
        return {9:bytes(2), 11:bytes(2)} if self.empty else {}

    def class_attributes(self):
        # I/O Map maximum ID and count are UDINTs. The Local controller module
        # is not an external I/O Map connection instance.
        return {1:b'\1\0', **({2:bytes(4), 3:bytes(4), **self.attributes()} if self.empty else {})}

    def connection_class_attributes(self):
        # Native v35 clients query the I/O Connection class below I/O Map 1,
        # including for a controller-only project. This is our software class
        # revision, not the controller firmware revision. No instance or
        # connection fields are synthesized from this namespace.
        return {1:b'\1\0'} if self.empty else None

    def description(self):
        return {'empty_status_available':self.empty, 'force_status':0 if self.empty else None,
                'led_status':0 if self.empty else None, 'source':'Complete L5X with no external I/O modules',
                'instance_count':0 if self.empty else None, 'instance_list':self.empty,
                'connection_class_revision':1 if self.empty else None,
                'connection_class_parent':1 if self.empty else None,
                'root_link_address':self.root_link_address,
                'root_link_address_available':self.root_link_address is not None,
                'module_connections':False, 'force_writes':False, 'physical_io_state_imported':False}
