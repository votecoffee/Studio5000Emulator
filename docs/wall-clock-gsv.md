# Wall-clock GSV reads

The v35 ControlLogix 5580 software profile lets ladder and existing ST GSV calls
read the emulator's host UTC clock. It shares the `WallClock` implementation
used by the CIP endpoint; separate calls have separate sampling times.

```text
GSV(WallClockTime,,CurrentValue,Timestamp);
GSV(WallClockTime,,CurrentValue,ClockDate);
GSV(WallClockTime,,CurrentValue,Words[0]);
GSV(WallClockTime,,DateTime,Calendar[0]);
GSV(WallClockTime,,LocalDateTime,LocalCalendar[0]);
```

Class and attribute lookup are case insensitive. The instance operand is empty.

| Attribute | Destination | Meaning |
| --- | --- | --- |
| CurrentValue | Scalar DT, scalar LINT or two contiguous DINT cells | UTC microseconds since 1970-01-01; DINT cells contain the signed low and high 32-bit words. |
| DateTime | Seven contiguous DINT cells or the first member of a [calendar record](#calendar-records) | UTC year, month, day, hour, minute, second and microsecond. |
| LocalDateTime | Same destination forms as DateTime | Same UTC calendar under the explicit local-time policy described below. |

Microseconds retain integer precision. DT checks the
[supported timestamp range](time-date-storage.md); calendar fields require a
timestamp that fits Python's calendar range. Time comes from host `time.time_ns`, independently of
simulated scan milliseconds. Pausing scans retains previously written tags; the
host clock keeps advancing. The [appliance launcher](vmware-appliance.md) seeds
UTC from Windows when it boots a new owned VM; that one-time whole-second
initialization is separate from this read-only GSV profile. Each reached GSV takes one sample. Multiple GSV/CIP
reads can differ and do not form one scan-wide snapshot.

## Coordinated system time

```text
GSV(CST,,CurrentValue,ClockCst);
GSV(CST,,CurrentValue,ClockCstWords[1]);
GSV(WallClockTime,,CSTOffset,ClockCstOffset[0]);
```

`CST.CurrentValue` reads elapsed microseconds from the application's
monotonic clock. Its origin survives project reload, reset and routine
scope changes. Direct engine use starts its own clock. Simulated scan
time and host UTC adjustments do not change the elapsed counter.

`WallClockTime.CSTOffset` uses the same counter as the
[EtherNet/IP offset](wall-clock-policy.md). It subtracts one elapsed sample
from one UTC sample. This read requires the explicit UTC local-time policy.
Calls take separate samples, so separate GSV results can differ by the time
between calls.

Both attributes accept a scalar TIME or two contiguous DINT or TIME32 cells.
The low word comes first. DINT pairs preserve all bits. The scalar TIME and
both TIME32 cells are checked against their normal duration ranges before
writing. Use a DINT pair for the UTC offset, which normally exceeds the
scalar TIME range. An invalid sample or destination range faults the
advance and restores both words.
[Rockwell CST reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/input-output-instructions/access-the-cst-object.html)

## Calendar records

Pass the first member of an explicitly declared user-defined record.
Its first seven members must be visible scalar DINTs, in the order
year, month, day, hour, minute, second and microsecond. The declaration
determines the assignment order. Field names can follow the project's
conventions. Members after the seven calendar fields retain their values.

```text
GSV(WallClockTime,,DateTime,ClockRecord.Year);
```

A supported record can be a scalar tag, a member, or a selected array
element. The destination can resolve through an alias. The whole write
is validated before the clock is sampled. The same layout works for
LocalDateTime under the policy below.
[Rockwell calendar UDT example](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf#page=61)

## Local-time policy

LocalDateTime requires the existing source-qualified UTC local policy: a complete
project with one unambiguous direct `WallClockTime` element containing explicit
`TimeZone="0"` and `LocalTimeAdjustment="0"`, under the existing import rules.
This selects emulator UTC with daylight saving disabled. The emulator does not
infer a workstation time zone or saved extended DST settings. CurrentValue and
DateTime remain available without that local-time declaration.

## Operand selection and rollback

Preflight checks the declared destination type, complete logical window, shape,
permissions and index grammar without reading live indices or sampling time.
False ladder rungs, prescan and skipped ST branches retain destinations. A
reached call resolves the whole destination window before sampling the clock.
Unknown complete DT/LINT/DINT cells can be established; surrounding cells remain
unchanged. Windows stay inside the selected logical scalar/member/array region.

Aliases, Program-local scope, indexed elements and existing typed AOI InOut/local
bindings retain normal memory rules. ST FOR validation protects every cell:
direct static windows have exact effects, while aliases/AOI/indirect references
conservatively protect their enclosing array. Some disjoint dynamic forms remain
blocked by this conservative policy.

An unavailable host clock, out-of-range DT, invalid calendar/index/window or later instruction
fault rolls back tag values, AOI bindings, trace, task scheduling and simulated
time for the whole advance. The host clock itself cannot be rolled back; retrying
reads the current time. No native fault/status record, packed layout, hardware
clock, task interruption or lifecycle equivalence is established by this model.

## System Lab

Choose **System lab** and step once. Enable `ReadClock`, then step to populate
`ClockMicros`, low/high `ClockWords[1..2]`, `ClockUtc[1..7]`, `ClockLocal[1..7]`,
`StClockMicros` and `StClockUtc`. The called **ReadClockValues** ladder routine
also writes the seven named members of `ClockRecord`. Its trailing
`Guard` stays at 999. The existing **ReadSettings** ST routine has gated
reads. The example explicitly selects the UTC-local policy. Array guard
cells stay 101/999. `ClockCst` and `ClockCstWords[1..2]` show elapsed
microseconds, and `ClockCstOffset[0..1]` holds the UTC offset. The
`ClockCstWords` guard cells retain 101 and 999.

Set `ClockIndex` to 99 while ReadClock is false to observe lazy retention. A
reached calendar read then faults and rolls back the advance. Restore the index
to 1 to recover. Calls may have slightly different microseconds. `ReadConfig`
also gates the existing call to ReadSettings, so it must stay true for ST reads.

Enable ReadTypedTimes and step to run **ReadTypedClock**. ClockDate holds
the live UTC timestamp in DT microseconds. MOV copies it to ClockDateNs
in LDT nanoseconds. TaskStartDate and the duration tags read the previous
committed [Task](task-start-gsv.md) and [Program](scan-time-gsv.md) measurements.

Installed v35 help 14645 and Rockwell's published
[WallClockTime object reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-wallclocktime-object.html)
define the counter/calendar formats. The installed version determines this
profile. Built-in DATETIMESTRUCT layout, other attributes, SSV clock setters,
non-UTC/DST policies, CST status, chassis synchronization and broader profiles remain separate.
