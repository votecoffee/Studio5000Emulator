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

[Typed bitwise/MEQ operands](typed-bitwise-operands.md) have a separate pattern
profile. [Wide integer SQR and XPY](math-operations.md#wide-integer-roots-and-powers)
check the computed result range. Basic arithmetic narrowing, non-covering
signed/unsigned mixtures, typed radix and other consumer profiles remain open. General memory literal parsing is unchanged. The source basis
is installed v35 Immediate values (14454), ADD (14623), EQU (14589), LIM (14610),
Data conversions (14451) and the existing integer arithmetic/ordering profiles.
These checks establish bounded software behavior, not native Studio acceptance.

See [integer execution](../source/logixlab/integer_math.py),
[arithmetic selection](../source/logixlab/scalar_math.py),
[comparisons](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_typed_integer_operands.py).
