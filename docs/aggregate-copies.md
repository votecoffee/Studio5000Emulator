# Matching aggregate COP/CPS

The v35 ControlLogix 5580 L81E–L85E software profile gives matching TIMER,
COUNTER, CONTROL, STRING, PID and explicit nested qualified UDT copies structural
validation and lazy live operands. Existing ladder and ST calls use the same
profile. See [implementation](../source/logixlab/aggregate_copy.py) and
[checks](../source/tests/test_aggregate_copy.py).

```text
COP(SourceRecords[SourceIndex],DestRecords[DestIndex],Length);
CPS(SourceTimers,DestTimers[DestIndex],Length);
```

Both operands must have the identical declared element type. Basic UDTs can
contain BOOL, signed/unsigned integers, REAL, LREAL, time/date fields, their arrays, basic records,
explicit DINT LEN/SINT DATA strings and nested basic UDTs. Nesting is limited
to 32 levels. PID records are also supported as described below. Other operational members
and AOI aggregate schemas are outside this profile. Other controller profiles retain legacy copy behavior.

## PID records

App `26.1112.220217` gives matching logical PID COP/CPS the same structural/lazy
selection as basic records, including scalar/selected array elements, aliases,
explicit nested UDTs, and existing AOI local/InOut bindings. The complete record
copies: CTL, the modeled REAL fields and DATA[17]. CTL bit aliases reflect the
copied word. Unknown represented fields remain unknown; full records establish
unknown destinations, and nested arrays are detached from source storage.

Both instructions retain captured addresses/counts, logical clipping, forward
overlap, per-scalar work limits, existing ST FOR protections and whole-advance
rollback. A zero count resolves both addresses without reading record values.
The shared FLL schema validator still excludes PID, including inside UDTs.
Other operational/AOI records and redefined PID schemas remain unqualified.

The destination keeps its own private solver history; no copy transfers, shares
or clears that history. Public DATA fields do not seed it. On the next PID call,
the ordinary INI flag and Run lifecycle determine whether to reinitialize it.
Copying a fresh preset with INI clear starts a fresh calculation on that next call;
copying INI set into an already-running instance preserves that destination's
history. These are explicit software policies, not native DATA/layout, internal
state, synchronization or partial-fault equivalence.

In **PID lab**, set LoadTuning and Execute true for one Step. CPS copies LoopPreset
before PID: SP=60, KP=2, KI=0.25, and the default PV=20 gives CV=90. Clear LoadTuning
before the next Step to let the loop retain its evolving state. CaptureLoop copies
the represented Loop into LoopSnapshot after calculation. Disable CaptureLoop,
then change a Loop member to observe independent snapshot storage. FaultDivisor=0
rolls back earlier copies and calculations. Both copy gates default false.

See [PID solver](ladder-pid.md), [sample](../source/samples/PIDLab.L5X) and
[focused cases](../source/tests/test_pid_copies.py). Installed v35 COP/CPS help
14516 supplies the structure-copy baseline; the logical policies above define
this bounded emulator profile.

## Precise UDT fields

App `26.1112.210459` adds matching UDT copies containing LREAL and
TIME32/TIME/LTIME/DT/LDT fields, including nested records and arrays. Binary64
positions and exact duration/timestamp ticks copy as represented values without
numeric conversion. Unknown members remain unknown, and each destination owns
its nested storage. Scalar work limits, logical clipping, alias/AOI bindings,
existing ST FOR protection and whole-advance rollback retain their existing rules.

In **Record lab**, set IncomingPart.Position and IncomingPart.Timestamp, then
enable CopyPart or SyncCopyPart. CopiedPart receives the complete record. Disable
both copy gates before changing the source to observe detached storage. Enable
ClearCopiedPart to apply a [typed zero fill](aggregate-fill.md#precise-udt-zero-fills).
These are level-sensitive operations, independent of the queue edge controls.

This extends the matching logical schema; it does not add native packed layouts,
mixed record conversion, cross-member traversal or native CPS synchronization.

## Selection and complete records

Length is a scalar SINT/INT/DINT tag or an integer immediate in 0..100000.
Preflight validates schemas, shapes, destination permissions, index grammar
and literal bounds without consuming saved lengths, dynamic indices or record
values. Oversized static windows clip to the selected logical region.
False ladder rungs, skipped ST statements and prescan perform no copy and
skip these live operands. Existing ST FOR destination protections remain.

Reached calls capture Length and complete source/destination windows before
writing. The count clips to the shorter remaining source/destination logical
scalar/member/array region; sibling members are never traversed. See
[clipped aggregate operations](clipped-aggregates.md), including ST FOR effects.
Zero length still resolves both live addresses, and reads no record values.
Unknown consumed lengths and invalid live indices fault; unknown record fields
are copied as unknowns, without treating them as numeric or Boolean inputs.

Copies replace complete records, including all string DATA entries beyond LEN.
Full writes can replace previously unknown destinations. Each stored element
owns independent nested storage. Unselected elements and surrounding members
retain their values. Aliases, program-local references, multidimensional
row-major arrays, nested member arrays and existing AOI local/InOut bindings
resolve to their canonical storage.

Both instructions preserve the model's existing sequential overlap behavior.
A forward copy from Records[0] to Records[1] over two elements propagates the
first value through both destinations. Backward copies read later elements
in order. Addresses and Length stay captured even when the copy overwrites
fields that selected them; source values are read per element.

## Work limits and boundaries

Each actual copied scalar member consumes one advance-budget unit. Budget failures,
invalid windows/lengths/indices and later instruction faults restore earlier
record writes, AOI bindings, time and scheduling within the modeled advance.
Completed prescan is a separate lifecycle boundary.

This is a logical matching-record model. It does not infer packed byte layouts,
permit mixed aggregate types, clip across native base-tag boundaries, reset
private timer/counter histories or establish native partial-fault, scan or
CPS synchronization behavior. [Numeric copies](numeric-copies.md) retain their
separate byte-image, clipping and byte-budget rules. No new instruction
mnemonics, ST syntax or FBD/SFC execution forms are added.

## Data lab

Choose **Data lab**. With CopyAggregates false, the saved copy Length is unknown
and both copy indices are 99 without blocking a step. Set
AggregateCopyLength[0]=1, AggregateCopySourceIndex=1 and AggregateCopyDestIndex=1,
then enable CopyAggregates. The selected unknown source fields copy as unknowns.

To prepare typed values, set AggregateIndex=1, AggregateLength[0]=1 and
AggregateSource[0]=0, then enable FillAggregates and step. The existing zero
fills run before these three copies:

| Source | Destination | Instruction |
| --- | --- | --- |
| ZeroRecords[1] | CopyRecords[1] | COP |
| ZeroTimers[1] | CopyTimers[1] | CPS |
| ZeroStrings[1] | CopyStrings[1] | COP |

Disable FillAggregates before changing source members. Another step copies
those values, including unused string DATA, while sibling destinations remain
unknown. Disable CopyAggregates before changing its indices to 99 to retain
the results. Re-enable to observe a bounds fault, correct the input and retry.
See [DataLab.L5X](../source/samples/DataLab.L5X).

Rockwell's [copy reference](https://www.rockwellautomation.com/en-ca/docs/factorytalk-design-studio/current/contents-ditamap/instructions/instruction-set/array--file--misc-instructions/copy-cop-synch-copy-cps.html)
describes destination-element lengths and structure-copy examples. Declared
schemas, logical-region clipping, unknown propagation and transactional work
limits here are explicit software policies. These checks do not establish
native Studio/controller equivalence.
