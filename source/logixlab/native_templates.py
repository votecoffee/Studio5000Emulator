"""Optional read-only Template snapshots checked against the original sources.

Only layouts already supported by the software model are bound. Saved native
identities, handles, headers and trailers describe those layouts; they neither
install compiled code nor establish signature validity or native execution.
"""
from dataclasses import dataclass, replace
import hashlib
import re
import struct

from .model import ModelError
from .native_types import NativeTypes
from .template_layout import decode
from .template_staging import Attributes, Template as SavedTemplate, MAX_TEMPLATES, MAX_TOTAL_BYTES, MAX_DEFINITION_BYTES
from .templates import Catalog, Template, Member as WireMember, MAX_BYTES


@dataclass(frozen=True)
class SnapshotTemplate(Template):
    words: int = 0
    recon: int = 0

    @property
    def definition_storage(self):
        return self.definition

    def attributes(self):
        # This software model has no generated Multiply Code routine/address.
        return {1: struct.pack('<H', self.handle), 2: struct.pack('<H', len(self.members)),
                4: struct.pack('<I', self.words), 5: struct.pack('<I', self.size),
                6: struct.pack('<H', self.family), 7: bytes(4), 8: bytes((self.recon,))}


class NativeTemplates:
    def __init__(self, native_types, templates):
        if not isinstance(native_types, NativeTypes) or not isinstance(templates, (tuple, list)) or not 1 <= len(templates) <= MAX_TEMPLATES:
            raise ModelError('Native Template snapshot requires source types and bounded definitions')
        total = 0
        for t in templates:
            if not isinstance(t, SavedTemplate) or not isinstance(t.attributes, Attributes):
                raise ModelError('Invalid native Template snapshot entry')
            for value, minimum, maximum in ((t.instance, 1, 0xFFF), (t.words, 6, (MAX_DEFINITION_BYTES+20)//4),
                    (t.attributes.handle, 0, 65535), (t.attributes.members, 1, 4096),
                    (t.attributes.structure_bytes, 1, 1024*1024), (t.attributes.family, 0, 65535), (t.attributes.recon, 0, 255)):
                if type(value) is not int or not minimum <= value <= maximum:
                    raise ModelError('Native Template snapshot integer is outside its bound')
            if not isinstance(t.definition, bytes) or len(t.definition) != 4*t.words-20:
                raise ModelError('Native Template snapshot definition differs from its allocation')
            total += len(t.definition)
            if total > MAX_TOTAL_BYTES:
                raise ModelError('Native Template snapshot exceeds its total byte bound')
        checked = native_types.verify(templates)
        if checked['status'] != 'matched' or not checked['template_identities_verified']:
            raise ModelError('Native Template snapshot differs from original source layouts or identities')
        self._source = NativeTypes.from_manifest(native_types.manifest(), native_types.source_l5x_sha256)
        self._templates = tuple(templates)
        self._by_name = {decode(t.definition, t.attributes.members).name.casefold(): t for t in templates}
        self.definition_bytes = total
        self._definition_sha256 = hashlib.sha256(b''.join(t.definition for t in self._templates)).hexdigest()

    def check_source(self, project, native_types):
        if (not isinstance(native_types, NativeTypes) or project.sha256 != self._source.source_l5x_sha256 or
                native_types.source_acd_sha256 != self._source.source_acd_sha256 or
                native_types.source_l5x_sha256 != self._source.source_l5x_sha256 or
                native_types.type_ids != self._source.type_ids or native_types.types != self._source.types):
            raise ModelError('Native Template snapshot source binding changed')

    def bind(self, project, native_types):
        self.check_source(project, native_types)
        catalog = Catalog(project)
        ids = {}
        for key, model in catalog.types.items():
            saved = self._by_name.get(key)
            source = self._source.types.get(key)
            if (saved is None or source is None or model.family != 0 or saved.attributes.family != 0 or
                    model.size != source.size or len(model.members) != len(source.members) or len(saved.definition) > MAX_BYTES):
                raise ModelError('Native Template snapshot cannot bind an unsupported software layout')
            for member, original in zip(model.members, source.members, strict=True):
                dims = (member.count,) if member.array else ()
                bit = original.bit % 8 if original.bit is not None else None
                offset = original.offset + (original.bit//8 if original.bit is not None else 0)
                if (member.name.casefold() != original.name.casefold() or member.dtype.casefold() != original.dtype.casefold() or
                        member.offset != offset or member.bit != bit or dims != original.dimensions or member.hidden != original.hidden):
                    raise ModelError('Native Template snapshot differs from the software member layout')
                node = next(n for n in project.udts[key].findall('./Members/Member') if n.get('Name') == member.name)
                if not member.hidden and node.get('ExternalAccess', 'Read/Write') != original.access:
                    raise ModelError('Native Template snapshot differs from software member access')
            ids[key] = saved.instance
        # These two predefined interpreter structures already have an exact
        # download encoder. Reuse its source-layout check rather than accepting
        # arbitrary built-in families or guessing a firmware definition.
        for dtype in ('TIMER','COUNTER'):
            key=dtype.casefold();saved=self._by_name.get(key)
            if saved is None:continue
            from .download_values import encode_value
            from .download_image import ImageError
            try:encode_value(dtype,project.default(dtype),self._source)
            except ImageError as error:raise ModelError(str(error)) from error
            source=self._source.types[key]
            if any(m.access!='Read/Write' for m in source.members):
                raise ModelError('Native builtin member access differs from the interpreter')
            members=tuple(WireMember(m.name,m.dtype,1,False,m.offset+(m.bit//8 if m.bit is not None else 0),
                0xC1 if m.dtype=='BOOL' else 0xC4,1 if m.dtype=='BOOL' else 4,
                m.bit%8 if m.bit is not None else None,m.hidden) for m in source.members)
            catalog.types[key]=Template(saved.instance,dtype,members,source.size,saved.definition,
                saved.attributes.handle,1,4,saved.attributes.family)
            ids[key]=saved.instance
        if len(set(ids.values())) != len(ids):
            raise ModelError('Native Template snapshot has colliding software identities')
        bound = {}
        for key, model in catalog.types.items():
            saved = self._by_name[key]
            members = tuple(replace(m, code=(m.code & ~0xFFF) | ids[m.dtype.casefold()])
                            if m.code & 0x8000 else m for m in model.members)
            bound[key] = SnapshotTemplate(saved.instance, model.name, members, model.size, saved.definition,
                saved.attributes.handle, model.depth, model.alignment, saved.attributes.family, saved.words, saved.attributes.recon)
        catalog.types = bound
        catalog.ids = {**catalog.ids, **ids}
        return catalog

    def manifest(self):
        return {'format_version': 1, 'source_acd_sha256': self._source.source_acd_sha256,
                'source_l5x_sha256': self._source.source_l5x_sha256,
                'templates': [{'instance': t.instance, 'words': t.words, 'handle': t.attributes.handle,
                    'members': t.attributes.members, 'structure_bytes': t.attributes.structure_bytes,
                    'family': t.attributes.family, 'recon': t.attributes.recon,
                    'definition_hex': t.definition.hex()} for t in self._templates]}

    @classmethod
    def from_manifest(cls, manifest, native_types):
        if (not isinstance(native_types, NativeTypes) or not isinstance(manifest, dict) or
                set(manifest) != {'format_version', 'source_acd_sha256', 'source_l5x_sha256', 'templates'} or
                type(manifest['format_version']) is not int or manifest['format_version'] != 1 or
                manifest['source_acd_sha256'] != native_types.source_acd_sha256 or
                manifest['source_l5x_sha256'] != native_types.source_l5x_sha256 or
                not isinstance(manifest['templates'], list) or not 1 <= len(manifest['templates']) <= MAX_TEMPLATES):
            raise ModelError('Invalid native Template snapshot manifest or source binding')
        rows = []
        total = 0
        fields = {'instance', 'words', 'handle', 'members', 'structure_bytes', 'family', 'recon', 'definition_hex'}
        for row in manifest['templates']:
            if (not isinstance(row, dict) or set(row) != fields or not isinstance(row['definition_hex'], str) or
                    not 2 <= len(row['definition_hex']) <= 2*MAX_DEFINITION_BYTES or
                    not re.fullmatch(r'(?:[0-9a-f]{2})+', row['definition_hex'])):
                raise ModelError('Invalid native Template snapshot fields or definition encoding')
            total += len(row['definition_hex'])//2
            if total > MAX_TOTAL_BYTES:
                raise ModelError('Native Template snapshot exceeds its total byte bound')
            rows.append(SavedTemplate(row['instance'], row['words'],
                Attributes(row['handle'], row['members'], row['structure_bytes'], row['family'], row['recon']),
                bytes.fromhex(row['definition_hex'])))
        return cls(native_types, rows)

    def description(self):
        return {'bound': True, 'source': 'Explicit saved native Template snapshot checked against original ACD types',
                'source_acd_sha256': self._source.source_acd_sha256, 'source_l5x_sha256': self._source.source_l5x_sha256,
                'templates': len(self._templates), 'definition_bytes': self.definition_bytes,
                'definition_sha256': self._definition_sha256,
                'visibility': 'Public software UDT and source-checked TIMER/COUNTER closure in native compatibility mode only',
                'headers_and_trailers': 'opaque', 'multiply_code_reference': 'null_uint32',
                'native_code_installed': False, 'signature_verified': False, 'native_execution': False}
