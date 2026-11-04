# LREAL arithmetic result selection

App `26.1104.092011` extends standalone ladder ADD, SUB, MUL, DIV, MOD, NEG, ABS
and XPY in the v35 ControlLogix 5580 software profile. A scalar LREAL destination
selects finite binary64 inputs and calculation. Sources may be any of the ten
numeric tag types or signed DINT-range integer constants. Neither source needs
to be LREAL; constant-only calls also execute.

```text
ADD(DintInput,1,DoubleSum);
DIV(3,2,DoubleQuotient);
NEG(UnsignedInput,DoubleNegative);
ABS(-3,DoubleMagnitude);
XPY(IntegerBase,IntegerExponent,DoublePower);
```

All required inputs convert to binary64 before calculation, including division
and remainder. DIV(3,2,DoubleResult) produces 1.5. ADD(DINT 2147483647,1,DoubleResult)
produces 2147483648 without a DINT intermediate overflow. NEG/ABS likewise operate
on converted inputs; NEG(0,DoubleResult) retains a binary64 negative zero.

Tag sources can be SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL.
Signed values keep their numeric sign; unsigned values stay nonnegative. REAL
contributes its already stored float32 value. Integer constants must be from
-2147483648 through 2147483647 inclusive; existing radix syntax must also fit
that numeric range. Floating/typed/Boolean/larger constants remain excluded.

Large integer tags may round before the operation. For example, ULINT maximum
becomes binary64 2^64. MOD of that converted value by 3 is 1, while the exact
integer remainder of ULINT maximum by 3 is 0. This profile performs floating
calculations on promoted inputs; it does not preserve exact integer arithmetic
beyond binary64 precision. Integer-only comparisons keep their existing exact
rules; binary64 ordering still requires an actual LREAL input.

The existing finite solvers, dividend-sign remainder, power domains, signed zero,
subnormals and unknown/full-write rules remain. Zero divisors, complex-domain
powers, nonfinite results and later failures stop and roll back the advance.
Native numerical precision, math flags, overflow/minor-fault continuation and
lifecycle equivalence remain unverified.

Structural preflight checks declared types, scalar shapes, bounds, references
and permissions without saved values or live indices. False/prescan paths skip
live operands and calculations. True calls consume all required inputs, even
for zero products, unit bases or zero exponents. Full writes establish unknown
selected cells. Aliases, UDT members, overlapping results and existing AOI
bindings retain their rules. Rollback includes values, task progress/timing and
warm AOI local/external values and bindings. Run-entry prescan stays separate.

Open **Integer lab**, set DoubleResultsIndex to 1, enable DoubleResultsEnabled
and Step. The selected sum is 5; Sub=1, Mul=6, Div=1.5, Mod=1, Power=9, Neg=-3
and Abs=3. LiteralDivide=1.5 and LiteralPower=8 demonstrate constant-only calls.
Precision=16777218 avoids a REAL intermediate. WideRemainder=1 and WideNeg=-2^64
show documented promotion rounding. Neighboring guards remain 101.125 and 999.5.

The section starts disabled with index 99 dormant. DomainFault, ZeroFault and
OverflowFault demonstrate independent failures; LateDivisor=0 demonstrates a
later fault. Restore the switches to false and the divisor to 1. Disable the
section before returning its index to 99. Earlier Integer lab sections remain.

Other destination conversions, floating/typed/larger literals, bitwise forms,
broader CPT/CMP/ST expressions, new FBD/SFC forms and broader controller profiles
remain separate work. [Unary advanced math](lreal-unary-sources.md) already uses
its own LREAL-result selection. Comparison selection is unchanged.

The source basis is installed v35 ADD (14623), MOD (14620), XPY (14478) and Data
Conversions (14451). The published [Rockwell conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
provides related type-ranking context; these model checks do not establish
native instruction acceptance or numerical parity.

See [arithmetic implementation](../source/logixlab/scalar_math.py),
[power implementation](../source/logixlab/real_math.py),
[focused cases](../source/tests/test_lreal_destination_math.py) and
[IntegerLab.L5X](../source/samples/IntegerLab.L5X).

[REAL-result math](real-destination-math.md) additionally selects float32
inputs and result for arithmetic, XPY and eleven unary forms, across all nine
integer/REAL source types and bounded integer/finite floating constants.
LREAL result rules and other destination/consumer profiles remain separate.
