# Constants in LREAL ladder comparisons

The bounded v35 ControlLogix 5580 ladder profile supports constants in EQU,
NEQ, LES, LEQ, GRT, GEQ and LIM when a declared LREAL tag or floating L/l
constant selects binary64 comparison. The constant can select this profile
without an LREAL tag, including constant-only calls. Existing integer-only and
REAL-only comparison profiles retain their scope.

```text
EQU(DoubleValue,0.1L)OTE(Equal);
GRT(RealValue,0.1L)OTE(AboveDoubleThreshold);
LIM(0U,DoubleValue,1.0L)OTE(InRange);
LIM(0.0L,0.5L,1.0L)OTE(ConstantInRange);
```

Selected comparisons accept all ten numeric tag types, bounded DINT integers,
finite REAL floating constants, decimal L/l (LINT), U/u (UDINT), UL/ul/Ul/uL
(ULINT) integers and finite floating L/l (LREAL) constants. Both relation operands
and all three LIM operands follow the same rules. Typed integer constants alone
keep integer calculation under the separate [exact integer profile](typed-integer-operands.md).

Each source is checked at its declared range and precision before promotion.
Unsuffixed 0.1 contributes the REAL-rounded value 0.10000000149011612; 0.1L
contributes binary64 0.1. Consequently an LREAL tag holding 0.1 equals 0.1L and
differs from unsuffixed 0.1. A REAL tag holding 0.1 is greater than 0.1L after
promotion. Comparisons use no tolerance. Unsuffixed floating constants must fit
finite REAL, and their underflow occurs before promotion. Typed LREAL constants
retain representable large/subnormal values; positive and negative zero compare
equal.

Large integers can round during promotion. LINT 9007199254740993 compares equal
to 9007199254740992.0L because both become binary64 9007199254740992. Existing
integer-only tag comparisons retain exact ordering. Typed integer bounds are
checked before conversion. Binary, octal and hexadecimal words follow the
[declared-width radix rules](#radix-integer-thresholds);
[MOV radix patterns](radix-mov-literals.md) remain separate.

LIM includes both endpoints. When low is greater than high after promotion, it
accepts values at or outside the endpoints. Bounds can collapse after rounding;
the test uses the promoted values. Every required operand is consumed when
reached, including unknown values in a zero-width interval. Source tags remain
read-only; downstream ladder coils retain their normal behavior.

Structural preflight checks types, shapes, permissions and immediate ranges
without saved values or live indirect indices. False rungs and prescan skip
those values; downstream OTEs still clear as usual. Aliases, member arrays and
existing copied AOI input, InOut and local readers use canonical storage. Unknown
sources, bad indices and later faults roll back the whole advance, including
coils, task timing, traces and AOI bindings. Required copied AOI inputs retain
their own call-entry rules.

Load **Wide expression lab**, enable CompareLitEnabled and step to run
**ComparisonConstants**. It contrasts REAL/LREAL thresholds, wide integer
rounding, ordinary/reversed limits and constant-only selection. CompareLitInputs[1]
starts unknown; selecting it demonstrates rollback. Establish its value before
retrying. CompareLitLateDivisor=0 demonstrates a later fault after coil writes.

MEQ, typed integer-only forms, REAL-only radix forms, string/time comparisons, other
consumer/controller/firmware profiles and native numerical/status/fault/lifecycle
parity remain separate. No new ST/FBD forms are enabled. The source basis is
installed v35 EQU (14589), LIM (14610), Immediate values (14454), Data conversions
(14451) and the existing numeric comparison profile. These tests establish bounded
software behavior, not native Studio/controller acceptance.

See [implementation](../source/logixlab/comparisons.py),
[source precision](../source/logixlab/numeric_storage.py) and
[focused cases](../source/tests/test_lreal_comparison_literals.py).

## Radix integer thresholds

Explicit binary64 EQU, NEQ, LES, LEQ, GRT, GEQ and LIM accept base-2, base-8
and base-16 integer words. A declared LREAL tag or floating L/l literal must
select the profile. An integer suffix alone retains the exact integer profile.
Every required word is decoded as DINT (no suffix), LINT (L), UDINT (U) or
ULINT (UL) before conversion to binary64. This preserves declared sign and
width: 16#FFFFFFFF becomes -1.0, 16#FFFFFFFFL becomes 4294967295.0, and
16#FFFFFFFFFFFFFFFFUL rounds to binary64 18446744073709551616.

```text
EQU(DoubleValue,16#FFFFFFFF)OTE(MatchesSignedWord);
EQU(16#0020000000000001L,9007199254740992.0L)OTE(RoundedEqual);
LIM(16#FFFFFFFF,DoubleValue,2#1U)OTE(InSignedRange);
LIM(16#2L,0.5L,8#0UL)OTE(OutsideReversedRange);
```

Both relation positions and all three LIM positions use the same conversion.
Normal, reversed and collapsed limits operate on promoted values. Every
required source is still read on a reached call, even when an earlier bound
already determines the result. False rungs and prescan skip live unknowns and
bad indirect indices; output coils retain normal false cleanup. Known source
members, aliases and AOI Inputs/InOut/local tags remain read-only, and faults
restore earlier coils and state under the existing whole-advance policy.

Malformed/overwide words, negative-prefix radix text, expressions in scalar
operands, BOOL/aggregate inputs and unsupported controller profiles still block
preflight. Default conversion helpers, REAL-only comparisons and MEQ retain
their separate profiles. No ST/FBD forms or native acceptance are implied.

In **Wide expression lab**, enable RadixCompareEnabled to run
**RadixComparisons**. Select index 1 to demonstrate an unknown source fault,
then write RadixCompareInputs[1]=-1 to repair it. Index 99 or
RadixCompareLateDivisor=0 demonstrates rollback; disabling the gate clears the
coils without consuming those invalid values. See the
[radix cases](../source/tests/test_lreal_comparison_radix.py).
