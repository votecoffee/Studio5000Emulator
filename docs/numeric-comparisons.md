# Numeric ladder comparisons

[Typed bitwise operands](typed-bitwise-operands.md) extend the integer pattern
profile in app `26.1104.182610`: decimal L/U/UL constants preserve their declared
widths in AND/OR/XOR/NOT/MEQ. The arithmetic range-preservation rules remain
separate from these bit-pattern conversions.

[Typed integer operands](typed-integer-operands.md) extend this profile in app
`26.1104.180138`: decimal L/U/UL constants participate in the existing complete
source-range checks and exact integer calculations. Other consumer and narrowing
profiles retain their scope.

The v35 ControlLogix 5580 software profile validates EQU, NEQ, LES, LEQ, GRT,
GEQ, LIM and MEQ structurally. Saved numeric values may remain unknown at import.
Declared types, scalar shape, static references and existing immediate/profile
restrictions are still checked, even on false rungs.

False rungs and ordinary prescan skip operand values and live indices. Downstream
OTE instructions still clear their coils when rung power is false. True calls
consume every comparison operand; reached unknowns or invalid indices fail the
advance. A zero MEQ mask does not infer a result from unknown operands. Earlier
writes, coils, task/time state and existing AOI bindings roll back on failure.

## Mixed integer ordering and limits

Standalone EQU, NEQ, LES, LEQ, GRT, GEQ and LIM accept mixed integer tags in the
v35 5580 profile when the highest-ranked operand type can represent the complete
declared range of every input. The rank, from low to high, is SINT, USINT, INT,
UINT, DINT, UDINT, LINT, ULINT. A larger common type is not invented when no
operand has that type; saved values do not relax declared-range checks.

For example, DINT -1 compares less than LINT 4294967295; UDINT 4294967295 equals
LINT 4294967295. UINT 65535 compares greater than DINT -1. INT/USINT and all-
unsigned width mixtures can retain their numeric values. SINT/USINT, DINT/UDINT
and LINT/ULINT pairs remain blocked because their highest-ranked unsigned type
cannot represent every negative source value. Adding an actual LINT operand to
a LIM can cover DINT/UDINT ranges; adding ULINT cannot cover a signed tag's range.

No floating-point conversion or bitwise zero extension is used. Comparands are
read-only, including constant tags, selected array/UDT members, program aliases
and AOI Input/InOut/local bindings. LIM remains inclusive: reversed limits select
values at or outside the endpoints, and equal endpoints select only that value.
Mixed narrow/wide limits retain exact adjacent 64-bit values.

Structural validation permits unknown saved values. False/prescan skip operand
values and dynamic indices, and downstream OTE coils still clear. Reached true
comparisons consume every operand, including a missing high limit when another
comparison already appears false. Unknowns, bad indices and later faults restore
prior writes/coils, task/time state and AOI bindings. Source values are not written.

Homogeneous and existing narrow/REAL rules remain separate. Mixed limits also
accept bounded constants as described below. Lossy signed/unsigned conversion,
REAL/LREAL mixtures, ST/CPT/CMP/FBD forms, other targets and native status/fault/
lifecycle parity remain unqualified. MEQ uses the separate bit-pattern rules below.
The report exposes `numeric_comparisons.mixed_integer_ordering`.

Enable **MixedRelations** in **Integer lab** for six relation and three limit
examples. Initially the six relations and `RelationInRange` are true;
`RelationExactLimit` and `RelationReversed` are false. Raising `RelationHigh` to
9007199254740993 makes the exact limit true. Setting `RelationTest` to 2 or 8
makes the reversed limit true. Disabling the gate clears all nine coils.

## Bounded constants in mixed limits

LIM can combine two different integer tag types with a constant in the Low,
Test or High position. For example, `LIM(0,WideValue,UpperLimit)` accepts a LINT
Test tag and a DINT High tag. `LIM(LowLimit,5,HighLimit)` accepts DINT/LINT limit
tags. Each constant must be an integer in signed DINT range and representable
in the highest-ranked **tag** type. Decimal and existing binary/octal/hexadecimal
integer spellings follow this same value rule; radix patterns above signed DINT
range do not acquire a negative interpretation.

Constants do not select a larger common type or relax complete tag-range checks.
Thus a zero constant cannot authorize a DINT/UDINT or LINT/ULINT mixture, and a
negative constant cannot be used with a highest-ranked unsigned tag type. Larger,
typed and REAL/LREAL constants remain outside this mixed profile. Homogeneous
LIM, binary comparison immediates and narrow/REAL rules keep their respective
profiles. MEQ uses the bit-pattern rules below.

