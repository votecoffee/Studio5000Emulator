# Scalar arithmetic and bitwise operand selection

[Typed bitwise operands](typed-bitwise-operands.md) extend the integer pattern
profile in app `26.1104.182610`: decimal L/U/UL constants preserve their declared
widths in AND/OR/XOR/NOT/MEQ. The arithmetic range-preservation rules remain
separate from these bit-pattern conversions.

[Typed integer operands](typed-integer-operands.md) extend this profile in app
`26.1104.180138`: decimal L/U/UL constants participate in the existing complete
source-range checks and exact integer calculations. Other consumer and narrowing
profiles retain their scope.

The v35 ControlLogix 5580 ladder profile validates these existing operations
without requiring saved scalar values or live indices:

| Arithmetic | Integer bitwise |
| --- | --- |
| ADD, SUB, MUL, DIV, MOD, NEG, ABS | AND, OR, XOR, NOT |

Declared scalar types, references, destination permissions and the existing
homogeneous wide/immediate rules remain checked, with the widening tag/constant
arithmetic extension below. Invalid shapes, BOOL operands, unsupported bitwise
floating-point forms and excluded arithmetic type mixes still fail static
validation, including on false rungs. Standalone bitwise integer tags
use the separate mixed-type profile below.

False rungs and ordinary prescan skip operand values and dynamic indices. A true
instruction consumes every required source value. Its complete numeric write
can establish an unknown destination element or member without reading the old
value. Aliases and existing AOI InOut/local bindings use the same storage rules.
Unwritten siblings remain unknown. Reached unknowns, invalid indices, zero
divisors, excluded ranges and later faults roll back the complete advance,
including values, task/time state and existing AOI bindings.

Structural validation and operand selection apply to all eleven operations.
Integer division into integer destinations truncates toward zero; integer remainder retains the
dividend's sign. Wide homogeneous and qualified widening-tag arithmetic stay exact. Arithmetic overflow
still stops and rolls back the model rather than reproducing native status and
partial effects.

## Widening integer tag arithmetic

Standalone ADD, SUB, MUL, DIV, MOD, NEG and ABS may mix integer tag types when
the destination can represent the **complete declared range** of each source.
This is a v35 5580 ladder profile. It does not infer eligibility from the current
saved values. Signed values keep their sign, unsigned values keep their numeric
value, and no floating-point conversion occurs.

| Destination | Source types whose complete range it covers |
| --- | --- |
| SINT | SINT |
| USINT | USINT |
| INT | SINT, USINT, INT |
| UINT | USINT, UINT |
| DINT | SINT, USINT, INT, UINT, DINT |
| UDINT | USINT, UINT, UDINT |
| LINT | SINT, USINT, INT, UINT, DINT, UDINT, LINT |
| ULINT | USINT, UINT, UDINT, ULINT |

This extends mixed forms involving LINT or unsigned tags. Existing narrow and
homogeneous rules remain available separately. For example, adding DINT -1 to
UDINT 4294967295 into LINT produces 4294967294; negating USINT 255 into INT
produces -255. ABS of DINT -2147483648 into LINT produces 2147483648.
DIV truncates toward zero; MOD follows the dividend's sign. Results must fit the
destination even when its type covers all source ranges: overflow/underflow and
zero divisors stop and roll back the entire advance under the model policy.
Native overflow bits, minor faults and partial destination effects are not modeled.

Structural checks apply even to false rungs. False/prescan skip live values and
indices; true instructions require each source and may establish an unknown
scalar destination. Selected array elements, UDT members, aliases and existing
AOI InOut/local bindings share these rules. Late faults restore prior writes,
unknown siblings, scheduler state and AOI bindings.

Enable **MixedArithmetic** in **Integer lab** for eight gated examples, including
LINT/DINT exact sums, quotient/remainder, signed/unsigned products, widening NEG/ABS
and an ULINT/USINT difference. The report exposes `scalar_math.widening_arithmetic`.

Larger/typed arithmetic constants, narrowing, mixed signed-to-unsigned destinations, REAL/LREAL
mixtures, complete instruction/ST/CPT/CMP promotion and other controller families
remain separate qualification work. Homogeneous wide immediates keep their
existing signed-DINT, representable-value rules. ST and FBD are unchanged.
Installed v35 Data Conversions (14451) supplies the integer rank/sign-extension
basis; model validation does not establish native runtime equivalence.

## Bounded arithmetic constants

Widening ladder ADD, SUB, MUL, DIV and MOD also accept integer constants mixed
with tag types. Source tags must still have their complete declared ranges
covered by the destination. Each constant must be within signed DINT range
(-2147483648 through 2147483647) and representable in the destination. Its known
value is checked; a positive saved value in a signed tag does not relax the tag
range rule. Both source positions work, retaining noncommutative operand order.

