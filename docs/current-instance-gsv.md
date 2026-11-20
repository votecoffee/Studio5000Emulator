# Current-instance GSV

In the v35 ControlLogix 5580 software profile, ordinary scheduled ladder and ST
Program routines can use THIS for existing Program/Task timing and Task configuration
reads. Called routines in the same Program keep that context.

```text
GSV(Task,THIS,Name,TaskName);
GSV(Task,THIS,Watchdog,TaskWatchdog);
GSV(Task,THIS,Rate,PeriodicRate);
GSV(Program,THIS,LastScanTime,ProgramLast);
```

THIS is case insensitive and resolves from source-bound scheduling metadata,
without reading a tag or interpreting a native instance number. Task THIS selects
the current Program's unique owner Task. Program THIS selects that Program.
The source must identify an enabled ordinary Standard Program with a scheduled
entry under one Standard Continuous/Periodic or qualified Event Task.
Event configuration and inhibition contexts are described in
[Event task controls](event-task-inhibition.md) and
[Event timing](event-task-timing.md). Reached calls also verify that the
active execution Task matches that owner. Missing, ambiguous or changed context
fails instead of guessing a task from a saved value or the first configured row.

## Attribute and execution limits

Existing [configuration](gsv-configuration.md) and [timing](scan-time-gsv.md)
contracts still apply. Rate reads a Periodic interval or a configured Event
timeout. Priority permits Periodic and qualified Event Tasks.
Configuration times use microseconds and exact destination types. Program LastScanTime/MaxScanTime
read the preceding committed interpreter snapshot. [Task timing](scan-time-gsv.md)
also supports independent last/maximum durations in eligible multi-task projects,
including THIS reads in the executing Program. No new attribute is added.

Prescan, false ladder rungs and skipped ST statements retain output values.
Configuration destination validation is now structural for named and THIS reads:
saved dynamic indices are checked only when reached. Full writes establish
unknown scalar cells; string writes retain their existing unused-byte behavior.
ST FOR analysis covers complete static cells/strings. Changing indices, aliases
and AOI outputs conservatively cover enclosing arrays so saved selections cannot
hide a write to loop bounds or step. Invalid addresses, unavailable metadata or
a later fault roll back data, bindings, scheduling and uncommitted measurements.

[Event Task Status](event-task-status.md) separately supports Task THIS inside
qualified instruction-only Event tasks for Status GSV/SSV. Configuration reads
and SSV InhibitTask also support Event THIS. Task and Program timing now
support qualified ordinary Event contexts. AOIs can read their own
[Task diagnostics](#aoi-task-diagnostics) using the scheduled caller context.
Empty/numeric instance aliases and broader SSV forms remain unchanged.
[SSV InhibitTask](task-inhibition.md) now permits THIS for supported ordinary Tasks. Existing named AOI reads retain their prior software profile.
No FBD/SFC, CPU-preemption or new controller-profile behavior is introduced.

## AOI Program DisableFlag

[Program DisableFlag readback](program-disable.md#readback-inside-aois) uses
the calling Program. An AOI can see a same-scan change as well as the startup
value in an explicit Prescan routine.

## AOI Task configuration

In a Standard AOI, ladder and Structured Text GSV Task THIS can read Name,
Instance, Watchdog, DisableUpdateOutputs and InhibitTask. Rate and Priority
apply to Periodic and qualified Event Tasks, and EnableTimeOut applies to
qualified Event Tasks. Rate for an Event Task requires a defined timeout.
Instance is the emulator's Task registry slot. Rate and Watchdog use DINT
microseconds, Priority uses INT, and the flag reads use DINT 0 or 1.

Each AOI call uses the calling Program's scheduled Task. The reads can see
settings changed by earlier Program instructions in the same scan. An explicit
AOI Prescan routine reads its scheduled owner's settings, including at startup
before a Task release. Invalid destinations or a later fault roll back the
advance. Isolated routine harnesses lack the scheduled caller context. AOI
SSV requires ordinary scheduled Program logic. Native controller execution
remains unverified.
[Rockwell Task object reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)

## AOI Task diagnostics

`GSV(Task,THIS,Status,Destination)` and `GSV(Task,THIS,OverlapCount,Destination)`
read the calling Task from Standard ladder and Structured Text AOIs. Qualified
Event Tasks expose the live [status bits](event-task-status.md) and
[overlap count](event-overlap-count.md). Serial Periodic Tasks write zero.
Both attributes require a writable scalar DINT. An explicit AOI Prescan can
read the initial zero Event diagnostics. Status bits and overlap counts roll
back with the advance on a later fault. AOI SSV and named targets remain
outside this profile. Native execution remains unverified.

## AOI timing reads

Standard ladder and ST AOIs can read Program and Task LastScanTime and
MaxScanTime through THIS. Task THIS also reads StartTime, MinimumInterval and
MaximumInterval. The reads follow the scheduled caller through nested AOIs
and use the same [destination types](scan-time-gsv.md) and
[committed timing snapshot](task-start-gsv.md#measurement-and-visibility) as
reads in Program logic. Earlier Program instructions that reset a field are
visible in the same advance. A later fault rolls back the read and the reset.

Explicit AOI Prescan code can read the existing snapshot, which starts at
zero on project load. Timing setters still require ordinary scheduled Program
logic. These are measurements of the emulator's execution. Native controller
timing remains unverified.

## System lab

Step **System lab** with ReadThis false. Set ThisIndex=1 and enable ReadThis.
The called ReadCurrentInstances ladder routine reads BackgroundTask's name and
500000-microsecond watchdog, plus BackgroundProgram's last/maximum durations.
ThisWords[1] is the only timing cell changed; guards101/999 remain. The called
ReadSettings ST routine reads the same name/watchdog and committed Program last
duration when its existing ReadConfig gate is enabled.

FastProgram and SlowProgram independently read their own Task Rate/Priority:
10000/2 and 25000/5. ThisIndex=99 remains dormant when disabled and faults when
its timing destination is reached; correct it and retry. **ReadCurrentInstances**
exposes the four ladder calls in the viewer. See
[SystemLab.L5X](../source/samples/SystemLab.L5X) and
[focused tests](../source/tests/test_gsv_this.py).

Installed v35 help14626 shows Program THIS, help14708 shows Task THIS, and
help5713 describes the separate AOI instance contract. These references do not
establish native timing, packed destination, fault/status/lifecycle or Studio
acceptance parity for this bounded software implementation.
