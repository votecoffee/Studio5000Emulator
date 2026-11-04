# UID/UIE interrupt control

App `26.1103.193217` adds a bounded v35 ControlLogix 5580 software model for
UID() and UIE() in ladder and existing ST calls. Both instructions take no
operands. UID increases the executing task's nesting depth; UIE decreases it.
Only the outermost UIE allows queued higher-priority EVENT work to run before
the caller's next instruction. False rung input and prescan have no action.

```text
UID()UID()EVENT(WorkEvent)MOV(EventCount,BeforeRelease);
UIE();
UIE()MOV(EventCount,AfterRelease);
```

The task-local depth is shared across routine calls, ladder FOR iterations and
scheduled Programs in that task invocation. Each Event task has its own depth.
The existing EVENT queue retains priority ordering, FIFO ties, pending-request
coalescing and active-request overlap diagnostics. UID does not inhibit tasks or
discard accepted requests. Lower/equal-priority work still waits for task return.

## Supported boundaries

The source must be a complete Standard v35 L81E–L85E project with an executable
task schedule. Routine harnesses, AOI calls, ST FOR bodies and other controller
profiles are blocked. ST WHILE/REPEAT and ordinary calls share the global
instruction budget. Balanced pairs may span called routines and Programs.

This model requires balanced pairs in each task invocation. UIE without an
active UID, or a nonzero depth when the task finishes, produces a simulator
fault and rolls back the whole advance. These are conservative software guards,
not claims about native unmatched-pair behavior. RET/TND/BRK can leave a pair
unbalanced, so their control-flow paths must preserve the task-level balance.

Mask depth and pending queues are transient to the advance. Errors inside the
protected caller, a released Event, or later work restore tag values, timer
history, first scans, scheduler counts, diagnostics, calls and simulated time.
Run entry and a retry do not inherit a failed advance's mask or queue.

The scheduler uses zero simulated instruction execution time. Periodic releases
retain their existing deterministic ordering; this feature does not add CPU
preemption, interrupt latency, deadlines, watchdogs or communication timing.
Fault routines, Controller Fault Handler, Safety and external I/O/motion event
sources remain unsupported. Native priority-register changes, persistent depth,
unmatched behavior, fault handling and controller/Studio equivalence are
unverified.

## Event lab

Enable GuardEvents and Step. The producer calls GuardedEvent, which nests two
UID instructions, requests WorkEvent, samples EventCount, and executes two UIEs.
GuardSeen retains the pre-release count after the inner UIE. ReleasedSeen sees
the new count after the outer UIE. With other trigger flags off, the first
guarded scan produces 0/1, the next 1/2. Turning GuardEvents off leaves the
last observations and stops this producer's requests.

The operand, nesting and false/prescan baseline uses installed v35 help
14693/19554. Rockwell's published
[UID/UIE reference](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/program-control-instructions/user-interrupt-disable--uid--user-interrupt-enable.html)
also describes nested pairs. The simulator queue and guarded balance policy are
explicit software choices. See [EVENT execution](event-tasks.md) and
[task scheduling](task-scheduling.md) for their separate limits.
