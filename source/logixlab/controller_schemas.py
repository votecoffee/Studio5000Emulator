"""Read-only supplemental discovery and native v35 layout selection.

Reference class reads establish UINT revisions for classes 0x66 and 0x72.
The installed v35 definition identifies 0x72 as UserMemory. Class 0x66's
instance layout and semantics remain unimplemented; neither class grants
capacity, address, allocation or other instance operations.
Controller and Time Sync select observed v35 response schemas independently
of their deliberately partial source/runtime attribute implementations.
"""
import struct

SCHEMA_REVISIONS = {0x66: 3, 0x72: 5}
COMPATIBILITY_REVISIONS = {0x43: 5, 0x8E: 15}


def object_revision(class_id, *, native_compatibility=False):
    """Select the observed v35 layout; instance support remains independent."""
    return COMPATIBILITY_REVISIONS[class_id] if native_compatibility else 1


def class_attributes(class_id):
    return {1: struct.pack('<H', SCHEMA_REVISIONS[class_id])}


def description():
    return {'classes': [{'class_id': cls, 'schema_revision': revision,
                         'name': 'UserMemory' if cls == 0x72 else None}
                        for cls, revision in SCHEMA_REVISIONS.items()],
            'class_read_attributes': [1], 'instance_attributes': False,
            'capacity_reporting': False, 'pool_addresses': False,
            'allocation_services': False, 'native_controller_equivalence': False,
            'compatibility_classes': [{'class_id': cls, 'schema_revision': revision,
                                      'name': 'Time Sync' if cls==0x43 else 'Controller'}
                                     for cls,revision in COMPATIBILITY_REVISIONS.items()],
            'compatibility_scope': 'v35 response layout selection; partial instance attributes',
            'complete_instance_support': False}
