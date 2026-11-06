# Sequencer aliases, indirect starts and AOIs

The bounded v35 ControlLogix 5580 ladder profile supports SQO, SQI and SQL
tables through alias chains and indirect starting elements. Supported RLL AOI
bodies can use exact one-dimensional DINT InOut arrays and represented saved
local arrays, with selected element starts. [Sequencer row/edge semantics](sequencer-operations.md)
and saved CONTROL LEN/POS remain unchanged.

```text
SQO(Patterns[StartIndex],16#FF,Output,Sequence,?,?);
SQI(Patterns[StartIndex],16#FF,Feedback,Sequence,?,?);
SQL(Learned[StartIndex],TeachValue,TeachControl,?,?);
```

The selected start is row zero; CONTROL.POS supplies the row offset. Do not
include CONTROL.POS in the starting subscript. Direct, alias and nested index
references to CONTROL.POS are rejected, including inside AOIs. This bounded
profile rejects any CONTROL.POS dependency in a table subscript; deriving an
ordinary index value elsewhere does not remove the author's responsibility to
avoid applying the row offset twice.

## Resolution and bounds

Preflight checks types, array shape, permissions and index expression structure
without consuming dynamic index values. False instructions and invalid CONTROL
states do not consume the live table start. A reached data operation resolves
the start on every call, including held-true SQO/SQL calls that retain POS.
Changing StartIndex therefore relocates the current row without an enable edge.
A zero mask skips row/output values but still requires a valid table window.

A reached out-of-bounds start can trigger
[Type 4 Code 20 recovery](controller-handlers.md#recover-sequencer-array-faults)
during a whole-project ladder scan. An unknown index or an uncleared fault
rolls back the advance. If the start is valid and its LEN+1 window exceeds
the selected array/member, SQO/SQI set ER and retain the data. SQL rolls back
the advance. The configured region includes row zero and is limited
to 4096 elements. No operation crosses into adjacent members. Input tables
may be constant outside AOIs; SQL targets must be writable. Existing AOI InOut
bindings require writable actuals even for a read-only instruction use.

SQO destinations outside AOIs retain the existing separate-base-tag restriction.
Within an AOI, disjoint instance members can share the instance base tag, while
a destination inside the selected table array remains blocked. These are
software qualification boundaries, not a complete native operand/fault model.

## Scope and AOI lifecycle

Caller-supplied alias suffixes resolve their indices in the caller's namespace.
For example, a controller alias View to Patterns used as View[LocalIndex] in a
program uses that program's LocalIndex. Indices authored in AliasFor itself
retain the alias declaration's namespace. The shared resolver applies this
rule to reads, writes and packed bit suffixes, including ordinary MOV uses.
AOI suffixes similarly resolve in their frame before following InOut bindings.

Prescan sets SQO/SQL EN and retains POS/table data. An authored EnableInFalse
routine can false-call the instructions to clear those enable bits; without
one, skipped bodies retain their latches. Required AOI copied inputs are still
consumed before either body path. Missing saved local data remains unknown;
prescan may establish EN but does not invent POS or table values.

Indirect InOut rebinding selects the newly resolved table; failed advances
restore frames, binding caches and instance metadata with external/local table
and CONTROL values, trace, time and task state. Existing Continuous, Periodic,
Event and selected-routine profiles apply. Broader AOI shapes/lifecycle, mixed
SQI/SQL source types, ST/FBD sequencers and native status/fault/layout parity
remain unfinished.

## Try the AOI sequencer lab

Load **AOI sequencer lab** and step once to clear enable latches. Turn Step
and Teach on and step: OutputsA/B become 0x120001/0x340008; both Matched values
are true. LearnedA[2] and DriverA.Scratch[2] become 11; LearnedB[3] and
DriverB.Scratch[3] become 22. The instances use different starts and independent
controls. PatternView is an alias for PatternsA.

Keep Step/Teach on and change ValueA to reload the current external/local row.
Change IndexA from 1 to 2 to move that row without advancing POS; set FeedbackA
to 2 for a match. Disable EnabledA to invoke its authored false routine, then
enable it again to advance on the next true call. FaultDivisor zero exercises
whole-advance rollback. Guard rows outside the configured windows remain intact.

Reference basis: installed Studio 5000 v35 help 14703/14704/14706 and 3232.
Published [SQO guidance](https://www.rockwellautomation.com/en-ua/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/sequencer-instructions/sequencer-output--sqo-.html)
also describes the separate starting element and CONTROL.POS offset. These
software tests do not establish native Studio import or controller equivalence.

Mask and scalar payload selection is documented in [Sequencer operands](sequencer-operands.md).
These array-start rules remain; false/invalid-state paths skip live mask/payload
indices, and held true SQO/SQL calls still read current operands.
