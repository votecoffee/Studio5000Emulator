# Numeric unary inputs with LREAL results

App `26.1104.085804` extends eleven standalone ladder math instructions in the
v35 ControlLogix 5580 software profile:

| Family | Instructions |
| --- | --- |
| Root | SQR |
| Logarithms | LN, LOG |
| Angle conversion | DEG, RAD |
| Trigonometry | SIN, COS, TAN, ASN, ACS, ATN |

A scalar LREAL destination selects finite binary64 calculation. Sources may be
scalar SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL tags, or
integer constants from -2147483648 through 2147483647 inclusive. A LREAL source
is not required for these unary forms. Floating/typed/Boolean/larger constants
remain excluded; existing radix syntax must represent an integer in that range.

```text
SQR(DintInput,DoubleRoot);
SQR(9,DoubleRoot);
LN(IntegerInput,DoubleLog);
RAD(90,DoubleRadians);
SIN(RealInput,DoubleSine);
```

The required source converts numerically to binary64 before the existing host
math function. Signed integers keep their signs; unsigned values stay
nonnegative. REAL contributes its stored float32 value. No intermediate REAL
conversion occurs for an integer or LREAL source. Constants in the supported
range convert exactly. Larger integer tag values can round during promotion.

SQR(DINT 16777217) produces 4096.000122070311. A REAL tag assigned 16777217 first
stores 16777216, so its root is 4096. ULINT's maximum rounds to binary64 2^64 and
its root is 2^32. SQR retains absolute-value handling for negative inputs.

LN/LOG require positive inputs; ASN/ACS require values from -1 through +1.
Trig inputs and inverse-trig outputs use radians. Finite signed zero, subnormals
and large inputs follow the existing binary64 solver. Domain and nonfinite
results fault and roll back the advance. Native numerical precision, math flags,
minor-fault continuation and lifecycle equivalence remain unverified.

Structural preflight checks types, scalar shapes, literal bounds, references and
write permissions without saved values or live indices. False/prescan paths
skip live operands and domain calculations, including a dormant LN(0,Result).
True calls require known sources; full writes establish unknown result cells.
Aliases, UDT members, source/result overlap and existing AOI bindings retain
their rules. Required unknowns, bad indices and late failures restore values,
task progress/timing and warm AOI local/external state. Run-entry prescan remains
a separate boundary.

Open **Math lab**, set UnaryDoubleIndex to 1, enable UnaryDoubleEnabled and Step.
The selected root is 3 and neighboring guards remain 101.125 and 999.5. DintRoot
and RealRoot show the precision difference above. UnsignedRoot is 4294967296,
SignedRoot is 4, and LiteralRoot is 3. The other outputs demonstrate the ten
log/angle/trig forms, including Radians=pi/2 and Sine approximately 0.841471.

The section starts disabled with index 99 dormant. DomainFault, LiteralFault and
OverflowFault demonstrate independent failures; LateDivisor=0 demonstrates a
later fault. Restore the switches to false and the divisor to 1. Disable the
section before returning its index to 99. Other Math lab sections remain available.

XPY retains its [separate mixed-source rules](mixed-lreal-power.md), including a
required LREAL input. This extension adds no wide/unsigned result types, broader
CPT/CMP/ST expressions, floating literals, new aliases or new FBD/SFC forms.

The source basis is installed v35 SQR (14617), LN (14479) and Data Conversions
(14451), alongside the existing unary-instruction references. The published
[Rockwell conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
provides related type-ranking context. These references and model checks do not
establish native instruction acceptance or numerical parity.

See [implementation](../source/logixlab/real_math.py),
[focused cases](../source/tests/test_lreal_unary_sources.py) and
[MathLab.L5X](../source/samples/MathLab.L5X).
