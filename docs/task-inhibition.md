# Runtime task inhibition with SSV

App `26.1030.001741` adds `SSV(Task,TaskName,InhibitTask,Source)` in ladder and
Structured Text for the explicit v35 ControlLogix 5580 software profile.
The target must be a configured Standard Continuous or Periodic task, and
Source must be an exact scalar DINT tag. Zero enables the task; any nonzero
signed DINT inhibits it. Names and attributes are case insensitive.

```text
SSV(Task,FastTask,InhibitTask,DisableFast);
GSV(Task,FastTask,InhibitTask,FastDisabled);
```

The instruction reads its source without modifying it. Aliases, scalar members,
array elements, indirect indices, read-only constants and Program-local scope
retain normal memory rules. Immediate values, packed bits, implicit numeric
conversions and aggregate sources are blocked. A false ladder rung or skipped
ST body does not read the source or change inhibition. Prescan does not execute
SSV; malformed calls still block execution even in unreachable code.

## Scheduling and lifecycle

Each potential task release checks the current runtime flag. A higher-priority
task can therefore inhibit a lower-priority task before a coincident release,
and changes can affect later releases within the same simulation advance.
The currently executing body completes, including code after self-inhibition.
The emulator does not interrupt or abort an in-progress body.

Periodic phase continues while inhibited. Missed releases are discarded, and
re-enabling permits the next future release on that phase without catch-up.
Enabling does not itself execute a task or reassert `S:FS`. Initially inhibited
tasks are validated and prescanned at Run entry; their first actual execution
receives the Program's first-scan state.

Program-to-Run retains the runtime flag and restarts periodic phase using the
existing Run-entry rules. Reset/reload creates fresh flags from source. Supported
routine replacement retains flags and scheduling progress in detached state.
Source task settings and the original L5X bytes are not rewritten by SSV.

GSV Task InhibitTask reads the runtime flag in project mode. Coverage/API task
rows show live `inhibited` and separate `source_inhibited`; inhibited rows have
no eligible `next_release_ms`. A source-bound, already exposed Task object's
read attribute 19 follows the live flag too. This adds no new native task
identity, online transfer or native write service.

The release budget counts potential slots, including inhibited tasks, and
instruction-triggered events. At most 4,096 slots/events may be considered in
one advance. Use smaller steps for fast task rates even when tasks are disabled.
A later fault rolls back flags, data, phase, release counts and first-scan
progress together. Correcting the input allows retry from the prior commit.

## System Lab

Choose **System lab** and step 25 ms. Both controls start disabled, preserving
the original GSV and task-count example. Set ControlTasks=true and
TaskInhibitCommand=1, then step. Background logic inhibits FastTask after its
already due releases; LiveFastInhibit becomes 1. Later steps retain FastCount
while SlowTask continues. Set the command to 0 and step to enable FastTask;
its next periodic release resumes execution.

StApplyInhibit and StTaskInhibitCommand independently control SlowTask from the
called ST routine. StSlowInhibit shows its flag. These ST examples require
ReadConfig=true so that ReadSettings is called. Any nonzero command inhibits.

ControlDivisor defaults to 1. With ControlTasks enabled, setting it to 0 faults
after both examples, demonstrating rollback of inhibition and earlier task
work. Restore it before retrying. See [SystemLab.L5X](../source/samples/SystemLab.L5X),
[SSV implementation](../source/logixlab/task_inhibit.py) and
[scheduler](../source/logixlab/task_scheduler.py).

## Remaining scope

Other SSV classes/attributes, Event and Safety targets, AOI/routine-harness
calls remain unqualified. Bounded ST FOR bodies can execute this SSV profile. Dynamic rate/priority,
watchdogs, native abort/resume/phase details and native status/fault parity
remain unfinished. The deterministic boundary and phase rules above are
explicit software policies, not a claim of complete controller equivalence.

The installed v35 Task object help describes DINT InhibitTask, zero/nonzero
control and prescan of inhibited tasks. Rockwell's
[Tasks, Programs, and Routines manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm005_-en-p.pdf)
provides the SSV example context. Software checks do not establish native
Studio/controller acceptance of this implementation.
