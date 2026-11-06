# Ladder math with REAL precision

[Typed integer constants](real-integer-literals.md) extend this profile in app
`26.1104.174245`: decimal L/U/UL integers are checked at their declared ranges
before the existing float32 conversion. Other result and consumer profiles
retain their scope.

App `26.1104.100623` extends the v35 ControlLogix 5580 software profile when
the destination is a scalar REAL. Supported forms are ADD, SUB, MUL, DIV, MOD,
NEG, ABS, XPY, SQR, LN, LOG, DEG, RAD, SIN, COS, TAN, ASN, ACS and ATN.
Sources may be SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT or REAL tags.
Signed DINT-range integer literals and finite REAL-convertible floating literals
are accepted. Constant-only calls work; a REAL source is not required.

```text
ADD(DintInput,UnsignedInput,RealResult);
DIV(3,2,RealResult);
MOD(UlintInput,3,RealResult);
XPY(IntegerBase,2.0,RealResult);
SQR(UlintInput,RealResult);
```

Every required source converts to finite float32 before the operation. The
existing host arithmetic, remainder, power and unary solvers then run, and the
result rounds to float32. Inputs retain their stored values. Integer division
into REAL produces a fractional result; it does not use an integer quotient.
MOD uses the dividend's sign. SQR uses the absolute value of its input.

This corrects earlier narrow arithmetic that rounded only the destination.
For DINT input 16777217, ADD(input,1,realResult) now converts the input to
16777216 first and rounds the sum back to 16777216. The earlier result was
16777218. SUB(input,16777216,realResult) now yields zero. The DINT still stores
16777217. Signed and unsigned integers convert numerically, with possible
precision loss: ULINT maximum becomes float32 2^64, so its floating remainder
by 3 is 1. Integer-only profiles retain their exact arithmetic rules.

Floating literals also convert before evaluation. A tiny literal can underflow
to zero, including a divisor. NEG(0,realResult) retains negative zero. Existing
finite-result checks apply. Unknown required sources, zero divisors, invalid
power/log/inverse-trig domains and nonfinite results roll back the advance,
including task progress, timing and AOI state. A whole-project ladder handler
can clear reached array subscript faults in
[arithmetic](controller-handlers.md#recover-a-ladder-arithmetic-array-fault) and
[standalone math](controller-handlers.md#recover-standalone-math-array-faults).
True calls consume every source even for zero products or unit/zero powers.

Structural preflight validates scalar types, shapes, references, permissions,
static bounds and literals without consuming saved values or dynamic indices.
False/prescan paths skip operands and retain destinations. Full writes establish
unknown results; neighboring unknowns and guards remain unchanged. Aliases,
selected array elements, UDT members, overlapping results and existing AOI
local/Output/InOut references retain their behavior.

An LREAL tag or floating L/l input selects [binary64 calculation](lreal-math-literals.md#real-and-integer-results)
before conversion to REAL. The float32 rules above apply to calls whose inputs
are integer or REAL.
NaN/infinity, native math flags, minor faults, lifecycle semantics and numerical
bit-for-bit equivalence remain unqualified. The solvers use host arithmetic;
float32 inputs and results alone do not establish native numerical equivalence.

Open **Integer lab**, set RealResultsIndex to 1, enable RealResultsEnabled and
Step. The selected sum is 5; Sub=1, Mul=6, Div=1.5, Mod=1, Power=9, Neg=-3,
Abs=3. Eleven unary outputs include Sqrt=4294967296, Ln=0, Log=2 and the
expected float32 trigonometric values. Precision=16777216, WideRemainder=1,
WideNeg=-2^64, Literal is float32 1.1 and NegativeZero retains its sign.
Neighboring selected-result guards are 101.125 and 999.5.

DomainFault, ZeroFault and OverflowFault independently demonstrate rollback;
reset them to false. LateDivisor=0 demonstrates a failure after earlier results;
restore it to 1. External source writes update the next Step. Disable the
section before returning the selected index to 99; outputs remain stored.

## Wide and unsigned integer results

App `26.1105.081222` extends the same nineteen ladder forms to LINT, USINT,
UINT, UDINT and ULINT results when a REAL tag or an unsuffixed floating
immediate selects float32. All required inputs convert to finite REAL before
calculation. The result rounds to float32, then to the nearest integer with
ties to even. The rounded integer must fit its destination.

```text
ADD(2.5,0,SignedResult);
DIV(7.0,2U,ByteResult);
SUB(16777217U,16777216.0,FloatResidual);
SUB(16777217.0L,16777216.0,DoubleResidual);
```

These produce 2, 4, 0 and 1. In the third example, both inputs become
16777216 in float32. The LREAL source in the fourth selects binary64.
Integer-only arithmetic retains its exact calculation rules. Earlier
SINT/INT/DINT forms retain their existing profiles.

Enable `RealIntegerEnabled` in **Integer lab** and step through
**RealIntegerOutputs**. Set `RealIntegerIndex` to 1 to write the next
unknown element. Element 2 retains 903. Set `RealIntegerLateDivisor`
to zero to observe scan rollback, then restore it to 1 to retry.
Reached invalid indices, out-of-range results and nonfinite calculations
also roll back the advance.

Source basis: installed v35 ADD (14623), MOD (14620), XPY (14478), SQR (14617)
and Data Conversions (14451). See the
[Rockwell conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
for related conversion rules. Software tests do not prove Studio import,
controller acceptance or native parity.

See [scalar arithmetic](../source/logixlab/scalar_math.py),
[power/unary math](../source/logixlab/real_math.py),
[focused cases](../source/tests/test_real_destination_math.py) and
[IntegerLab.L5X](../source/samples/IntegerLab.L5X).
