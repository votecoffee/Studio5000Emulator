# Constants in LREAL ladder math

The bounded v35 ControlLogix 5580 ladder profile accepts constants in nineteen
standalone math instructions when the destination is a scalar LREAL:

| Family | Instructions |
| --- | --- |
| Arithmetic | ADD, SUB, MUL, DIV, MOD, NEG, ABS |
| Power and root | XPY, SQR |
| Logarithms | LN, LOG |
| Angles and trigonometry | DEG, RAD, SIN, COS, TAN, ASN, ACS, ATN |

Sources can be existing numeric tags, bounded DINT integer constants, finite
REAL floating constants, decimal L/l (LINT), U/u (UDINT), UL/ul/Ul/uL (ULINT)
integer constants or finite floating L/l (LREAL) constants. A scalar LREAL result
selects binary64 calculation even for constant-only calls. Both binary operand
positions support the same forms. An LREAL input can also select binary64
for [REAL and integer results](#real-and-integer-results).

```text
ADD(0.1L,0.0L,DoubleResult);
DIV(3L,2U,DoubleQuotient);
XPY(2L,3.5L,DoublePower);
SQR(16777217U,DoubleRoot);
LN(2.0L,DoubleLog);
```

Each constant is checked at its declared source range and precision before
binary64 promotion. Unsuffixed 0.1 first rounds to REAL and contributes
0.10000000149011612; 0.1L contributes binary64 0.1. Similarly, SQR(16777217.0)
uses the REAL-rounded input 16777216 and returns 4096, while 16777217U or
16777217.0L retains that integer before the binary64 root. An unsuffixed floating
constant must fit finite REAL even when the result is LREAL. Unsuffixed REAL
underflow occurs before promotion; LREAL constants retain representable binary64
subnormals and signed zero.

Large integer constants round when promoted: 9007199254740993L becomes binary64
9007199254740992, and ULINT maximum becomes 2^64. MOD of that promoted ULINT by
3 is 1. This profile does not provide exact integer calculation beyond binary64
precision. Typed decimal ranges are checked before conversion, including on
false rungs. Boolean, aggregate, malformed, out-of-range and nonfinite constants
are blocked structurally. Existing radix operands must still fit the signed
DINT numeric range; [MOV radix patterns](radix-mov-literals.md) remain separate.

Structural checks use declared types and permissions without saved values or
live indirect indices. False rungs and prescan skip those values and calculations.
Domain checks occur when reached; unit powers and zero products still consume
all required sources. Full writes establish unknown selected destinations and
retain neighboring values. Aliases, member arrays and existing copied AOI outputs,
InOuts and local storage keep their contracts. Domain/range errors, zero divisors,
unknown sources, invalid indices and later faults roll back the entire advance,
including task timing, traces and AOI bindings.

The existing ladder viewer shows typed constants and destination values. Load
**Wide expression lab**, enable MathLitEnabled and step to run **MathConstants**.
The routine contrasts REAL/LREAL precision, integer promotion, fractional
division, power and unary math. MathLitSelected retains an unknown neighbor and
a 903.25 guard; change MathLitIndex to 1 to fill the next element. DomainFault,
RangeFault and a zero LateDivisor demonstrate independent atomic fault/retry.

Standalone comparisons, bitwise/file/ST/FBD consumers,
typed radix forms and broader controller/firmware profiles remain separate.
Existing host binary64 functions and finite-result guards provide a software
model; native numerical/status/minor-fault/lifecycle parity remains unverified.
The source basis is installed v35 Immediate values (14454), ADD (14623), XPY
(14478), Data conversions (14451) and the existing qualified unary/result profiles.
The published [Rockwell immediate-value reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/immediate-values.html)
provides related type context; it does not establish v35 native acceptance.

## REAL and integer results

App `26.1105.075557` extends the same nineteen ladder instructions to REAL and
all eight integer destinations when at least one source is an LREAL tag or
finite floating L/l literal. The sources retain their declared precision before
promotion, and the instruction evaluates in binary64. The finite result converts
once to the destination. REAL uses float32 rounding, and integer destinations
round to nearest with ties to even and require the rounded value to fit.

```text
SUB(16777217.0L,16777216,RealResidual);
DIV(1e39L,1e39L,RealQuotient);
ADD(2.5L,0,IntegerResult);
XPY(4.0L,0.5L,SelectedLints[Index]);
```

The first two examples yield REAL 1.0. In the subtraction, float32 conversion
of the first source before calculation would lose the difference. The division
accepts two finite binary64 operands larger than the REAL range because the
quotient fits. ADD rounds 2.5 to integer 2, and XPY writes LINT 2.

In **Wide expression lab**, enable `Binary64ResultEnabled` and step into
**Binary64SourceResults**. Set `Binary64ResultIndex` to 1 to fill the next unknown
element. Element 2 retains 903. Set `Binary64ResultDivisor` to zero to exercise
a later fault and restore it to 1 to retry. Destination conversion overflow,
unknown reached inputs and invalid indices also roll back the advance.

See [shared source conversion](../source/logixlab/numeric_storage.py),
[arithmetic](../source/logixlab/scalar_math.py),
[advanced math](../source/logixlab/real_math.py) and
[focused cases](../source/tests/test_lreal_math_literals.py).
