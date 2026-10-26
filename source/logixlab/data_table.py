"""Read-only Data Table descriptors and bounded model storage.

IDs belong to this model and reuse the corresponding Symbol ID in each scope.
They are not native compiled Data Table IDs or physical controller addresses.
"""
import struct
from dataclasses import dataclass
from .model import ModelError
from . import controller_schemas

MAX_SCALARS = 4096
MAX_ARRAY_BYTES = 32768
MAX_ARRAY_STORAGE_BYTES = 1024*1024
DESCRIPTOR_BASE = 0x40000000
VALUE_BASE = 0x50000000
ARRAY_VALUE_BASE = VALUE_BASE+MAX_SCALARS*8
SYMBOL_BASE = 0x60000000


@dataclass(frozen=True)
class StructureLayout:
    """Reuse the symbolic wire catalog; this is never a native memory layout."""
    catalog: object
    template: object

    @property
    def size(self): return self.template.size

    def encode(self, ref, read): return self.catalog.encode(self.template,ref,read)


@dataclass(frozen=True)
class PackedBoolLayout:
    """Complete logical BOOL bits stored as little-endian 32-bit words."""
    bits: int

    def encode(self, value):
        if (type(value) is not list or len(value)!=self.bits
                or any(type(bit) is not bool for bit in value)):
            raise ModelError('Packed BOOL array shape or value changed')
        return b''.join(struct.pack('<I',sum(int(bit)<<i for i,bit in enumerate(value[start:start+32])))
                        for start in range(0,self.bits,32))