A known Test or limit does not skip another required unknown operand. False
rungs and ordinary prescan skip values and live indices; true LIM consumes every
source. Comparands stay read-only, including aliases and AOI sources. Scan faults
roll back runtime changes; completed deferred prescan effects precede that scan
transaction and remain visible. Native lifecycle equivalence is unverified.

Enable **RelationConstants** in **Integer lab** for eight gated examples. Six
outputs start true; `LimitConstantReversed` and `LimitConstantExact` start false.
Setting `RelationTest` to 2 makes the reversed endpoint true. Setting `SignedInput`
to 65535 makes the exact-value test true. The original value 9007199254740993
remains exact when it exceeds the UINT high limit. Disabling the gate clears all
eight outputs. The report describes this boundary in
`numeric_comparisons.mixed_integer_ordering.constants`.

## Mixed integer tag widths

App `26.1103.081017` allows all tag-only combinations of SINT, INT, DINT, LINT,
USINT, UINT, UDINT and ULINT in ladder MEQ for the v35 ControlLogix 5580 profile.
Source, Mask and Compare are read-only inputs: constant tags, aliases, selected
array/UDT members and existing AOI Input/InOut/local bindings are accepted.
Each declared pattern is zero-extended before comparing `(Source & Mask)` with
`(Compare & Mask)`. Negative DINT values retain 32 bits when combined with a
64-bit operand; negative LINT values retain 64 bits. No floating-point conversion
is used, so adjacent 64-bit values remain distinguishable.

For example, SINT -1 under a ULINT mask of 65536 matches LINT 0, because the
byte pattern contains only eight set bits. DINT -1 under LINT -1 matches ULINT
4294967295, rather than the full 64-bit all-ones pattern.

[Plain and typed immediates](typed-bitwise-operands.md#plain-immediates-with-wide-tags)
also mix with all eight types. The mask, source and compare operands each
accept signed DINT and 32-bit radix constants. For example,
`MEQ(Source,16#FFFF_FFFF,1)` tests the low 32 bits of a ULINT or LINT source.
Previously accepted homogeneous LINT calls preserve their existing signed
immediate promotion. REAL/LREAL operands remain outside MEQ's integer profile.

LIM includes both endpoints; reversed low/high limits select the outside ranges.
Equal limits select the single matching value.

Arithmetic comparisons keep their existing numeric conversion rules. Complete
arithmetic promotion and native status/fault/lifecycle behavior remain unqualified.
Other controller profiles and
string comparisons keep their separate paths. No ST call or FBD form is added.
The API report exposes this bounded profile under `numeric_comparisons`.

Choose **Data lab** and enable `CompareEnable`. `MaskedMatch`, `InRange` and
`CompareEqual` show masked, range and ordinary equality tests. With the gate
false, set `CompareIndex` outside the array and step: the coils clear without
consuming the invalid index. Enabling the gate then reports a modeled fault;
correct the index to retry.

Enable `MixedCompare` for three additional examples. Initially `MixedMaskMatch`
is true and `MixedExactMatch`/`MixedWidthMatch` are false. Set `MixedExpectedExact`
to 9007199254740993 and `MixedExpected` to 4294967295: the exact and width tests
become true and the first test becomes false. Disabling the gate clears all three
coils. Wide tag values are exchanged as decimal strings to retain precision.

Reference basis: installed Studio 5000 v35 **Compare Instructions** (14591),
**Mask Equal To (MEQ)** (14602), and **Limit (LIM)** (14610). The published
[MEQ reference](https://www.rockwellautomation.com/en-nl/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compare-instructions/mask-equal-to--meq-.html)
also documents narrow zero extension and false-rung propagation. Software-model
and HTTP checks do not establish native controller equivalence.

[Mixed LREAL comparisons/LIM](mixed-lreal-comparisons.md) promote numeric tag
inputs to binary64 when at least one input is LREAL. This includes both source
orders and any limit position; large integers can round before comparison.
Immediates and CMP/ST expressions remain separate.

[Matching-tag LREAL ladder math](lreal-math.md) adds a separate finite binary64
profile for seven basic operations and six direct relations/LIM. Other operand forms,
immediates, ST/CPT/CMP and native precision/status/lifecycle parity remain open.

[Integer constants with LREAL](lreal-constants.md) additionally qualify signed
DINT-range literals for binary arithmetic, direct relations and LIM. Floating,
typed and larger literals remain excluded; an actual LREAL source is required.

[REAL comparison promotion](mixed-real-comparisons.md) additionally converts
numeric tag/constant operands to float32 when a REAL tag is present and no
LREAL input selects binary64. Integer-only ordering remains exact.
