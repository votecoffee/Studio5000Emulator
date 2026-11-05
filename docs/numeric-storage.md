# Numeric move and clear

The v35 ControlLogix 5580 ladder profile supports scalar MOV and CLR across:

| Integer types | Floating point |
| --- | --- |
| SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT | REAL, LREAL |

MOV accepts any pairing of those ten source/destination types. CLR writes a
typed zero. Operands are scalar tags, selected array elements, members or aliases,
including existing AOI InOut/local bindings. MOV immediates are bounded DINT or
finite REAL values. [Typed MOV constants](typed-mov-literals.md) now add decimal
L/U/UL integers and finite floating L/l values. Unsigned radix patterns above
signed DINT range, typed radix forms and other spellings remain separate.

Integer moves preserve the low destination bits. Widening sign-extends signed
sources and zero-extends unsigned sources. For example, DINT 16#12345678 becomes
SINT 120 or INT 22136; signed -1 becomes the unsigned destination's all-ones value.
Native overflow/status effects accompanying these conversions remain unmodeled.

LREAL uses finite binary64 storage and conversion; see [its supported forms](lreal-storage.md).
Integer-to-REAL conversion produces float32, including precision loss for large
integers. REAL sources also use float32; integer results round to nearest, ties
to even, and must fit the signed or unsigned destination. Excluded REAL ranges
fail the complete advance rather than guessing native overflow result bits.
Thus integer -1 can move to USINT 255, while REAL -1.0 to USINT remains excluded.

Preflight checks types, scalar shape, permissions and immediate bounds without
reading saved scalar values or live indices. False rungs and ordinary prescan
skip both operands. True MOV consumes a known source; true CLR needs no old
destination. Complete writes establish unknown numeric values. Reached unknowns,
bad indices, excluded REAL ranges and later faults roll back values, time/task
state and existing AOI bindings. Unwritten members/elements remain unknown.

Choose **Data lab** and enable `MoveNumeric`. Inspect `MoveByte`, `MoveWord`,
`MoveUnsigned`, `MoveRealResult`, `MoveRounded`, `ClearValue` and
`ByteFill[FillIndex]`. This scalar model is separate from byte-copy instructions
and the homogeneous wide arithmetic profile. The report exposes `numeric_storage`.

[Same-type time and date operands](time-date-storage.md) use their own exact
storage rules. Other controllers retain their previous behavior. Mixed LREAL
arithmetic and expressions, time/date conversions, string and aggregate MOV/CLR
forms, broader literal support and native status/fault/lifecycle
parity remain unfinished. ST assignments and FBD are unchanged.

Reference basis: installed Studio 5000 v35 **Data Conversions** (14451),
**Clear (CLR)** (14685), and **Move (MOV)** (14688). Rockwell's published
[numeric conversion table](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/elementary-data-types.html)
also describes integer narrowing and REAL rounding. Software-model and HTTP
checks do not establish native controller equivalence.

[Finite LREAL storage](lreal-storage.md) adds a tenth numeric type for the
v35 5580 MOV/CLR profile and independent atomic tag access.
