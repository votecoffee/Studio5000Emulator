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
values or matching decimal L/U/UL constants representable in the chosen type;
see [matching typed constants](#matching-typed-constants).

For example, `CMP((WideCount>SmallCount)&&Enabled)` can compare LINT and DINT tags
without losing the sign or exact 64-bit values. Numeric relations `=`, `<>`, `<`,
`<=`, `>` and `>=` can be joined with `&&`, `||`, `^^`, `!`, BOOL AND/OR/XOR/NOT
and BOOL equality/inequality. Both logical operands are consumed, including when
the left operand already determines the truth value. Every required unknown or
invalid index faults rather than being hidden by a known logical operand.

Direct tag/constant comparisons use this profile; arithmetic uses the bounded
profile below. Numeric bitwise mixtures, other functions, REAL/LREAL mixtures,
nonmatching typed or untyped larger literals and lossy type combinations remain blocked even on false
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

Supported mixed operations are `+`, `-`, `*`, `/`, `MOD`, unary signs, `ABS`,
[SQR and bounded integer powers](#mixed-integer-roots-and-powers).
Every arithmetic subexpression must contain an actual source tag of the selected
common type. Thus a LINT Wide and DINT Small permit `(Wide+Small)+1`, while
`Wide+(Small+1)` remains blocked: its inner arithmetic has no LINT source. Unary
signs and ABS follow that same rule. This keeps intermediate widths explicit;
independent lower-type arithmetic, mixed numeric bitwise and other functions
beyond ABS/SQR remain unqualified. Existing homogeneous expressions keep their prior rules.

Every result must fit the selected type. Calculations use exact integers, quotient
truncation toward zero and dividend-sign remainders. A later operation does not
cancel an earlier overflow. Constants may be signed-DINT integers representable
in the selected type, including existing radix spellings within that value range,
or matching decimal L/U/UL constants as described below.
Nonmatching typed, untyped larger or REAL constants, REAL/LREAL mixtures, narrowing and destination-only
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

## Matching typed constants

App `26.1112.224640` extends mixed integer CPT/CMP and FAL/FSC expressions with
decimal L/l, U/u and UL/ul/Ul/uL constants **matching the common actual source
tag type**. The highest-ranked actual source type must still cover all source
ranges. Every arithmetic subtree must contain a source tag of that common type,
and a CPT/FAL destination must match. A literal does not satisfy that subtree
rule, select a wider common type, or permit a signed-to-unsigned conversion.

```text
CPT(Result,Wide+Small+9007199254740993L);
CMP(Wide+Small=9007199254740996L)OTE(Matches);
FAL(Calc,?,?,ALL,Out[Calc.POS],WideArray[Calc.POS]+Small+1L);
FSC(Find,?,?,INC,WideArray[Find.POS]+Small>=9007199254740996L);
```

With Wide/Result LINT and Small DINT, the first expression remains exact above
2^53. A U or UL constant is excluded even if its value would fit LINT. Likewise,
`Wide+(Small+1L)` is excluded because its inner arithmetic has no LINT tag.
LINT minimum, UDINT maximum and ULINT maximum use their declared integer ranges;
immediate unary signs participate in the preflight check. Unknown and invalid
live operands remain lazy, but a malformed/out-of-range constant blocks even
a false rung. Every intermediate and final result must fit.

All existing operators, eager Boolean comparisons, file modes/cursors, exact
AOI bindings, instruction budgets and whole-advance rollback remain. Other
typed mixtures, nonmatching radix forms, implicit promotion, independent lower-width
intermediates and new ST/index forms remain excluded. LREAL selectors retain
their separate binary64 profile. Native type promotion, math status, partial
effects and lifecycle equivalence remain unqualified.

Stats Lab's WideFiles FAL now includes a matching `0L` constant, preserving its
existing default results and WideFileDelta adjustment. Focused cases also use
full-width nonzero constants. See [tests](../source/tests/test_mixed_integer_literals.py)
and [file constants](file-integer-literals.md). The source baseline is installed
v35 Immediate values14454, CPT14597, CMP14592 and FAL/FSC14504/14515;
[Rockwell literal suffixes](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/structured-text-attributes/character-string-literals.html)
provide additional syntax context. The bounded rules above define this software model.

## Typed radix expressions

App `26.1113.065404` accepts attached binary/octal/hexadecimal L/l, U/u and
UL/ul/Ul/uL constants in the qualified integer CPT/CMP/FAL/FSC profiles.
LINT/ULINT use 64-bit patterns, UDINT uses 32, and short patterns zero-fill.
The signed LINT top bit is interpreted before arithmetic; a full all-ones L
is -1, while a shorter `16#FFFFFFFFL` is positive 4294967295. Expression unary
signs apply to that value. Invalid digits, widths and suffix groups block even
false instructions; every intermediate retains the existing range checks.

```text
CPT(Unsigned,16#FFFFFFFFFFFFFFFFUL/2#11UL);
CMP(16#0020000000000000L<16#0020000000000001L)OTE(Exact);
FAL(Calc,?,?,ALL,Output[Calc.POS],Input[Calc.POS]+16#0020000000000001L);
FSC(Find,?,?,INC,Input[Find.POS]>=8#37777777777U);
```

The literal type must match the selected integer type. Mixed source tags retain
the common-actual-tag and arithmetic-subtree rules above; constants cannot
promote tags or replace a required common-type source. REAL/LREAL mixtures,
wide BCD/root/power functions, general ST expressions and array-index arithmetic
remain outside this grammar extension. Default parser instances and general
memory literal reads are unchanged. This profile is integer-only, including
when another operand or the destination could otherwise select binary64.

False/prescan paths skip live values/indices, reached expressions consume all
required sources and Boolean sides, and complete writes establish unknown cells.
File ALL/numeric/INC state, eager FSC tests, AOI bindings and whole-advance
rollback retain their existing contracts. Native import, numerical/status/fault
and lifecycle parity remain unverified.

In **Wide expression lab**, enable ILitEnabled. IntegerConstants now uses all
three bases while retaining its exact results, selected guard, overflow gate
and late-divisor retry. In **Stats lab**, enable WideFiles for radix constants
in the existing mixed LINT transform, unsigned XOR and two searches. Their
previous results and dormant gates are unchanged.

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
a base example and separately gated ladder demonstrations. One step produces:

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

Remaining integer forms include lower-type-only mixed arithmetic subtrees,
additional conversions, nonmatching typed and untyped larger constants, mixed
numeric bitwise, additional mixed root/power forms and other functions beyond the
qualified homogeneous ABS/FRD/TOD/SQR forms in wide expressions. Time/date
expressions and wide arithmetic inside array indices remain unsupported.

[Integer FAL/FSC](integer-files.md), [LREAL CPT/CMP/FAL/FSC](lreal-expressions.md)
and [single wide tag indices](array-index-expressions.md) have separate bounded
profiles. Their support does not establish general numeric promotion or native
status/fault/lifecycle parity. General ladder and ST coverage is still incomplete;
no new FBD/SFC forms are included.

The operand families and operator grammar were checked against the installed
v35 help topics Compute (CPT), Compare (CMP) and Mask Equal To (MEQ), alongside
Rockwell's [General Instructions Reference Manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).

## Unsuffixed DINT radix expressions

The v35 ControlLogix 5580 ladder CPT, CMP, FAL and FSC integer profiles now
decode unsuffixed `2#`, `8#` and `16#` words as 32-bit DINT constants. Shorter
words zero-fill; bit 31 supplies the sign. Underscore digit grouping is accepted.
Thus `16#FFFFFFFF` is -1, `16#80000000` is -2147483648, and
`-16#FFFFFFFF` is 1: expression unary operators follow word decoding.

```text
CPT(Result,Input+16#FFFFFFFF);
CMP(16#80000000<0)OTE(Negative);
FAL(Control,?,?,ALL,Output[Control.POS],Input[Control.POS]+16#FFFFFFFF);
FSC(Control,?,?,ALL,Output[Control.POS]>16#FFFFFFFF);
```

The signed constants retain narrow integer functions, power, bitwise and
division rules. They may also combine with compatible wide tags or matching
typed literals under the existing range and intermediate rules. Every required
source is consumed; unknown values, bounds, overflow and later faults roll back
the modeled advance. False/prescan paths skip live values and dynamic indices,
while malformed words, permissions and static type errors remain blockers.

A word that decodes negative keeps the integer profile by default. An explicit
[LREAL selector](lreal-integer-literals.md#radix-constants) now permits binary64
promotion; REAL-only mixes remain blocked. Default literal parsing, ST, array-index syntax and other instruction
consumers retain their separate contracts. This does not establish native
promotion, status, overflow or partial-effect parity.

In **Wide expression lab**, set DintExprIndex=1 and DintExprEnabled=true.
The DintExpr outputs are Value=6, Quotient=-3, Remainder=-1, Bcd=166666665,
Root=3, Power=4 and Wide=9007199254740992. Match and Negative are true;
Selected[1] becomes 6 with guards 101/999. The gate starts false with index99
dormant. Divisor=0 or LateDivisor=0 demonstrates rollback. Restore 2 or 1,
respectively, before retrying. Disable the gate before restoring index99.

The report publishes `wide_ladder_expressions.signed_dint_radix_expressions`.
Source basis: installed v35 Immediate values (14454), CPT (14597), CMP (14592),
FAL (14504) and FSC (14515). See the existing [scalar-word profile](typed-integer-operands.md)
and [focused expression checks](../source/tests/test_dint_radix_expressions.py).

[Homogeneous wide BCD expressions](cpt-bcd.md#wide-integer-expressions) separately
qualify FRD/TOD in CPT/CMP/FAL/FSC for USINT, UINT, UDINT, LINT and ULINT, using
their selected 8/16/32/64-bit software conversion widths. Mixed numeric tag
widths, REAL/LREAL, ST/index expansion and native parity remain excluded.

## Integer roots and powers

Homogeneous v35 ControlLogix 5580 ladder CPT/CMP/FAL/FSC expressions now accept
SQR and `**` for USINT, UINT, UDINT, LINT and ULINT. Numeric tags and result
types must match; compatible constants keep their existing signed-DINT or
matching L/U/UL literal rules. BOOL condition tags remain allowed.

SQR takes the absolute integer magnitude and rounds its root to the nearest
integer without converting through REAL/LREAL. Adjacent ULINT values
16000000004000000000 and 16000000004000000001 produce 4000000000 and
4000000001, respectively. SQR of the minimum LINT produces 3037000500.
This reuses the existing standalone integer SQR software calculation.

Power uses exact integer arithmetic and nonnegative exponents bounded to one
less than the selected width: 0..7, 0..15, 0..31 or 0..63. Every intermediate
and result must fit the selected type. Zero exponent yields 1, including 0**0.
Negative and fractional exponents remain excluded; standalone XPY retains its
separate rules. Existing expression precedence and left-to-right equal-order
evaluation apply. These explicit bounds do not claim native limit/status parity.

```text
CPT(Root,SQR(Input));
CPT(Power,Base**Exponent);
CMP(SQR(Input)>=Threshold)OTE(Ready);
FAL(Calc,?,?,ALL,Output[Calc.POS],SQR(Input[Calc.POS]));
FSC(Find,?,?,ALL,Input[Find.POS]**2L>=Limit);
```

SQR and powers compose with the existing homogeneous arithmetic, bitwise,
ABS and qualified FRD/TOD forms. Structural preflight, false/prescan lazy reads,
file modes and eager Boolean evaluation are retained. Reached exponent ranges,
required unknowns, bounds, overflow and later faults roll back the advance.
Mixed numeric tag types use the [common-range profile](#mixed-integer-roots-and-powers)
below. Other functions, ST/index expansion and broader controller profiles remain separate. Native precision/status/fault/partial-effect
parity is unverified.

In **Wide expression lab**, set RootPowerIndex=1 and RootPowerEnabled=true.
UnsignedRoot is 4000000000, Power is 16677181699666569, SignedRoot is 4,
Composed is 16, and Match is true. Selected[1] receives UnsignedRoot and guards
101/999 remain. Add 1 to UnsignedInput to observe the adjacent rounding boundary.
Exponent=64 or LateDivisor=0 exercises rollback; restore 34 or 1 before retrying.
The gate starts false with index99 dormant.

Reports publish `wide_ladder_expressions.root_power`. Source basis: installed
v35 CPT/CMP/FAL/FSC tables 14597/14592/14504/14515 and SQR/XPY references
14617/14478. See [focused checks](../source/tests/test_wide_integer_root_power.py).

## Mixed integer roots and powers

The v35 5580 CPT/CMP/FAL/FSC mixed integer profile now supports SQR and bounded
nonnegative `**`. A common actual source tag type must cover every source tag's
complete declared range; the CPT/FAL result must match it. Positive saved values
do not justify signed-to-unsigned conversion. No wider type is invented.

For example, a LINT Base with a DINT Exponent can use `Base**Exponent` without
floating conversion. A LINT Value and DINT Delta can use `SQR(Value)+Delta`
or `SQR(Value+Delta)`. Compatible INT/USINT and DINT/UINT sources also select
their existing INT/DINT common type when this mixed profile applies.

Every arithmetic subtree, including each SQR call and power expression, must
contain an actual source tag of that common type. Thus `SQR(Value)+Delta` is
qualified, while `Value+SQR(Delta)` and `Value**(Exponent+1)` remain blocked:
their inner arithmetic lacks a common-type tag. Compatible constants retain
the existing signed-DINT or matching decimal/radix L/U/UL rules. These are
explicit software restrictions, not a complete native promotion model.

Roots retain exact integer magnitude/nearest-root calculations. Powers retain
the common width's 0..width-1 exponent bound and checked intermediates/results.
Unknowns, invalid indices, exponent limits, overflow and later faults roll back
the advance. False/prescan reads, file modes, eager BOOL composition, aliases and
AOI binding rules are retained. Mixed numeric bitwise and mixed FRD/TOD,
REAL/LREAL, ST/index expansion and native status/precision parity stay excluded.

**Wide expression lab** now uses a DINT RootPowerExponent with its LINT base.
Its gate and index controls are unchanged. RootPowerOffset is DINT 1:
RootPowerShifted is 5, RootPowerScaled is 4 and RootPowerMixedMatch is true.
Set Offset=100 to get 104 and 9. The existing late divisor demonstrates rollback.
Reports expose the source/common-width rules in `wide_ladder_expressions.root_power`
and include SQR/power in `mixed_integer_arithmetic.operators`.
See [focused mixed checks](../source/tests/test_mixed_integer_root_power.py).
