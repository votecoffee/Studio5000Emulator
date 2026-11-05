"""Committed simulator Program durations, measured on the host monotonic clock."""
from dataclasses import dataclass,field
import struct


@dataclass(frozen=True)
class ProgramTiming:
    last_ns: int = 0
    maximum_ns: int = 0
    executions: int = 0
    # An explicit clear stays readable even if the old maximum cannot be encoded.
    last_reset: bool = field(default=False,repr=False)

    def __post_init__(self):
        if (any(type(value) is not int or value<0 for value in (self.last_ns,self.maximum_ns,self.executions))
                or type(self.last_reset) is not bool or self.last_reset and self.last_ns
                or 0<self.maximum_ns<self.last_ns
                or not self.executions and (self.last_ns or self.maximum_ns)):
            raise ValueError('Invalid measured Program timing')

    def record(self, elapsed_ns):
        return ProgramTiming(elapsed_ns,max(self.maximum_ns,elapsed_ns),self.executions+1)

    def attributes(self):
        # Preserve the real measurement internally; do not wrap or saturate a
        # duration that cannot be represented by the native DWORD contract.
        last=self.last_ns//1000;maximum=self.maximum_ns//1000
        if maximum>0xFFFFFFFF:return {2:bytes(4)} if self.last_reset else {}
        result={}
        if last<=0xFFFFFFFF:result[2]=struct.pack('<I',last)
        result[3]=struct.pack('<I',maximum)
        return result
