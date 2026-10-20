"""Bounded, temporary library descriptors; no library data or executable code.

Names stay in memory and are never interpreted as filesystem paths. The owning
programming lease supplies source binding, serialization and lifecycle cleanup.
"""
from dataclasses import dataclass
import re
import struct

MAX_LIBRARIES = 64
MAX_NAME_BYTES = 256


class LibraryError(ValueError):
    def __init__(self,status,reason):
        self.status=status;self.reason=reason
        super().__init__(reason)


@dataclass(frozen=True)
class Descriptor:
    library_type:int
    name:bytes


def parse_create(payload):
    """The observed ordered Type/Name initializer, with exact byte bounds."""
    if not isinstance(payload,bytes):raise LibraryError(3,'invalid_request')
    if len(payload)<12:raise LibraryError(0x13,'invalid_request')
    if payload[:4]!=b'\2\0\3\0' or payload[8:10]!=b'\2\0':
        raise LibraryError(3,'invalid_request')
    library_type,size=struct.unpack_from('<I',payload,4)[0],struct.unpack_from('<H',payload,10)[0]
    if not 1<=size<=MAX_NAME_BYTES:raise LibraryError(3,'invalid_request')
    if len(payload)<12+size:raise LibraryError(0x13,'invalid_request')
    if len(payload)!=12+size:raise LibraryError(0x15,'invalid_request')
    if library_type!=0:raise LibraryError(0x0F,'library_type_not_permitted')
    name=payload[12:]
    if re.fullmatch(rb'[A-Za-z0-9_+.\-]+',name) is None:raise LibraryError(3,'invalid_request')
    return Descriptor(library_type,name)


class LibraryStaging:
    def __init__(self):self.rows={}

    def create(self,instance,payload):
        if type(instance) is not int or not 1<=instance<=65535:
            raise LibraryError(5,'invalid_request')
        descriptor=parse_create(payload)
        previous=self.rows.get(instance)
        if previous is not None:
            if previous!=descriptor:raise LibraryError(0x0C,'library_stage_conflict')
        else:
            if descriptor in self.rows.values():raise LibraryError(0x0C,'library_stage_conflict')
            if len(self.rows)>=MAX_LIBRARIES:raise LibraryError(2,'library_stage_full')
            self.rows[instance]=descriptor
        return struct.pack('<H',instance)

    def delete(self,instance):
        if type(instance) is not int or instance not in self.rows:
            raise LibraryError(5,'library_stage_missing')
        del self.rows[instance]

    def clear(self):self.rows.clear()

    def description(self):
        return {'descriptor_only':True,'instances':len(self.rows),
                'name_bytes':sum(len(d.name) for d in self.rows.values()),
                'max_instances':MAX_LIBRARIES,'max_name_bytes':MAX_NAME_BYTES,
                'data_transfer':False,'commit':False,'names_exposed':False}