For example, DINT `Count` plus literal 1 into LINT `Total` is supported. USINT 255
plus 1 into UINT gives 256. DIV of DINT -7 by literal 3 into LINT produces -2;
MOD produces -1. Reversing the operands gives 0 and 3 respectively. Integer
calculations never pass through REAL. Existing NEG/ABS and homogeneous constant
forms retain their signed-DINT, destination-representability limits.

False/prescan skip live values and indices, but invalid constant/type/permission
combinations remain static blockers even on false rungs. Multiplication by zero
still requires the tag source; unknown data is not folded away. Full writes can
establish unknown destinations through arrays, UDT members, aliases and AOI
InOut/local bindings. Zero divisors, overflow/underflow, bad indices, unknowns and
later faults retain whole-advance rollback, including AOI bindings and siblings.

Enable **ArithmeticConstants** in **Integer lab** for eight examples, including
reversed operands, unsigned widening, the minimum DINT constant, and existing
ABS behavior. The report includes the constant contract under
`scalar_math.widening_arithmetic.constants`.

Larger decimal constants, typed RLL literals, radix patterns above signed-DINT
range, REAL/LREAL constants, negative constants into unsigned destinations and
tag narrowing or signed-to-unsigned promotion remain unqualified. Use typed tags
for larger values. Existing narrow/homogeneous rules remain separate. ST/CPT/CMP,
bitwise and FBD rules are unchanged; native status, fault and intermediate parity
are not established.

## SINT/INT/DINT bitwise widths

Ladder `AND`, `OR`, `XOR` and `NOT` use declared SINT/INT/DINT source widths.
Smaller source patterns are zero extended before the operation. The result keeps
the destination's low 8/16/32 bits, interpreted as its signed integer type. A
complete result write can establish an unknown destination without reading its
old value. Full SINT/INT/DINT source/result width combinations are modeled.

For example, a SINT value of -1 contributes the pattern 255. OR with a DINT
value of 256 produces 511 in a DINT destination. `NOT` performs complement after
promotion: SINT -1 into DINT becomes -256. A DINT value of 255 complemented into
SINT becomes 0; upper bits are discarded instead of causing a modeled range
fault. Native overflow/math flags remain unqualified.

Immediates are signed decimal DINT values or complete 32-bit binary/octal/hex
patterns. `-1` and `16#FFFF_FFFF` both supply 32 one bits. Larger patterns,
out-of-range decimal literals, REAL/BOOL operands, invalid shapes and constant
destinations remain blocked, even on false rungs. Every enabled source is still
required, including an unknown input combined with a zero mask. False/prescan
skip live values/indices. Unknowns, reached invalid indices and later faults roll
back the whole advance and existing AOI bindings.

The narrow forms retain their existing immediate rules. Wide operands with
immediates use the separate homogeneous profile described below. Floating-point
bitwise operands and native status/fault/lifecycle/packed layout qualification
remain unfinished. ST expressions and FBD are unchanged.

Choose **Bit lab** and enable `BitwiseWidths`. Its default inputs produce
`AndWidths` 0, `OrWidths` 131071, `XorWidths` 65791, `NotWidened` -256 and
`NotNarrowed` -1. The report describes this profile under `scalar_math.bitwise`.

## Mixed integer tag widths

When all operands are tags, standalone ladder AND/OR/XOR/NOT may combine
SINT, INT, DINT, LINT, USINT, UINT, UDINT and ULINT sources and destinations.
Selected elements, members, aliases and existing AOI bindings use their declared
types. Source patterns are zero extended; NOT complements after promotion. The
result keeps the destination's low bits and uses its signed/unsigned
interpretation. All calculations stay integer-exact, including 64-bit values
beyond browser-safe numeric precision. LINT/ULINT watches use decimal text.

For example, SINT -1 contributes the bit pattern 255 when ORed with an ULINT value.
NOT of that SINT into ULINT produces 18446744073709551360. XOR of LINT -1 and
UDINT 65536 into LINT produces -65537. Narrowing an all-one LINT into USINT
produces 255. These logical bit conversions do not use arithmetic sign extension.

Literal handling remains deliberately bounded. If any operand is LINT or unsigned
and an immediate is present, the existing homogeneous rules still apply: all tag
operands and destination must match, and the signed-DINT immediate must fit that
type. Negative unsigned immediates, full 32-bit radix patterns above signed DINT
in these wide forms, mixed-wide/immediate combinations and typed/wider immediates
remain unqualified. The existing narrow forms retain their signed decimal DINT/
32-bit radix-pattern rules. Arithmetic, CPT/CMP/MEQ, ST and FBD keep separate rules.

