"""Read-only File Manager discovery for a model with no storage devices.

Class attributes use the v35 File Manager layout: UINT revision and UDINT
instance count. No storage instance, file contents or transfer is emulated.
"""
import struct


OBJECT_REVISION = 1
INSTANCE_COUNT = 0


def class_attributes():
    return {1: struct.pack('<H', OBJECT_REVISION), 3: struct.pack('<I', INSTANCE_COUNT)}


def description():
    return {'object_revision': OBJECT_REVISION, 'instance_count': INSTANCE_COUNT,
            'emulated_storage': False, 'file_operations': False}
