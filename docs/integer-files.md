# Wide integer file operations

App `26.1103.195250` adds LINT, USINT, UINT, UDINT and ULINT expressions to
the bounded v35 L81E–L85E ladder FAL/FSC profiles. Narrow integer and REAL
behavior remains available. FAL/FSC are not new ST or FBD calls.

FAL uses the existing exact-integer evaluator with a matching declared numeric
tag type and destination type. Basic arithmetic, bitwise operations, unary
signs and ABS are supported. Literal-only expressions use the destination
type. Immediates remain signed DINT integers representable in that type.
Every intermediate must fit; quotient truncates toward zero and remainder
keeps the dividend's sign. Bitwise patterns retain their declared width.

```text
FAL(Calc,?,?,ALL,Result[Calc.POS],Input[Calc.POS]*Gain+1);
FSC(Find,?,?,ALL,Input[Find.POS]>=Threshold);
```

FSC shares the existing wide/mixed CMP profile, including eager BOOL composition
and range-preserving integer comparisons. Mixed arithmetic must contain the
common source type in every arithmetic subtree. See the separate
[ladder expression profile](ladder-wide-expressions.md).
[Binary64 FAL](file-arithmetic.md#binary64-expressions) provides a separate
LREAL-selected profile. Other mixed promotions, typed radix, wider integer
power and additional functions remain unqualified.

## Iteration and state

ALL, positive numeric modes and idle-source INC retain their existing CONTROL
contracts. Numeric operations can continue on false rungs while active; INC
requires observed enable edges. Done/inhibited calls do not consume unused
expression data. Unknown complete destinations can be established, while
required unknown inputs or invalid addresses fault. Data references resolve
at each iteration; overlapping reads see earlier writes.

Existing alias/member/indirect selections and qualified RLL AOI InOut/local
arrays share the profile. Exact AOI binding types still apply. CONTROL addresses,
LEN/POS/flags, the idle saved INC qualification, 4096-element work limit and
global instruction budget remain required. No hidden native INC state is
inferred. See [FAL](file-arithmetic.md), [FSC](file-search.md),
[INC](file-incremental.md) and [AOI file operations](aoi-file-operations.md).

Overflow, underflow, zero division, required unknowns, invalid selections and
later errors roll back the whole advance, including values, CONTROL flags,
incremental progress, time and scheduler state. These are simulator faults;
native status bits, partial effects, precision/cursor/lifecycle and packed-layout
parity remain unverified.

## Stats lab

Enable WideFiles and Step. WideFileOperations transforms two LINT values above
2^53 with matching WideFactor=2 and adds one, producing
18014398509481987 and 18014398509481989. Its unsigned XOR example preserves the
ULINT maximum's low-bit change as 18446744073709551614 and transforms
9007199254740993 to 9007199254740992. Values remain exact in the runtime and
browser's integer-string transport. Third destination elements remain unknown.

The two FSC examples find the second element, distinguishing adjacent 64-bit
values and the ULINT maximum. Their IN/DN latches retain the existing behavior.
Held completed transforms skip new operands; disable WideFiles and Step to
rearm them. Search IN must be cleared separately before its normal cleanup.

The operand baseline is the installed v35 FAL/FSC help, pages 14504/14515,
which list wide/unsigned types for ControlLogix 5580. Rockwell's published
[FAL reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-arithmetic_logic-fal.html)
and [FSC reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/array-file-misc-instructions/file-search-and-compare-fsc.html)
provide context. Operand availability does not establish complete native
arithmetic, scan, fault or Studio compatibility.

[Decimal L/U/UL constants in FAL/FSC](file-integer-literals.md) now cover
matching LINT/UDINT/ULINT expressions, with exact arithmetic/comparisons and
existing ALL/numeric/INC progress, lazy selection and whole-advance rollback.
Mixed typed forms, floating/radix/file-argument expansion and native parity
remain separate.
