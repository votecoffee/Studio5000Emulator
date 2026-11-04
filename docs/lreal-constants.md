# Integer constants with LREAL

App `26.1104.081351` adds signed DINT-range integer constants to the v35
ControlLogix 5580 ladder software profile for ADD, SUB, MUL, DIV, MOD,
EQU, NEQ, LES, LEQ, GRT, GEQ and LIM.

```text
ADD(DoubleInput,1,DoubleResult);
SUB(3,DoubleInput,DoubleResult);
GRT(DoubleInput,0)OTE(Positive);
LIM(0,DoubleInput,100)OTE(InRange);
LIM(DoubleLow,25,IntegerHigh)OTE(ConstantInRange);
```

At least one source must be an actual scalar LREAL tag. Arithmetic requires a
LREAL destination; either binary source position can contain the constant.
Relations allow either position and LIM allows any position, including both
bounds or the tested value. Existing mixed numeric tag forms retain their rules.
NEG/ABS still require a LREAL source; this does not add constant-only arithmetic.

Constants must parse as integers between -2147483648 and 2147483647 inclusive.
Decimal signs, underscores and existing binary/octal/hexadecimal syntax follow
the existing literal parser; radix values must also fit that numeric range.
The constants promote exactly to finite binary64, without a REAL intermediate.
For example, SUB(LREAL 16777217,16777217) produces zero. Floating literals such as
1.0 or 1e0, Boolean/typed literals and larger integers remain excluded. Using a
tag for another supported numeric type retains its documented promotion rules.

Every required input is read before calculation. Binary64 calculations, signed
zero, finite subnormals, dividend-sign remainder and inclusive/reversed limit
behavior retain their existing software rules. A zero DIV/MOD divisor and a
nonfinite result fault and roll back the entire advance. A zero product or
constant limit does not bypass an unknown required tag.

Structural preflight validates references, permissions, types and literal bounds
even on false rungs, without reading saved tag values or dynamic indices.
False/prescan paths skip live operands; downstream OTEs receive false power.
Full writes establish unknown destination cells. Aliases, UDT members and
existing AOI InOut/local bindings retain their rules. Reached unknowns, bad
indices and late faults restore values, coils, scheduling/timing and AOI state.
Warm AOI cases are separate from run-entry prescan.

Open **Integer lab**, set DoubleConstantsIndex to 1 and EnableDoubleConstants to
true, then Step. DoubleConstants demonstrates:

- Add=10.5, Sub=-4.5, Mul=22.5, Div=0.4 and Mod=1.5.
- Eq/Lt/Le false and Ne/Gt/Ge true for 7.5 compared with 3.
- NormalLimit and ConstantTest true, ReverseLimit false.
- Precision=0 for the integer constant 16777217 and PrecisionGreater true.

The section starts disabled with index 99 to demonstrate dormant references.
DoubleConstantsZeroFault=true triggers a zero-divisor fault after earlier work;
restore it to false. DoubleConstantsLateDivisor=0 triggers a later fault; restore
it to 1. Disable the section before returning its index to 99. Unselected values
and neighboring lab sections remain available.

Advanced math, CPT/CMP/ST expressions, narrowing arithmetic destinations,
floating/typed/larger literals, MEQ/bitwise, new FBD/SFC forms and broader
controller profiles remain separate. These model tests do not establish native
Studio/controller acceptance, numerical precision, status, minor-fault or
lifecycle equivalence.

The source basis remains installed v35 arithmetic/comparison help and Data
Conversions 14451. The published [Rockwell data-conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
provides related type-ranking context; the bounded literal policy above is an
explicit software profile.

See [focused cases](../source/tests/test_lreal_constants.py),
[arithmetic implementation](../source/logixlab/scalar_math.py),
[comparison implementation](../source/logixlab/comparisons.py) and
[IntegerLab.L5X](../source/samples/IntegerLab.L5X).

[Mixed LREAL powers](mixed-lreal-power.md) additionally qualify XPY with numeric
tag sources or signed DINT-range integer constants, one actual LREAL input and
a LREAL result. Other advanced math and expression profiles remain separate.

[Unary LREAL results](lreal-unary-sources.md) additionally qualify all ten numeric
source tag types and signed DINT-range constants for eleven standalone unary
math forms. A LREAL destination selects this finite binary64 software profile.
