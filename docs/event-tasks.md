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
Instruction Only" and an explicit EnableTimeout flag. Priority and inhibition
must be explicit and unambiguous. Other trigger kinds, Safety and incomplete
source are blocked. The EVENT target is a literal configured task name.

When no [UID/UIE mask](interrupt-control.md) is active, a higher-priority target
runs synchronously at the EVENT instruction, at the
same simulated timestamp, before the caller's next instruction. Lower/equal-
priority targets wait for a task return. Ready Event tasks drain by priority,
then FIFO request order. Coincident Periodic releases precede queued Events at
equal priority; higher-priority queued Events run before lower-priority base work.
All pending work drains before moving to the next timestamp.
[Task Priority writes](gsv-configuration.md#changing-a-task-priority) take effect
for arbitration on the next advance. Current requests, UIE drains and
coincident releases all use the priorities captured at advance start.

After a nested higher-priority task returns, newly eligible queued work runs
before the restored caller resumes. Task and first-scan context are preserved.
These are logical boundaries with zero simulated execution cost. Equal-priority
CPU time slicing and native interrupt latency are not modeled.

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
branches and prescan do not trigger. A request for an already active task is
discarded and increments the modeled overlap diagnostic, including cross-task
retriggering from a preempting task.

The software queue holds at most one pending execution per task. Duplicate
requests while pending coalesce and increment a separate diagnostic. This is an
explicit software policy; native pending-duplicate behavior is unverified. Once
the task completes, it can be requested again in the same advance. An inhibited
Event task is ignored. Naming an existing Continuous/Periodic task is a no-op
and does not reschedule it.

EVENT inside AOIs, routine harnesses and ST FOR loops remains unqualified.
WHILE/REPEAT calls share the instruction budget. Higher-priority Event writes
are visible immediately; waiting on a deferred Event from inside a caller loop
cannot make progress until that caller returns and will exhaust the budget.
Task logic can alter loop data, so ST FOR calls await full write-effect analysis.
[Ladder FOR](ladder-loops.md) supports live loop data and separate per-task call
stacks, including nested Event calls; native timing and sampling remain unverified.

## Configured timeouts

An instruction-only Event task can declare `EnableTimeout="true"` on
its EventInfo and an explicit `Rate` on the Task element. The emulator
accepts 1 through 60000 whole milliseconds for Rate. At Run entry the
first deadline is one configured interval away. Each completed invocation
starts a fresh interval, whether triggered by EVENT or by timeout.

Deadlines use simulated time and can release a task between Periodic
releases. A long advance can execute several timeout invocations at their
individual timestamps. Coincident work uses the advance-start priorities.
A Periodic release wins a tie with an equally ranked timeout. An already
queued EVENT wins a tie with a timeout at equal priority. If it runs the
same task first, its completion replaces the old deadline. A timeout that
runs first can be followed by a separate explicit EVENT at the same time.
Equal-priority timeout candidates use source order. These tie rules are
deterministic software policies.

An inhibited task skips its timeout and advances to the next deadline.
Enabling it resumes from the next future deadline without replay. Skipped
timeout slots count against the same release budget as other scheduled
work. A fault rolls back deadlines, status, data and execution progress.
Routine replacement retains committed deadlines. Run entry restarts the
deadline and reset or reload restores the initial state.

GSV reads `EnableTimeOut` as a DINT flag and the configured timeout
`Rate` as DINT microseconds. Timeout execution latches
[Status bit 1](event-task-status.md) independently of explicit EVENT and
active overlap. SSV Rate and EnableTimeOut for Event tasks, external
triggers, fractional-millisecond intervals and native timing remain open.

See the installed v35 Task object help 14646 and Rockwell's
[Event task configuration](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/studio-5000-logix-designer/tasks--programs--and-routines/tasks/edit-task-properties/create-an-event-task.html)
and [Task import/export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf).

## State, limits and timing

Event Programs participate in prescan and have their own first actual scan.
First-scan flags remain true for the caller when a nested Event task returns;
repeated triggers do not repeat the Event Program's first scan. Timers use the
trigger's simulated timestamp. Inhibited-task prescan retains the existing model
limitation described in [task scheduling](task-scheduling.md).

Periodic/Continuous and Event releases share the 4096-release limit per advance
and the global instruction budget. Writes, timer/first-scan state, execution
counts and active/pending diagnostics commit only when the entire advance succeeds.
Queues are transient to the advance. Faults before draining, inside deferred work
or in later base tasks roll everything back and discard the queue. Deferred
cycles share the same limits and cannot bypass them through queueing. Run
entry rearms first scans and resets scheduler diagnostic counts.

Coverage distinguishes Event tasks, their priority, execution count and
event_instruction_overlaps (active requests discarded) and
event_pending_requests_coalesced (pending duplicates merged). For a
timeout-enabled Event, the next release time shows its current deadline.
[Logical Status GSV/SSV](event-task-status.md) exposes the latched causes and
supports clearing them.
[OverlapCount GSV/SSV](event-overlap-count.md) additionally provides live reads
and zero resets of the active-request counter, separately from Status clearing.
Neither feature expands native Task Status/OverlapCount protocol attributes.
Native interrupt latency, CPU preemption/time slicing, watchdog expiration,
and external I/O, motion or consumed-tag triggers remain unfinished.

[Runtime Event inhibition](event-task-inhibition.md) now checks live flags for
new requests and queued dispatch. Current bodies complete, enabling does not
replay discarded work, and accepted status remains latched.

[Event Task/Program timing](event-task-timing.md) now exposes prior committed
interpreter last/maximum durations in ordinary named/THIS RLL/ST contexts.
Ignored, overlapping, coalesced and canceled requests do not add timing records.

## Event Lab

Choose Event lab. A 10 ms Periodic RLL producer and a Continuous ST producer can
both trigger priority-1 WorkEvent. With both TriggerRLL and TriggerST true, one
10 ms advance executes the event twice. RllSeen observes the first increment;
StSeen observes the second, showing that each EVENT completes before the next
caller instruction. EventFirst increments only on its first execution.

Set SelfTrigger true to request WorkEvent from within itself. EventCount still
increments once per producer request; modeled overlaps increase once per active
self-request.

Set TriggerDeferred true to make the priority-5 Periodic producer request the
priority-10 DeferredEvent twice. One execution remains pending until the producer
finishes. After the first 10 ms step, DeferredCount is 1, RllDeferredSeen is 0 and
StDeferredSeen is 1: the producer read the old value while the later Continuous
Program read the completed Event's value. The pending-duplicate count increases
once per producer release. DeferredFirst increments once and DeferredTimer uses
release timestamps. Turn the producer flags off to stop their explicit requests.

With the producer flags off, TimeoutDemoEvent runs first at 35 ms and then
at 70 ms. TimeoutDemoRuns and TimeoutDemoFirst count releases and first
scans. TimeoutDemoStatus reads 2, TimeoutDemoRateUs reads 35000 and
TimeoutDemoEnabled reads 1. To postpone the first deadline, reset, enable
TriggerTimeoutDemo for the first 10 ms step, and disable the flag. The
explicit request sets Status to 1 at 10 ms. The next timeout runs at 45 ms
and the two latched bits read 3.

See [EventLab.L5X](../source/samples/EventLab.L5X) and
[implementation](../source/logixlab/event_tasks.py).

The baseline uses installed v35 help 14708/19549. Rockwell's published
[EVENT reference](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/program-control-instructions/trigger-event-task--event-.html)
and [task scheduling manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm005_-en-p.pdf),
alongside the [Import/Export task definitions](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
provide context. Software checks do not establish native controller/Studio
acceptance or complete event-task semantics.
