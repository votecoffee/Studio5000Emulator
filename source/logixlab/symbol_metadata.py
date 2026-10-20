"""Symbol descriptors for supported values in this model's address space.

Addresses identify backed model bytes, never firmware or host-process memory.
Unsupported tag kinds retain basic discovery without invented storage fields.
"""
import struct


ATTRIBUTES = (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 14)


def attributes(symbol, constant, storage=None):
    name = symbol['name'].encode('ascii')
    result = {1: struct.pack('<H', len(name)) + name,
              2: struct.pack('<H', symbol['type']),
              8: struct.pack('<III', *symbol['dimensions']),
              9: b'\0',  # Discovery exposes Standard tags only.
              10: bytes((symbol['external_access'],)),
              11: bytes((int(constant),))}
    if storage is not None:
        result.update({3: struct.pack('<I', storage.value_address),
                       5: struct.pack('<I', storage.symbol_address),
                       6: bytes(4), 7: struct.pack('<H', storage.element_size),
                       12: struct.pack('<I', storage.instance),
                       14: bytes(4)})  # Model storage does not claim native signatures.
    return result


def description():
    return {'read_attributes': [1, 2, 8, 9, 10, 11],
            'scalar_attributes': [3, 5, 6, 7, 12, 14],
            'scalar_storage': 'Nonconstant base atoms and supported explicit user structures',
            'shared_symbolic_layouts': True,
            'modeled_addresses': True, 'physical_addresses': False,
            'formal_types': False, 'native_project_upload': False}
