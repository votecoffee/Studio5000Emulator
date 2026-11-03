# Ladder wide integer expressions

App `26.1102.075653` adds bounded ladder `CPT`, `CMP` and `MEQ` forms for
homogeneous `LINT`, `USINT`, `UINT`, `UDINT` and `ULINT` tags in the Standard
v35 ControlLogix 5580 profile (`1756-L81E` through `1756-L85E`). Existing
SINT/INT/DINT/REAL expression and narrow MEQ behavior remains available.
App `26.1103.081017` extends tag-only MEQ to all eight integer types; CPT/CMP
wide expressions retain their homogeneous rules.

Development order is ladder, then Structured Text, then FBD, then SFC. This
increment extends ladder operand forms; it adds no ST, FBD or SFC features.

## Supported forms

```text
CPT(Result,Input+Delta);
CPT(Quotient,Dividend/Divisor);
CMP((Result>Input)&&!Blocked)OTE(ExactCompare);
MEQ(Pattern,Mask,Expected)OTE(MaskMatches);
```

Numeric tags within one wide expression, including the CPT destination, must
have the same declared type. Literals must be signed DINT integers that also
fit that type. Store larger constants in typed tags. CPT can infer its type
from the destination for literal-only expressions. A destination's previous
value may be unknown if the expression does not read it.

CPT supports `+`, `-`, `*`, `/`, `MOD`, `AND`, `OR`, `XOR`, `NOT`, unary signs,
parentheses and `ABS`. Integer arithmetic is exact, including values above
`2^53`. Division truncates toward zero; the remainder has the dividend's sign.
Every numeric intermediate must fit the declared type. Bitwise results use
that type's width and signed interpretation.

CMP adds exact relations `=`, `<>`, `<`, `<=`, `>` and `>=`, BOOL tags and
`&&`, `||`, `^^`, `!`, and BOOL `AND`/`OR`/`XOR`/`NOT`. The existing ladder
expression precedence applies. Both logical operands are evaluated: a true
left side does not conceal unknown data or division by zero on the right.

[Tag-only MEQ](numeric-comparisons.md#mixed-integer-tag-widths) permits mixed
signed/unsigned integer types. Each read-only operand uses its declared pattern
with zero extension before masked equality, including bit 63 and negative LINT
patterns. All three operands must be known even when the mask is zero. Any wide
operand with an immediate retains matching tag types and the bounded immediate
rule above. CPT/CMP expression promotion remains separate.

Aliases, program-local tags, selected array/UDT members, typed JSR parameters
and supported RLL AOI bindings use the same memory resolver. Standard periodic,
instruction-only Event and isolated-routine execution share these forms.

## Scans and faults

A false rung skips expression evaluation. CPT retains its destination on
false rungs and during prescan. Comparison outputs follow ordinary downstream
coil behavior. The instructions add no hidden retained state.

Unknown required values, invalid dynamic indices, divide-by-zero, overflow,
underflow and instruction-budget failures stop and roll back the entire
simulation advance, including earlier writes, task scheduling and traces.
This is the emulator's transactional policy. Native partial effects, math
flags, minor/major faults and intermediate precision still need qualification.

## Try it

Choose **Ladder wide expression lab** or load
[WideExpressionLab.L5X](../source/samples/WideExpressionLab.L5X). It contains
22 controller tags, nine rungs and only ladder routines. One step produces:

| Tag | Expected value |
| --- | --- |
| SignedResult | 9007199254740995 |
| UnsignedResult | 18446744073709551615 |
| SignedQuotient | -3074457345618258602 |
| SignedRemainder | -2 |
| ByteResult | 203 |
| ExactCompare / MaskMatches | true / true |

Set `Execute` false to retain arithmetic results and clear the two comparison
coils. Set it true and set `FaultDivisor` to zero to exercise a late fault;
the scan counter and earlier results roll back. Restore the divisor to one
and step again. The browser exchanges wide values as decimal strings to
preserve their exact value.

The report's `wide_ladder_expressions` field publishes the profile and limits.
Focused model and HTTP checks exercise exact values, masks, references, AOIs,
scan modes and recovery. They do not establish native Studio/controller parity
or native import acceptance of the public fixture.

## Remaining work

Mixed arithmetic/expression types and their conversion rules, wide immediate
syntax, LREAL/time expressions, power and other functions, wide file-expression
consumers and wide array indices remain unsupported. General ladder and ST
coverage is still incomplete. No new FBD/SFC forms are included.

The operand families and operator grammar were checked against the installed
v35 help topics Compute (CPT), Compare (CMP) and Mask Equal To (MEQ), alongside
Rockwell's [General Instructions Reference Manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
