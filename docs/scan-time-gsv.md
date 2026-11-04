# Program and Task scan-time GSV

The v35 ControlLogix 5580 project profile supports ladder and existing ST reads
of `LastScanTime` and `MaxScanTime` for eligible named Programs and Tasks.

```text
GSV(Program,MainProgram,LastScanTime,ProgramLast);
GSV(Program,MainProgram,MaxScanTime,ProgramMaximum);
GSV(Task,MainTask,LastScanTime,TaskLast);
GSV(Task,MainTask,MaxScanTime,TaskMaximum);
```

All four destinations are exact scalar DINT elements. Class, attribute and
literal instance names are case insensitive. [THIS](current-instance-gsv.md)
selects the current ordinary scheduled Program or its owner Task. Empty/numeric
instances and AOI/harness/Event THIS contexts remain unqualified. Existing configuration and
[wall-clock GSV](wall-clock-gsv.md) profiles remain separate.

## Measurement and visibility

Values come from the existing committed interpreter measurements using host
`perf_counter_ns`, in whole microseconds. They are initialized to zero before
the first successful advance. Reads within an advance see the preceding
committed timing snapshot. In particular, several periodic Program executions
in one advance do not publish intermediate timings to GSV. This model does not
establish native per-execution update ordering or predict hardware performance.

Program timing covers the completed main routine and its nested calls.
Whole-Task timing covers the complete scheduled interpreter execution in the
existing [single-Task measurement profile](task-runtime.md). Prescan and failed
advances do not commit new measurements. Maximum values retain the longest
successful execution since model reset. Existing counters and protocol reads
are unchanged by GSV observation.

DINT storage preserves the same 32-bit word as the protocol counter. A set
high bit appears negative in signed DINT storage; this is not a negative
elapsed duration. Existing unrepresentable counters remain unavailable rather
than wrapping or saturating. Task fields retain independent availability;
the existing Program timing record withholds both fields if its maximum cannot
fit the protocol word.

## Eligibility and operands

Program reads require complete current source, an ordinary scheduled Standard
Program, and project execution. Disabled, unscheduled, folder or ambiguous
Programs remain unavailable. The existing explicitly qualified no-main Program
profile retains its initialized zero values. Program reads work with supported
multiple-task scheduling.

Task reads retain the existing complete-source single Standard Continuous or
Periodic Task profile, including explicit priority, output-update/inhibit
settings, a known ordered Program schedule and current registry identity.
Multiple Tasks, Event/Safety forms and routine harnesses do not acquire whole-Task
measurements through this change. No source defaults fabricate availability.

Preflight validates destination type, shape, permissions and index grammar
without reading timing values or saved dynamic indices. False ladder rungs,
prescan and skipped ST branches retain outputs. Reached full writes can establish
unknown DINT cells. Aliases, Program-local scope and typed AOI InOut/local
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
faults atomically. Restore the index to 1 to recover. System lab has three Tasks,
so the separate whole-Task GSV forms above require a qualifying single-Task project.

The type/unit baseline follows installed v35 help 14638/14646 and Rockwell's
[Program object](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)
and [Task object](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
references. The installed version determines this profile. Timing setters,
other runtime attributes, broader source/language profiles and native precision,
status/fault, packed layout, scheduling and lifecycle parity remain separate work.
