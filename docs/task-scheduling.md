# Continuous and periodic task scheduling

App `26.1029.080759` executes mixed Standard Continuous and Periodic tasks using
a deterministic, serial simulation clock. This supports common multi-task
projects without assigning invented CPU durations or claiming native scheduler
equivalence. Event tasks and Safety execution remain blocked.

## Try Task Lab

Choose **Task lab** in the header, then **Step scan**. The example contains one
Continuous task, a 10 ms Periodic task at priority 2 and a 25 ms Periodic task
at priority 5. After three 10 ms steps, BackgroundCount/FastCount/SlowCount are
3/3/1. FastTimer.ACC is 20 ms, and each Program's first-scan counter is 1.

```powershell
py -3.13 -X utf8 source/launch.py --sample TaskLab --data-dir .local/task-lab
```

The **Coverage → Task scheduling** view shows each task's rate, priority,
inhibition, execution count and next release. The API state and coverage export
contain `task_schedule`; rung and ST traces include `task` and `release_ms`.
The displayed scan counter counts simulation steps. Per-task counts show the
number of task executions, which may differ from the step count.

Choose **System lab** for [GSV configuration reads](gsv-configuration.md)
alongside the same mixed task rates. These reads do not change the scheduler
or add watchdog enforcement. Task Lab remains the scheduling-only example.

## Release rules

- One to 32 Standard tasks, with at most one Continuous task. This is the
  software model's bound; individual controller capacities need qualification.
- Periodic rates are integral milliseconds from 1 through 60,000. Priorities
  are 1 through 15, with 1 first at a coincident release. Missing source Priority
  uses the model default 10; this does not manufacture missing native metadata.
- The first Periodic release occurs one period after modeled Run entry.
  Releases remain anchored to that epoch across simulation steps.
- Each advance executes all releases in `(previous time, new time]`, in
  timestamp order. Coincident Periodic releases use priority, then source order.
- The Continuous task executes one complete pass at the end of each advance,
  after due Periodic tasks. Its run frequency therefore depends on step size.
- Programs execute in each task's configured order. A Program may be scheduled
  only once. Inhibited tasks retain configuration and execute no logic or
  prescan. A project with all tasks inhibited can advance time without logic.
- A single active Periodic task retains the existing interface contract: each
  step must equal its configured rate. Mixed/multiple-task projects accept any
  supported whole-millisecond step and dispatch releases within that interval.
- At most 4,096 task releases are permitted in one advance, sharing the engine's
  instruction budget. Excessive advances are rejected; releases are not silently
  dropped. Use smaller steps for fast task rates.

Prescan initializes enabled scheduled Programs at Run entry. `S:FS` is true for
each Program's first actual execution after that entry, including a Periodic
Program that does not run during the first simulation step. A Program-to-Run
transition rearms first scans and restarts Periodic phase at the current
simulation time. An isolated routine harness bypasses task scheduling.

Timer elapsed calculations use the actual modeled release timestamps, so a
large outer step does not force every timer execution to the same end time.
External queued inputs currently apply at the simulation-step boundary; there
is no asynchronous physical I/O update inside the advance.

## Rollback and reporting

Task releases are prepared without advancing scheduler state. If any executed
instruction fails, the whole simulation advance rolls back memory, timer/clock
state, first-scan state, release phase and task counts. This retains the existing
model policy rather than reproducing a native controller's partial execution
or fault handler behavior. A failed advance cannot silently consume future work.

Task execution counts and next releases are simulation diagnostics. Existing
native Task measurement/status services retain their guarded single-task
profile; multi-task counts are not substituted into unimplemented native fields.
Program host-time measurements remain separate from simulated release times.

## Validation checkpoint

The scheduler has 23 focused cases covering mixed rates, coincident priorities,
Program order/first scans, inhibition, timer elapsed values, ST trace context,
source guards, budgets, rollback and routine-replacement state preservation.
The milestone suite runs 2,344 tests with two platform checks skipped. Real
HTTP lifecycle tests also exercise the bundled Task Lab. These checks validate
the software model; native controller timing and SDK acceptance are separate.

## Remaining scheduler work

CPU instruction-level preemption, equal-priority time slicing, execution costs,
deadline overlaps, watchdog enforcement, event triggers/queues, system overhead
and Safety scheduling remain unfinished. Periodic releases are instantaneous
serial executions at their timestamps. First-release phase, Continuous frequency
and tie ordering are explicit model policies requiring independent native
comparison before claiming controller parity.

Rockwell's [task programming manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm005_-en-p.pdf)
describes controller task types, priorities and preemption. Those native rules
are a reference for future work; this initial scheduler does not implement all
of them. See [implementation](../source/logixlab/task_scheduler.py),
[runtime integration](../source/logixlab/runtime.py) and
[focused scheduler cases](../source/tests/test_task_scheduler.py).
