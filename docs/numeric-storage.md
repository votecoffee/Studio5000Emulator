# Numeric move and clear

The v35 ControlLogix 5580 ladder profile supports scalar MOV and CLR across:

| Integer types | Floating point |
| --- | --- |
| SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT | REAL, LREAL |

MOV accepts any pairing of those ten source/destination types. CLR writes a
typed zero. Operands are scalar tags, selected array elements, members or aliases,
including existing AOI InOut/local bindings. MOV immediates are bounded DINT or
finite REAL values. [Typed MOV constants](typed-mov-literals.md) now add decimal
L/U/UL integers and finite floating L/l values. [Radix MOV sources](radix-mov-literals.md)
support unsuffixed DINT and attached L/U/UL bit patterns with declared-width
zero fill and signed interpretation. Other spellings/consumers remain separate.

Integer moves preserve the low destination bits. Widening sign-extends signed
sources and zero-extends unsigned sources. For example, DINT 16#12345678 becomes
SINT 120 or INT 22136; signed -1 becomes the unsigned destination's all-ones value.
When the stored integer differs from the source, MOV sets the modeled
[rung overflow flag](scalar-math.md#overflow-status).

LREAL uses binary64 storage and conversion. See [its supported forms](lreal-storage.md).
Integer-to-REAL conversion produces float32, including precision loss for large
integers. Integer results round to nearest, with ties going to the even integer.

### REAL moves into SINT or INT

Ladder MOV rounds the float32 source first. When the rounded value fits DINT, a
SINT or INT destination receives the low bits. For example, 127.5 rounds to
128 and stores -128 in SINT with `S:V` set. -128.5 also stores -128, with
`S:V` clear because the rounded value already fits. `S:N` and `S:Z`
reflect the stored value. With `ReportMinorOverflow` enabled, narrowing also
sets the task's `S:MINOR` flag.

Rounded values outside DINT range, other destination types, and LREAL sources
use the existing checked conversion. For example, REAL -1.0 to USINT fails the
advance. The rule applies to both REAL tags and REAL literals in ladder MOV.
[Rockwell data conversions](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/37-00/contents-ditamap/data-conversions.html)

### NaN and infinity

A REAL or LREAL source tag can hold a NaN or an infinity produced by
[floating DIV](scalar-math.md#floating-div-with-a-zero-divisor). Ladder MOV
preserves NaN and the sign of infinity in either floating-point destination.
When converting to SINT, INT, DINT or LINT, MOV stores zero for NaN, the signed
maximum for positive infinity, and the signed minimum for negative infinity.
These moves establish the destination and continue the rung. An infinity
converted to a signed integer sets `S:V`, and sets the modeled task `S:MINOR`
bit when the controller export explicitly enables `ReportMinorOverflow`.
An unsigned destination still rejects a nonfinite source.

For the conversion rules, see [Rockwell's Replacement Guidelines, pp. 171–172](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm100_-en-p.pdf#page=171).
Native math flags, fault records and NaN payload bits have not been qualified.

### Operand evaluation

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

[Time and date operands](time-date-storage.md) use exact same-family conversions
and raw LINT/DT microsecond and LINT/LDT nanosecond timestamp bridges. [Ladder string MOV](string-operations.md#ladder-string-mov)
has a separate tag/literal and capacity-clipping profile. Lossy time/date
conversions, non-string aggregate MOV/CLR, string CLR and native status,
fault and lifecycle parity remain unfinished.

Reference basis: installed Studio 5000 v35 **Data Conversions** (14451),
**Clear (CLR)** (14685), and **Move (MOV)** (14688). Rockwell's published
[numeric conversion table](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/elementary-data-types.html)
also describes integer narrowing and REAL rounding. Software-model and HTTP
checks do not establish native controller equivalence.

[Finite LREAL storage](lreal-storage.md) adds a tenth numeric type for the
v35 5580 MOV/CLR profile and independent atomic tag access.
