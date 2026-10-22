"""Committed whole-Task measurements and simulator WALLCLOCKTIME start samples.

These counters measure successful interpreter executions. They are separate
from source rate/watchdog settings and contain no original controller history.
"""
from dataclasses import dataclass,field
import struct
from time import perf_counter_ns


@dataclass(frozen=True)
class TaskMeasurements:
    last_ns: int = 0
    maximum_ns: int = 0
    minimum_interval_ns: int = 0
    maximum_interval_ns: int = 0
    executions: int = 0
    last_start_ns: int | None = field(default=None,repr=False)
    start_time_us: int | None = None

    def __post_init__(self):
        values=(self.last_ns,self.maximum_ns,self.minimum_interval_ns,self.maximum_interval_ns,self.executions)
        if (any(type(value) is not int or value<0 for value in values)
                or self.last_ns>self.maximum_ns or self.minimum_interval_ns>self.maximum_interval_ns
                or (self.last_start_ns is not None and (type(self.last_start_ns) is not int or self.last_start_ns<0))
                or bool(self.executions)!=(self.last_start_ns is not None)
                or not self.executions and any(values)
                or self.executions<2 and (self.minimum_interval_ns or self.maximum_interval_ns)):
            raise ValueError('Invalid measured Task timing')
        if (self.start_time_us is not None and (type(self.start_time_us) is not int
                or not 0 <= self.start_time_us < 1 << 63 or not self.executions)):
            raise ValueError('Invalid Task wall clock start time')

    def record(self,start_ns,end_ns,*,start_time_us=None):
        if (type(start_ns) is not int or type(end_ns) is not int or start_ns<0 or end_ns<start_ns
                or self.last_start_ns is not None and start_ns<self.last_start_ns):
            raise ValueError('Invalid Task monotonic interval')
        interval=start_ns-self.last_start_ns if self.last_start_ns is not None else 0
        minimum=(min(self.minimum_interval_ns,interval) if self.executions>=2 else interval)
        return TaskMeasurements(end_ns-start_ns,max(self.maximum_ns,end_ns-start_ns),
            minimum,max(self.maximum_interval_ns,interval),self.executions+1,start_ns,start_time_us)

    def attributes(self):
        # Do not wrap, saturate or hide an independently representable field.
        values={7:(self.maximum_ns,32),8:(self.last_ns,32),
                14:(self.minimum_interval_ns,64),15:(self.maximum_interval_ns,64)}
        result={number:struct.pack('<I' if bits==32 else '<Q',value//1000)
                for number,(value,bits) in values.items() if value//1000<1<<bits}
        if self.start_time_us is not None:result[13]=struct.pack('<q',self.start_time_us)
        return result
