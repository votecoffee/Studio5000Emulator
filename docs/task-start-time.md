# Task Start Time

Version `.140` adds read-only Task attribute 13 for the supported single
Standard Continuous/Periodic interpreter Task. The eight-byte little-endian
value is the simulator's WALLCLOCKTIME at the start of the last successful
execution, in UTC microseconds since 1970-01-01. It uses the same sampling
function as the [software Wall Clock Time](controller-schema-discovery.md#read-only-wall-clock-time)
CurrentValue reads. It never imports the original controller's timestamp.

## Execution and lifetime

The engine samples the clock once, before executing scheduled Programs. It
commits the timestamp alongside Task measurements only when the entire scan
succeeds. A failed scan preserves the previous successful timestamp and rolls
back values and timing state. Prescan does not record a Task execution.

Before the first successful execution, attribute 13 is unavailable. If a clock
sample fails, has the wrong type, is negative or exceeds the signed 64-bit
microsecond range, a successful scan still commits its independent monotonic
measurements, while Start Time becomes unavailable. A later valid scan restores
it. Host clock adjustments can move Start Time backward; monotonic scan durations
and intervals remain independent.

Reads return the committed timestamp, including repeated fields in one list;
they do not sample the clock again. Reset/import creates a fresh measurement
record. Supported Program-mode Routine replacement preserves the record until
the next execution. Existing complete-source, Task configuration, current
object and execution-mode guards apply. Native writes remain denied.

Endpoint state exposes Start Time availability, clock source and lifetime in
`task_measurements`. It does not expose monotonic start ticks or claim physical
scheduler accuracy. Task fields 22/23 retain their unavailable statuses.

## Contract and verification

The installed v35 Task-object help defines StartTime as WALLCLOCKTIME when the
last execution started, with the low 32 bits first. The Wall Clock Time help
defines CurrentValue as microseconds since 1970-01-01; the installed Task
attribute schema gives attribute 13 an eight-byte value. Legacy clock encoding
is not used for this Task field.

Focused checks cover epoch and exact wire encoding, no prescan/read sampling,
clock adjustments, failed-scan rollback, invalid samples, range boundaries,
reset, source/object guards, signed mixed reads and write denial. The supported
Routine replacement test retains a populated start timestamp.

The isolated SDK upload uses the saved/reopened empty-Program project and the
existing private clock/schema/empty-repository hypotheses. After one successful
scan, attribute 13 succeeds and only fields 22/23 are unavailable. Upload still
fails Task collection across 358 verified signed requests and 361 expanded
leaves. Actual Offline/cleanup, preserved originals/model and no fatal SDK fault
are confirmed. The private hypotheses remain excluded from the release.
Full native upload/download and the complete edit lifecycle remain unfinished.
