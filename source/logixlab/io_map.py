"""Read-only I/O settings and bounded root connection-class metadata."""
from collections import Counter
from dataclasses import dataclass
from ipaddress import IPv4Address
from .tag_catalog import complete_tag_source
from .task_configuration import NAME

ETHERNET_BRIDGES = frozenset(("1756-EN2T", "1756-EN2TR"))


@dataclass(frozen=True)
class ModuleSettings:
    name: str
    inhibited: bool | None
    major_fault: bool | None
    route: bytes | None = None
    routed_parent: str | None = None

    def mode(self):
        if self.inhibited is None or self.major_fault is None:
            return None
        return (int(self.inhibited) << 2) | int(self.major_fault)


def _ports(module):
    return module.findall('./Ports/Port') if len(module.findall('Ports')) == 1 else []


def _port(ports, port_id, port_type, *, upstream):
    matches = [port for port in ports if _decimal_field(port, 'Id') == port_id]
    if len(matches) != 1:
        return None
    port = matches[0]
    if (port.get('Id') != str(port_id) or port.get('Type') != port_type
            or port.get('Upstream') != ('true' if upstream else 'false')):
        return None
    return port


def _backplane_port(module, *, upstream):
    if module.get('ParentModPortId') != '1':
        return None
    ports = _ports(module)
    port = _port(ports, 1, 'ICP', upstream=upstream)
    upstream_ports = [candidate for candidate in ports if candidate.get('Upstream') == 'true']
    return port if upstream_ports == ([port] if upstream else []) else None


def _decimal_field(node, attribute):
    value = node.get(attribute, '')
    return int(value) if 1 <= len(value) <= 2 and value.isascii() and value.isdecimal() else None


def _backplane_slots(parent_port, children):
    if parent_port is None:
        return {}
    buses = parent_port.findall('Bus')
    size = _decimal_field(buses[0], 'Size') if len(buses) == 1 else None
    parent_slot = _decimal_field(parent_port, 'Address')
    if size is None or parent_slot is None or not 0 <= parent_slot < size <= 17:
        return {}
    slots = {}
    for name, module in children.items():
        port = _backplane_port(module, upstream=True)
        slot = _decimal_field(port, 'Address') if port is not None else None
        if slot is not None and 0 <= slot < size:
            slots[name] = slot
    counts = Counter(slots.values())
    return {name: slot for name, slot in slots.items() if slot != parent_slot and counts[slot] == 1}


def _is_ethernet_bridge(module):
    return (NAME.fullmatch(module.get('Name', '')) is not None
            and module.get('CatalogNumber') in ETHERNET_BRIDGES and module.get('Vendor') == '1'
            and module.get('ProductType') == '12' and 'SafetyNetwork' not in module.attrib)


def _ethernet_address(module):
    ports = _ports(module)
    upstream = [port for port in ports if port.get('Upstream') == 'true']
    if len(upstream) != 1 or upstream[0].get('Type') != 'Ethernet':
        return None
    port = upstream[0]
    port_id = _decimal_field(port, 'Id')
    if not port_id or sum(_decimal_field(other, 'Id') == port_id for other in ports) != 1:
        return None
    try:
        address = IPv4Address(port.get('Address', ''))
    except ValueError:
        return None
    if address.is_unspecified or address.is_multicast or int(address) == 0xffffffff:
        return None
    return str(address)


def _ethernet_routes(local, entries, slots):
    # A parent must expose an unambiguous Ethernet port. A local bridge
    # also needs a proven slot to construct the first hop.
    parents = {'local': (b'', _port(_ports(local), 2, 'Ethernet', upstream=False))}
    for name, slot in slots.items():
        bridge = entries[name]
        if _is_ethernet_bridge(bridge):
            parents[name] = (bytes((1, slot)), _port(_ports(bridge), 2, 'Ethernet', upstream=False))
    links = {}
    for name, module in entries.items():
        parent = module.get('ParentModule', '').casefold()
        if name == 'local' or module.get('ParentModPortId') != '2' or parent not in parents:
            continue
        _, port = parents[parent]
        address = _ethernet_address(module) if port is not None else None
        if address is not None and address != port.get('Address'):
            links[name] = parent, address
    counts = Counter(links.values())
    routes = {}
    for name, link in links.items():
        if counts[link] == 1:
            parent, address = link
            raw = address.encode('ascii')
            segment = bytes((0x12, len(raw))) + raw
            routes[name] = parents[parent][0] + segment + bytes(len(raw) % 2)
    return routes


