"""Bounded, aligned wire layouts for explicit numeric and packed BIT UDTs.

Template IDs and handles belong to this software model. They are not copied
from, or authenticated against, a native controller's compiled type database.
"""
from __future__ import annotations

import binascii
import re
import struct
from dataclasses import dataclass
from .model import ModelError, dimensions


ATOMS = {'SINT': (0xC2, 'b'), 'INT': (0xC3, 'h'), 'DINT': (0xC4, 'i'),
         'LINT': (0xC5, 'q'), 'USINT': (0xC6, 'B'), 'UINT': (0xC7, 'H'),
         'UDINT': (0xC8, 'I'), 'ULINT': (0xC9, 'Q'), 'REAL': (0xCA, 'f')}
MAX_BYTES = 32768
MAX_MEMBERS = 256
MAX_DEPTH = 8


def aligned(value, boundary):
    return (value + boundary - 1) // boundary * boundary


@dataclass(frozen=True)
class Member:
    name: str
    dtype: str
    count: int
    array: bool
    offset: int
    code: int
    element_size: int
    bit: int | None = None
    hidden: bool = False


@dataclass(frozen=True)
class Template:
    instance: int
    name: str
    members: tuple
    size: int
    definition: bytes
    handle: int
    depth: int
    alignment: int
    family: int | None = None

    @property
    def definition_storage(self):
        # Attribute 4's words describe the model's aligned allocation. The
        # compact read extent excludes these three reserved bytes; larger
        # bounded reads may include them, without crossing into another type.
        return self.definition+bytes(3)

    def attributes(self):
        values={1: struct.pack('<H', self.handle), 2: struct.pack('<H', len(self.members)),
                4: struct.pack('<I', (len(self.definition) + 23) // 4), 5: struct.pack('<I', self.size)}
        # The supported explicit NoFamily declaration maps to the source's
        # family value. Missing declarations do not become native metadata.
        if self.family is not None:values[6]=struct.pack('<H',self.family)
        return values


class Catalog:
    def __init__(self, project):
        self.project = project
        self.types = {}
        self.unsupported = {}
        # Reserve the documented user-type instance range. Unsupported types do
        # not cause otherwise valid types to change ID during this generation.
        self.ids = {name: 0x100 + i for i, name in enumerate(sorted(project.udts)[:0xE00])}
        for name in self.ids:
            try: self.build(name)
            except ModelError as error: self.unsupported[name] = str(error)

    def build(self, name, stack=()):
        key = name.lower()
        if key in stack or len(stack) >= MAX_DEPTH: raise ModelError('Recursive or overly deep wire UDT')
        if key in self.types: return self.types[key]
        if key in self.unsupported: raise ModelError(self.unsupported[key])
        schema = self.project.udts.get(key)
        if schema is None or key not in self.ids: raise ModelError('No explicit wire UDT definition')
        if key == 'string': raise ModelError('Built-in STRING wire layouts are unsupported')
        if schema.get('Class', 'User') != 'User' or schema.get('Family', 'NoFamily') != 'NoFamily':
            raise ModelError('Only explicit user-defined wire structures are supported')
        type_name = schema.get('Name', name)
        valid_name = lambda value: re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,39}', value)
        if not valid_name(type_name): raise ModelError('Invalid wire UDT name')
        nodes = schema.findall('./Members/Member')
        if not 1 <= len(nodes) <= MAX_MEMBERS: raise ModelError('Wire UDT member count must be 1..256')
        if self.project.string_capacity(name) is not None:
            length = next(node for node in nodes if node.get('Name') == 'LEN')
            if dimensions(length.get('Dimension', '0')): raise ModelError('String LEN must be a scalar DINT')
        # Only explicit, non-overlapping BIT mappings may use hidden storage.
        # Hidden hosts carry no independent application value in the model.
        hosts = set(); bits = set()
        for index, node in enumerate(nodes):
            if node.get('DataType') != 'BIT': continue
            target = node.get('Target', '')
            candidates = [n for n in nodes[:index] if n.get('Name') == target]
            if len(candidates) != 1: raise ModelError('BIT requires a preceding hidden SINT host')
            host = candidates[0]
            if (host.get('DataType') != 'SINT' or host.get('Hidden', 'false').lower() != 'true'
                    or dimensions(host.get('Dimension', '0'))):
                raise ModelError('BIT host must be a scalar hidden SINT')
            bit_text = node.get('BitNumber', '')
            if not re.fullmatch('[0-7]', bit_text) or dimensions(node.get('Dimension', '0')):
                raise ModelError('BIT requires one scalar bit in the range 0..7')
            bit = int(bit_text)
            if (target, bit) in bits: raise ModelError('Overlapping BIT mappings are unsupported')
            bits.add((target, bit)); hosts.add(target)
        members = []; names = set(); offset = 0; depth = 1; alignment = 4
        for node in nodes:
            member_name = node.get('Name', '')
            if not valid_name(member_name) or member_name.lower() in names: raise ModelError('Invalid or duplicate wire member')
            names.add(member_name.lower())
            is_host = member_name in hosts
            is_bit = node.get('DataType') == 'BIT'
            if (node.get('Hidden', 'false').lower() != ('true' if is_host else 'false')
                    or node.get('AOILocal', 'false').lower() != 'false'
                    or (not is_host and node.get('ExternalAccess', 'Read/Write') not in ('Read/Write', 'Read Only'))
                    or (not is_bit and (node.get('Target') or node.get('BitNumber'))) or node.get('AliasFor')):
                raise ModelError('Hidden, private or overlaid wire members are unsupported')
            if is_bit:
                host = next(m for m in members if m.name == node.get('Target'))
                members.append(Member(member_name, 'BOOL', 1, False, host.offset, 0xC1, 1,
                                      int(node.get('BitNumber'))))
                continue
            dims = dimensions(node.get('Dimension', '0'))
            if len(dims) > 1 or dims and not 1 <= dims[0] <= 4096:
                raise ModelError('Wire member arrays require one dimension of 1..4096')
            count = dims[0] if dims else 1
            dtype = node.get('DataType', '')
            if dtype.upper() in ATOMS:
                dtype = dtype.upper(); code = ATOMS[dtype][0]; size = struct.calcsize('<' + ATOMS[dtype][1])
                member_alignment = size
            else:
                nested = self.build(dtype, stack + (key,))
                code = 0x8000 | nested.instance; size = nested.size
                member_alignment = nested.alignment
                depth = max(depth, 1 + nested.depth)
                if depth > MAX_DEPTH: raise ModelError('Wire UDT nesting exceeds eight levels')
            if dims: member_alignment = max(4, member_alignment)
            alignment = max(alignment, member_alignment); offset = aligned(offset, member_alignment)
            occupied = aligned(size * count, member_alignment) if dims else size
            if offset + occupied > MAX_BYTES: raise ModelError('Wire UDT exceeds 32768 bytes')
            members.append(Member(member_name, dtype, count, bool(dims), offset, code, size, hidden=is_host))
            offset += occupied
        offset = aligned(offset, alignment)
        if offset > MAX_BYTES: raise ModelError('Aligned wire UDT exceeds 32768 bytes')
        info = b''.join(struct.pack('<HHI', m.bit if m.bit is not None else m.count if m.array else 0,
                                    m.code | (0x2000 if m.array else 0), m.offset) for m in members)
        names_data = (type_name + ';n\0' + '\0'.join(m.name for m in members) + '\0').encode('ascii')
        definition = info + names_data
        # Attribute 4 includes 23 bytes of template overhead and is in words.
        definition += b'\0' * (-(len(definition) + 23) % 4)
        if len(definition)+3 > MAX_BYTES: raise ModelError('Wire template definition exceeds 32768 bytes')
        handle = binascii.crc_hqx(definition, 0xFFFF)
        family_fields=[field for field in schema.attrib if field.rsplit('}',1)[-1].casefold()=='family']
        family=0 if family_fields==['Family'] and schema.get('Family')=='NoFamily' else None
        template = Template(self.ids[key], type_name, tuple(members), offset, definition, handle, depth, alignment,family)
        self.types[key] = template
        return template

    def for_type(self, dtype):
        return self.types.get(dtype.lower())

    def closure(self, instances):
        visible = set(instances); by_id = {t.instance: t for t in self.types.values()}; todo = list(visible)
        while todo:
            template = by_id.get(todo.pop())
            if template is None: continue
            for member in template.members:
                if member.code & 0x8000 and member.code & 0xFFF not in visible:
                    instance = member.code & 0xFFF; visible.add(instance); todo.append(instance)
        return {i: by_id[i] for i in visible if i in by_id}

    def leaves(self, template, ref, base=0):
        """Yield offsets, types, references and optional packed bit locations."""
        for member in template.members:
            if member.hidden: continue
            member_ref = ref + '.' + member.name
            nested = self.for_type(member.dtype) if member.dtype not in ATOMS and member.bit is None else None
            size = member.element_size
            for index in range(member.count):
                item_ref = member_ref + (f'[{index}]' if member.array else '')
                offset = base + member.offset + index * size
                if nested:
                    yield from self.leaves(nested, item_ref, offset)
                else:
                    yield offset, member.dtype, item_ref, member.bit

    def encode(self, template, ref, read):
        # Padding and unused host bits are reserved zero data in this model.
        # Every application value, including each visible flag, is read below.
        result = bytearray(template.size)
        for offset, dtype, item_ref, bit in self.leaves(template, ref):
            value = read(item_ref)
            if value is None or isinstance(value, (dict, list)): raise ModelError('Unknown structured wire data')
            if bit is not None:
                if value not in (False, True): raise ModelError('Invalid packed BOOL value')
                result[offset] |= int(value) << bit
            else:
                struct.pack_into('<' + ATOMS[dtype][1], result, offset, value)
        return bytes(result)
