# Time/date ladder conditions

The bounded v35 ControlLogix 5580 software profile supports tag-only temporal
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

The temporal expression profile requires at least one temporal tag. It adds no
literal syntax, temporal arithmetic in expressions, numeric mixtures, CPT/FAL
temporal results, ST/FBD/SFC execution, new controller profiles or native
numerical/status/fault/layout/lifecycle parity. Bare numeric constants have no
implicit time unit. Typed temporal literals remain available in the previously
supported standalone instructions, not inside this new condition grammar.

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
