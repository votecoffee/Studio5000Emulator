# Scalar arithmetic and bitwise operand selection

The v35 ControlLogix 5580 ladder profile validates these existing operations
without requiring saved scalar values or live indices:

| Arithmetic | Integer bitwise |
| --- | --- |
| ADD, SUB, MUL, DIV, MOD, NEG, ABS | AND, OR, XOR, NOT |

Declared scalar types, references, destination permissions and the existing
homogeneous wide-integer rules remain checked. Invalid shapes, BOOL operands,
unsupported bitwise floating-point forms and mixed wide arithmetic types still
fail static validation, including on false rungs. Standalone bitwise integer tags
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
dividend's sign. Wide arithmetic stays homogeneous and exact. Arithmetic overflow
still stops and rolls back the model rather than reproducing native status and
partial effects.

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
including when the destination is REAL. Homogeneous wide-integer operations
retain their separate profile. Mixed wide/unsigned and REAL operands, LREAL,
complete mixed-type arithmetic, mixed-wide/typed bitwise immediates and floating-point bitwise forms,
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
