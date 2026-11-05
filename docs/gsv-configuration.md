# Configuration and identity GSV

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
| Program | Name | STRING or explicit user string | Named ordinary nonfolder Program or current Program |
| Routine | Name | STRING or explicit user string | Named Routine in the current Program or current executing Routine |
| Task | Name | STRING or explicit user string | Existing named Standard Continuous/Periodic or qualified Event task |
| Task | Instance | DINT | Current emulator registry slot from 0 through 31 |
| Task | Rate | DINT | Effective Periodic rate, or [defined Event timeout](event-tasks.md#runtime-timeout-settings), in microseconds |
| Task | EnableTimeOut | DINT | Current Event timeout enable, 0 or 1 |
| Task | Watchdog | DINT | Effective setting in project execution, explicit positive source setting in a harness, in microseconds |
| Task | Priority | INT | Effective Periodic/Event priority in project execution, explicit source priority in a harness |
| Task | InhibitTask | DINT | Explicit source flag, 0/1 |
| Task | DisableUpdateOutputs | DINT | Explicit source flag, 0/1 |
| Controller | Name | STRING or explicit user string | Explicit unambiguous source name |
| ControllerDevice | DeviceName | SINT[33] window | Counted catalog name from ProcessorType |
| ControllerDevice | ProductCode, ProductRev, Type, Vendor | INT | v35 5580 model identity |
| ControllerDevice | Status | INT | Controller mode sampled at scan entry |
| Controller | TimeSlice | INT | Explicit source setting, 10..90 |
| Controller | ShareUnusedTimeSlice | INT | Explicit source setting, 0/1 |

Class, attribute and object lookup are case insensitive. Returned names retain
source spelling. Task references use literal configured names or
[THIS in ordinary scheduled Program routines](current-instance-gsv.md).
Controller and ControllerDevice use an empty instance operand. Numeric object references and
AOI/harness THIS contexts remain outside the profile.

Structural preflight validates destinations without reading saved dynamic
indices. ST FOR effects cover complete static cells/strings and conservatively
widen changing/alias/AOI outputs across enclosing arrays.

Metadata must come from a complete loaded source snapshot. Task times use the
existing exact source milliseconds-to-microseconds conversion. For example,
10 ms reads as 10000 and 500 ms as 500000. Missing, malformed, zero-watchdog or
unqualified settings fail explicitly; compatibility defaults do not become GSV
source values. Continuous rate/priority remain unqualified. Event settings
require the [qualified Event project context](event-tasks.md). Event Rate is
available when source enables the timeout with an explicit rate or when SSV
defines one. A defined period remains readable while the timeout is disabled.

## Object identity reads

Program Name and Routine Name use the current loaded source catalogs. Both
require an ordinary scheduled caller. Program THIS selects its owning Program.
Routine THIS follows the executing routine through JSR and nested Event calls.
A named Routine resolves within the caller's Program. String writes update LEN
and the active DATA bytes and retain the unused backing bytes.

Task Instance reads the zero-based Task slot in the current emulator registry.
Slots follow the loaded Task inventory. A changed registry makes the attribute
unavailable until reload. These values are separate from native CIP instance
IDs. Task Instance requires project execution.

```text
GSV(Program,FastProgram,Name,StObjectProgramName);
GSV(Routine,THIS,Name,ObjectRoutineName);
GSV(Task,THIS,Instance,ObjectTaskSlot);
```

Open **System lab**, enable ReadObjectIdentity and step. The ladder routine
ReadCurrentInstances reads BackgroundProgram, ReadCurrentInstances and slot
0. The ST routine ReadSettings reads FastProgram by name, ReadSettings via THIS
and SlowTask slot 2. ST also uses the existing ReadConfig gate.

The operand types follow the installed v35 Program, Task and Routine help
topics 14638, 14646 and 14651. Native instance identity and execution parity
remain separate.

## Controller device identity

ControllerDevice reads the loaded v35 ControlLogix 5580 model's catalog name,
product code, firmware revision, device type (14), and vendor (1). The complete
source must declare the processor and major revision explicitly. ProductRev
also requires an explicit byte-sized MinorRev. Its low byte is the major
revision and its high byte is the minor revision. The destination is a signed
INT, so show it in hexadecimal to see the packed word.

DeviceName writes the ASCII character count, the catalog name, and zero
padding into 33 writable SINT elements. A larger array or an indexed start
works when the complete window fits in the selected array. Bytes outside
the window retain their values. The catalog name comes from the project
processor, independent of the endpoint's advertised identity profile.

In **System lab**, enable ReadControllerDevice and step 25 ms. Ladder writes
DeviceNameBytes, product code 168, and revision 16#0B23. ST writes device type
14 and vendor 1. ST also uses the existing ReadConfig gate. Physical serial
numbers and native ControllerDevice execution remain unqualified. These reads
follow installed v35 help topic 14635.
[Rockwell ControllerDevice reference](https://www.rockwellautomation.com/en-pr/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/input-output-instructions/access-the-controllerdevice-object.html)

### Controller device status

ControllerDevice Status uses the same INT word as the emulator's Logix
EtherNet/IP Identity status. The virtual keyswitch remains Remote. Every
routine in an advance sees the mode sampled at its entry.

| Scan entry | Status word |
| --- | --- |
| Manual Step in Remote Program | 16#3070 |
| Background scan in Remote Run | 16#3060 |
| Manual retry entered while the emulator still reports a software fault | 16#3450 |

A failed advance rolls back the destination. If a manual retry succeeds, the
next step samples Remote Program. Switching back to Program updates the
endpoint immediately. The GSV destination retains its last value until a scan
reaches the instruction.

Enable ReadControllerDevice in **System lab**. Compare DeviceStatus in ladder
and StDeviceStatus in ST after Step, Run, and another Step in Program.
The software model covers these modes and the existing emulator fault word.
Native fault classifications, debug, and transition flags remain unqualified.

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
Native phase and fault behavior, sub-millisecond periods,
Safety, AOI SSV and routine-harness SSV remain outside this profile.

## Changing a task priority

`SSV(Task,SlowTask,Priority,SlowPriorityCommand)` accepts an exact scalar
INT from 1 through 15 for a Standard Periodic or qualified instruction-only
Event task. A lower number means higher priority. The target is a configured
task name or `THIS` in an eligible scheduled Program. False rungs, skipped
ST calls and prescan skip source values.

GSV Priority reads the latest write during the advance. Periodic release
order, immediate EVENT dispatch and pending Event arbitration all use the
priorities captured at the start of that advance. A successful commit
changes the order for subsequent advances and keeps the existing periodic
phase. Coincident Periodic releases with equal priority use source order,
and pending Events with equal priority use request order. A fault restores
the prior priorities, task progress and values.

Run entry and routine replacement retain effective priorities. Reset or
reload restores the source priorities. The Coverage panel shows effective
and source priorities when they differ. In **System lab**, set the advance
to 25 ms, enable ApplySlowPriority, and step. SlowTask now reads 1 with
source priority 5. On the next step, SlowTask runs before FastTask at their
coincident 50 ms release.

The installed v35 Task object help 14646 lists the INT operand and a wider
0..15 attribute range. This software profile follows the
[ControlLogix 5580 task configuration range](https://www.rockwellautomation.com/en-mde/docs/technical/logix5000/_online/1756-um543/controllogix-5580-and-guardlogix-5580-controllers-/develop-standard-applications/tasks.html)
of 1..15. CIP Task Priority reads retain source metadata. Continuous, Safety,
other Event profiles, AOI and routine-harness setters, and native arbitration
remain outside this profile.

## Changing a task watchdog

`SSV(Task,THIS,Watchdog,WatchdogCommandUs)` changes the effective watchdog
setting of a Standard Continuous, Periodic or qualified instruction-only
Event task with an explicit positive source setting. The source operand is
an exact scalar DINT tag in microseconds. Positive values from 1000 through
2000000000 retain microsecond precision. A zero write selects 500000
microseconds for a Periodic task or 5000000 for a Continuous task. Event
watchdog writes require a positive value.

Named tasks and `THIS` use the existing scheduled Program context. GSV
Watchdog immediately reads the latest write. A later fault restores the
previous setting, tag values and task progress together. False rungs, skipped
ST calls and prescan skip the source value. Run entry and routine replacement
retain the setting. Reset or reload restores the explicit source setting.

In **System lab**, enable ApplyWatchdog and step. LiveWatchdogUs reads
125001 microseconds. The earlier BackgroundWatchdog read sees it on the
following step. Set WatchdogCommandUs to zero and step to see the 5-second
Continuous default in LiveWatchdogUs. Disable the gate to retain it.
Task schedule reports `watchdog_override_us` after a runtime write.

Installed v35 help 14646 defines the DINT operand and zero-write defaults.
Topic 18424 describes the configured range. See Rockwell's
[Task object](https://www.rockwellautomation.com/en-in/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
and [task configuration](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/37-01/contents-ditamap/studio-5000-logix-designer/tasks--programs--and-routines/tasks.html)
references. The emulator models the setting and keeps CIP reads bound to
source metadata. Expiration, fault handlers, CPU timing and Safety watchdogs
remain separate. Missing or zero values in the source remain unavailable.

## Destinations and execution

Numeric destinations must be exact scalar INT or DINT tags as listed above;
cross-type byte copies/conversions and packed bits are blocked. Strings use
represented DINT LEN / SINT DATA storage, with declared capacity enforced.
Aliases, indexed array elements, UDT members, Program-local scope and existing
AOI output/InOut bindings retain normal memory rules. Unknown destinations can
be established; strings preserve unused destination bytes.

Prescan, false ladder rungs and skipped ST branches retain outputs. Each reached
call reads the loaded configuration or the current project-mode
[InhibitTask flag](task-inhibition.md), Periodic Rate, Periodic/Event Priority
or Watchdog. Event Rate and EnableTimeOut use the [runtime timeout
settings](event-tasks.md#runtime-timeout-settings). A disk edit takes effect on project reload. Bound metadata with a different source hash is rejected. ST FOR checks
track every destination, including a string's LEN/DATA region. Capacity/bounds
errors and later failures retain whole-advance rollback of data and scheduling.

GSV reads the effective settings without changing them. Output I/O, watchdog
enforcement, CPU time slicing and native arbitration are separate profiles.
See [Task InhibitTask SSV](task-inhibition.md) for live inhibition.

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
