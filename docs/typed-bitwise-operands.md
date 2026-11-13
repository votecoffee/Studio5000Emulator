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

## Typed radix masks

App `26.1112.235605` accepts attached L/l, U/u and UL/ul/Ul/uL suffixes on
binary, octal and hexadecimal constants in AND, OR, XOR, NOT and MEQ. They use
the [MOV radix source widths](radix-mov-literals.md#typed-radix-mov-sources):
LINT64, UDINT32 and ULINT64. Short patterns zero-fill to that width; the LINT
top bit selects a negative source value. Each operand then contributes its
declared bit pattern, zero-extended for combination. Arithmetic range-preserving
promotion is not used for these bit operations.

```text
AND(Input,16#FFFF_FFFFu,LowWord);
NOT(16#FFFF_FFFFU,WideComplement);
XOR(Input,16#8000_0000_0000_0000L,ToggleTopBit);
MEQ(Input,2#1000000000000000000000000000000000000000000000000000000000000000UL,16#8000000000000000L)OTE(TopBitSet);
```

Patterns work in either binary position and all three read-only MEQ positions.
All eight integer result types retain low-bit truncation/reinterpretation.
Existing finite REAL/LREAL conversion rules remain: signed inputs may produce
floating results, unsigned inputs to floating destinations stay excluded, and
MEQ remains integer-only. Overwide/invalid words block even false rungs.
Required unknowns, indices, zero masks, full writes and AOI/advance rollback
retain their existing contracts. Explicit radix signs and alternate syntax
remain excluded. [Integer arithmetic and relations/LIM](typed-integer-operands.md#typed-radix-integer-operands)
have a separate profile, as do [ladder BCD sources](numeric-conversions.md#typed-radix-bcd-sources).
Floating radix operations, expression/file/ST, AOI call arguments and SBR/RET
parsing are not extended.

The bitwise viewer interpretation is scoped to these source operands; MOV and
integer arithmetic/ordering have separate qualified profiles.
Unsuffixed bitwise patterns retain their prior monitoring and execution rules.
In **Bit lab**, enable WideMaskEnabled. Existing AND/OR/XOR/NOT/MEQ examples now
use three-base typed masks with their original results. WideMaskFull preserves
the complete input through a signed 64-bit all-ones mask; WideMaskTopMatch tests
bit 63 using unsigned mask and signed comparison patterns. Set WideMaskDivisor
to zero to exercise rollback after all results, then restore one to retry.
This is bounded software execution; native typed-radix import, status/fault and
controller lifecycle acceptance remain unverified.

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
BOOL bitwise forms, MVM/BTD, expression/file/ST/FBD and other
controller profiles remain separate. Native numerical/status/fault/lifecycle
parity remains unverified. The source basis is installed v35 AND (14670), OR
(14687), XOR (14683), NOT (14669), MEQ (14602), Immediate values (14454), and the
existing declared-width integer pattern model. General memory literal parsing
is unchanged; this is bounded software evidence, not native Studio acceptance.

See [width/pattern readers](../source/logixlab/integer_math.py),
[bitwise execution](../source/logixlab/scalar_math.py),
[MEQ execution](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_typed_bitwise_operands.py).
