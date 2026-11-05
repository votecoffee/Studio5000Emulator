# Event task scan timing

The v35 ControlLogix 5580 project profile supports `LastScanTime` and
`MaxScanTime` GSV reads for qualified instruction-only Standard Event tasks.
An ordinary scheduled Program can name the target; `THIS` inside the Event
selects its Task. Program THIS timing also works in that ordinary Event
context and matches the existing named Program measurement.

```text
GSV(Task,WorkEvent,LastScanTime,EventLast);
GSV(Task,THIS,MaxScanTime,EventMaximum);
GSV(Program,THIS,LastScanTime,EventProgramLast);
```

Destinations remain exact scalar DINT elements. Class, attribute and instance
names are case insensitive. Values preserve the unsigned DWORD's bits in
signed DINT storage. Last and maximum availability are independent; an
unrepresentable field is withheld rather than wrapping or saturating.

## Measurement and visibility

Each successfully completed Event invocation records its host monotonic
interpreter duration, including nested calls and synchronously dispatched
higher-priority Event work. Nested Events also keep independent measurements.
These inclusive durations do not predict controller CPU performance, exclusive
CPU usage, preemption, watchdogs or interrupt latency.

Values start at zero and publish only with a successful complete advance.
GSV normally reads the previous committed snapshot, including after a
synchronous Event return. A [MaxScanTime reset](scan-time-gsv.md#resetting-maxscantime)
clears that maximum immediately and includes only durations completed after
the reset. The final successful invocation still supplies LastScanTime.

Ignored requests, active-overlap requests, pending duplicate coalescing and
pending work canceled by inhibition do not add execution or timing records.
Unexecuted and inhibited Events retain their previous measurements. An
initially inhibited qualified Event has initialized zero values and can be
enabled and measured later. Its body still records a successful duration if it
self-inhibits and completes. An Event-only project with no supported request
source stays idle; initialized zeros do not imply an execution.

Prescan does not sample Event execution. A failed Event or later caller fault
discards all pending Task/Program measurements together with tag, binding,
status, scheduling and first-scan work. Run entry retains committed timing;
load/reset initializes it. Detached routine replacement preserves independent
timing state.

## Eligibility and operands

Task measurements require complete current source, an unchanged task graph,
canonical instruction-only EventInfo with a supported timeout setting, a known ordered
Program schedule, and explicit priority/output-update/inhibit settings. Missing
metadata does not fabricate a default. Safety, external Event sources,
AOI and isolated routine-harness Event timing contexts remain unqualified.
The established Continuous/Periodic and single-Task native profiles are retained.

Structural preflight, false/prescan/skipped paths, indirect and alias
destinations, complete unknown-cell writes and conservative ST FOR effects
follow the shared [scan-time GSV](scan-time-gsv.md) rules.

## Event lab

Step **Event lab** with ReadEventTiming false; EventTimingIndex99 is dormant.
Set EventTimingIndex=1, ReadEventTiming=true, TriggerRLL=true and
TriggerDeferred=true. After successful advances, EventTimingWords[1],
ThisWorkTaskLast and StWorkTaskLast match; WorkTaskMax matches ThisWorkTaskMax.
DeferredTaskLast, ThisDeferredTaskLast and StDeferredTaskLast likewise match.
NamedWorkProgramLast matches ThisWorkProgramLast. Guards101/999 remain intact.

The called ReadEventTimings routine shows the named ladder reads. Event bodies
show THIS reads, and Background ST shows named reads. Inhibit controls retain
the affected Task's timing while other work continues. TimingDivisor0 faults
late in Background ST; restore it to1 before retrying. A reached invalid
EventTimingIndex also rolls back the advance. See
[EventLab.L5X](../source/samples/EventLab.L5X) and
[focused tests](../source/tests/test_event_timing.py).

The report exposes these logical measurements under task_scan_timing with
native_protocol_expanded=false. No Event native timing/status attribute,
physical history, controller clock or Studio acceptance is added. Installed
v35 Task/Program object help14646/14638 supplies the type/unit baseline; native
precision, visibility, status/fault and lifecycle equivalence remain separate.
