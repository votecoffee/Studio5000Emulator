# Task and Controller configuration GSV

The explicit v35 ControlLogix 5580 profile supports source-configuration reads
in ladder and Structured Text. Existing [audit-value GSV](controller-gsv.md)
keeps its original 64-bit destination contract. [Wall-clock GSV](wall-clock-gsv.md)
adds separate host UTC CurrentValue/DateTime and qualified LocalDateTime reads;
these are runtime clock samples rather than source-configuration attributes.
[Scan-time GSV](scan-time-gsv.md) separately reads committed Program/Task
LastScanTime and MaxScanTime through the existing interpreter counters.

```text
GSV(Task,FastTask,Rate,FastRate);
GSV(Task,FastTask,Priority,FastPriority);
GSV(Task,FastTask,Name,TaskName);
GSV(Controller,,TimeSlice,CommTimeSlice);
```

## Attributes and types

| Class | Attribute | Destination type | Scope |
| --- | --- | --- | --- |
| Task | Name | STRING or explicit user string | Existing named Standard Continuous/Periodic or qualified Event task |
| Task | Rate | DINT | Effective Periodic rate in project execution, explicit source rate in a harness, in microseconds |
| Task | Watchdog | DINT | Explicit positive time, in microseconds |
| Task | Priority | INT | Explicit Periodic/Event priority |
| Task | InhibitTask | DINT | Explicit source flag, 0/1 |
| Task | DisableUpdateOutputs | DINT | Explicit source flag, 0/1 |
| Controller | Name | STRING or explicit user string | Explicit unambiguous source name |
| Controller | TimeSlice | INT | Explicit source setting, 10..90 |
| Controller | ShareUnusedTimeSlice | INT | Explicit source setting, 0/1 |

Class, attribute and task lookup are case insensitive. Returned names retain
source spelling. Task instances are literal configured names or
[THIS in ordinary scheduled Program routines](current-instance-gsv.md). Empty
instances, native instance numbers and AOI/harness THIS contexts remain
unqualified.
Controller uses an empty instance operand.

Structural preflight validates destinations without reading saved dynamic
indices. ST FOR effects cover complete static cells/strings and conservatively
widen changing/alias/AOI outputs across enclosing arrays.

Metadata must come from a complete loaded source snapshot. Task times use the
existing exact source milliseconds-to-microseconds conversion. For example,
10 ms reads as 10000 and 500 ms as 500000. Missing, malformed, zero-watchdog or
unqualified settings fail explicitly; compatibility defaults do not become GSV
source values. Continuous rate/priority remain unqualified. Event settings require the qualified project context described in
[Event task inhibition](event-task-inhibition.md); Event Rate is not inferred.

## Changing a periodic task rate

`SSV(Task,FastTask,Rate,FastRateCommandUs)` changes the effective period of a
Standard Periodic task with an explicit source rate. The source is a scalar
DINT in microseconds, from 1000 through 60000000 in multiples of 1000. Ladder
and ST calls in project execution accept a literal task name or `THIS` in an
eligible scheduled Program. False ladder rungs, skipped ST calls and prescan
skip source values. A reached invalid value faults and rolls back the advance.

GSV Rate sees the latest successful write in the current advance. Releases
already scheduled for that advance run at their original times. When the
advance commits a changed period, the next release is one new period after
the end of the advance. Writing the same rate keeps the phase, including
when multiple writes leave the original period in effect. Inhibited tasks
use the same phase rule and discard missed releases. A later fault restores
the previous rate, release schedule and values together.

Program-to-Run restarts phase using the effective period. Routine replacement
retains the rate and phase. Reset and reload restore the source rate. The
scheduler reports both `rate_ms` and `source_rate_ms`. A project with one
initially enabled Periodic task uses its effective rate for automatic Run and
updates the Step interval after a committed change. A multi-task project's
Step or Run advance interval is independent of each task's period.

In **System lab**, leave FastRateCommandUs at 20000, enable ApplyFastRate,
and step 25 ms. LiveFastRateUs reads 20000. Task schedule shows FastTask at
20 ms with its 10 ms source rate. Set FastRateCommandUs to 10000 and step
to restore the original rate before disabling the gate.

The installed v35 Task object help 14646 and Rockwell's
[Task object reference](https://www.rockwellautomation.com/en-in/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
specify DINT microseconds. The whole-millisecond range and commit boundary
are software scheduler policies. CIP Task rate reads retain the source value.
Native phase and fault behavior, sub-millisecond periods, Event timeouts,
Safety, AOI SSV and routine-harness SSV remain outside this profile.

## Destinations and execution

Numeric destinations must be exact scalar INT or DINT tags as listed above;
cross-type byte copies/conversions and packed bits are blocked. Strings use
represented DINT LEN / SINT DATA storage, with declared capacity enforced.
Aliases, indexed array elements, UDT members, Program-local scope and existing
AOI output/InOut bindings retain normal memory rules. Unknown destinations can
be established; strings preserve unused destination bytes.

Prescan, false ladder rungs and skipped ST branches retain outputs. Each reached
call reads the loaded configuration or the current project-mode
[InhibitTask flag](task-inhibition.md) and Periodic Rate. A disk edit takes
effect on project reload. Bound metadata with a different source hash is rejected. ST FOR checks
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
