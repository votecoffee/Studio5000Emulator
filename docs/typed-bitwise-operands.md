# Typed bitwise operands

The v35 ControlLogix 5580 ladder profile accepts plain and typed integer constants.

## Typed decimal immediates

The typed forms are decimal L/l (LINT),
U/u (UDINT) and UL/ul/Ul/uL (ULINT) in AND, OR, XOR, NOT and MEQ. With
at least one such source operand, scalar integer tags and existing bounded DINT
or 32-bit binary/octal/hexadecimal patterns can mix in the same call. Other
instruction consumers retain their own contracts.

Each source keeps its declared width: signed and unsigned integer tags use
8/16/32/64 bits; LINT/ULINT constants use 64 bits, UDINT constants use 32 bits,
and existing untyped immediates use 32 bits. Source ranges are checked before
execution. Patterns are masked at that width and zero-extended before combining.
This is distinct from [numeric arithmetic range checks](typed-integer-operands.md).

```text
OR(4294967295U,0L,WideResult);
NOT(4294967295U,WideNot);
AND(18446744073709551615UL,255U,ByteResult);
MEQ(SignedDword,4294967295U,18446744073709551615UL)OTE(LowWordMatches);
```

For example, OR of UDINT maximum and 0L becomes LINT 4294967295, while OR of
-1L and 0UL becomes the destination's all-ones pattern. A DINT tag holding -1
contributes only 32 ones, even alongside a 64-bit operand. NOT inverts after
promotion; NOT(4294967295U) stored in LINT is -4294967296. Complete integer result
writes retain the destination's low bits and reinterpret its signed top bit;
AND(4294967295U,255UL) stored in SINT is -1. Untouched elements remain unchanged.

MEQ applies each operand's pattern width, then compares Source AND Mask against
Compare AND Mask. A 32-bit mask ignores differences above bit 31; a 64-bit mask
can expose them. All three positions support typed constants. Operands remain
read-only and all required values are consumed, including under a zero mask.

Structural preflight checks type, shape, immediate range and permissions without
saved values or live indices. False/prescan paths skip those values and retain
integer destinations; downstream OTEs clear normally. Full writes establish
unknown result elements. Reached unknowns, bad indices and later faults roll back
the complete advance, including task timing, traces and existing copied AOI
outputs, InOut/local storage and bindings. Required AOI copied inputs retain
their independent call-entry rules.

Load **Wide expression lab**, enable TypedBitsEnabled and step to run
**BitwiseOperandConstants**. It contrasts a DINT -1 with a full 64-bit constant,
shows NOT/truncation/MEQ, and retains an unknown selected neighbor plus a 903
guard. A zero TypedBitsLateDivisor demonstrates atomic fault/retry.

## Plain immediates with wide tags

App 26.1105.170122 accepts unsuffixed signed DINT decimal constants and
32-bit binary, octal and hexadecimal patterns alongside all eight integer tag
types in ladder AND, OR, XOR, NOT and MEQ. Plain immediates supply 32 bits
before promotion. For example, `AND(WideInput,16#FFFF_FFFF,Result)` extracts
the low 32 bits of an ULINT value. `XOR(-1,WideInput,Result)` flips those low
bits and preserves the high bits. `MEQ(WideInput,16#FFFF_FFFF,1)` ignores
differences above bit 31.

Previously accepted homogeneous LINT calls keep their signed-DINT immediate
promotion. For example, `OR(LintInput,-1,LintResult)` still yields -1.
In a newly supported call mixing LINT and ULINT, the same plain -1 supplies
only 32 ones. To select 64 ones explicitly, use `-1L` or an ULINT constant
with all bits set. Unsuffixed decimal values outside signed DINT and unsigned
radix patterns above 32 bits remain blocked even on false rungs.

Enable `WideMaskEnabled` in **Bit lab**. With the default
`WideMaskInput = 16#8000000100000001`, the AND result is 1, the OR result
is `16#8000000180000001`, the XOR result is `16#80000001FFFFFFFE`,
and NOT of the plain mask is `16#FFFFFFFF00000000`. `WideMaskMatches` is
true. Set `WideMaskDivisor` to zero to see all writes roll back after a late
fault. Restore it to one and step to retry.

[Mixed floating operands](scalar-math.md#mixed-floating-and-integer-bitwise-operands)
can use these constants in AND, OR, XOR and NOT. MEQ retains integer operands.
BOOL bitwise forms, typed radix, MVM/BTD, expression/file/ST/FBD and other
controller profiles remain separate. Native numerical/status/fault/lifecycle
parity remains unverified. The source basis is installed v35 AND (14670), OR
(14687), XOR (14683), NOT (14669), MEQ (14602), Immediate values (14454), and the
existing declared-width integer pattern model. General memory literal parsing
is unchanged; this is bounded software evidence, not native Studio acceptance.

See [width/pattern readers](../source/logixlab/integer_math.py),
[bitwise execution](../source/logixlab/scalar_math.py),
[MEQ execution](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_typed_bitwise_operands.py).
