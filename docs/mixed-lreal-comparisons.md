# Mixed numeric comparisons with LREAL

[LREAL comparison constants](lreal-comparison-literals.md) extend this profile
in app `26.1104.172031`: floating L/l literals can select binary64 without an
LREAL tag, and selected comparisons accept finite REAL and decimal typed
integer/LREAL constants. Historical tag-only and signed-DINT-only restrictions
below no longer apply to this selected profile.

App `26.1104.021141` extends the v35 ControlLogix 5580 ladder software profile
for EQU, NEQ, LES, LEQ, GRT, GEQ and LIM. The original form uses scalar numeric
tags, with at least one LREAL operand. The other operands can be SINT,
INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL. Both relation source
orders and all three LREAL positions in LIM are supported.

```text
EQU(DoubleInput,DintInput)OTE(Equal);
GRT(DoubleInput,RealInput)OTE(Greater);
LES(SignedWide,DoubleInput)OTE(Less);
LIM(IntegerLow,DoubleInput,UnsignedHigh)OTE(InRange);
LIM(DoubleLow,IntegerInput,UnsignedHigh)OTE(InRange);
```

[Signed DINT-range constants](lreal-constants.md) additionally occupy either
relation position or any LIM position while one actual LREAL input remains.
Floating/typed/larger literals remain excluded.

Declared types select the profile independently of saved values. Every required
source is read, then all operands promote to finite host binary64 before
comparison. Signed values retain their numeric signs; unsigned values retain
their nonnegative values. REAL contributes its already stored float32 value.
No tolerance is applied. Comparisons do not write or convert the stored inputs.

LREAL 16777217 equals DINT 16777217 without a REAL intermediate. LREAL
1.0000000000000002 is greater than REAL 1. A REAL tag previously assigned
16777217 stores 16777216, so it differs from LREAL 16777217.

Large integers may round during binary64 promotion. LINT 9007199254740993
promotes to 9007199254740992 and therefore compares equal to a LREAL holding that
rounded value. ULINT's maximum promotes to 2^64 and compares equal to that
LREAL value. This profile compares promoted floating values; it does not promise
mathematically exact integer comparisons beyond binary64 precision. Integer-only
comparisons retain their separate existing range-preserving profile.

LIM applies inclusive bounds after promotion. If the converted low bound exceeds
the high bound, it accepts values at or outside either endpoint and rejects the
interior gap. Promotion can collapse distinct integer bounds to the same floating
value; bound direction is determined after conversion. Signed zero compares
equal to zero. Finite subnormal and large LREAL inputs retain their host values.
Native rounding, signed-zero/subnormal handling, status, fault classification,
lifecycle and bit-for-bit numerical equivalence remain unverified.

Structural preflight checks declared types, scalar shapes, references and static
bounds without saved values or dynamic indices. False rungs and prescan skip live
comparison operands. Downstream OTEs still receive false rung power. True calls
consume every input, including all three LIM values; they do not short-circuit
unknown inputs based on a partial comparison result. Aliases, UDT members,
selected elements and existing AOI bindings retain their rules.

Reached unknown values, invalid indices and later failures roll back the advance,
including earlier writes, result coils, task progress/timing and AOI local/
external values and bindings. Copied DINT AOI inputs with represented LREAL
locals have independent warm-state cases. Run-entry initialization remains a
separate preceding prescan boundary. Broader copied LREAL AOI parameters remain
unqualified. Floating/typed/larger immediates, BOOL/aggregate operands, MEQ, CMP/ST expressions,
time/date types and new FBD/SFC forms remain outside this extension.

Open **Integer lab** and Step with EnableDoubleCompare false. DoubleCompareIndex
starts at 99 without consuming the invalid index. Set it to 1, enable the section
and Step. The MixedDoubleCompare routine demonstrates:

- Eq true and Ne false for the selected LREAL value and DINT 16777217.
- Lt/Le false and Gt/Ge true for DoubleA=1.0000000000000002 versus REAL 1.
- InLimit true and ReverseLimit false for the normal bounds and reversed gap.
- WideEqual/UnsignedEqual true after documented large-integer promotion rounding.
- TinyGreater true for the smallest positive subnormal against integer zero.

All comparison sources and neighboring guards retain their stored values.
DoubleCompareLateDivisor=0 demonstrates rollback after the earlier coils were
evaluated; restore it to 1. Disable the section before returning its index to 99;
the downstream OTEs then clear without consuming that invalid index. Existing
Integer lab sections remain available.

The source basis is installed v35 help for the seven instructions, including
EQU14589, LIM14610 and Data Conversions14451. The published
[Rockwell data-conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
provides related context for type ranking. These software checks do not establish
native Studio/controller acceptance or numerical equivalence.

See [implementation](../source/logixlab/comparisons.py),
[focused cases](../source/tests/test_mixed_lreal_comparisons.py) and
[IntegerLab.L5X](../source/samples/IntegerLab.L5X).

[REAL comparison promotion](mixed-real-comparisons.md) additionally converts
numeric tag/constant operands to float32 when a REAL tag is present and no
LREAL input selects binary64. Integer-only ordering remains exact.
