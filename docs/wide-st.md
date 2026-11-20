# Wide integer Structured Text

App `26.1029.224802` extends the v35 ControlLogix 5580 software profile with
homogeneous LINT, USINT, UINT, UDINT and ULINT expressions in Structured Text.
The [existing ladder profile](integer-execution.md) remains available.

```text
SignedSum:=SignedInput+SignedDelta;
SignedQuotient:=SignedInput/Divisor;
UnsignedComplement:=NOT UnsignedInput;
IF Enable AND (SignedSum>SignedInput) THEN SignedResult:=SignedSum; END_IF;
```

## Types and arithmetic

All numeric tag operands in an expression must have one matching declared type.
A numeric assignment destination must match that type. Literal-only assignments
use the destination's declared wide type. Untyped immediates are signed DINT
integers representable in the selected type. [Decimal L/U/UL literals](st-integer-literals.md)
now provide full-width constants with matching declared types.
[REAL-selected expressions](real-expressions.md#structured-text) use their
own promotion rules. A mixed integer-only expression must still meet the
integer profile's type rules, including in unreachable branches.

Supported operations are addition, subtraction, multiplication, exact integer
division/remainder, integer powers and roots, unary plus/minus, ABS,
AND/OR/XOR/NOT and comparisons. Every
numeric intermediate must fit its declared type. Bitwise operations use that
type's width; unsigned NOT retains the full unsigned result. Quotients truncate
toward zero and remainders retain the dividend's sign. Values above 2^53 remain
exact integers throughout evaluation and appear as decimal text in the tag watch.

Wide comparisons can combine with BOOL operands and logic in assignments,
IF/ELSIF and WHILE/REPEAT. Different numeric widths in one expression remain
unqualified even when they occur in separate comparisons. Split such comparisons
into BOOL results. Operands are evaluated eagerly. A skipped branch does not
execute its body, but a false operand of AND does not suppress a required fault
in another operand.

## Integer powers

Use `**` with matching declared integer types or qualifying literals.
The exponent must be between zero and one less than the type's bit width.
For example, `3UL**40UL` gives 12157665459056928801 with an ULINT result.
Each power must fit its expression type. Chained powers follow the existing
ST left-to-right evaluation at equal precedence. The emulator defines `0**0` as
one and checks powers at execution. An invalid exponent or overflowing
result rolls back the advance. Wide ST uses the existing checked ladder
integer evaluator for power. Native v35 wide exponent behavior remains
unverified.
[Rockwell Structured Text arithmetic operators](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/structured-text-attributes/use-operators-and-functions.html)

## Integer square roots

`SQRT` rounds the square root of the operand's magnitude to the nearest
integer in its declared type. The emulator also accepts `SQR` as an alias
in ST. It uses integer arithmetic throughout, so two adjacent ULINT values
can round to different results even near the top of the type's range. The
existing intermediate range checks apply before evaluating the root.
Native v35 wide square-root behavior remains unverified.
[Rockwell square-root reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/square-root--sqrt-.html)

## Context and failures

Aliases, program-local tags, selected array/UDT members, typed JSR/SBR/RET
parameters and matching AOI Input/Output/InOut bindings use their resolved types.
Nonretentive assignments reset during prescan. Existing aggregate-write and
constant-tag restrictions remain in force.

Overflow, unsigned underflow, unrepresentable ABS/negation, division by zero,
required unknown data and budget exhaustion roll back the whole simulation
advance, including earlier ladder/ST writes and scheduler state. This software
policy does not implement native partial effects, math flags or fault records.

## Integer Lab

Choose **Integer lab** and step. The ladder main routine calls WideText, then
compares the eight numeric results. StAllMatches is true with the default values.
SignedInput is 9007199254740993; both sums are exactly 9007199254740995.
The unsigned sum reaches 18446744073709551615 and its complement example is 1.

StDelta and StDivisor are independent ST inputs. Change StDelta to 3 to see
StAllMatches become false. Restore it to 2 to match again. StDivisor zero causes
a later ST fault after ladder work; correct the input to 3 before retrying.
Enable `RunStPower` to evaluate `3UL**StPowerExponent`. The result is exact
with the default exponent 40. Exponent 41 overflows ULINT and rolls back the
advance. Restore 40 to retry.

Enable `RunStRoot` to evaluate `SQRT(StRootInput)`. The saved input
16000000004000000000 produces 4000000000. Increase the input by one and step
again to see 4000000001.
See [IntegerLab.L5X](../source/samples/IntegerLab.L5X) and
[implementation](../source/logixlab/wide_st.py).

## Remaining qualification

Wide FOR counters/bounds, CASE selectors and array-index expressions remain
blocked. [Narrow ST/CPT/CMP integer division](integer-expressions.md) has a
separate DINT-intermediate profile. Additional wide math functions, mixed
conversions, additional literal forms, wide file-expression consumers, LREAL/time types
and native intermediate/status/fault parity remain unfinished. The controller
gate is an explicit software profile; native Studio/controller acceptance of
these new ST forms has not been demonstrated.

Rockwell's [Structured Text manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm007_-en-p.pdf)
and [General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provide language/operator context. Their complete type/conversion matrix is
broader than this bounded implementation.
