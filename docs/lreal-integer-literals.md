# Typed integer constants in LREAL ladder expressions

The bounded v35 ControlLogix 5580 CPT/CMP evaluator accepts decimal L/l, U/u
and UL/ul/Ul/uL integer constants when an LREAL source tag, floating literal or
CPT destination selects binary64 calculation. It checks the constant's LINT,
UDINT or ULINT range first, then converts it to binary64 just like an integer
tag. This extends the existing LREAL expression profile; it adds no parser mode.

```text
CPT(DoubleResult,9007199254740993L);
CPT(DoubleResult,3L/2U);
CPT(IntegerResult,3L/2U+0.0L);
CMP(9007199254740993L=9007199254740992L+0.0L)OTE(RoundedEqual);
```

## Selection and precision

The first example requires an LREAL destination. It stores 9007199254740992.0:
binary64 cannot distinguish every integer above 2^53. Conversion occurs at each
constant before arithmetic and comparison, so the last example is true. A typed
integer tag with the same declared value follows the same conversion rule.

The second example stores 1.5 in an LREAL destination. The third explicitly
selects LREAL with 0.0L and stores integer 2 under the existing nearest-even,
representable-result policy. All ten numeric destination types retain their
[checked conversions](lreal-results.md). Integer constants of different declared
types can mix with numeric tags under this binary64 profile.

| LREAL expression | Software result |
| --- | --- |
| 9007199254740993L-9007199254740992L | 0.0 |
| 18446744073709551615UL | 18446744073709551616.0 |
| -9223372036854775808L | -9223372036854775808.0 |
| 3L/2U | 1.5 |

Without an LREAL selector, typed constants retain the separate
[exact integer profile](ladder-integer-literals.md), including its matching-type
and intermediate range rules. Adding an integer suffix alone does not select
binary64. REAL destinations alone also do not select this profile.

## Range, execution and limits

Declared integer ranges are checked before floating conversion, including on
false rungs. A directly applied unary sign participates in the literal check;
parentheses around that literal are accepted. The LINT minimum is valid and
unsigned negative zero is zero. Out-of-range LINT/UDINT/ULINT values are rejected
even when their rounded binary64 representation would otherwise be finite.
Unsigned negative values remain invalid. Unsuffixed integers retain signed-DINT
limits; floating defaults and LREAL suffixes retain their existing rules.

Rounding a valid integer constant can make a later integer destination overflow:
the LINT maximum becomes 2^63 and the ULINT maximum becomes 2^64. Those rounded
values cannot be written back to their respective integer types. Conversely,
ABS of the LINT minimum is a valid finite LREAL value. These are binary64
intermediates followed by checked destination conversion.

The existing arithmetic, functions, powers, six relations and eager CMP Boolean
composition remain available. False calls skip domains, unknown values and live
indices; reached failures roll back the entire modeled advance, including warm
AOI copied outputs, InOut values, local state, scheduler/timing and trace.

Typed radix forms, separators and alternate typed spellings remain blocked.
[Ladder FAL](file-arithmetic.md#binary64-expressions) also accepts these
constants when an LREAL operand selects binary64. Numeric bitwise/BCD forms,
FSC, generic/index consumers, other controllers and additional languages
remain separate. ST retains its separate
integer literal behavior. Native numerical, status, fault, partial-write,
packed-layout and Studio/controller lifecycle equivalence remain unverified.

## Wide expression lab

Step Wide expression lab once, then enable FIntEnabled. DoubleIntegerConstants
contrasts rounded full-width constants with IntegerConstants, shows mixed-suffix
division and final integer conversion, and establishes one selected unknown
cell. FIntSelected becomes [9007199254740994.0, unknown, 903.0]. RangeFault and
DomainFault exercise independent failures; clear each flag to recover. Set
FIntIndex=1 and FIntLateDivisor=0 to check rollback, then restore the divisor to
1 to establish 9007199254740998.0. Disable FIntEnabled before leaving Index=999
dormant.

See the [sample](../source/samples/WideExpressionLab.L5X),
[evaluator](../source/logixlab/lreal_expressions.py) and
[tests](../source/tests/test_lreal_integer_literals.py). Source baseline:
installed v35 Immediate values (14454), Data conversions (14451), CPT (14597)
and CMP (14592). Rockwell's published
[immediate-value reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/immediate-values.html)
provides additional context; installed v35 definitions govern this bounded model.
