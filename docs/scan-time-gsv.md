# Program and Task scan-time GSV

The v35 ControlLogix 5580 project profile supports ladder and existing ST reads
of `LastScanTime` and `MaxScanTime` for eligible named Programs and Tasks.

```text
GSV(Program,MainProgram,LastScanTime,ProgramLast);
GSV(Program,MainProgram,MaxScanTime,ProgramMaximum);
GSV(Task,MainTask,LastScanTime,TaskLast);
GSV(Task,MainTask,MaxScanTime,TaskMaximum);
```

All four destinations accept scalar DINT or TIME32 elements. Class, attribute and
literal instance names are case insensitive. [THIS](current-instance-gsv.md)
selects the current ordinary scheduled Program or its owner Task. Empty/numeric
instances and AOI/harness/Event THIS contexts remain unqualified. Existing configuration and
[wall-clock GSV](wall-clock-gsv.md) profiles remain separate.

[Task start and interval GSV](task-start-gsv.md) also reads committed Task
StartTime, MinimumInterval and MaximumInterval through scalar DT/TIME tags or complete 64-bit word windows.

## Measurement and visibility

Values come from the existing committed interpreter measurements using host
`perf_counter_ns`, in whole microseconds. They are initialized to zero before
the first successful advance. Reads within an advance see the preceding
committed timing snapshot. In particular, several periodic Program executions
in one advance do not publish intermediate timings to GSV. This model does not
establish native per-execution update ordering or predict hardware performance.

Program timing covers the completed main routine and its nested calls.
The established [single-Task measurement profile](task-runtime.md) is retained.
In projects with multiple tasks, each eligible Continuous/Periodic invocation
measures its own completed body, including nested calls and synchronously
dispatched Event work. Several releases of a periodic Task in one advance update
its pending last/maximum durations independently. GSV observes the prior committed
advance throughout that batch. Unreleased or runtime-inhibited tasks retain their
measurements. Run entry retains committed values; reset/reload initializes them.
Prescan and failed
advances do not commit new measurements. Maximum values retain the longest
successful execution since model reset. Existing counters and protocol reads
are unchanged by GSV observation.

DINT storage preserves the same 32-bit word as the protocol counter. A set
high bit appears negative in signed DINT storage; this is not a negative
elapsed duration. TIME32 writes check the signed duration range using the
unsigned elapsed microseconds. An out-of-range TIME32 value faults. Existing
unrepresentable protocol counters remain unavailable. Task fields retain independent availability;
the existing Program timing record withholds both fields if its maximum cannot
fit the protocol word.

## Eligibility and operands

Program reads require complete current source, an ordinary scheduled Standard
Program, and project execution. Disabled, unscheduled, folder or ambiguous
Programs remain unavailable. The existing explicitly qualified no-main Program
profile retains its initialized zero values. Program reads work with supported
multiple-task scheduling.

Task reads require complete current source, Standard Continuous/Periodic or
[qualified instruction-only Event Tasks](event-task-timing.md),
explicit priority/output-update/inhibit settings and a known ordered Program
schedule. Initially inhibited Continuous/Periodic Tasks remain outside their
existing measurement profile; initially inhibited qualified Events have zero
measurements until enabled and executed. A runtime-inhibited eligible Task
retains readable committed values. The existing single-Task native registry
requirement is retained for Continuous/Periodic measurement. Safety, other
Event sources/timeouts and routine harnesses remain unqualified. No source
defaults fabricate availability.

Multi-task and Event measurements are logical GSV data. They add no native Task identity,
protocol timing/status attribute, watchdog enforcement or controller CPU model.
The coverage report exposes per-task microseconds and successful invocation
counts under task_scan_timing; native_protocol_expanded remains false.
Routine replacement deep-copies this state into its detached candidate.

Preflight validates destination type, shape, permissions and index grammar
without reading timing values or saved dynamic indices. False ladder rungs,
prescan and skipped ST branches retain outputs. Reached full writes can establish
unknown DINT or TIME32 cells. Aliases, Program-local scope and typed AOI InOut/local
operands use normal memory rules. ST FOR checks protect exact static cells and
conservatively cover the enclosing array for alias/AOI/indirect destinations.

Unavailable measurements, invalid selected indices and later faults roll back
tag values, AOI bindings, trace, scheduling and uncommitted measurements for the
whole advance. Invalid named main entries produce explicit blockers. Changing a file
on disk does not replace the loaded source snapshot.

## System Lab

Choose **System lab** and step once to generate measurements. Enable `ReadTiming`
and step again. The called **ReadProgramTimes** ladder routine reads the
Background, Fast and Slow Program timings. `TimingWords[TimingIndex]` contains
Background LastScanTime; `ProgramMax` is its maximum. FastLast/FastMax and
SlowLast/SlowMax show the other Programs. Existing **ReadSettings** ST calls
populate StProgramLast/StProgramMax when ReadConfig and ReadTiming are true.
Ladder and ST values for the same Program use the same committed snapshot.

TimingIndex starts at 1; neighboring cells remain 101, 77 and 999. Set ReadTiming
false to retain outputs. A dormant index99 is skipped; a reached invalid index
faults atomically. Restore the index to 1 to recover.

Enable ReadTaskTiming with TaskTimingIndex=1 to read all three whole-Task
last/maximum values in the called ReadTaskTimes routine. TaskWords[1] is the
background last duration; guards101/77/999 remain. TaskTimingIndex starts99 and
is dormant while disabled. StBackgroundTaskLast/StFastTaskLast/StSlowTaskLast
match the ladder values when the existing ReadConfig gate is enabled. Each
Program also reads Task THIS LastScanTime; with25ms advances these match the
named values. ControlTasks and TaskInhibitCommand can inhibit FastTask; its
last/maximum durations retain while other tasks continue. Re-enable at the
existing phase without catch-up. Disable ReadTaskTiming to retain outputs.

Enable ReadTypedTimes and step to read the previous Background Program
last duration into ProgramTime32 and its owner Task maximum into TaskTime32.

The type/unit baseline follows installed v35 help 14638/14646 and Rockwell's
[Program object](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)
and [Task object](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
references. The installed version determines this profile. Timing setters,
other runtime attributes, broader source/language profiles and native precision,
status/fault, packed layout, scheduling and lifecycle parity remain separate work.
