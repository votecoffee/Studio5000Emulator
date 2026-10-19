"""Read-only Data Table descriptors for supported base tags in model memory.

IDs belong to this model and reuse the corresponding Symbol ID in each scope.
They are not native compiled Data Table IDs or physical controller addresses.
"""
import struct


def attributes(symbol):
    return {1:struct.pack('<III',*symbol['dimensions']),
            2:struct.pack('<H',symbol['type']),8:struct.pack('<I',symbol['id'])}


def description():
    return {'object_revision':1,'instance_list':True,'read_attributes':[1,2,8],
            'id_policy':'Model IDs reuse Symbol IDs within each program scope',
            'coverage':'Supported externally readable base tags; aliases excluded',
            'physical_addresses':False,'formal_types':False,'native_project_upload':False}
