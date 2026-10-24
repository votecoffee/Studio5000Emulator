"""Bounded empty energy inventory for the software controller.

The model has no energy meters, proxies or controls. Empty discovery is offered
only for complete ordinary-tag projects with checked ordinary user types,
no AOIs or external modules. Unknown source configurations remain unavailable; no readings are
substituted for unsupported energy objects.
"""
from collections import Counter
from dataclasses import dataclass
import re
from .tag_catalog import complete_tag_source

CLASSES = (0x4E, 0x4F, 0x50)  # Base, Electrical, Non-Electrical Energy
# Empty successful replies to this exact request were observed for these two
# controller and known-Program scopes. Other newer profiles stay unsupported.
EMPTY_PROBE_CLASSES = (0x4E, 0x4F)
ORDINARY_TYPES = frozenset(('BOOL', 'SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT',
                            'UDINT', 'ULINT', 'REAL', 'TIMER', 'COUNTER', 'STRING'))
CONTROLLER_SECTIONS = frozenset(('Description', 'RedundancyInfo', 'Security', 'SafetyInfo',
    'DataTypes', 'Modules', 'AddOnInstructionDefinitions', 'Tags', 'Programs', 'Tasks',
    'CST', 'WallClockTime', 'Trends', 'DataLogs', 'TimeSynchronize', 'EthernetPorts'))


def ordinary_user_types(controller):
    """Prove a bounded declaration graph contains only ordinary data members.

    This establishes absence of Energy object types, not a runtime wire layout.
    Namespaces, context exports, opaque children and unresolved references never
    disappear through the runtime's filtering of unsupported types.
    """
    containers = controller.findall('DataTypes')
    if len(containers) > 1 or any(n.attrib.keys()-{'Use'} or n.get('Use') not in (None, 'Target') for n in containers):
        return None
    declarations = list(containers[0]) if containers else []
    if len(declarations) > 1024:return None
    types = {}; total = 0
    valid_name = lambda name: isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,39}', name)
    for node in declarations:
        name = node.get('Name')
        if (node.tag != 'DataType' or not valid_name(name) or name.upper() in ORDINARY_TYPES or name.upper() == 'BIT' or
                name.upper().startswith('ENERGY_') or name.casefold() in types or
                node.attrib.keys()-{'Name', 'Class', 'Family', 'Use'} or
                node.get('Class') != 'User' or node.get('Family') != 'NoFamily' or node.get('Use') not in (None, 'Target') or
                len(node.findall('Members')) != 1 or len(node.findall('Description')) > 1 or
                len(node.findall('Dependencies')) > 1 or
                any(n.tag not in ('Members', 'Description', 'Dependencies') for n in node)):
            return None
        members = node.find('Members')
        if members.attrib or not 1 <= len(members) <= 256:return None
        names = set(); targets = []; declared = {}; bits = set()
        for member in members:
            member_name = member.get('Name'); dtype = member.get('DataType')
            if (member.tag != 'Member' or not valid_name(member_name) or member_name.casefold() in names or not valid_name(dtype) or
                    member.attrib.keys()-{'Name', 'DataType', 'Dimension', 'Radix', 'Hidden', 'ExternalAccess', 'Target', 'BitNumber', 'Use'} or
                    member.get('Use') not in (None, 'Target') or member.get('Hidden', 'false') not in ('false', 'true') or
                    member.get('ExternalAccess', 'Read/Write') not in ('Read/Write', 'Read Only', 'None') or
                    len(member.findall('Description')) > 1 or any(n.tag != 'Description' for n in member)):
                return None
            dims = member.get('Dimension', '0')
            if not re.fullmatch(r'[0-9]{1,5}(?:[, ][0-9]{1,5}){0,2}', dims):return None
            if any(int(n) > 65535 for n in re.split('[, ]', dims)):return None
            if dtype == 'BIT':
                host = declared.get(member.get('Target'))
                bit = member.get('BitNumber')
                if (host != ('SINT', '0', 'true') or dims != '0' or bit not in tuple('01234567') or
                        (member.get('Target'), bit) in bits):return None
                bits.add((member.get('Target'), bit))
            elif 'Target' in member.attrib or 'BitNumber' in member.attrib:return None
            declared[member_name] = (dtype, dims, member.get('Hidden', 'false'))
            names.add(member_name.casefold()); targets.append(dtype.casefold())
        total += len(members)
        if total > 65536:return None
        dependencies = node.find('Dependencies')
        if dependencies is not None:
            if dependencies.attrib or len(dependencies) > len(members) or (dependencies.text or '').strip():return None
            references = []
            for dependency in dependencies:
                if (dependency.tag != 'Dependency' or set(dependency.attrib) != {'Type', 'Name'}
                        or dependency.get('Type') != 'DataType' or not valid_name(dependency.get('Name'))
                        or len(dependency) or (dependency.text or '').strip() or (dependency.tail or '').strip()):
                    return None
                references.append(dependency.get('Name').casefold())
            # Studio's export repeats a nested DataType dependency for each
            # member that uses it. Verify that redundant graph, never ignore
            # unknown object families or opaque dependency declarations.
            expected = [target for target in targets if target.upper() not in ORDINARY_TYPES and target != 'bit']
            if Counter(references) != Counter(expected):return None
        types[name.casefold()] = targets
    for node in (n for t in declarations for n in t.iter() if n.tag == 'Description'):
        if node.attrib or len(node):return None
    depths = {}
    def visit(key, chain=()):
        if key in chain or len(chain) >= 8:return 0
        if key in depths:return depths[key] if len(chain)+depths[key] <= 8 else 0
        depth = 1
        for target in types[key]:
            if target.upper() in ORDINARY_TYPES or target == 'bit':continue
            if target not in types:return 0
            child = visit(target, chain+(key,))
            if not child:return 0
            depth = max(depth, 1+child)
        depths[key] = depth
        return depth
    if not all(visit(key) for key in types):return None
    return frozenset(types)


@dataclass(frozen=True)
class EnergyCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        if any(node.tag not in CONTROLLER_SECTIONS for node in controller):
            return cls(False)
        user_types = ordinary_user_types(controller)
        if user_types is None:return cls(False)
        containers = controller.findall('AddOnInstructionDefinitions')
        if len(containers) > 1 or any(len(node) or node.attrib.keys()-{'Use'} or node.get('Use') not in (None, 'Target') for node in containers):
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
            if any(key.rsplit('}', 1)[-1].casefold() == 'datatype' and key != 'DataType' for key in node.attrib):
                return cls(False)
            dtype = node.get('DataType')
            if dtype is not None and (dtype.upper() not in ORDINARY_TYPES and dtype.casefold() not in user_types
                    and not (node.tag == 'Member' and dtype == 'BIT')):
                return cls(False)
            if name in ('tag', 'localtag', 'parameter') and dtype is None:
                return cls(False)
            if name == 'data' and node.get('Format') not in (None, 'Decorated', 'L5K', 'String'):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'classes': list(CLASSES),
                'source': 'ordinary tag/type declarations and software-controller-only module layout',
                'new_empty_probe_classes': list(EMPTY_PROBE_CLASSES) if self.empty else [],
                'physical_inventory': False, 'energy_measurement': False,
                'energy_aggregation': False, 'energy_control': False}
