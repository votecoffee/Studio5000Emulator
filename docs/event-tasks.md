# Instruction-triggered Event tasks

The v35 ControlLogix 5580 software profile supports EVENT(task_name) in ladder
and Structured Text for explicitly configured Standard Event tasks.

```text
XIC(Request)EVENT(WorkEvent);
```

```text
IF Request THEN EVENT(WorkEvent); END_IF;
```

## Source and dispatch profile

The task must declare one canonical EventInfo with EventTrigger="EVENT
Instruction Only" and EnableTimeout="false". Priority and inhibition must be
explicit and unambiguous. Other trigger kinds, timeouts, Safety and incomplete
source are blocked. The target name is a literal configured task name.

A supported target has a higher priority than its caller. It runs synchronously
at the EVENT instruction, at the same simulated timestamp, before the caller's
next instruction. This provides a logical priority boundary without inventing
CPU execution costs or interrupt latency. Nested calls to still higher-priority
Event tasks are supported; task/first-scan context is restored on return.

```mermaid
sequenceDiagram
    participant Caller
    participant WorkEvent
    Caller->>WorkEvent: EVENT(WorkEvent)
    WorkEvent->>WorkEvent: Execute scheduled Programs
    WorkEvent-->>Caller: Complete; resume next instruction
```

Each executed true EVENT requests an execution; there is no implicit one-shot.
Use an explicit ONS or ST edge condition when needed. False rungs, skipped ST
branches and prescan do not trigger. A supported active self-request increments
the modeled overlap diagnostic and is discarded, avoiding recursive execution.
An inhibited Event task is ignored. Naming an existing Continuous/Periodic task
is a no-op and does not reschedule it.

Lower/equal-priority other-task targets need deferred dispatch and remain
explicitly blocked. EVENT inside AOIs, routine harnesses and ST FOR loops is
also unqualified. WHILE/REPEAT calls share the instruction budget and can observe
the Event task's writes. Task logic can alter loop data, so FOR calls are withheld
until full write-effect analysis is available.

## State, limits and timing

Event Programs participate in prescan and have their own first actual scan.
First-scan flags remain true for the caller when a nested Event task returns;
repeated triggers do not repeat the Event Program's first scan. Timers use the
trigger's simulated timestamp. Inhibited-task prescan retains the existing model
limitation described in [task scheduling](task-scheduling.md).

Periodic/Continuous and Event releases share the 4096-release limit per advance
and the global instruction budget. Writes, timer/first-scan state, execution
counts and modeled overlap diagnostics commit only when the entire advance
succeeds. Event faults or later caller/task faults roll everything back. Run
entry rearms first scans and resets scheduler diagnostic counts.

Coverage distinguishes Event tasks, their priority, execution count and
event_instruction_overlaps. They have no periodic next-release time. These
diagnostics do not implement native GSV Status/OverlapCount or SSV clearing.
Native interrupt latency, CPU preemption/time slicing, deadlines, watchdogs,
external I/O/motion/consumed triggers and timeout queues remain unfinished.

## Event Lab

Choose Event lab. A 10 ms Periodic RLL producer and a Continuous ST producer can
both trigger priority-1 WorkEvent. With both TriggerRLL and TriggerST true, one
10 ms advance executes the event twice. RllSeen observes the first increment;
StSeen observes the second, showing that each EVENT completes before the next
caller instruction. EventFirst increments only on its first execution.

Set SelfTrigger true to request WorkEvent from within itself. EventCount still
increments once per producer request; modeled overlaps increase once per active
self-request. Turn the producer flags off to stop new event executions.
See [EventLab.L5X](../source/samples/EventLab.L5X) and
[implementation](../source/logixlab/event_tasks.py).

The baseline uses installed v35 help 14708/19549. Rockwell's published
[EVENT reference](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/program-control-instructions/trigger-event-task--event-.html)
and [Import/Export task definitions](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
provide context. Software checks do not establish native controller/Studio
acceptance or complete event-task semantics.
