"""Read-only supplemental schema discovery in the native v35 profile.

Reference class reads establish UINT revisions for classes 0x66 and 0x72.
The installed v35 definition identifies 0x72 as UserMemory. Class 0x66's
instance layout and semantics remain unimplemented; neither class grants
capacity, address, allocation or other instance operations.
"""
import struct

SCHEMA_REVISIONS = {0x66: 3, 0x72: 5}


def class_attributes(class_id):
    return {1: struct.pack('<H', SCHEMA_REVISIONS[class_id])}


def description():
    return {'classes': [{'class_id': cls, 'schema_revision': revision,
                         'name': 'UserMemory' if cls == 0x72 else None}
                        for cls, revision in SCHEMA_REVISIONS.items()],
            'class_read_attributes': [1], 'instance_attributes': False,
            'capacity_reporting': False, 'pool_addresses': False,
            'allocation_services': False, 'native_controller_equivalence': False}
