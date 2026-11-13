# Ladder wide integer expressions

App `26.1102.075653` adds bounded ladder `CPT`, `CMP` and `MEQ` forms for
homogeneous `LINT`, `USINT`, `UINT`, `UDINT` and `ULINT` tags in the Standard
v35 ControlLogix 5580 profile (`1756-L81E` through `1756-L85E`). Existing
SINT/INT/DINT/REAL expression and narrow MEQ behavior remains available.
App `26.1103.081017` extends tag-only MEQ to all eight integer types.
App `26.1103.113157` adds direct mixed integer CMP conditions;
`26.1103.151913` adds bounded mixed CPT/CMP arithmetic as described below.

Development order is ladder, then Structured Text, then FBD, then SFC. This
increment extends ladder operand forms; it adds no ST, FBD or SFC features.

## Supported forms

```text
CPT(Result,Input+Delta);
CPT(Quotient,Dividend/Divisor);
CMP((Result>Input)&&!Blocked)OTE(ExactCompare);
MEQ(Pattern,Mask,Expected)OTE(MaskMatches);
```

Homogeneous wide expressions use matching numeric tag types, including the CPT
destination. The mixed profiles below have separate range and intermediate rules. Literals must be signed DINT integers that also
fit that type. Matching decimal [L/U/UL constants](ladder-integer-literals.md)
now cover the full LINT, UDINT and ULINT ranges in direct CPT/CMP. CPT can infer its type
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

