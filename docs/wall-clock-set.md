# Controller UTC setting

The Standard v35 ControlLogix 5580 software profile supports:

```text
SSV(WallClockTime,,CurrentValue,RequestedTime);
SSV(WallClockTime,,DateTime,Calendar[0]);
SSV(WallClockTime,,LocalDateTime,CalendarRecord.Year);
GSV(WallClockTime,,CurrentValue,Readback);
```

RequestedTime must be a scalar DT/LINT tag or the beginning of two contiguous
DINT cells, low word first. It is a read-only source: constant tags, aliases,
selected elements and existing AOI parameter bindings retain their permissions.
Immediate literals, whole DT/LINT arrays, bit selections, unsupported clock attributes
and other controller profiles remain outside this setting profile. Existing
ladder and ST SSV calls share the implementation.

Values are exact UTC microseconds since 1970-01-01. The accepted setting range
ends at 2068-12-29 23:59:59.999999 UTC, following installed v35 help 14645.
The larger DT storage range does not enlarge the clock-setting range.
Structural validation checks types, shape and references without sampling time
or reading live indices/values. False rungs, prescan and skipped ST branches
leave the clock unchanged. Reached instructions capture every source word
before calculating a setting; unknown or invalid values fault the advance.

## Calendar sources

DateTime accepts seven contiguous DINT cells, in year/month/day/hour/minute/
second/microsecond order. LocalDateTime uses the same fields only under the
existing explicit UTC local-time policy: complete source with one direct
WallClockTime element declaring TimeZone="0" and LocalTimeAdjustment="0".
DateTime always interprets its calendar as UTC. Workstation timezone and saved
extended DST values are not inferred. See [the read policy](wall-clock-gsv.md#local-time-policy).

Sources can be array windows or the first member of an explicit user record
whose first seven declared members are visible scalar DINTs. Declaration order
determines field order. Aliases, selected records/member arrays and existing AOI references
retain their normal contracts. Built-in DATETIMESTRUCT layout remains unqualified.
Every required field is captured before conversion; unused cells and guard
members remain untouched and may be unknown. Gregorian/leap-day, hour 0..23,
minute/second 0..59 and microsecond 0..999999 checks precede the common setting
range and update interval. Invalid dates do not roll over into the next month.
False/prescan skip data and live indices, but malformed schemas and references
still block. Unknown fields, invalid dates, range failures and later faults
discard the setting and retain its update admission history.

## Commit and readback

The instruction stages an adjustment to the emulator's host UTC source. Later
GSV calls, Generic MSG clock replies and alarm events in that advance use the
staged time. Successful completion commits the adjustment for subsequent GSV,
Wall Clock Time and Time Sync CIP reads, messaging and alarm timestamps.
A later fault restores tag values, task state and the previous clock setting.
External clock reads use committed state. Explicit ALMD ProgTime remains
independent of this adjustment.

The adjusted clock continues advancing with host UTC. This operation changes
emulator state; it does not set the workstation clock. Simulation milliseconds,
timers, task release schedules and the application-lifetime monotonic CST origin
retain their existing behavior. Task start measurements and fault timestamps
use the controller UTC source. The software CST offset continues to satisfy
CST + offset = UTC; setting a very early UTC value can give a negative software
offset, represented by its signed 64-bit words.

Accepted updates must be at least 15 seconds apart on the monotonic clock.
Advancing simulation time does not bypass this limit. A second request too soon
causes a modeled rollback error; a failed advance consumes no update interval.
This is the emulator's conservative handling of the documented update limit,
not a claim about native fault codes or partial effects.

## Lifetime and host UTC reset

The adjustment and last accepted update survive project replacement, reset,
scope changes and ordinary Program/Run transitions in the same application.
Restarting the application returns to its normal host UTC source.

HTTP state includes `wall_clock.source`, `adjustment_microseconds` and
`last_set_cst_microseconds`; integer counters use decimal text. A stopped,
non-importing application can return to host UTC with:

```text
POST /api/clock-configure
{"use_host_utc":true}
```

This clears the adjustment and update admission history. It retains tags, scan
counts, scheduling and the CST origin. Network clock-object setters remain
disabled. This profile does not implement PTP synchronization, remaining clock
attributes, timezone/DST configuration, hardware clock persistence
or native instruction/fault/lifecycle equivalence.

## System lab

Load **System lab**. ClockSetpoint starts at 1893456000000000, representing
2030-01-01 00:00:00 UTC. Set SetClock true and step. The instruction sets time,
captures ClockSetReadback and clears SetClock after successful execution.
Enable ReadClock on the next step to inspect the existing counter, calendar
and CST/offset examples under the new time.

ClockSetDivisor starts at one. Setting it to zero before SetClock demonstrates
rollback after the pending update and readback. Restore one and retry; the failed
attempt has not consumed the update interval. Use the stopped-controller reset
command above to return the application to host UTC when finished.

SetClockDateTime and SetClockLocalTime demonstrate the calendar forms. Their
shared ClockCalendarSetpoint[1..7] starts at 2032-02-29 12:34:56.123456 UTC;
elements 0 and 8 are guards. ClockCalendarIndex selects the first source field.
Each successful request writes ClockCalendarReadback and clears its own request.
Only request one setting at a time; all forms share the same 15-second interval.
They share ClockSetDivisor for fault/retry demonstrations. ReadClock on the next
step shows the new calendar. Return to host UTC with the stopped reset command
before trying another immediate independent setting.

The source basis is installed v35 help 14645 and Rockwell's
[WallClockTime object reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-wallclocktime-object.html).
The installed version determines this bounded profile. See the
[implementation](../source/logixlab/gsv_wall_clock.py),
[transaction boundary](../source/logixlab/runtime.py) and
[focused cases](../source/tests/test_ssv_wall_clock.py).
