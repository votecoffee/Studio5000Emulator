"""Read-only Data Table descriptors and bounded atomic model storage.

IDs belong to this model and reuse the corresponding Symbol ID in each scope.
They are not native compiled Data Table IDs or physical controller addresses.
"""
import struct
from dataclasses import dataclass
from .model import ModelError

MAX_SCALARS = 4096
MAX_ARRAY_BYTES = 32768
MAX_ARRAY_STORAGE_BYTES = 1024*1024
DESCRIPTOR_BASE = 0x40000000
VALUE_BASE = 0x50000000
ARRAY_VALUE_BASE = VALUE_BASE+MAX_SCALARS*8
SYMBOL_BASE = 0x60000000


@dataclass(frozen=True)
class Cell:
    ref: str
    instance: int
    code: int
    fmt: str
    slot: int
    dimensions: tuple = (0,0,0)
    array_offset: int = 0

    @property
    def element_size(self): return struct.calcsize(self.fmt)

    @property
    def size(self):
        result=self.element_size
        for dimension in self.dimensions:
            if dimension:result*=dimension
        return result

    @property
    def address(self): return DESCRIPTOR_BASE + self.slot * 32

    @property
    def value_address(self):
        return ARRAY_VALUE_BASE+self.array_offset if any(self.dimensions) else VALUE_BASE+self.slot*8

    @property
    def symbol_address(self): return SYMBOL_BASE + self.slot * 32

    def header(self):
        # This is this model's descriptor layout, not a vendor firmware header.
        return struct.pack('<3IHHIIH6x', *self.dimensions, self.code, 0,
                           self.instance, self.value_address, 0)

    def symbol_header(self):
        # Model-owned Symbol descriptor: value/table links, type, size, ID,
        # ordinary-base control and scalar dimensions. Not a firmware layout.
        return struct.pack('<IIHHI4I', self.value_address, self.address,
                           self.code, self.element_size, self.instance, 0, *self.dimensions)

    def value(self, read):
        value = read(self.ref)
        if value is None: raise ModelError('Unknown Data Table scalar value')
        if any(self.dimensions):
            items=[];shape=tuple(d for d in self.dimensions if d)
            def flatten(part,depth):
                if depth==len(shape):
                    if part is None or isinstance(part,(list,dict)):
                        raise ModelError('Invalid Data Table array element')
                    items.append(part);return
                if not isinstance(part,list) or len(part)!=shape[depth]:
                    raise ModelError('Data Table array shape changed')
                for item in part:flatten(item,depth+1)
            flatten(value,0)
            try:return struct.pack('<'+self.fmt.removeprefix('<')*len(items),*items)
            except (TypeError,ValueError,OverflowError,struct.error) as error:
                raise ModelError('Invalid Data Table array value') from error
        try: return struct.pack(self.fmt, int(value) if self.code == 0xC1 else value)
        except (TypeError, ValueError, OverflowError, struct.error) as error:
            raise ModelError('Invalid Data Table scalar value') from error


class AddressSpace:
    """Catalog-local addresses backed by descriptor and current value bytes.

    No host/native memory is read. Addresses are valid only in this catalog;
    callers must discard it when the project or exposed atomic set changes.
    """
    def __init__(self, rows):
        ordered = sorted(rows, key=lambda row: row[0]['ref'].lower())[:MAX_SCALARS]
        cells=[];array_bytes=0
        for slot,(symbol,fmt) in enumerate(ordered):
            dimensions=tuple(symbol.get('dimensions',(0,0,0)))
            if (len(dimensions)!=3 or any(type(d) is not int or not 0<=d<=0xFFFFFFFF for d in dimensions)
                    or dimensions!=tuple(sorted(dimensions,key=lambda d:d==0))
                    or (symbol['type']>>13)&3!=sum(d>0 for d in dimensions)):
                raise ModelError('Invalid Data Table array dimensions')
            cell=Cell(symbol['ref'],symbol['id'],symbol['type'],fmt,slot,dimensions,array_bytes)
            if any(dimensions):
                if symbol['type']&0x1FFF==0xC1:continue  # Packed BOOL arrays remain unsupported.
                size=(cell.size+7)//8*8
                if cell.size>MAX_ARRAY_BYTES or array_bytes+size>MAX_ARRAY_STORAGE_BYTES:continue
                array_bytes+=size
            cells.append(cell)
        self.cells=tuple(cells);self.array_bytes=array_bytes
        self.by_slot={cell.slot:cell for cell in self.cells}
        self.by_ref = {cell.ref.lower(): cell for cell in self.cells}

    def read(self, address, count, read):
        if type(address) is not int or type(count) is not int or not 1 <= count <= 32:
            raise ModelError('Invalid model storage range')
        for base, stride, kind in ((DESCRIPTOR_BASE, 32, 'table'),
                                   (VALUE_BASE, 8, 'value'), (SYMBOL_BASE, 32, 'symbol')):
            slot, offset = divmod(address - base, stride)
            # Slots retain their original IDs even when an oversized array is
            # omitted, so resolve descriptor slots rather than tuple positions.
            cell=self.by_slot.get(slot)
            if cell is None:continue
            if kind=='value' and any(cell.dimensions):continue
            size = cell.size if kind == 'value' else 32
            if offset + count > size: raise ModelError('Model storage read crosses a cell boundary')
            raw = (cell.header() if kind == 'table' else cell.symbol_header()
                   if kind == 'symbol' else cell.value(read))
            return raw[offset:offset + count]
        for cell in self.cells:
            if not any(cell.dimensions) or not cell.value_address<=address<cell.value_address+cell.size:continue
            offset=address-cell.value_address
            if offset+count>cell.size:raise ModelError('Model storage read crosses a cell boundary')
            return cell.value(read)[offset:offset+count]
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
            'scalar_storage':'Ordinary nonconstant base atomic scalars and arrays; zero data-use flags',
            'scalar_storage_limit':MAX_SCALARS,'modeled_addresses':True,
            'atomic_arrays':True,'array_byte_limit':MAX_ARRAY_BYTES,'array_storage_byte_limit':MAX_ARRAY_STORAGE_BYTES,
            'id_policy':'Model IDs reuse Symbol IDs within each program scope',
            'coverage':'Supported externally readable base tags; aliases excluded',
            'physical_addresses':False,'formal_types':False,'native_project_upload':False}