Structural validation, false/prescan skipping, required true-source reads, full
unknown writes and whole-advance/AOI rollback remain. Invalid indices, unknown
sources and later faults restore exact values and bindings. Integer bitwise
sources are required even if another source is zero. REAL/LREAL, native status/
fault/lifecycle/packed layouts and broader controller profiles remain unqualified.

Choose **Bit lab** and enable `MixedBitwise`. Defaults produce `MixedAnd` 0,
`MixedOr` 9007199254741247, `MixedXor` -65537, `MixedNot` 18446744073709551360
and `MixedLow` 255. The mask tag is `MixedDwordMask`. Existing demos remain.

## Finite REAL remainder

Ladder `MOD` accepts SINT/INT/DINT/REAL sources and SINT/INT/DINT/REAL results
within the v35 5580 profile. A REAL source or floating immediate selects REAL
calculation: convert both inputs to float32, compute a finite remainder using
host `fmod`, then round the result to float32. The remainder follows the
**dividend's sign**, even when the divisor is negative. For example,
`MOD(-7.5,2.0,Result)` produces -1.5; this differs from floor-based modulo.

Integer destinations use nearest-integer conversion, with halfway results
rounded to even. A remainder of -1.5 becomes -2; 2.5 becomes 2. Results outside
the destination's range stop and roll back the complete advance. Full writes
can establish unknown destination elements/members through aliases and AOI
bindings, retaining unwritten siblings. A late fault also restores earlier
remainder writes and existing AOI bindings.

Sources and results must be finite. Zero divisors, including nonzero immediates
that round to float32 zero, stop and roll back. The native zero-result/minor-fault
behavior is not modeled. The host remainder avoids forming a quotient, allowing
very small nonzero divisors without quotient overflow or cancellation; native
intermediate rounding and bit-for-bit results remain unqualified.

Two integer sources retain the existing exact quotient/remainder calculation,
including when the destination is REAL. Homogeneous wide-integer and widening integer-tag operations
retain their separate profiles. Mixed wide/unsigned and REAL operands, mixed LREAL forms,
arithmetic narrowing/larger or typed constants/signed-to-unsigned promotion, mixed-wide/typed bitwise immediates and floating-point bitwise forms,
native overflow/status/fault/lifecycle and packed layout parity remain unfinished.
Other controller profiles retain their separate validation paths.

Choose **Math lab** and enable `BasicMath`. `BasicA` and `BasicB` drive eleven
named results for the operations above. Start with 7 and 3 to see sum 10,
quotient 2, remainder 1 and complement -8. The original advanced-math and called
ST examples remain available. Enable `RealModulo` separately to calculate
`ModuloA` (-7.5) modulo `ModuloB` (2): `ModuloResult` is -1.5 and
`ModuloRounded` is -2. The report exposes the profile as `scalar_math`, including
its `real_remainder` contract.

Reference basis: installed Studio 5000 v35 instruction help for these eleven
instructions, including DIV 14621, MOD 14620, NOT 14669, AND 14670, XOR 14683,
OR 14687 and Data Conversions 14451. The
[public MOD reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/modulo--mod-.html)
provides additional context; installed v35 help is the version-specific basis.
Software-model and HTTP checks do not establish native controller equivalence.

[Matching-tag LREAL ladder math](lreal-math.md) adds a separate finite binary64
profile for seven basic operations and six direct relations/LIM.
[Mixed-tag binary arithmetic](mixed-lreal-math.md) additionally promotes numeric
tags when at least one input and the result are LREAL. Other mixed forms,
immediates, ST/CPT/CMP and native precision/status/lifecycle parity remain open.

[Integer constants with LREAL](lreal-constants.md) additionally qualify signed
DINT-range literals for binary arithmetic, direct relations and LIM. Floating,
typed and larger literals remain excluded. Direct ordering still requires a
LREAL input; arithmetic can use the [LREAL result](lreal-destination-math.md).

[LREAL arithmetic results](lreal-destination-math.md) additionally select binary64
for basic arithmetic and XPY without a LREAL source, including bounded
constant-only calls. Direct ordering still requires a LREAL input for binary64.

[REAL-result math](real-destination-math.md) additionally selects float32
inputs and result for arithmetic, XPY and eleven unary forms, across all nine
integer/REAL source types and bounded integer/finite floating constants.
A REAL tag or floating immediate also selects float32 for [LINT and unsigned results](real-destination-math.md#wide-and-unsigned-integer-results).
An LREAL input takes priority and selects [binary64 calculation](lreal-math-literals.md#real-and-integer-results)
before conversion to the declared REAL or integer result.
