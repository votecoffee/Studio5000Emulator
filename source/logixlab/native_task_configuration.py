"""Selected stored settings from the observed v35 Task body format 18.

Only the fixed 4506-byte Standard Continuous/Periodic layout is understood.
Runtime counters, timestamps, pointers and extended stack properties are never
imported. Unsupported bodies leave the independent Task identity usable.
"""
from dataclasses import dataclass
import struct

from .task_configuration import MAX_SCHEDULED_PROGRAMS
from .task_timing import MAX_TIME_US,STORED_TYPE_CODES


BODY_BYTES=4506
TYPE_CODES=STORED_TYPE_CODES


@dataclass(frozen=True)
class StoredTaskConfiguration:
    programs:tuple[int,...]
    rate_us:int
    kind_code:int
    priority:int
    watchdog_us:int
    disable_output_update:bool
    inhibited:bool
    trigger:bytes=bytes(5)
    timeout_us:int=0
    data_use:int=0
    tag_mapping_count:int=0

    def __post_init__(self):
        if (not isinstance(self.programs,tuple) or len(self.programs)>MAX_SCHEDULED_PROGRAMS
                or any(type(n) is not int or not 1<=n<=0xFFFFFFFF for n in self.programs)
                or len(set(self.programs))!=len(self.programs)
                or any(type(n) is not int or not 0<n<=MAX_TIME_US for n in (self.rate_us,self.watchdog_us))
                or type(self.kind_code) is not int or self.kind_code not in TYPE_CODES.values()
                or type(self.priority) is not int or not 1<=self.priority<=15
                or any(type(value) is not bool for value in (self.disable_output_update,self.inhibited))
                or type(self.trigger) is not bytes or self.trigger!=bytes(5)
                or any(type(value) is not int or value!=0 for value in (self.timeout_us,self.data_use,self.tag_mapping_count))):
            raise ValueError('Unsupported stored Task configuration')

    def attributes(self):
        return {2:struct.pack('<I',self.rate_us),4:struct.pack('<H',len(self.trigger))+self.trigger,
                5:struct.pack('<H',self.kind_code),17:struct.pack('<I',self.timeout_us),
                21:struct.pack('<H',self.tag_mapping_count)}

    def manifest(self):
        return {'programs':list(self.programs),'rate_us':self.rate_us,'kind_code':self.kind_code,
                'priority':self.priority,'watchdog_us':self.watchdog_us,
                'disable_output_update':self.disable_output_update,'inhibited':self.inhibited,
                'trigger_hex':self.trigger.hex(),'timeout_us':self.timeout_us,
                'data_use':self.data_use,'tag_mapping_count':self.tag_mapping_count}

    @classmethod
    def from_manifest(cls,value):
        fields={'programs','rate_us','kind_code','priority','watchdog_us','disable_output_update',
                'inhibited','trigger_hex','timeout_us','data_use','tag_mapping_count'}
        if (not isinstance(value,dict) or set(value)!=fields or not isinstance(value['programs'],list)
                or not isinstance(value['trigger_hex'],str) or value['trigger_hex']!='0000000000'):
            raise ValueError('Invalid stored Task configuration manifest')
        return cls(**{k:v for k,v in value.items() if k not in ('programs','trigger_hex')},
                   programs=tuple(value['programs']),trigger=bytes.fromhex(value['trigger_hex']))


def read(body):
    """Return only a recognized static profile; malformed/unknown is optional."""
    if not isinstance(body,(bytes,bytearray,memoryview)) or len(body)!=BODY_BYTES:return None
    if struct.unpack_from('<H',body,8)[0]!=18:return None
    count=struct.unpack_from('<H',body,90)[0]
    if count>MAX_SCHEDULED_PROGRAMS or any(body[92+4*count:4204]):return None
    trigger_count=struct.unpack_from('<H',body,4212)[0]
    if trigger_count!=5 or any(body[4214:4342]):return None
    disable,inhibited=struct.unpack_from('<II',body,4398)
    if disable not in (0,1) or inhibited not in (0,1):return None
    try:
        return StoredTaskConfiguration(tuple(struct.unpack_from('<'+str(count)+'I',body,92)),
            struct.unpack_from('<I',body,4204)[0],*struct.unpack_from('<HH',body,4342),
            struct.unpack_from('<I',body,4362)[0],bool(disable),bool(inhibited),
            bytes(body[4214:4219]),struct.unpack_from('<I',body,4394)[0],
            *struct.unpack_from('<HH',body,4406))
    except ValueError:return None
