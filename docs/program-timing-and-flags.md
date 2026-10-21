# Program scan timing and source flags

Version `.119` adds read-only Program attributes to the native profile:

| Attribute | Value | Availability |
| --- | --- | --- |
| `2` Last Execution Time | DWORD, whole microseconds | Executable scheduled ordinary Programs in whole-project mode |
| `3` Maximum Execution Time | DWORD, whole microseconds | Same as `2` |
| `29` Synchronize Data | One byte, false `0`, true `1` | Explicit canonical `SynchronizeRedundancyDataAfterExecution` boolean |
| `31` Can Schedule | One byte, folder `0`, ordinary program `1` | Explicit canonical `UseAsFolder` boolean |

Program identity and the active source must match the native bindings. Single
and list reads share these values. Writes remain denied. Missing, malformed,
contextual, opaque or unsupported source flags remain unavailable; omitted
synchronization settings never acquire a default. Disable and scheduling
eligibility are separate: a disabled ordinary Program can still be schedulable.

The source flags follow the Program settings in Rockwell's
[Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf).
They report configuration; the emulator does not implement redundant controllers
or data crossloading. A Program used as a folder cannot execute through a Task
or the isolated routine harness. A Task that schedules a folder is blocked and
its native schedule/owner metadata is withheld. Logical children retain their
separate Task scheduling.

## Timing behavior

The emulator measures each scheduled main routine with the host monotonic
`perf_counter_ns` clock. Its measurement includes nested routine and AOI calls;
it excludes prescan, scan interval delays and the other Programs in the Task.
The last duration and maximum duration start at zero in a fresh engine. Each
successful whole-project scan commits new measurements for its Programs.
If any Program fails, all measurements for that scan roll back with the model.
Supported in-memory routine replacements preserve the committed timing history.
Reload/reset creates a fresh engine and clears that history.

The native fields convert nanoseconds to whole microseconds. A measurement
outside the DWORD range remains recorded internally but is unavailable over
the native interface; it never wraps or clamps. Routine harnesses, blocked,
disabled and unscheduled Programs do not provide whole-Program timing values.
The endpoint's `program_timing` summary identifies the measurement source and
successful execution count. Reading these values never advances the simulation.

These are host simulator durations, not estimates of ControlLogix hardware
performance. GSV/SSV timing instructions, timing setters and native Task scan
statistics are separate capabilities and are not added by this change.

## Native acceptance

Focused runtime and signed-wire checks cover measurement, rollback, source
flags and access boundaries. Full native upload/download and the complete
Test/Untest/Assemble edit lifecycle remain unfinished. SDK connection acceptance
does not establish Studio GUI acceptance or complete programming support.
