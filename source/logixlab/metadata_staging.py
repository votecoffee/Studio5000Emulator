"""Temporary definition names, isolated from project metadata and its values.

The programming lease supplies ownership, source binding and cleanup. Staging
does not install definitions or acknowledge metadata-value transfer or commit.
"""
import re
import struct

MAX_DEFINITIONS = 256
MAX_NAME_BYTES = 128


class MetadataError(ValueError):
    def __init__(self,status,reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


def parse_create(payload):
    """One Name attribute, with its UINT length and exact ASCII identifier."""
    if not isinstance(payload,bytes):raise MetadataError(3,'invalid_request')
    if len(payload)<6:raise MetadataError(0x13,'invalid_request')
    if payload[:4]!=b'\1\0\1\0':raise MetadataError(3,'invalid_request')
    size=struct.unpack_from('<H',payload,4)[0]
    if not 1<=size<=MAX_NAME_BYTES:raise MetadataError(3,'invalid_request')
    if len(payload)<6+size:raise MetadataError(0x13,'invalid_request')
    if len(payload)!=6+size:raise MetadataError(0x15,'invalid_request')
    name=payload[6:]
    if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_]*',name) is None:raise MetadataError(3,'invalid_request')
    return name


class MetadataStaging:
    def __init__(self):self.rows={}

    def create(self,instance,payload):
        if type(instance) is not int or not 1<=instance<=0xFFFFFFFF:
            raise MetadataError(5,'invalid_request')
        name=parse_create(payload)
        previous=self.rows.get(instance)
        if previous is not None:
            if previous!=name:raise MetadataError(0x0C,'metadata_stage_conflict')
        else:
            if name in self.rows.values():raise MetadataError(0x0C,'metadata_stage_conflict')
            if len(self.rows)>=MAX_DEFINITIONS:raise MetadataError(2,'metadata_stage_full')
            self.rows[instance]=name
        return struct.pack('<I',instance)

    def delete(self,instance):
        if type(instance) is not int or instance not in self.rows:
            raise MetadataError(5,'metadata_stage_missing')
        del self.rows[instance]

    def clear(self):self.rows.clear()

    def description(self):
        return {'descriptor_only':True,'instances':len(self.rows),
                'name_bytes':sum(map(len,self.rows.values())),
                'max_instances':MAX_DEFINITIONS,'max_name_bytes':MAX_NAME_BYTES,
                'values_transfer':False,'commit':False,'names_exposed':False}
