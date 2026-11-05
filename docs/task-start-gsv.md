# Task start times and intervals

The ladder/ST GSV reads of Task `StartTime`, `MinimumInterval` and
`MaximumInterval` are available for the v35 ControlLogix 5580 software
profile. Named instances and `THIS` use the existing ordinary scheduled context
rules. Eligible Standard Continuous, Periodic and instruction-only Event tasks
retain independent successful invocation histories.

```text
GSV(Task,THIS,StartTime,LastStart);
GSV(Task,FastTask,StartTime,StartWords[1]);
GSV(Task,FastTask,MinimumInterval,MinimumWords[1]);
GSV(Task,FastTask,MaximumInterval,MaximumWords[1]);
```

StartTime accepts a scalar LINT or DT. MinimumInterval and MaximumInterval
accept a scalar TIME. Each attribute also accepts two contiguous DINT elements
within one logical array or member boundary, lower word first.
Complete writes establish unknown destination cells and retain neighboring
elements. The full window and permissions are checked before its first write.

## Measurement and visibility

StartTime samples the existing host UTC WallClockTime at invocation entry, in
microseconds since 1970-01-01. Intervals measure successive actual host starts
using `perf_counter_ns`, in whole microseconds. They include pauses between
Steps and host processing time. They are independent of simulated scan time,
configured task Rate and changes to the UTC clock. Two Periodic releases in
one Step can therefore have an interval shorter than their simulated period.
These diagnostics measure the interpreter, not controller performance.

Before execution StartTime is zero. Minimum/maximum intervals remain zero until
two successful invocations. Every read within an advance sees the previous
committed snapshot, including reads after another task has run in that advance.
Event requests that overlap, coalesce, are inhibited or are canceled without
dispatch do not add invocation samples. Successful nested Event work is included
in its parent's duration; each Event also has its own independent start history.

An unavailable host UTC sample withholds only that invocation's StartTime.
Durations and intervals remain independently available. Unrepresentable 64-bit
intervals are withheld without wrapping or saturation. DINT pairs preserve all
64 bits, including a set sign bit in either word. DT and TIME writes check the
[supported type ranges](time-date-storage.md) and fault on overflow.

## Selection, faults and lifecycle

Structural preflight checks types, shapes, reference grammar, fixed bounds and
write permissions without saved dynamic indices. False ladder rungs, skipped ST
bodies and prescan skip live outputs and timing reads. Reached invalid indices,
insufficient windows, unavailable measurements and later faults roll back the
whole advance: tags, bindings, all task histories and scheduling progress.

ST FOR validation protects the whole destination, including both cells of a word pair. Alias and changing-index
destinations conservatively protect their enclosing array. Run entry and
detached routine replacement retain committed timing histories; fresh load/reset
initializes them. Runtime-inhibited tasks retain their last successful samples.
The existing single-Task protocol measurement contract remains unchanged; these
instruction reads do not expose new multi-Task/Event native protocol attributes.

## System lab

Open **System lab**. `ReadTaskStarts` starts false, leaving `TaskStartIndex=99`
dormant and the selected word pairs unknown. Step once, set `TaskStartIndex=1`,
enable `ReadTaskStarts`, then Step again. `ThisTaskStart` and `StTaskStart` agree
on the preceding Background invocation. `TaskStartWords[1..2]` contains the
preceding FastTask UTC start. Ladder `TaskMinWords`/`TaskMaxWords` match ST
`StTaskMin`/`StTaskMax`, with guard elements 0=101 and 3=999 retained.

Set `TaskStartDivisor=0` to demonstrate a late fault and rollback. Restore 1
before continuing. Disable `ReadTaskStarts` before returning the index to 99.
Enable ReadTypedTimes to read the prior Background Task start into TaskStartDate
and the prior FastTask intervals into TaskMinTime and TaskMaxTime.

See the authored [SystemLab.L5X](../source/samples/SystemLab.L5X),
[timing reads](../source/logixlab/gsv_timing.py) and
[invocation measurements](../source/logixlab/task_runtime.py).

The attribute names and layouts follow installed v35 help topic 14646.
Rockwell's later [Task object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
uses shortened interval names; those aliases are outside this v35 profile.
SSV timing changes, Safety/other Event profiles, broader AOI/harness contexts,
TIME32[2] interval destinations and native sampling/precision/status/fault/lifecycle
equivalence remain unqualified.
