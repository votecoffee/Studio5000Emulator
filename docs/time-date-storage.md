# Ladder time and date storage

LogixLab models scalar time and date tags in Standard v35 ControlLogix 5580
projects (L81E through L85E). MOV accepts temporal tags and typed literals, CLR
writes zero ticks, and EQU, NEQ, LES, LEQ, GRT and GEQ compare time operands
within one family. ADD and SUB handle the duration and timestamp combinations
below.
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
decimal tick counts. The tag watch, change history, inspector and HTTP
state/snapshot use decimal text to preserve all digits. The ladder inspector
shows the exact parsed ticks and declared type for each valid time literal.
Enter a decimal tick count when editing from the browser. A matching typed literal is also accepted by the local write API.

## Exact mixed operands

MOV scales ticks within the duration family (TIME32, TIME, LTIME) or the
timestamp family (DT, LDT). A nanosecond-to-microsecond move requires an exact
multiple of 1000. Out-of-range or fractional results fault on a reached rung
and preserve the modeled advance. The exact-only rule is the emulator's
conversion policy.

A LINT tag can supply raw nanosecond ticks to LDT. An LDT tag or literal can
copy its ticks to LINT. No unit change occurs on this bridge, and LDT range
checks still apply. Installed v35 help 414477 documents LINT/LDT interoperability.
See [Rockwell's LINT and time guidance](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/time-and-date-data-types.html).

Comparisons within one family use exact nanoseconds, so a one-nanosecond
difference is visible even when the other operand is in microseconds.
Mixed timestamp/duration operands and LINT comparisons with time tags remain
outside this profile.

Preflight checks types, scalar shape, permissions, literal bounds and index
grammar. False rungs and prescan skip live values and indices. A complete MOV
or CLR can establish an unknown selected element. Reached unknown sources,
bad indices and later faults roll back the advance.

## Exact time arithmetic

ADD and SUB consume time tags or typed literals in the v35 5580 ladder profile.
They calculate in integer nanoseconds, then convert the result once to the
declared destination precision and check its range.

| Operation | Source types | Result type |
| --- | --- | --- |
| ADD or SUB | Two durations | Duration |
| ADD or SUB | One timestamp and one duration | Timestamp |
| SUB | Two timestamps | Signed elapsed duration |

SUB preserves source order. ADD of two timestamps is rejected. The
signed-duration result for two timestamps is the emulator's interpretation
of timestamp subtraction. An exact result can combine sub-microsecond sources
into a whole-microsecond value. Fractional destination ticks, a timestamp
outside the supported calendar range or a duration beyond its type range
fault and roll back the advance.

Structural validation checks both source types, scalar shape, destination
permissions and literal bounds. False rungs and prescan skip saved source
values and live indices. Reached operations can write unknown destinations
and preserve unwritten siblings. LINT remains available through the separate
MOV bridge. See installed v35 help 14623 (ADD), 14616 (SUB) and 414477 and
[Rockwell's time and date rules](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/time-and-date-data-types.html).

In **Data Lab**, enable TimeDateDemo and step. The TimeAndDate routine copies
a duration, writes date literals and compares timestamps one nanosecond apart.
LongStamp reads 1767225600000000001, EarlierNano is true, ShortDelay reads
-1501 and TimeToClear reads zero. ConvertedDuration reads 1250007000 and
DurationMatches is true. TimestampTicks and BridgedStamp retain the exact
LongStamp ticks. PromotedWallStamp reads 1767225600000001000. DurationTotal
reads 1248506 microseconds and DurationDelta reads -749993 microseconds.
NextStamp is one nanosecond after WallStamp, and NanoDelta reads 1.

Lossy conversion, clock attributes, ST, native packed
layouts and CIP time/date access remain separate. Native Studio/controller
acceptance is unverified.
