"""Bounded structural decoding of staged Template member definitions.

The documented eight-byte member entries and NUL-terminated names are decoded.
Native offset encodings and the download trailer remain uninterpreted. Decoding
does not establish a storage layout, CRC/signature validity or executable type.
"""
from collections import Counter
from dataclasses import dataclass
import re
import struct

MAX_DEFINITION_BYTES = 65536
MAX_MEMBERS = 4096
MAX_NAME_BYTES = 254
MAX_TEMPLATES = 1024
NAME = re.compile(rb'[A-Za-z_][A-Za-z_0-9:]{0,253}\Z')


class LayoutError(ValueError):
    def __init__(self, reason): self.reason = reason; super().__init__(reason)


@dataclass(frozen=True)
class Member:
    name: str
    info: int
    type_word: int
    offset_word: int


@dataclass(frozen=True)
class Definition:
    name: str
    members: tuple[Member, ...]
    trailer_bytes: int


def decode(raw, member_count):
    """Read structure only; retain the full offset/type words without masking.

    Semicolon suffixes in the type-name string are opaque. All bytes following
    the last member name are counted, never treated as harmless zero padding.
    """
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_DEFINITION_BYTES:
        raise LayoutError('definition_size_limit')
    if type(member_count) is not int or not 1 <= member_count <= MAX_MEMBERS:
        raise LayoutError('member_count_limit')
    position = member_count * 8
    if position >= len(raw): raise LayoutError('truncated_member_entries')

    def string(limit=MAX_NAME_BYTES):
        nonlocal position
        end = raw.find(b'\0', position, min(len(raw), position + limit + 1))
        if end < 0: raise LayoutError('unterminated_or_long_name')
        value = raw[position:end]; position = end + 1
        return value

    header = string(MAX_DEFINITION_BYTES); name = header.split(b';', 1)[0]
    if not NAME.fullmatch(name): raise LayoutError('invalid_template_name')
    members = []; names = set()
    for index in range(member_count):
        name_bytes = string()
        if not NAME.fullmatch(name_bytes): raise LayoutError('invalid_member_name')
        key = name_bytes.lower()
        if key in names: raise LayoutError('duplicate_member_name')
        names.add(key)
        info, type_word, offset = struct.unpack_from('<HHI', raw, index * 8)
        members.append(Member(name_bytes.decode('ascii'), info, type_word, offset))
    return Definition(name.decode('ascii'), tuple(members), len(raw) - position)


class Inspection:
    """Immutable decoded definitions plus aggregate, payload-free diagnostics."""
    def __init__(self, templates=()):
        if len(templates) > MAX_TEMPLATES: raise LayoutError('template_count_limit')
        definitions = []; errors = Counter()
        for template in templates:
            try: definition = decode(template.definition, template.attributes.members)
            except LayoutError as error: errors[error.reason] += 1
            else: definitions.append((template.instance, definition))
        self.definitions = tuple(definitions)
        self._attempted = len(templates)
        self._errors = tuple(sorted(errors.items()))
        self._members = sum(len(d.members) for _, d in self.definitions)
        self._trailers = sum(d.trailer_bytes for _, d in self.definitions)
        self._encoded_offsets = sum(m.offset_word > 0x0FFFFFFF
                                    for _, d in self.definitions for m in d.members)

    def description(self):
        # High bits are observed in native download offsets; their meaning is
        # deliberately not inferred from a successful structural decode.
        return {'status': ('idle' if not self._attempted else 'decoded' if not self._errors
                           else 'partial' if self.definitions else 'invalid'),
                'templates_decoded': len(self.definitions),
                'templates_unavailable': self._attempted - len(self.definitions),
                'members_decoded': self._members,
                'opaque_trailer_bytes': self._trailers,
                'encoded_offset_members': self._encoded_offsets,
                'errors': [{'reason': reason, 'templates': count} for reason, count in self._errors],
                'storage_mapping_supported': False, 'signature_verified': False,
                'definitions_exposed': False, 'execution_supported': False}
