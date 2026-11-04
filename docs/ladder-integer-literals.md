# Wide integer constants in ladder expressions

Direct CPT/CMP expressions in the bounded v35 ControlLogix 5580 profile accept
decimal integer constants with L/l (LINT), U/u (UDINT) and UL/ul/Ul/uL (ULINT)
suffixes. They use the existing exact integer evaluator and retain every bit,
including values above the precision of REAL or LREAL.

```text
CPT(SignedResult,-9223372036854775808L);
CPT(UnsignedResult,18446744073709551615UL);
CPT(DwordResult,4294967295U);
CPT(Quotient,18446744073709551615UL/3UL);
CMP(9007199254740992L<9007199254740993L)OTE(Exact);
```

## Types and arithmetic

All numeric tags, typed constants and the CPT destination must have one matching
type. An unsuffixed signed-DINT constant may participate when its value fits that
type. Typed constants can select the profile without a numeric source tag, as
in the examples above. Lowercase suffixes, leading decimal zeroes, unary signs
and parentheses are accepted. Negative unsigned values remain out of range;
negative zero is zero.

Literal ranges are checked during preflight, including false rungs. The unary
minus immediately applied to a literal participates in that check, allowing the
LINT minimum. Arithmetic remains exact and every numeric intermediate must fit.
Division truncates toward zero, MOD has the dividend's sign and bitwise forms
use the selected type's width. Existing ABS and arithmetic operators remain
available; no additional math functions or power forms are added.

False calls and prescan skip live domains, unknown data and dynamic indices.
Required CMP Boolean operands remain eager. A failed modeled advance rolls
back earlier writes, warm AOI bindings/local state, timing, scheduler and trace.
Prior successful advances and prescan remain separate committed events.

## Scope and limits

The parser/cache explicitly opt in for direct ladder CPT/CMP. Generic, FAL/FSC
and array-index consumers retain their existing restrictions. ST retains its
separate [integer constant profile](st-integer-literals.md). Other instruction
arguments do not acquire suffix support through this change.

Typed radix forms, separators, alternate typed spellings, mixed typed/tag
integers and nonmatching destinations remain blocked in the exact integer profile.
An LREAL selector uses the separate [binary64 constant profile](lreal-integer-literals.md);
it can mix numeric types and convert final results under its existing rules.
For example, 1L is LINT, while 1.0L is a distinct
[LREAL floating constant](lreal-literals.md). Their numeric types cannot be
combined in this exact integer profile; an LREAL selector chooses binary64 instead. The previously qualified mixed-tag
integer arithmetic profile remains separate.

## Wide expression lab

Open Wide expression lab, step once, then enable ILitEnabled. IntegerConstants
shows full-range signed/unsigned constants, exact quotients and bitwise results,
an exact comparison and selected array writes. ILitSelected becomes
[9007199254740995, unknown, 903]. Set ILitIndex=1 and ILitLateDivisor=0 to
exercise rollback; restoring the divisor to 1 establishes 9007199254740999.
ILitOverflow enables a LINT overflow. Clear it to recover. Disable ILitEnabled
before leaving an invalid index dormant.

See the [sample](../source/samples/WideExpressionLab.L5X),
[tests](../source/tests/test_ladder_integer_literals.py),
[parser](../source/logixlab/expressions.py) and
[integer evaluator](../source/logixlab/wide_st.py). The source baseline is
installed v35 Immediate values (14454), CPT (14597) and CMP (14592). This is a
software-model feature; native numerical/status/fault/partial-write/layout and
Studio/controller lifecycle equivalence remain unverified.