def _module_settings(controller, modules):
    entries = {module.get('Name', '').casefold(): module for module in modules}
    local = entries.get('local')
    if (len(entries) != len(modules) or '' in entries or local is None
            or local.get('ParentModule', '').casefold() != 'local'
            or local.get('CatalogNumber') != controller.get('ProcessorType')
            or local.get('Vendor') != '1' or local.get('ProductType') != '14'):
        return ()
    children = {}
    for name, module in entries.items():
        parent = module.get('ParentModule', '').casefold()
        if name != parent:
            children.setdefault(parent, {})[name] = module
    slots = _backplane_slots(_backplane_port(local, upstream=False), children.get('local', {}))
    routes = {name: bytes((1, slot)) for name, slot in slots.items()}
    ethernet_routes = _ethernet_routes(local, entries, slots)
    routes.update(ethernet_routes)
    for name, prefix in ethernet_routes.items():
        if name in children and _is_ethernet_bridge(entries[name]):
            port = _port(_ports(entries[name]), 1, 'ICP', upstream=False)
            remote_slots = _backplane_slots(port, children[name])
            routes.update({child: prefix + bytes((1, slot)) for child, slot in remote_slots.items()})
    bool_values = {'true': True, 'false': False}
    settings = []
    for name, module in entries.items():
        product = module.get('ProductType', '')
        parent = module.get('ParentModule', '').casefold()
        if (name == 'local' or not NAME.fullmatch(module.get('Name', ''))
                or (parent != 'local' and name not in routes)
                or not module.get('CatalogNumber') or 'SafetyNetwork' in module.attrib
                or not (product.isascii() and product.isdecimal() and len(product) <= 5)
                or not 0 < int(product) <= 0xffff or int(product) == 14):
            continue
        routed_parent = parent if name in routes and parent in routes else None
        settings.append(ModuleSettings(name, bool_values.get(module.get('Inhibited')),
                                       bool_values.get(module.get('MajorFault')), routes.get(name),
                                       routed_parent))
    return tuple(settings)


@dataclass(frozen=True)
class IOMap:
    empty: bool = False
    root_link_address: int|None = None
    root_link_port: int|None = None
    local_identity: tuple[int,int,int,int,int]|None = None
    module_status_qualified: bool = False
    module_settings: tuple[ModuleSettings, ...] = ()

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
        external_modules = len(modules) > 1
        module_status_qualified = True
        for node in controller.iter():
            local = node.tag.rsplit('}', 1)[-1].lower()
            if local in ('module', 'modules') and (node.tag not in ('Module', 'Modules')
                    or node.get('Use') not in (None, 'Target')
                    or node.tag == 'Modules' and node is not sections[0]
                    or node.tag == 'Module' and node not in modules):
                return cls()
            if external_modules:
                continue
            if (local in ('produceinfo', 'consumeinfo')
                    or local in ('tag', 'localtag') and node.get('TagType', '').casefold() in ('produced', 'consumed')
                    or any(word in local or word in node.get('Format', '').casefold()
                           for word in ('encoded', 'encrypted', 'protected'))):
                module_status_qualified = False
            if 'force' in local or node.tag in ('Tag', 'LocalTag') and (
                    ':' in node.get('Name', '') or node.get('DataType', '').upper() == 'MODULE'):
                return cls()
            if any(any(word in name.lower() for word in ('force', 'encoded', 'encrypted', 'protected'))
                   for name in node.attrib):
                return cls()
        if external_modules:
            # Named GSV settings use only module declarations. They never
            # establish an empty native I/O Map or infer connection state.
            return cls(module_settings=_module_settings(controller, modules))
        root_link_address=None;root_link_port=None;local_identity=None
        if modules:
            # A native full-controller export includes its own Local module.
            # It is not an I/O Map connection to an external module.
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
                root_link_address=0;root_link_port=1
                # Preserve explicit Local identity fields independently of its
                # route. Missing or contradictory fields cannot become a key
                # by borrowing values from a different software-device profile.
                raw=tuple(module.get(name) for name in ('Vendor','ProductType','ProductCode','Major','Minor'))
                revision=tuple(controller.get(name) for name in ('MajorRev','MinorRev'))
                if all(value is not None and 1<=len(value)<=5 and value.isascii() and value.isdecimal() for value in (*raw,*revision)):
                    key=tuple(map(int,raw))
                    if (all(0<=value<=0xFFFF for value in key[:3]) and all(0<=value<=255 for value in key[3:])
                            and key[3:]==tuple(map(int,revision))):local_identity=key
        return cls(True,root_link_address,root_link_port,local_identity,module_status_qualified)

    def named_module(self, name):
        name = name.casefold()
        return next((entry for entry in self.module_settings if entry.name == name), None)

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
                'root_link_port':self.root_link_port,
                'root_link_port_available':self.root_link_port is not None,
                'named_module_settings':len(self.module_settings),
                'named_backplane_paths':sum(len(entry.route or b'') == 2 for entry in self.module_settings),
                'named_ethernet_paths':sum(len(entry.route or b'') > 2 for entry in self.module_settings),
                'module_connections':False, 'force_writes':False, 'physical_io_state_imported':False}
