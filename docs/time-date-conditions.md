# Time/date ladder conditions

The bounded v35 ControlLogix 5580 software profile supports exact temporal tag/literal
relations in CMP and FSC. Existing temporal storage, direct comparisons and
standalone ADD/SUB retain their separate profiles.

| Family | Tag types | Stored tick | Comparison |
| --- | --- | --- | --- |
| Duration | TIME32, TIME | microsecond | Exact integer nanoseconds |
| Duration | LTIME | nanosecond | Exact integer nanoseconds |
| Timestamp | DT | microsecond | Exact integer nanoseconds |
| Timestamp | LDT | nanosecond | Exact integer nanoseconds |

All six relations are supported within one family. A TIME tag can compare with
LTIME, and DT with LDT. Negative durations preserve their sign; dates preserve
their absolute ticks. No float conversion or precision loss occurs. A single
condition may combine separate duration and timestamp comparisons using BOOL
tags, !/NOT and eager AND/OR/XOR or symbolic Boolean operators. BOOL ordering and
comparisons across timestamp/duration/numeric categories remain blocked.

```text
CMP((FineDuration>CoarseDuration)&&!Inhibited)OTE(Expired);
FSC(Find,?,?,ALL,(Times[Find.POS]>Threshold)&&(Codes[Find.POS]=ExpectedCode));
```

STRING and declared DINT LEN/SINT DATA strings retain case-sensitive lexical
relations over active bytes. LEN and active bytes must be known and valid;
unused bytes are not consumed. Both Boolean sides remain required even when one
already determines the result. Reached unknowns, bounds, invalid strings and
later faults roll back the modeled advance. False/prescan paths skip saved data
and live indices. Aliases, selected array elements, UDT members and qualified
AOI bindings keep their existing address rules. FSC retains ALL/numeric/INC,
first-match inhibit/resume, held/done skips and numeric false continuation.

The temporal expression profile requires at least one temporal tag or typed
temporal literal. Constant-only conditions are supported. Bare numeric constants
have no implicit time unit. Unsupported temporal operators, numeric mixtures,
ST/FBD/SFC execution, new controller profiles and native
numerical/status/fault/layout/lifecycle parity remain separate.

In **Wide expression lab**, set TemporalIndex=1 and TemporalEnabled=true.
TemporalDurationMatch, TemporalStampMatch and TemporalCombined become true:
1001 ns exceeds 1 us, and the LDT timestamp exceeds its DT counterpart by 1 ns.
TemporalLimits is a TIME array. The combined result also compares the shared
StringNumericCodes[1] and CODE_12 StringNumericNeedle. Set TemporalHighDuration
to 1000 ticks for equality, or TemporalHighStamp to 1767225600000001000 ticks
for timestamp equality. These are raw stored ticks at their declared precision.
TemporalIndex=99 or TemporalLateDivisor=0 demonstrates rollback. TemporalInhibit
clears all three results while retaining eager required operands.

The report exposes this scope at numeric_comparisons.time_date.conditions.
See [temporal storage](time-date-storage.md), [condition parser](../source/logixlab/conditions.py),
[temporal evaluator](../source/logixlab/time_values.py),
[FSC](../source/logixlab/file_search.py) and
[focused cases](../source/tests/test_time_conditions.py).

## Typed thresholds and dates

Qualified ladder CMP/FSC accepts T32#, T#, LT#, DT# and LDT# literals using the
existing bounded storage syntax. Prefixes and UTC are case-insensitive. Duration
components descend from days to nanoseconds; TIME32/TIME retain microsecond
precision and LTIME supports nanoseconds. Negative durations put the sign after
the prefix, for example LT#-1us_1ns. Existing declared ranges remain required.
Dates support fractional seconds, grouped fractions and explicit UTC offsets.

```text
CMP(FineDuration>T#1us)OTE(Expired);
CMP(Stamp>=DT#2026-01-01-08:00:00(UTC+08:00))OTE(AfterStart);
FSC(Find,?,?,ALL,(Times[Find.POS]>LT#1ns)&&(Codes[Find.POS]=ExpectedCode));
```

Every constant is checked at declared precision/range before conversion to exact
integer nanoseconds. UTC offsets are normalized by the existing date parser;
they do not change the emulator or host clock. Both operands can be constants.
Same-family relations and eager Boolean/string rules are unchanged. Invalid
constants block a routine even on false rungs. Generic, ST, index, CPT and FAL
parsers retain their separate defaults. Qualified CPT/FAL arithmetic is described
below. The lexer also opts in through their existing complete expression flags,
leaving consumer cache keys unchanged. No floating conversion is introduced.

In **Wide expression lab**, set TimeLiteralIndex=1 and TimeLiteralEnabled=true.
DurationMatch, StampMatch, ConstantMatch and Combined become true (all have the
TimeLiteral prefix). The routine reuses TemporalHighDuration/HighStamp/Limits and
StringNumericCodes/Needle. It demonstrates tag/constant, constant-only, UTC-offset,
cross-precision and selected string composition. Index99 or LateDivisor0 tests
rollback. Changing a shared time value or code is reflected on the next step.

## Temporal arithmetic and results

CPT/CMP/FAL/FSC support exact temporal + and - expressions, including typed
constants and duration unary signs. Allowed combinations are duration +/-
duration, date +/- duration, duration + date, and date - date. Two dates cannot
be added, and a date cannot be subtracted from a duration. Multiplication,
division, functions and numeric/time mixtures remain excluded.

Each temporal node uses exact integer nanoseconds within the existing canonical
LTIME duration or LDT timestamp range. This is an explicit software-model policy,
not native intermediate-width or status qualification. Timestamp differences
must fit the modeled duration range; dates cannot underflow the epoch. Comparisons
and eager BOOL/string composition consume the resulting families as before.

```text
CPT(Elapsed,StopStamp-StartStamp);
CPT(NextStamp,StartStamp+LT#1ms);
CMP((StopStamp-StartStamp)>T#1s)OTE(Expired);
FAL(Calc,?,?,ALL,Next[Calc.POS],Stamps[Calc.POS]+LT#1ns);
```

CPT/FAL destinations must be scalar TIME32/TIME/LTIME for durations or DT/LDT
for dates. The result must fit its declared range and exact stored tick precision;
fractional ticks are rejected rather than rounded. Complete writes establish
unknown destination cells. False/prescan and existing file modes retain lazy
reads. Unknowns, precision/range errors and later faults roll back the advance,
including earlier FAL cells and CONTROL progress. Earlier successful numeric/INC
advances stay committed. Temporal failures do not use FAL's REAL ER/prefix retry.

In **Wide expression lab**, set TemporalMathIndex=1 and TemporalMathEnabled=true.
Elapsed=1ns, Next=1767225600000001001ns, Total=2001ns, Negative=-1ns,
Selected[1]=2001ns and Match=true (all have TemporalMath prefix). The routine uses
shared TemporalHighStamp/Stamp/HighDuration. Enable TemporalMathCoarseEnabled
to demonstrate rejected fractional TIME ticks; change TemporalHighDuration to
1000ns to obtain an exact Coarse=2us. Index99 and LateDivisor0 demonstrate rollback.
The report exposes temporal_expressions. ST/FBD/SFC arithmetic and native
precision/status/fault/layout/lifecycle parity remain unqualified.
