# Typed numeric MOV constants

The bounded v35 ControlLogix 5580 MOV profile accepts decimal integer constants
with L/l (LINT), U/u (UDINT) and UL/ul/Ul/uL (ULINT) suffixes. Floating constants
with a decimal point or exponent and L/l suffix use finite LREAL precision.

```text
MOV(-9223372036854775808L,SignedValue);
MOV(18446744073709551615UL,UnsignedValue);
MOV(4294967295U,ByteValue);
MOV(0.1L,DoubleValue);
MOV(3.5L,IntegerValue);
```

## Source type and conversion

Each constant is checked at its declared source width or precision before the
existing [numeric MOV conversion](numeric-storage.md). Integer sources preserve
the low destination bits, sign-extending signed sources and zero-extending
unsigned sources when widening. For example, 4294967295U becomes LINT 4294967295,
or SINT -1. Integer -1L becomes the unsigned destination's all-ones pattern.
These are the same conversions as a tag holding the declared value.

Integer-to-floating moves can lose precision: 9007199254740993L becomes LREAL
9007199254740992.0. Moving that constant directly into LINT retains every bit.
An LREAL constant retains binary64 precision before final conversion. Thus
MOV(0.1L,DoubleValue) stores 0.1, while unsuffixed 0.1 first uses REAL precision
and stores approximately 0.10000000149011612 in LREAL. Floating-to-integer moves
round ties to even and require a representable result; 3.5L becomes integer 4.

Lowercase/mixed-case suffixes, leading decimal zeroes and a directly attached
unary sign are accepted. Integer and floating L are distinct: 1L is LINT;
1.0L, .5l and 1e3L are LREAL. Finite large/subnormal floating values and signed
zero are retained within binary64 representation. A negative unsigned zero is
integer zero. Unsuffixed decimal inputs retain their existing DINT/finite REAL
rules. [Unsuffixed radix MOV constants](radix-mov-literals.md) use a separate
32-bit DINT pattern rule, including zero-fill and a signed top bit.

## Selection and failure behavior

Declared source ranges and finite floating encodings are checked during
preflight, including false calls. A destination conversion that cannot fit
faults only when the MOV executes. False calls and prescan skip live destination
indices and old values. Complete MOV writes establish unknown destinations;
unselected cells/members remain unknown.

Reached bounds, conversion and later instruction faults roll back the entire
modeled advance, including earlier writes, AOI copied outputs/InOut/local state,
bindings, scheduler/timing and trace. Prior successful advances remain committed.
Native overflow result bits, status/fault records, partial effects, packed layouts
and Studio/controller lifecycle equivalence remain unverified.

## Viewer and scope

The viewer displays valid typed constants with their declared literal type.
Integer digits remain decimal strings, preserving values above 2^53. Invalid
literal ranges/encodings have no computed viewer value. Existing tag names and
index resolution stay separate. Viewer notation does not qualify an instruction
for execution; runtime support is scoped by each instruction profile.

This parser is local to MOV's source operand. It does not change general memory
reads, expression parsing, AOI call arguments or other instruction parameters.
Expressions, parentheses, typed radix forms, separators and alternate typed
spellings remain blocked as MOV immediates. Existing CPT/CMP, file and ST
literal profiles retain their own rules. Other controllers are not extended.

## Wide expression lab

Step Wide expression lab once, then enable MovLitEnabled. NumericMoveConstants
shows signed/unsigned ranges, integer narrowing and widening, ordinary versus
LREAL 0.1, nearest-even integer conversion, large/subnormal values and a selected
unknown LINT write. MovLitSelected becomes [9007199254740993, unknown, 903].

MovLitRangeFault enables an overflowing SINT conversion; MovLitFloatRangeFault
enables an overflowing REAL conversion. Clear each flag to recover. Set
MovLitIndex=1 and MovLitLateDivisor=0 to exercise rollback after the selected
write, then restore the divisor to 1 and retry. Disable MovLitEnabled before
leaving an invalid destination index dormant.

See the [sample](../source/samples/WideExpressionLab.L5X),
[runtime tests](../source/tests/test_mov_literals.py),
[viewer tests](../source/tests/web/mov-literals.test.cjs) and
[implementation](../source/logixlab/numeric_storage.py). Source baseline:
installed v35 Immediate values (14454), Data conversions (14451) and MOV (14688).
These are software-model checks; native numerical/status/fault/layout and
Studio acceptance remain separate qualification work.
