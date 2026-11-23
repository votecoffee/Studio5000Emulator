# Mixed numeric LREAL powers

App `26.1104.083644` extends standalone ladder XPY in the v35 ControlLogix 5580
software profile. Both sources may be scalar numeric tags with a LREAL destination. The other tag may be SINT, INT, DINT,
LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL. Either source may instead be a
signed DINT-range integer constant. [Result-selected math](lreal-destination-math.md)
additionally covers calls without a LREAL input and constant-only powers.

```text
XPY(DoubleBase,DintExponent,DoubleResult);
XPY(DintBase,DoubleExponent,DoubleResult);
XPY(DoubleBase,2,DoubleSquare);
XPY(2,DoubleExponent,DoubleResult);
```

Every required source is read. Finite sources are converted to binary64 before
the host real-valued power operation. Integer signs and unsigned numeric values are
preserved. REAL contributes its already stored float32 value. Integer constants
between -2147483648 and 2147483647 inclusive promote exactly.
[Typed and floating literals](lreal-math-literals.md) use their declared ranges
and precision. A LREAL destination selects this profile even without a LREAL
source, including constant-only calls.

DINT 16777217 squared with a LREAL exponent produces 281475010265089. A REAL
source assigned 16777217 first stores 16777216, so its square is
281474976710656. LREAL 1.0000000000000002 squared retains 1.0000000000000004.
Wide integers can round during promotion: the LINT exponent 9007199254740993
becomes the even binary64 value 9007199254740992, so a base of -1 produces +1.
This profile operates on converted floating values, not exact integer powers.

For finite operands, a negative base requires an integer-valued exponent.
Fractional powers requiring a complex result, zero raised to a negative power
and overflow fault and roll back the advance. Host 0^0 is 1. Signed zero, subnormals and underflow retain
the existing binary64 solver behavior. Native precision, math flags, minor-fault
continuation and lifecycle equivalence remain unverified.

## Powers with NaN and infinity

Either floating tag operand can hold NaN or signed infinity. In the ladder
model, an exponent of zero or a base of one returns one, even if the other
operand is NaN. A negative infinity raised to an odd positive integer gives
negative infinity. An odd negative integer exponent gives negative zero.
A negative base with a finite fractional exponent still faults, including a
base of negative infinity. Zero to a finite negative exponent still faults.
[Rockwell XPY guidance](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/advanced-math-instructions/expt.html)
[Host power rules](https://docs.python.org/3.13/library/math.html#math.pow)

Floating destinations retain the result. Signed integer destinations receive
zero for NaN or the signed limit for infinity. A signed conversion of infinity
sets the modeled task `S:MINOR` bit with explicit `ReportMinorOverflow`
enabled. Unsigned integer destinations reject a nonfinite result and roll back
the advance.

Structural preflight checks types, scalar shapes, references, permissions and
literal bounds without saved values or dynamic indices. False/prescan paths
skip live operands. True calls require both sources even when the exponent is
zero or base is one. Full writes establish unknown selected cells; neighboring
cells retain their values. Aliases, UDT members, source/result overlap and
existing AOI bindings retain their rules. Required unknowns, invalid indices,
domain/overflow and late failures restore values, task progress/timing and warm
AOI local/external state. Run-entry prescan remains a separate boundary.

Open **Math lab**, set MixedPowerIndex to 1, enable MixedPowerEnabled and Step.

- The selected result is 8, with guards 101.125 and 999.5.
- Precision is 1.0000000000000004 and ConstantBase is 4.
- DintResult and RealResult demonstrate the different squares above.
- WideBaseResult is 9007199254740992 and WideExponentResult is +1 after promotion.
- NegativeResult is -8 for the negative base and DINT exponent 3.

The section starts disabled with index 99 dormant. MixedPowerDomainFault=true
demonstrates a negative base with fractional REAL exponent. MixedPowerOverflowFault
demonstrates overflow; MixedPowerLateDivisor=0 demonstrates a later failure.
Restore both fault switches to false and the divisor to 1. Disable the section
before returning its index to 99. Existing Math lab sections remain available.

[Unary LREAL results](lreal-unary-sources.md) additionally accept all numeric tag
inputs and signed DINT constants for eleven unary math forms. Narrowing results,
floating/typed/larger constants, CPT/CMP/ST expressions, EXPT aliases, new FBD/SFC
forms and broader controller profiles remain separate work.

The source basis is installed v35 XPY help (14478) and Data Conversions (14451).
Those operand listings do not establish native acceptance or numerical parity
for this bounded software implementation.

See [implementation](../source/logixlab/real_math.py),
[focused cases](../source/tests/test_mixed_lreal_power.py),
[matching LREAL advanced math](lreal-advanced.md) and
[MathLab.L5X](../source/samples/MathLab.L5X).
