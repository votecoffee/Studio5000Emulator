# Task execution measurements

Version `.137` adds whole-Task execution measurements and a live Task object
reference to the existing [source-bound Task metadata](task-metadata.md).
Version `.140` adds [simulator WALLCLOCKTIME start timestamps](task-start-time.md).
Version `.138` adds separate [execution status and registered slots](task-execution-state.md).

| Task attribute | Software-model value | Encoding |
| --- | --- | --- |
| 7, Maximum Scan Time | Longest completed Task execution since reset | UINT32 microseconds |
| 8, Last Scan Time | Most recent completed Task execution | UINT32 microseconds |
| 11, Task Address | Reference backed by the current interpreter Task object | UINT32 opaque reference |
| 14, Minimum Interval | Shortest interval between successful Task starts | UINT64 microseconds |
| 15, Maximum Interval | Longest interval between successful Task starts | UINT64 microseconds |

The installed v35 Task descriptions establish these field widths. Rockwell's
[Task object reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
also describes the scan-time units and zero interval values before two executions.

## Execution and preservation

The host monotonic clock measures the scheduled Program calls together as one
Task execution. The measurement includes interpreter dispatch and nested calls;
it excludes prescan, initial snapshot copying and later tag-change reporting.
Intervals measure actual host time between successful starts, independently of
the simulator's scan interval, simulated elapsed time and source periodic rate.
These values do not predict physical controller performance.

All four timing counters start at zero. The interval counters remain zero until
the second successful execution. Measurements commit only when the complete
Task scan succeeds. A later Program failure rolls back the new measurements
alongside Program timings, tags, scan count and simulated time. Reset starts
new counters; a supported Program-mode Routine replacement preserves the existing
Task measurements. A later execution records the changed logic normally.

Conversions discard sub-microsecond fractions. An out-of-range value remains
unavailable; it does not wrap or saturate, and independently representable fields
remain readable. Single and ordered list reads share the same immutable values.
The endpoint's `task_measurements` state reports availability, execution count,
units and limits without exposing a raw monotonic timestamp or object reference.

## Availability and references

The existing single Standard Continuous/Periodic Task execution profile applies.
Complete current source, a canonical Task declaration, explicit priority/output
and inhibit settings, and a known ordered Program schedule are required. Blocked
projects, routine harnesses, inhibited Tasks and ambiguous source do not gain
these measurements. Task metadata still requires the matching native Task names
and L5X binding.

Task Address additionally requires matching original ACD/L5X Project and Task
bindings and no programming scan inhibit. The reference resolves to the current
Task object in the existing interpreter registry. It is stable while that object
lives; reset or replacement revokes the previous reference. It grants no native
memory read/write or machine-code execution service. Logical CIP IDs and Task
execution-instance slots remain separate. Version `.138` supplies attribute 16
from the interpreter's own Task registry.

The `.139` [stored configuration profile](stored-task-configuration.md) separately
adds trigger, latent rate, type, timeout and mapping-count reads. Start-time epoch
and AOI stack fields remain outside this change. No setter,
watchdog enforcement, native scheduler or Test/Untest/Assemble authority is added.

## Validation

All 152 affected tests pass; the full suite was not rerun. Checks cover exact
units and overflow, whole-Task measurements across multiple Programs, failed-scan
rollback, prescan exclusion, source/mode guards, reference lifetime, signed reads
and write denial. The supported Routine replacement test also retains the
existing Task measurement record across engine replacement.

Two isolated SDK uploads use the same saved/reopened empty-Program ACD and the
same private clock/schema/empty-repository assumptions. The `.136` control has
16 unavailable Task fields. The `.137` comparison reads all five new fields
successfully, leaving 11 unavailable fields. Both still fail Task upload across
358 verified signed requests and 361 expanded leaf requests. Actual Offline
and endpoint cleanup, preserved source/model and no fatal SDK fault are confirmed.
The private substitutes remain unshipped. Full native upload/download and the
nonempty Routine source-retrieval failure remain unfinished.

A separate native SDK test uses the saved/reopened single-NOP project and the
normal protocol behavior. After one measured scan, a supported Program-mode
rung insertion and reconnect preserve the four timing values and execution
count. The replacement engine supplies a new live Task reference; a second
scan records the changed logic normally. All 183 signed requests complete with
actual Offline/cleanup, preserved original files and no fatal SDK fault.
This validates the supported import and reconnect; Test/Untest/Assemble remains
unfinished.

The restarted normal demo passes SDK Go Online/Go Offline across 75 verified
signed requests, with actual Offline/cleanup, preserved source/model and no
fatal SDK fault. All 17 deployment checks pass, including the frozen executable's
Task measurements and references. All 95 deployed modules match the build;
served assets, packaged resources and webpage/executable versions match `.137`.
The demo's tags, logic, tasks, mode and edit configuration survive the restart.