@dataclass(frozen=True)
class Cell:
    ref: str
    instance: int
    code: int
    fmt: str | StructureLayout | PackedBoolLayout
    slot: int
    dimensions: tuple = (0,0,0)
    array_offset: int = 0
    symbol_instance: int | None = None

    @property
    def symbol_id(self):return self.instance if self.symbol_instance is None else self.symbol_instance

    @property
    def element_size(self):
        if isinstance(self.fmt,PackedBoolLayout):return 4
        return self.fmt.size if isinstance(self.fmt,StructureLayout) else struct.calcsize(self.fmt)

    @property
    def storage_dimensions(self):
        return (self.fmt.bits//32,0,0) if isinstance(self.fmt,PackedBoolLayout) else self.dimensions

    @property
    def table_code(self):return 0x20D3 if isinstance(self.fmt,PackedBoolLayout) else self.code

    @property
    def aggregate(self): return isinstance(self.fmt,StructureLayout) or any(self.dimensions)

    @property
    def size(self):
        result=self.element_size
        for dimension in self.storage_dimensions:
            if dimension:result*=dimension
        return result

    @property
    def address(self): return DESCRIPTOR_BASE + self.slot * 32

    @property
    def value_address(self):
        return ARRAY_VALUE_BASE+self.array_offset if self.aggregate else VALUE_BASE+self.slot*8

    @property
    def symbol_address(self): return SYMBOL_BASE + self.slot * 32

    def header(self):
        # This is this model's descriptor layout, not a vendor firmware header.
        return struct.pack('<3IHHIIH6x', *self.storage_dimensions, self.table_code, 0,
                           self.instance, self.value_address, 0)

    def symbol_header(self):
        # Model-owned Symbol descriptor: value/table links, type, size, ID,
        # ordinary-base control and dimensions. Not a firmware layout.
        return struct.pack('<IIHHI4I', self.value_address, self.address,
                           self.code, self.element_size, self.symbol_id, 0, *self.dimensions)

    def value(self, read):
        value = read(self.ref)
        if isinstance(self.fmt,PackedBoolLayout):return self.fmt.encode(value)
        structured=isinstance(self.fmt,StructureLayout)
        if value is None: raise ModelError('Unknown Data Table value')
        if any(self.dimensions):
            items=[];shape=tuple(d for d in self.dimensions if d)
            def flatten(part,depth,ref):
                if depth==len(shape):
                    if part is None or isinstance(part,list) or isinstance(part,dict)!=structured:
                        raise ModelError('Invalid Data Table array element')
                    items.append(ref if structured else part);return
                if not isinstance(part,list) or len(part)!=shape[depth]:
                    raise ModelError('Data Table array shape changed')
                for index,item in enumerate(part):flatten(item,depth+1,ref+'['+str(index)+']')
            flatten(value,0,self.ref)
            try:
                if structured:return b''.join(self.fmt.encode(ref,read) for ref in items)
                return struct.pack('<'+self.fmt.removeprefix('<')*len(items),*items)
            except (TypeError,ValueError,OverflowError,struct.error) as error:
                raise ModelError('Invalid Data Table array value') from error
        if structured:
            if not isinstance(value,dict):raise ModelError('Invalid Data Table structure value')
            try:return self.fmt.encode(self.ref,read)
            except (TypeError,ValueError,OverflowError,struct.error) as error:
                raise ModelError('Invalid Data Table structure value') from error
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
            if symbol['type']&0x1FFF==0xC1 and any(dimensions):
                # The source Symbol counts logical bits; the Table counts
                # storage words. Other BOOL shapes keep storage unavailable.
                if (symbol['type']!=0x20C1 or fmt!='<B' or dimensions[1:]!=(0,0)
                        or not 32<=dimensions[0]<=65536 or dimensions[0]%32):continue
                fmt=PackedBoolLayout(dimensions[0])
            cell=Cell(symbol['ref'],symbol['id'],symbol['type'],fmt,slot,dimensions,array_bytes,symbol.get('symbol_id'))
            if cell.aggregate:
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
            if kind=='value' and cell.aggregate:continue
            size = cell.size if kind == 'value' else 32
            if offset + count > size: raise ModelError('Model storage read crosses a cell boundary')
            raw = (cell.header() if kind == 'table' else cell.symbol_header()
                   if kind == 'symbol' else cell.value(read))
            return raw[offset:offset + count]
        for cell in self.cells:
            if not cell.aggregate or not cell.value_address<=address<cell.value_address+cell.size:continue
            offset=address-cell.value_address
            if offset+count>cell.size:raise ModelError('Model storage read crosses a cell boundary')
            return cell.value(read)[offset:offset+count]
        raise ModelError('Unknown model storage address')


def attributes(symbol, storage=None):
    result = {1:struct.pack('<III',*(storage.storage_dimensions if storage is not None else symbol['dimensions'])),
              2:struct.pack('<H',storage.table_code if storage is not None else symbol['type']),8:struct.pack('<I',symbol['id'])}
    if storage is not None:
        result.update({3:struct.pack('<I',storage.address),6:bytes(2),
                       7:struct.pack('<I',storage.value_address),9:bytes(2)})
    return result


def description(*,native_compatibility=False):
    return {'object_revision':controller_schemas.object_revision(0x6A,native_compatibility=native_compatibility),
            'instance_list':True,'read_attributes':[1,2,8],
            'scalar_attributes':[3,6,7,9],'scalar_value_service':'0x4F',
            'scalar_storage':'Nonconstant base atoms and supported explicit user structures; zero data-use flags',
            'scalar_storage_limit':MAX_SCALARS,'modeled_addresses':True,
            'atomic_arrays':True,'array_byte_limit':MAX_ARRAY_BYTES,'array_storage_byte_limit':MAX_ARRAY_STORAGE_BYTES,
            'packed_bool_arrays':'Rank one, complete groups of 32 logical bits; Table type 0x20D3',
            'explicit_user_structures':True,'aggregate_byte_limit':MAX_ARRAY_BYTES,
            'aggregate_storage_byte_limit':MAX_ARRAY_STORAGE_BYTES,'shared_symbolic_layouts':True,
            'id_policy':'Model IDs reuse Symbol IDs within each program scope',
            'coverage':'Supported externally readable base tags; aliases excluded',
            'physical_addresses':False,'formal_types':False,'native_project_upload':False}
