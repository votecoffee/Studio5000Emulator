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
entry under one Standard Continuous/Periodic Task. Reached calls also verify the
active execution Task matches that owner. Missing, ambiguous or changed context
fails instead of guessing a task from a saved value or the first configured row.

## Attribute and execution limits

Existing [configuration](gsv-configuration.md) and [timing](scan-time-gsv.md)
contracts still apply. Rate/Priority require a Periodic Task; configuration times
use microseconds and exact destination types. Program LastScanTime/MaxScanTime
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

THIS inside AOIs, Event tasks and isolated routine harnesses remains unqualified.
Empty/numeric instance aliases, broader SSV forms and current-instance setters
are unchanged. Existing named AOI reads retain their prior software profile.
No FBD/SFC, CPU-preemption or new controller-profile behavior is introduced.

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
