# Typed integer operands

The bounded v35 ControlLogix 5580 ladder profile accepts decimal L/l (LINT),
U/u (UDINT) and UL/ul/Ul/uL (ULINT) constants in ADD, SUB, MUL, DIV, MOD, NEG,
ABS, EQU, NEQ, LES, LEQ, GRT, GEQ and LIM under the existing range-preserving
integer rules. Constant-only calls are supported. No floating conversion is
used for these selected integer operations.

```text
ADD(9007199254740993L,1L,SignedResult);
DIV(18446744073709551615UL,3UL,UnsignedQuotient);
GRT(9007199254740993L,9007199254740992L)OTE(ExactGreater);
LIM(0UL,UnsignedValue,18446744073709551615UL)OTE(InRange);
```

Each typed constant is checked at its declared source range. Arithmetic requires
an integer result type that covers the complete range of every source tag and
typed constant. Thus a DINT tag plus 1L can use a LINT result; a LINT source plus
1UL cannot use a ULINT result because ULINT does not cover negative LINT values.
A small current tag or constant value does not justify that conversion.

Comparisons select the highest-ranked actual source tag or typed constant type
in SINT, USINT, INT, UINT, DINT, UDINT, LINT, ULINT order. That type must cover
every complete declared source range; no larger type is invented. A UDINT tag
can compare with a LINT constant, while LINT/ULINT mixtures remain blocked.
Existing unsuffixed DINT-range constants must fit the selected integer type.
REAL/LREAL comparison priority retains its [existing profiles](numeric-comparisons.md).

Calculation stays exact beyond 2^53. DIV of ULINT maximum by 3 returns
6148914691236517205, and MOD returns zero. Signed division truncates toward zero;
remainder has the dividend's sign. Results must fit their declared destination.
Overflow and zero divisors fault and roll back the modeled advance. Native
math flags, minor-fault continuation and partial effects remain unverified.

Both binary positions and all three LIM positions support typed constants.
LIM includes endpoints and accepts values at or outside reversed endpoints.
Sources remain read-only; complete arithmetic writes can establish unknown
elements and preserve untouched neighbors. Structural preflight checks type,
shape, permissions and immediate ranges without saved values or live indices.
False/prescan paths skip those values; downstream OTEs still clear. Reached calls
consume all required operands, including zero products and zero-width limits.
Aliases, member arrays and existing copied AOI inputs/outputs, InOuts and locals
keep canonical storage and transaction-wide rollback, including timing and bindings.

Load **Wide expression lab**, enable TypedIntEnabled and step to run
**IntegerOperandConstants**. It demonstrates exact sums, ULINT division/remainder,
UDINT maximum, mixed safe signed arithmetic and ordering beyond binary64
precision. TypedIntSelected retains an unknown neighbor and a 903 guard.
Overflow and a zero LateDivisor demonstrate separate atomic fault/retry paths.

## Typed radix integer operands

App `26.1113.002036` accepts attached binary/octal/hexadecimal L/U/UL constants
in ADD, SUB, MUL, DIV, MOD, NEG, ABS, EQU, NEQ, LES, LEQ, GRT, GEQ and LIM.
A typed radix selects an **integer-only** call. Source bit patterns use LINT64,
UDINT32 or ULINT64 before exact arithmetic or numeric ordering. Short patterns
zero-fill to that width; the LINT top bit represents a negative value.

```text
ADD(16#0020_0000_0000_0001L,1L,ExactSum);
DIV(16#FFFF_FFFF_FFFF_FFFFUL,3UL,ExactQuotient);
LES(16#FFFF_FFFF_FFFF_FFFFL,0L)OTE(Negative);
LIM(16#8000000000000000L,Count,16#7FFFFFFFFFFFFFFFL)OTE(InRange);
```

The existing complete-source-range rules apply. Arithmetic destinations must
cover every declared source range; comparisons select the highest-ranked
actual tag or typed constant type, which must cover every source range.
No saved value justifies narrowing or signed-to-unsigned promotion. Decimal
typed values and bounded DINT constants can accompany the radix sources.
Full 64-bit all-ones L is numerically -1; UL is unsigned maximum. Unlike bitwise
masks, numeric operations preserve those signs and enforce arithmetic ranges.

DIV/MOD stay exact above 2^53, using quotient truncation toward zero and a
dividend-sign remainder. Reached zero divisors/result overflow roll back the
entire advance. Invalid/overwide words block even false rungs. False/prescan
skip live values/indices; true calls consume required unknowns even under zero
products or coincident limits. Aliases, AOI bindings and complete writes retain
their existing contracts. The viewer preserves authored spelling, declared
literal type and exact decimal values only for these operand positions.

REAL/LREAL or time/date sources/results combined with typed radix remain
excluded. Existing decimal floating priority is unchanged. [Radix BCD sources](numeric-conversions.md#typed-radix-bcd-sources)
have a separate ladder profile. Advanced math, expressions/file/ST, AOI call
arguments and SBR/RET parsing are not extended.
This is bounded software execution; native import, numerical/status/fault and
controller lifecycle equivalence remain unverified.

In **Wide expression lab**, enable TypedIntEnabled. IntegerOperandConstants
uses all three bases while retaining its prior exact sums, quotient, remainder,
limits and guarded writes. Additional TypedRadixProduct/Negative/Absolute values
are -4, -2 and 2. TypedIntOverflow and TypedIntLateDivisor demonstrate rollback
after the radix calculations; clear the overflow gate or restore the divisor
to one to retry.

[Typed bitwise/MEQ operands](typed-bitwise-operands.md) have a separate pattern
profile. [Wide integer SQR and XPY](math-operations.md#wide-integer-roots-and-powers)
check the computed result range. Basic arithmetic narrowing, non-covering
signed/unsigned mixtures, floating radix mixes and other consumer profiles remain open. General memory literal parsing is unchanged. The source basis
is installed v35 Immediate values (14454), ADD (14623), EQU (14589), LIM (14610),
Data conversions (14451) and the existing integer arithmetic/ordering profiles.
These checks establish bounded software behavior, not native Studio acceptance.

See [integer execution](../source/logixlab/integer_math.py),
[arithmetic selection](../source/logixlab/scalar_math.py),
[comparisons](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_typed_integer_operands.py).
