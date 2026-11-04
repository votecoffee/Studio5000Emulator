# REAL comparison promotion

[Typed integer constants](real-integer-literals.md) extend this profile in app
`26.1104.174245`: decimal L/U/UL integers are checked at their declared ranges
before the existing float32 conversion. Other result and consumer profiles
retain their scope.

App `26.1104.094330` extends the v35 ControlLogix 5580 ladder software profile
for EQU, NEQ, LES, LEQ, GRT, GEQ and LIM. A scalar REAL tag selects finite
float32 comparison when no actual LREAL input selects the separate binary64
profile. Other tag inputs may be SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT
or REAL. Both relation positions and every limit position are supported.

```text
EQU(RealInput,DintInput)OTE(Equal);
GRT(UnsignedInput,RealInput)OTE(Greater);
LIM(IntegerLow,RealInput,UnsignedHigh)OTE(InRange);
EQU(RealInput,1.1)OTE(LiteralEqual);
```

All required sources convert to float32 before comparison. Signed and unsigned
integers convert numerically; stored inputs remain unchanged. There is no
equality tolerance. This corrects earlier narrow REAL/integer comparisons that
used the stored integer directly, and adds the previously blocked wide/REAL
tag mixtures.

REAL 16777216 compares equal to DINT 16777217 because the integer rounds to
float32 16777216 before evaluation. The DINT tag still stores 16777217. ULINT
maximum rounds to float32 2^64 and compares equal to a REAL holding that value.
This profile compares converted floating values, not exact mathematical integers.

An actual REAL tag is required to select this profile. Signed DINT-range integer
constants and finite REAL-convertible floating literals are accepted in either
relation position or any limit position. Constants also round to float32:
EQU(REAL 1.1,1.1) compares the same stored float32 values. Tiny literals can
underflow to zero. Boolean/typed/larger integer constants and floating constants
outside finite REAL range remain excluded. Existing immediate-only or no-REAL-tag
forms keep their separate rules.

LIM applies inclusive endpoints after conversion. Reversed bounds accept values
at or outside either endpoint. If rounding collapses the low and high bounds,
they become a singleton rather than a reversed interval. For example, DINT low
16777217 and REAL high 16777216 both convert to 16777216; test 16777215 is false
and test 16777216 is true.

Actual LREAL inputs retain binary64 precedence, including mixtures with REAL.
Integer-only ordering retains its existing exact range-preserving behavior.
MEQ, CMP/ST expressions and new FBD/SFC forms are outside this extension.

Structural preflight checks types, shapes, references, static bounds and literal
limits without saved values or dynamic indices. False/prescan paths skip live
operands; downstream OTEs receive false power. True calls consume every required
source, including all three LIM inputs. Aliases, UDT members and existing AOI
bindings retain their rules. Unknowns, bad indices and later faults restore
values/coils, task progress/timing and warm AOI local/external state and bindings.
Native numerical, math-status, fault and lifecycle equivalence remain unverified.

Open **Integer lab**, set RealCompareIndex to 1, enable RealCompareEnabled and
Step. Eq/Le/Ge are true and Ne/Lt/Gt false after the DINT conversion above.
NormalLimit is true, ReverseLimit false and CollapsedLimit false. WideEqual,
LiteralEqual, TinyPositive, ZeroEqual, DoublePriority and ExactInteger are true.
The source values and neighboring guards remain unchanged.

Write RealCompareValue=16777216 to make CollapsedLimit true. Set the selected
RealCompareValues[1] to 16777218 to demonstrate the upper endpoint in both normal
and reversed limits. RealCompareLateDivisor=0 demonstrates rollback after earlier
coils; restore it to 1. Disable the section before returning its index to 99.
Earlier lab sections remain available.

The source basis is installed v35 EQU (14589), LIM (14610) and Data Conversions
(14451). The published [Rockwell conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
provides related integer-to-REAL rounding rules; model tests do not establish
native controller acceptance or bit-for-bit parity.

See [implementation](../source/logixlab/comparisons.py),
[focused cases](../source/tests/test_mixed_real_comparisons.py) and
[IntegerLab.L5X](../source/samples/IntegerLab.L5X).
