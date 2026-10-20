"""Source-bound symbol instance IDs from the optional ACD TagInfo.XML stream.

These are logical object paths, not compiled controller memory addresses.
Only root tags are mapped; structure layouts still belong to the software model.
"""
import gzip
import io
import re
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass

from .model import ModelError
from .native_project import _hash, acd_stream
from .native_programs import read_programs, MAX_PROGRAMS

MAX_XML = 16_000_000
MAX_SYMBOLS = 100_000
NAME = re.compile(r'[A-Za-z_][A-Za-z_0-9:]{0,254}\Z')


def read_tag_info(path, limit=MAX_XML):
    """Read the bounded, versioned TagInfo XML without extracting ACD paths."""
    digest, raw = acd_stream(path, 'TagInfo.XML')
    try:
        reader = gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b'\x1f\x8b' else io.BytesIO(raw)
        with reader: data = reader.read(limit+1)
        if len(data) > limit: raise ModelError('Native tag XML exceeds the expanded size limit')
        text = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
        if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ModelError('Native tag XML cannot contain DTDs or entities')
        root = ET.fromstring(text)
    except (OSError, EOFError, UnicodeError, ET.ParseError, zlib.error) as error:
        raise ModelError('Invalid native tag XML') from error
    if root.tag != 'LogixTagInfo' or len(root.findall('SchemaVersion')) != 1:
        raise ModelError('Unsupported native tag XML schema')
    if root.find('SchemaVersion').attrib != {'Major': '1', 'Minor': '0'}:
        raise ModelError('Unsupported native tag XML schema revision')
    return digest, root


@dataclass(frozen=True)
class Symbol:
    scope: str
    program_instance: int
    name: str
    instance: int

    def __post_init__(self):
        if not isinstance(self.scope, str) or self.scope and not NAME.fullmatch(self.scope):
            raise ModelError('Invalid native symbol program name')
        if not isinstance(self.name, str) or not NAME.fullmatch(self.name):
            raise ModelError('Invalid native symbol tag name')
        if type(self.instance) is not int or not 1 <= self.instance <= 0xFFFFFFFF:
            raise ModelError('Invalid native symbol instance')
        if type(self.program_instance) is not int or not 0 <= self.program_instance <= 0xFFFFFFFF:
            raise ModelError('Invalid native program instance')
        if bool(self.scope) != bool(self.program_instance):
            raise ModelError('Native program name and instance must agree')

    @property
    def key(self): return (f'Program:{self.scope}.{self.name}' if self.scope else self.name).lower()

    def manifest(self):
        return dict(scope=self.scope, program_instance=self.program_instance, name=self.name, instance=self.instance)


