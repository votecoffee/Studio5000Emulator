# Ladder time and date storage

LogixLab models scalar time and date tags in Standard v35 ControlLogix 5580
projects (L81E through L85E). MOV copies a matching tag or typed literal, CLR
writes zero ticks, and EQU, NEQ, LES, LEQ, GRT and GEQ compare matching types.
The operations also work on selected array elements, explicit UDT members and
aliases. A zero date represents the UTC epoch.

| Type | Storage unit | Literal example |
| --- | --- | --- |
| TIME32 | Microseconds, 32-bit duration | T32#-1ms_501us |
| TIME | Microseconds, 64-bit duration | T#1s_250ms_7us |
| LTIME | Nanoseconds, 64-bit duration | LT#1s_42ns |
| DT | Microseconds from the UTC epoch | DT#2026-01-01-00:00:00.000_001 |
| LDT | Nanoseconds from the UTC epoch | LDT#2026-01-01-00:00:00.000_000_001 |

Duration components use underscores and descending units. TIME32 accepts
±2,147,483,647 microseconds. TIME and LTIME accept signed durations through
31 days, 12 hours, 59 minutes and 59 seconds plus the maximum fractional
second for the type. DT and LDT accept UTC times from January 1, 1970 through
the end of December 31, 2250, at their respective precision. Date literals
without an offset use UTC in the emulator. An explicit (UTC+HH:MM) or
(UTC-HH:MM) offset converts to UTC before the range check. See installed
Logix Designer v35 help 414477 and 14452 and
[Rockwell's time and date type reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/time-and-date-data-types.html).

Decorated L5X scalar and array values accept matching typed literals or
decimal tick counts. The tag watch, change history and HTTP state/snapshot use decimal text
to preserve all digits. Enter a decimal tick count when editing from the
browser. A matching typed literal is also accepted by the local write API.

Preflight checks types, scalar shape, permissions, literal bounds and index
grammar. False rungs and prescan skip live values and indices. A complete MOV
or CLR can establish an unknown selected element. Reached unknown sources,
bad indices and later faults roll back the advance.

In **Data Lab**, enable TimeDateDemo and step. The TimeAndDate routine copies
a duration, writes date literals and compares timestamps one nanosecond apart.
LongStamp reads 1767225600000000001, EarlierNano is true, ShortDelay reads
-1501 and TimeToClear reads zero.

Mixed-type conversion, time arithmetic, clock attributes, ST, native packed
layouts and CIP time/date access remain separate. Native Studio/controller
acceptance is unverified.
