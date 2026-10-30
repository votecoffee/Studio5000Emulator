# Task and Controller configuration GSV

The explicit v35 ControlLogix 5580 profile supports source-configuration reads
in ladder and Structured Text. Existing [audit-value GSV](controller-gsv.md)
keeps its original 64-bit destination contract.

```text
GSV(Task,FastTask,Rate,FastRate);
GSV(Task,FastTask,Priority,FastPriority);
GSV(Task,FastTask,Name,TaskName);
GSV(Controller,,TimeSlice,CommTimeSlice);
```

## Attributes and types

| Class | Attribute | Destination type | Scope |
| --- | --- | --- | --- |
| Task | Name | STRING or explicit user string | Existing named Standard Continuous/Periodic task |
| Task | Rate | DINT | Explicit Periodic rate, in microseconds |
| Task | Watchdog | DINT | Explicit positive time, in microseconds |
| Task | Priority | INT | Explicit Periodic priority |
| Task | InhibitTask | DINT | Explicit source flag, 0/1 |
| Task | DisableUpdateOutputs | DINT | Explicit source flag, 0/1 |
| Controller | Name | STRING or explicit user string | Explicit unambiguous source name |
| Controller | TimeSlice | INT | Explicit source setting, 10..90 |
| Controller | ShareUnusedTimeSlice | INT | Explicit source setting, 0/1 |

Class, attribute and task lookup are case insensitive. Returned names retain
source spelling. Task instances are literal configured names; current-task,
THIS/empty-instance aliases and native instance numbers are not inferred.
Controller uses an empty instance operand.

Metadata must come from a complete loaded source snapshot. Task times use the
existing exact source milliseconds-to-microseconds conversion. For example,
10 ms reads as 10000 and 500 ms as 500000. Missing, malformed, zero-watchdog or
unqualified settings fail explicitly; compatibility defaults do not become GSV
source values. Continuous rate/priority remain unqualified.

## Destinations and execution

Numeric destinations must be exact scalar INT or DINT tags as listed above;
cross-type byte copies/conversions and packed bits are blocked. Strings use
represented DINT LEN / SINT DATA storage, with declared capacity enforced.
Aliases, indexed array elements, UDT members, Program-local scope and existing
AOI output/InOut bindings retain normal memory rules. Unknown destinations can
be established; strings preserve unused destination bytes.

Prescan, false ladder rungs and skipped ST branches retain outputs. Each reached
call reads the loaded configuration, with project-mode InhibitTask following the
[live runtime flag](task-inhibition.md); changing a disk file is not a project
reload. Bound metadata with a different source hash is rejected. ST FOR checks
track every destination, including a string's LEN/DATA region. Capacity/bounds
errors and later failures retain whole-advance rollback of data and scheduling.

These instructions read configuration. They do not change task rate/inhibition,
drive output I/O, enforce watchdogs, allocate CPU timeslices or measure execution
time. Native scan times, intervals, status/fault attributes, other system objects
and broader SSV remain unfinished. Bounded [Task InhibitTask SSV](task-inhibition.md) is available separately. Existing protocol metadata and software task counters
do not establish native controller execution parity.

## System Lab

Choose System lab in the header and step 25 ms. The authored
[SystemLab.L5X](../source/samples/SystemLab.L5X) combines the scheduling example
with configuration reads in background/periodic ladder and a called ST routine.
Task Lab remains unchanged.

FastRate/SlowRate read 10000/25000; FastWatchdog/BackgroundWatchdog read 500000.
FastPriority/SlowPriority read 2/5. FastTaskName and ControllerName become
FastTask and SystemLab. CommTimeSlice/ShareUnused read 30/1. FastInhibit and
FastNoOutput are zero; StSlowRate/StCommTimeSlice/StFastTaskName match ladder.
Background/Fast/Slow execution counts are 1/2/1 after that advance.

ReadConfig gates the examples. Set it false and scan to retain output tags while
the three tasks continue running. Editing a result tag changes that result;
reenabling reads restores the source setting when its task next executes.

The baseline uses installed v35 help 14636 (Controller) and 14646 (Task).
Rockwell's published [Task object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
and [Controller object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-controller-object.html)
provide context. Software tests do not establish native Studio/controller
acceptance. See [implementation](../source/logixlab/gsv_configuration.py).
