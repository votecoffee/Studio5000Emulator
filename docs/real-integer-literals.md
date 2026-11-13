# Typed integer constants in REAL ladder operations

The bounded v35 ControlLogix 5580 profile accepts decimal L/l (LINT), U/u (UDINT)
and UL/ul/Ul/uL (ULINT) integer constants in these selected ladder operations:

| Selection | Instructions |
| --- | --- |
| Scalar REAL result | ADD, SUB, MUL, DIV, MOD, NEG, ABS, XPY, SQR, LN, LOG, DEG, RAD, SIN, COS, TAN, ASN, ACS, ATN |
| At least one actual REAL source tag, with no LREAL selection | EQU, NEQ, LES, LEQ, GRT, GEQ, LIM |

Both binary math/comparison operands and all three LIM operands support the
same constant forms. Existing bounded DINT and finite REAL constants retain
their rules. Constant-only math calls can select REAL through their destination;
typed integer constants alone use the separate [exact integer profile](typed-integer-operands.md).

```text
ADD(16777217U,1L,RealSum);
SQR(16777217UL,RealRoot);
DIV(3L,2U,RealQuotient);
EQU(RealValue,16777217U)OTE(EqualAfterPromotion);
LIM(16777216L,RealValue,16777217UL)OTE(InPromotedRange);
```

The declared integer source range is checked before the existing finite float32
conversion. An invalid UDINT/ULINT/LINT constant remains blocked even on a false
rung. Valid constants follow the same path as a tag of that declared type.
Integer narrowing or wrapping is not used to repair an invalid constant.

Sources round to REAL before calculation or comparison. Therefore ADD(16777217U,
1L) produces REAL 16777216.0, SQR(16777217U) produces 4096.0 and a REAL tag holding
16777216 compares equal to 16777217U. ULINT maximum rounds to REAL 2^64; its REAL
MOD by 3 is 1. DIV(3L,2U) produces REAL 1.5. Math results also round to REAL.
These forms retain the existing host float32 conversion/solver profile, not a
native numerical bit-parity guarantee.

[LREAL comparison selection](lreal-comparison-literals.md) retains priority:
an actual LREAL tag or floating L/l constant selects binary64. A REAL tag holding
16777216 compares less than 16777217.0L. The [LREAL input profile](lreal-math-literals.md#real-and-integer-results)
also takes priority in REAL-result math. Existing exact integer-only comparison rules remain.

Structural preflight checks types, scalar shapes, permissions and immediate
ranges without saved values or live indices. False/prescan paths skip those
values; downstream OTEs clear normally. Reached calls consume all required
sources, including zero products and zero-width limits. Full math writes can
establish unknown elements, while comparisons leave sources unchanged. Aliases,
member arrays and existing copied AOI inputs, InOuts and locals keep canonical
storage. Domain/range errors, zero divisors, unknowns, invalid indices and later
faults roll back the full advance, including task timing, traces and AOI bindings.

Load **Wide expression lab**, enable RealIntEnabled and step to run
**RealIntegerConstants**. It demonstrates pre-calculation rounding, root,
remainder, fractional division, typed thresholds and collapsed limits.
RealIntSelected retains an unknown neighbor and a 903.25 guard. RangeFault and
a zero LateDivisor demonstrate separate atomic fault/retry paths.

Other integer-result, bitwise, MEQ, expression/file/ST/FBD and
controller/firmware profiles remain separate. Selected REAL forms also admit
[declared-width radix sources](real-radix-math.md); [MOV radix patterns](radix-mov-literals.md) retain
their separate contract. Native numerical/status/minor-fault/lifecycle parity
remains unverified. The source basis is installed v35 Immediate values (14454),
ADD (14623), XPY (14478), EQU (14589), LIM (14610), Data conversions (14451) and
the existing REAL-result/REAL-comparison profiles.

See [source conversion](../source/logixlab/numeric_storage.py),
[math](../source/logixlab/scalar_math.py), [advanced math](../source/logixlab/real_math.py),
[comparisons](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_real_integer_literals.py).
