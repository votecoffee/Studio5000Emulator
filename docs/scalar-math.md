# Scalar arithmetic and bitwise operand selection

The v35 ControlLogix 5580 ladder profile validates these existing operations
without requiring saved scalar values or live indices:

| Arithmetic | Integer bitwise |
| --- | --- |
| ADD, SUB, MUL, DIV, MOD, NEG, ABS | AND, OR, XOR, NOT |

Declared scalar types, references, destination permissions and the existing
homogeneous wide-integer rules remain checked. Invalid shapes, BOOL operands,
unsupported bitwise floating-point forms and mixed wide types still fail static
validation, including on false rungs.

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
complete mixed-type arithmetic and bitwise promotion, native overflow/status/
fault/lifecycle and packed layout parity remain unfinished. In particular, the
complete bitwise width-conversion matrix remains unqualified. ST expressions and FBD are unchanged; other controller
profiles retain their separate validation paths.

Choose **Math lab** and enable `BasicMath`. `BasicA` and `BasicB` drive eleven
named results for the operations above. Start with 7 and 3 to see sum 10,
quotient 2, remainder 1 and complement -8. The original advanced-math and called
ST examples remain available. Enable `RealModulo` separately to calculate
`ModuloA` (-7.5) modulo `ModuloB` (2): `ModuloResult` is -1.5 and
`ModuloRounded` is -2. The report exposes the profile as `scalar_math`, including
its `real_remainder` contract.

Reference basis: installed Studio 5000 v35 instruction help for these eleven
instructions, including DIV 14621, MOD 14620 and Data Conversions 14451. The
[public MOD reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/modulo--mod-.html)
provides additional context; installed v35 help is the version-specific basis.
Software-model and HTTP checks do not establish native controller equivalence.
