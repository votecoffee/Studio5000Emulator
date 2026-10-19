"""Read-only Data Table descriptors and bounded scalar model storage.

IDs belong to this model and reuse the corresponding Symbol ID in each scope.
They are not native compiled Data Table IDs or physical controller addresses.
"""
import struct
from dataclasses import dataclass
from .model import ModelError

MAX_SCALARS = 4096
DESCRIPTOR_BASE = 0x40000000
VALUE_BASE = 0x50000000


@dataclass(frozen=True)
class Scalar:
    ref: str
    instance: int
    code: int
    fmt: str
    slot: int

    @property
    def size(self): return struct.calcsize(self.fmt)

    @property
    def address(self): return DESCRIPTOR_BASE + self.slot * 32

    @property
    def value_address(self): return VALUE_BASE + self.slot * 8

    def header(self):
        # This is this model's descriptor layout, not a vendor firmware header.
        return struct.pack('<3IHHIIH6x', 0, 0, 0, self.code, 0,
                           self.instance, self.value_address, 0)

    def value(self, read):
        value = read(self.ref)
        if value is None: raise ModelError('Unknown Data Table scalar value')
        try: return struct.pack(self.fmt, int(value) if self.code == 0xC1 else value)
        except (TypeError, ValueError, OverflowError, struct.error) as error:
            raise ModelError('Invalid Data Table scalar value') from error


class AddressSpace:
    """Catalog-local addresses backed by descriptor and current value bytes.

    No host/native memory is read. Addresses are valid only in this catalog;
    callers must discard it when the project or exposed scalar set changes.
    """
    def __init__(self, rows):
        ordered = sorted(rows, key=lambda row: row[0]['ref'].lower())[:MAX_SCALARS]
        self.cells = tuple(Scalar(s['ref'], s['id'], s['type'], fmt, slot)
                           for slot, (s, fmt) in enumerate(ordered))
        self.by_ref = {cell.ref.lower(): cell for cell in self.cells}

    def read(self, address, count, read):
        if type(address) is not int or type(count) is not int or not 1 <= count <= 32:
            raise ModelError('Invalid model storage range')
        for base, stride, header in ((DESCRIPTOR_BASE, 32, True), (VALUE_BASE, 8, False)):
            slot, offset = divmod(address - base, stride)
            if not 0 <= slot < len(self.cells): continue
            cell = self.cells[slot]
            size = 32 if header else cell.size
            if offset + count > size: raise ModelError('Model storage read crosses a cell boundary')
            raw = cell.header() if header else cell.value(read)
            return raw[offset:offset + count]
        raise ModelError('Unknown model storage address')


def attributes(symbol, storage=None):
    result = {1:struct.pack('<III',*symbol['dimensions']),
              2:struct.pack('<H',symbol['type']),8:struct.pack('<I',symbol['id'])}
    if storage is not None:
        result.update({3:struct.pack('<I',storage.address),6:bytes(2),
                       7:struct.pack('<I',storage.value_address),9:bytes(2)})
    return result


def description():
    return {'object_revision':1,'instance_list':True,'read_attributes':[1,2,8],
            'scalar_attributes':[3,6,7,9],'scalar_value_service':'0x4F',
            'scalar_storage':'Ordinary nonconstant base scalar atoms only; zero data-use flags',
            'scalar_storage_limit':MAX_SCALARS,'modeled_addresses':True,
            'id_policy':'Model IDs reuse Symbol IDs within each program scope',
            'coverage':'Supported externally readable base tags; aliases excluded',
            'physical_addresses':False,'formal_types':False,'native_project_upload':False}
