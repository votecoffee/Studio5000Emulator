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
LREAL-selected profile. Other mixed promotions, nonmatching typed radix, wider integer
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

## Mixed integer FAL

App `26.1112.223602` extends the existing CPT mixed-integer software rules to FAL
ALL, numeric and qualified INC modes. An actual numeric source tag selects the
highest-ranked type: SINT, USINT, INT, UINT, DINT, UDINT, LINT, ULINT. That type
must represent every complete source tag range, and the destination must match
it. Saved positive values do not justify signed-to-unsigned conversions; neither
the destination nor a constant invents a wider source type.

```text
FAL(Calc,?,?,ALL,Result[Calc.POS],Wide[Calc.POS]+DintDelta);
FAL(Calc,?,?,1,Result[Calc.POS],(Wide[Calc.POS]*DintGain)+DintDelta);
```

Supported mixed operations are +, -, *, /, MOD, unary signs and ABS. Every
arithmetic subtree must contain an actual source of the common type, matching
[CPT's existing rule](ladder-wide-expressions.md#mixed-integer-arithmetic).
For LINT Wide and DINT Small, `(Wide+Small)+1` is supported while
`Wide+(Small+1)` is excluded. Integer division truncates toward zero; remainder
keeps the dividend sign. Every intermediate must fit, even when a later operation
would cancel an overflow. Results above 2^53 remain integer-exact.

Signed-DINT constants must fit the selected type. Mixed numeric bitwise,
nonmatching typed or untyped larger/REAL literals, independent lower-type arithmetic subtrees, other
functions/powers, narrowing and additional ST/index forms remain excluded.
Homogeneous typed constants and binary64 expressions retain their separate rules.

Structural preflight checks types without saved values or dynamic indices.
False/held/completed calls retain existing lazy behavior; active numeric work
can continue on a false rung. Sequential reads/writes, exact AOI bindings,
CONTROL progress, work budgets and whole-advance rollback remain. Integer
overflow still follows rollback; the separate REAL ER/retry profile is unchanged.
Native intermediate widths, status/faults, partial effects, cursor and lifecycle
parity remain unqualified. See [focused cases](../source/tests/test_mixed_integer_files.py).

[Matching typed constants](ladder-wide-expressions.md#matching-typed-constants)
can also accompany mixed integer source tags. They must match the actual common
source type and do not replace the common-tag requirement for each subtree.

## Stats lab

Enable WideFiles and Step. WideFileOperations transforms two LINT values above
2^53 with LINT WideFactor=2 and DINT WideFileDelta=1, producing
18014398509481987 and 18014398509481989. Its unsigned XOR example preserves the
ULINT maximum's low-bit change as 18446744073709551614 and transforms
9007199254740993 to 9007199254740992. Values remain exact in the runtime and
browser's integer-string transport. Third destination elements remain unknown.

The two FSC examples find the second element, distinguishing adjacent 64-bit
values and the ULINT maximum. Their IN/DN latches retain the existing behavior.
Change WideFileDelta to adjust the mixed-integer result on the next rearmed
transform. Held completed transforms skip new operands; disable WideFiles and Step to
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
[Matching typed radix constants](ladder-wide-expressions.md#typed-radix-expressions)
also preserve the same integer types, ALL/numeric/INC state and rollback.
Other mixed typed forms, floating/radix mixtures, file-argument expansion and native parity
remain separate.
