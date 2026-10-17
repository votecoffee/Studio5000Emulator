"""Bounded, aligned wire layouts for explicit numeric UDT definitions.

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

    def attributes(self):
        return {1: struct.pack('<H', self.handle), 2: struct.pack('<H', len(self.members)),
                4: struct.pack('<I', (len(self.definition) + 23) // 4), 5: struct.pack('<I', self.size)}


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
        if schema.get('Class', 'User') != 'User' or schema.get('Family', 'NoFamily') != 'NoFamily':
            raise ModelError('Only explicit user-defined wire structures are supported')
        if self.project.string_capacity(name) is not None: raise ModelError('Whole STRING wire layouts are unsupported')
        type_name = schema.get('Name', name)
        valid_name = lambda value: re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,39}', value)
        if not valid_name(type_name): raise ModelError('Invalid wire UDT name')
        nodes = schema.findall('./Members/Member')
        if not 1 <= len(nodes) <= MAX_MEMBERS: raise ModelError('Wire UDT member count must be 1..256')
        members = []; names = set(); offset = 0; depth = 1; alignment = 4
        for node in nodes:
            member_name = node.get('Name', '')
            if not valid_name(member_name) or member_name.lower() in names: raise ModelError('Invalid or duplicate wire member')
            names.add(member_name.lower())
            if (node.get('Hidden', 'false').lower() != 'false' or node.get('AOILocal', 'false').lower() != 'false'
                    or node.get('ExternalAccess', 'Read/Write') not in ('Read/Write', 'Read Only')
                    or node.get('Target') or node.get('BitNumber') or node.get('AliasFor')):
                raise ModelError('Hidden, private or overlaid wire members are unsupported')
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
            members.append(Member(member_name, dtype, count, bool(dims), offset, code, size))
            offset += occupied
        offset = aligned(offset, alignment)
        if offset > MAX_BYTES: raise ModelError('Aligned wire UDT exceeds 32768 bytes')
        info = b''.join(struct.pack('<HHI', m.count if m.array else 0,
                                    m.code | (0x2000 if m.array else 0), m.offset) for m in members)
        names_data = (type_name + ';n\0' + '\0'.join(m.name for m in members) + '\0').encode('ascii')
        definition = info + names_data
        # Attribute 4 includes 23 bytes of template overhead and is in words.
        definition += b'\0' * (-(len(definition) + 23) % 4)
        if len(definition) > MAX_BYTES: raise ModelError('Wire template definition exceeds 32768 bytes')
        handle = binascii.crc_hqx(definition, 0xFFFF)
        template = Template(self.ids[key], type_name, tuple(members), offset, definition, handle, depth, alignment)
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
        """Yield wire offsets and typed member references without reading values."""
        for member in template.members:
            member_ref = ref + '.' + member.name
            nested = self.for_type(member.dtype) if member.dtype not in ATOMS else None
            size = member.element_size
            for index in range(member.count):
                item_ref = member_ref + (f'[{index}]' if member.array else '')
                offset = base + member.offset + index * size
                if nested:
                    yield from self.leaves(nested, item_ref, offset)
                else:
                    yield offset, member.dtype, item_ref

    def encode(self, template, ref, read):
        # Alignment padding is reserved, canonical zero data in this model. It
        # does not stand in for omitted application values or hidden host bits.
        result = bytearray(template.size)
        for offset, dtype, item_ref in self.leaves(template, ref):
            value = read(item_ref)
            if value is None or isinstance(value, (dict, list)): raise ModelError('Unknown structured wire data')
            struct.pack_into('<' + ATOMS[dtype][1], result, offset, value)
        return bytes(result)
