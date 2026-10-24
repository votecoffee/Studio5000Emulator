"""Read-only supplemental discovery and native v35 layout selection.

Reference class reads establish UINT revisions for classes 0x66 and 0x72.
The installed v35 definition identifies 0x72 as UserMemory. Class 0x66's
instance layout and semantics remain unimplemented; neither class grants
capacity, address, allocation or other instance operations.
Native compatibility selects observed v35 response schemas independently of
their deliberately partial source/runtime attribute implementations. A layout
revision does not enable missing fields, synthesize an inventory or grant writes.
"""
import struct

SCHEMA_REVISIONS = {0x66: 3, 0x72: 5}
COMPATIBILITY_REVISIONS = {0x43:5,0x64:6,0x68:9,0x69:17,0x6A:6,0x6B:7,0x6C:5,0x70:7,0x8E:15}
COMPATIBILITY_NAMES = {0x43:'Time Sync',0x64:'Extended Device',0x68:'Program',0x69:'I/O Map',
    0x6A:'Data Table',0x6B:'Symbol',0x6C:'Template',0x70:'Task',0x8E:'Controller'}


def object_revision(class_id, *, native_compatibility=False,legacy_revision=1):
    """Select the observed v35 layout; instance support remains independent."""
    return COMPATIBILITY_REVISIONS[class_id] if native_compatibility else legacy_revision


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
                                      'name':COMPATIBILITY_NAMES[cls]}
                                     for cls,revision in COMPATIBILITY_REVISIONS.items()],
            'compatibility_scope': 'v35 response layout selection; partial instance attributes',
            'complete_instance_support': False}
