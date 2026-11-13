# Typed integer constants in LREAL ladder expressions

The bounded v35 ControlLogix 5580 CPT/CMP evaluator accepts decimal/radix L/l, U/u
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

Radix forms have the separate qualification below. Other separators and
alternate typed spellings remain blocked.
[Ladder FAL](file-arithmetic.md#binary64-expressions) and
[FSC](file-search.md#binary64-searches) also accept these constants when an
LREAL operand selects binary64. Numeric bitwise/BCD forms, generic/index
consumers, other controllers and additional languages remain separate. ST retains its separate
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

## Radix constants

The explicit LREAL CPT/CMP/FAL/FSC profile now admits `2#`, `8#` and `16#`
integer words. An unsuffixed word uses 32-bit signed DINT storage; attached
case-insensitive L/U/UL suffixes select LINT/UDINT/ULINT storage. The existing
radix parser zero-fills missing bits, decodes the declared sign bit, and checks
word width and digits before execution. Typed interior digit groups retain their
existing underscore/space syntax. Default, ST and index parsers do not expand.

Integer words follow the same declared-range and direct-unary checks as decimal
constants, then convert to binary64. Thus `16#FFFFFFFF` and
`16#FFFFFFFFFFFFFFFFL` become -1.0; `16#FFFFFFFFL` is positive 4294967295.0;
`16#FFFFFFFFFFFFFFFFUL` rounds to 18446744073709551616.0. Rounding occurs before
arithmetic/comparison and can make a later integer result overflow.

```text
CPT(DoubleResult,16#0020000000000001L);
CPT(DoubleResult,16#3L/2#10U);
CMP(16#0020000000000001L=9007199254740992L+0.0L)OTE(RoundedEqual);
FAL(Calc,?,?,ALL,Output[Calc.POS],16#FFFFFFFFU+0.0L);
FSC(Find,?,?,ALL,DoubleInput[Find.POS]>=16#0020000000000001L);
```

The first two examples need an LREAL destination. The third explicitly selects
binary64 with 0.0L; the fourth does likewise for any qualified numeric result.
In the last, DoubleInput is LREAL. A tag, floating L/l literal or CPT/FAL LREAL
destination still selects this profile. Integer suffixes alone keep exact integer
evaluation; REAL-only contexts retain their previous guards. A signed DINT word
may now promote when an LREAL selector is present.

Existing arithmetic/functions/powers, eager BOOL composition, false/prescan lazy
reads, file progress/retry, full unknown writes and whole-advance rollback remain.
Invalid digits/widths, excluded unary ranges, permissions, unknowns, conversion
overflow and domain failures retain their existing checks. Numeric bitwise,
FRD/TOD, other consumers/languages and native precision/status parity remain separate.

In **Wide expression lab**, set BinaryRadixIndex=1 and BinaryRadixEnabled=true.
Value=9007199254740992, Unsigned=18446744073709551616,
Signed=-9223372036854775808, Dint=-1, Rounded=0 and Mixed=2.5. Match is true;
Selected[1]=4294967296, with guards 101/999. Source=2 changes Mixed to 3.5
and Selected[1] to 4294967297. The gate starts false with index99 dormant.
LateDivisor=0 demonstrates rollback; restore 1 and retry.

The report exposes `lreal_expression_execution.radix_literals`. Source basis: installed
v35 Immediate values 14454 and CPT/CMP/FAL/FSC tables 14597/14592/14504/14515.
See [focused checks](../source/tests/test_lreal_radix_expressions.py).