class NativeSymbols:
    def __init__(self, source_acd_sha256, source_l5x_sha256, symbols, programs=(), program_inventory_error=None):
        self.source_acd_sha256 = _hash(source_acd_sha256)
        self.source_l5x_sha256 = _hash(source_l5x_sha256)
        symbols = tuple(symbols)
        if len(symbols) > MAX_SYMBOLS: raise ModelError('Native symbol catalog is too large')
        self.by_key = {}; self.programs = {}; self.program_ids = {}; instances = set()
        if not isinstance(programs, (list, tuple)) or len(programs) > MAX_PROGRAMS:
            raise ModelError('Invalid explicit native program inventory')
        self.explicit_programs = []
        for program in programs:
            if not isinstance(program, dict) or set(program) != {'name', 'instance'}:
                raise ModelError('Invalid native program fields')
            name, instance = program['name'], program['instance']
            if not isinstance(name, str) or not NAME.fullmatch(name) or type(instance) is not int or not 1 <= instance <= 0xFFFFFFFF:
                raise ModelError('Invalid native program identity')
            if name.lower() in self.programs or instance in self.program_ids:
                raise ModelError('Duplicate native program identity')
            self.programs[name.lower()] = instance; self.program_ids[instance] = name.lower()
            self.explicit_programs.append(dict(program))
        if program_inventory_error is not None and (not isinstance(program_inventory_error, str) or not 1 <= len(program_inventory_error) <= 256):
            raise ModelError('Invalid program inventory diagnostic')
        if self.explicit_programs and program_inventory_error is not None:
            raise ModelError('Program inventory cannot be both bound and unavailable')
        self.program_inventory_error = program_inventory_error
        for symbol in symbols:
            if not isinstance(symbol, Symbol): raise ModelError('Invalid native symbol entry')
            scope = symbol.scope.lower(); pair = (scope, symbol.instance)
            if symbol.key in self.by_key or pair in instances: raise ModelError('Duplicate native symbol name or instance')
            if scope:
                if self.programs.get(scope, symbol.program_instance) != symbol.program_instance:
                    raise ModelError('Conflicting native program instances')
                if self.program_ids.get(symbol.program_instance, scope) != scope:
                    raise ModelError('Conflicting native program names')
                self.programs[scope] = symbol.program_instance; self.program_ids[symbol.program_instance] = scope
            self.by_key[symbol.key] = symbol; instances.add(pair)

    @classmethod
    def from_manifest(cls, manifest, source_l5x_sha256):
        required = {'source_acd_sha256', 'source_l5x_sha256', 'symbols'}
        if not isinstance(manifest, dict) or not required <= manifest.keys() or manifest.keys() - required - {'programs', 'program_inventory_error'}:
            raise ModelError('Invalid native symbol manifest')
        if manifest['source_l5x_sha256'] != source_l5x_sha256:
            raise ModelError('Native symbol catalog does not match the loaded L5X bytes')
        rows = manifest['symbols']
        if not isinstance(rows, list) or len(rows) > MAX_SYMBOLS: raise ModelError('Invalid native symbol entries')
        symbols = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'scope', 'program_instance', 'name', 'instance'}:
                raise ModelError('Invalid native symbol fields')
            symbols.append(Symbol(**row))
        return cls(manifest['source_acd_sha256'], source_l5x_sha256, symbols,
                   manifest.get('programs', ()), manifest.get('program_inventory_error'))

    @classmethod
    def from_acd(cls, path, source_l5x_sha256):
        digest, root = read_tag_info(path, MAX_XML)
        symbols = []
        groups = [('', root.findall('./Tags/Tag'))]
        for program in root.findall('./Programs/Program'):
            scope = program.get('Name')
            if not isinstance(scope, str) or not NAME.fullmatch(scope): raise ModelError('Invalid native program name')
            groups.append((scope, program.findall('./Tags/Tag')))
        for scope, tags in groups:
            for tag in tags:
                ioi = tag.get('IOI', '')
                if not re.fullmatch(r'@[0-9]{1,10}(?: [0-9]{1,10}){5}@', ioi):
                    raise ModelError('Unsupported native symbol logical path')
                values = tuple(int(n) for n in ioi[1:-1].split(' '))
                if not scope and values[0] == 107 and values[2:] == (0, 0, 0, 0):
                    program_instance = 0; instance = values[1]
                elif scope and values[0] == 104 and values[2] == 107 and values[4:] == (0, 0):
                    program_instance = values[1]; instance = values[3]
                else: raise ModelError('Unsupported native symbol logical path')
                symbols.append(Symbol(scope, program_instance, tag.get('Name'), instance))
                if len(symbols) > MAX_SYMBOLS: raise ModelError('Native symbol catalog is too large')
        programs = []; inventory_error = None
        if len(groups) > 1:
            try:
                program_digest, programs = read_programs(path, [name for name, _ in groups[1:]])
            except ModelError as error:
                inventory_error = str(error)
            else:
                if program_digest != digest:
                    raise ModelError('ACD changed while reading program inventory')
                try:
                    cls(digest, source_l5x_sha256, symbols, programs)
                except ModelError as error:
                    # Optional component metadata cannot discard valid TagInfo
                    # tag paths or replace their independently supplied IDs.
                    programs = []; inventory_error = str(error)
        return cls(digest, source_l5x_sha256, symbols, programs, inventory_error)

    def manifest(self):
        result = dict(source_acd_sha256=self.source_acd_sha256, source_l5x_sha256=self.source_l5x_sha256,
                      symbols=[s.manifest() for s in self.by_key.values()])
        if self.explicit_programs: result['programs'] = [dict(row) for row in self.explicit_programs]
        if self.program_inventory_error is not None: result['program_inventory_error'] = self.program_inventory_error
        return result

    def description(self):
        return dict(bound=True, source='ACD TagInfo.XML logical paths', symbols=len(self.by_key),
                    programs=len(self.programs), compiled_addresses=False,
                    explicit_programs=len(self.explicit_programs),
                    program_inventory_source='Comps.Dat Program format 19 and TagInfo names' if self.explicit_programs else None,
                    program_inventory_error=self.program_inventory_error,
                    source_acd_sha256=self.source_acd_sha256, source_l5x_sha256=self.source_l5x_sha256)