[MEQ](numeric-comparisons.md#mixed-integer-tag-widths) permits mixed
signed/unsigned integer types and bounded plain or typed immediates. Each
read-only operand uses its declared pattern, including bit 63 and negative
LINT patterns. All three operands must be known even when the mask is zero.
CPT/CMP expression promotion follows its own rules.

Aliases, program-local tags, selected array/UDT members, typed JSR parameters
and supported RLL AOI bindings use the same memory resolver. Standard periodic,
instruction-only Event and isolated-routine execution share these forms.

## Mixed integer CMP

CMP accepts compatible mixed integer tags for direct comparisons and Boolean
composition in the v35 5580 profile. The highest-ranked numeric tag type in the
**whole expression** must cover every numeric tag's complete declared range.
Rank order is SINT, USINT, INT, UINT, DINT, UDINT, LINT, ULINT. No larger type is
invented and positive saved values do not justify signed-to-unsigned conversion.
BOOL tags do not select the numeric type. Integer immediates must be signed-DINT
values representable in the chosen type.

For example, `CMP((WideCount>SmallCount)&&Enabled)` can compare LINT and DINT tags
without losing the sign or exact 64-bit values. Numeric relations `=`, `<>`, `<`,
`<=`, `>` and `>=` can be joined with `&&`, `||`, `^^`, `!`, BOOL AND/OR/XOR/NOT
and BOOL equality/inequality. Both logical operands are consumed, including when
the left operand already determines the truth value. Every required unknown or
invalid index faults rather than being hidden by a known logical operand.

Direct tag/constant comparisons use this profile; arithmetic uses the bounded
profile below. Numeric bitwise mixtures, other functions, REAL/LREAL mixtures,
wider/typed literals and lossy type combinations remain blocked even on false
rungs. Homogeneous and narrow/REAL calculations, ST and MEQ remain separate. Expression-wide qualification is deliberately conservative; independently
safe subexpressions do not bypass an incompatible whole-expression type set.

Wide CMP preflight checks scalar shapes, static references, constant bounds and
index grammar structurally. Unknown saved operands and dynamic indices can remain
until a true rung reaches them; literal out-of-range indices remain blockers.
False rungs/prescan skip live values and indices while downstream OTE clears.
Sources remain read-only through constant tags, aliases, UDT members and supported
AOI Input/InOut/local bindings. Runtime faults restore prior writes/coils,
scheduler state and AOI bindings; completed deferred prescan remains a separate
lifecycle boundary. These checks establish software behavior, not native parity.

Enable **MixedConditions** in **Integer lab** for eight gated examples. Six outputs
start true; `MixedConditionGate` and `MixedConditionExact` start false. Enabling
`MixedRelations` makes the BOOL-gated result true. Setting `RelationHigh` to
9007199254740993 makes the adjacent-value comparison true. Disabling MixedConditions
clears all eight outputs. The report exposes
`wide_ladder_expressions.mixed_integer_comparisons`.

## Mixed integer arithmetic

CPT and CMP accept bounded mixed integer arithmetic in Standard v35 ControlLogix
5580 projects. The highest-ranked **actual numeric source tag type** in the whole
expression must cover every source tag's complete declared range. CPT's destination
must match that source type. Destination context and constants do not invent a
larger source type; positive saved values do not justify lossy signed/unsigned
conversion. Types rank SINT, USINT, INT, UINT, DINT, UDINT, LINT, ULINT.

Supported mixed operations are `+`, `-`, `*`, `/`, `MOD`, unary signs and `ABS`.
Every arithmetic subexpression must contain an actual source tag of the selected
common type. Thus a LINT Wide and DINT Small permit `(Wide+Small)+1`, while
`Wide+(Small+1)` remains blocked: its inner arithmetic has no LINT source. Unary
signs and ABS follow that same rule. This keeps intermediate widths explicit;
independent lower-type arithmetic, mixed numeric bitwise and functions beyond
ABS remain unqualified. Existing homogeneous expressions keep their prior rules.

Every result must fit the selected type. Calculations use exact integers, quotient
truncation toward zero and dividend-sign remainders. A later operation does not
cancel an earlier overflow. Constants remain signed-DINT integers representable
in the selected type, including existing radix spellings within that value range.
Larger/typed/REAL constants, REAL/LREAL mixtures, narrowing and destination-only
promotion remain outside this mixed profile. [FAL](integer-files.md#mixed-integer-fal)
now shares these rules. ST and index consumers do not expand. Native intermediate, flags, fault and partial-effect parity are unverified.

Structural preflight and false/prescan selection follow the rules below. Enabled
expressions consume every required source, including a source multiplied by zero
or an arithmetic operand on the right of a known Boolean result. Complete CPT
writes establish unknown selected results; self-read results must first be known.
Source aliases, constants and UDT/AOI members stay read-only. Faults restore the
whole runtime advance, including prior writes, scheduler state and AOI bindings.
The report describes this under `wide_ladder_expressions.mixed_integer_arithmetic`.

Enable **MixedExpressionMath** in **Ladder wide expression lab** for eight numeric
results and one arithmetic condition: sums, differences, products, exact minimum-
LINT quotient/remainder, unsigned subtraction, ABS and nested arithmetic. Set
`ExpressionDelta` to zero while enabled to test rollback, then restore it to 3.
Disabling the gate retains numeric outputs and clears `MixedExpressionMatches`.

## Scans and faults

A false rung skips expression evaluation. CPT retains its destination on
false rungs and during prescan. Comparison outputs follow ordinary downstream
coil behavior. The instructions add no hidden retained state.

Unknown required values, invalid dynamic indices, divide-by-zero, overflow,
underflow and instruction-budget failures stop and roll back the entire
simulation advance, including earlier writes, task scheduling and traces.
This is the emulator's transactional policy. Native partial effects, math
flags, minor/major faults and intermediate precision still need qualification.

Numeric CPT/CMP also use [structural calculation preflight](integer-expressions.md#operand-selection)
in the v35 5580 profile. Saved unknown inputs/results and dynamic indices are
consumed only on enabled rungs. Existing calculations and type rules stay in
force; full CPT writes establish selected unknown results without reading them.

## Try it

Choose **Ladder wide expression lab** or load
[WideExpressionLab.L5X](../source/samples/WideExpressionLab.L5X). It contains
42 controller tags, twenty-two rungs and only ladder routines. One step produces:

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

Additional arithmetic intermediates and expression conversions, wide immediate
syntax, LREAL/time expressions, power and other functions, wide file-expression
consumers and wide array indices remain unsupported. General ladder and ST
coverage is still incomplete. No new FBD/SFC forms are included.

The operand families and operator grammar were checked against the installed
v35 help topics Compute (CPT), Compare (CMP) and Mask Equal To (MEQ), alongside
Rockwell's [General Instructions Reference Manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
