# Floating constants in REAL ladder comparisons

The bounded v35 ControlLogix 5580 ladder profile uses an unsuffixed floating
immediate to select REAL comparison in EQU, NEQ, LES, LEQ, GRT, GEQ and LIM.
A REAL tag is no longer required for that selection. Constant-only calls,
integer-tag thresholds and mixed integer operands can therefore use float32
comparison when a floating constant is present.

```text
EQU(0.1,0.1)OTE(ConstantEqual);
EQU(IntegerValue,16777216.0)OTE(RoundedEqual);
EQU(16#FFFFFFFF,-1.0)OTE(SignedWordEqual);
LIM(0L,0.5,1UL)OTE(InRange);
LIM(1U,0.5,0L)OTE(OutsideReversedRange);
```

Every required numeric operand converts to finite REAL before comparison.
Integer tags retain their stored values and signs, but large values can round
during conversion. DINT/UDINT 16777217 compares equal to 16777216.0 because
both become float32 16777216. Typed decimal and radix integer words use their
declared width and sign before conversion. For example, 16#FFFFFFFF becomes
-1.0, while 16#FFFFFFFFL becomes REAL 4294967296.

Both relation positions and all three LIM positions accept the floating
selector. LIM includes its endpoints. Reversed or collapsed limits operate
on converted values. Comparison uses no tolerance; tiny floating constants
can underflow to positive or negative zero before comparison.

An LREAL tag or floating L/l immediate still selects the separate binary64
profile first. Thus EQU(16777217U,16777216.0L) is false. Integer-only calls
retain exact ordering and their existing range/type rules; integer suffixes
alone do not select REAL. Unused tags do not influence calculation precision.

Structural preflight checks types, scalar shapes, literals, references and
permissions without reading saved values or live indirect indices. False
rungs and prescan skip those values; downstream coils clear normally. Every
required source is consumed on reached calls, including a decisive or
zero-width limit. Unknowns, bounds failures and later faults restore the
advance, including earlier coil changes and supported AOI bindings.

Aliases, selected members and supported AOI copied Inputs, local tags and
InOut arrays remain read-only comparison sources. Malformed/overwide words,
nonfinite REAL literals, BOOL/aggregate sources, negative-prefix radix text,
expressions in scalar operands and unqualified targets remain blocked.

Load **Wide expression lab**, enable RealCmpEnabled and step to run
**RealComparisonConstants**. LiteralEqual, MixedTag, ConstantWide,
SignedWord, UnsignedWord, Normal, Collapsed, Underflow, Selected and
Unsigned64 are true; Reversed and Binary64Diff are false. The routine uses
integer source tags and immediate floating selectors. Index 1 selects an
unknown DINT; write RealCmpInputs[1]=1 to repair it. Index 99 or
RealCmpLateDivisor=0 demonstrates rollback. Disable the gate to skip invalid
live operands and clear the comparison coils.

Default numeric parsers, MEQ, expression/file/ST/FBD consumers and other
controller profiles retain their separate scope. Native numerical, math-status,
fault and lifecycle parity is unverified. The source basis is installed v35
Immediate values (14454), Data conversions (14451), EQU (14589) and LIM (14610).

See [comparison selection](../source/logixlab/comparisons.py),
[REAL source decoding](../source/logixlab/numeric_storage.py),
[radix comparisons](real-radix-math.md) and
[focused cases](../source/tests/test_real_comparison_literals.py).
