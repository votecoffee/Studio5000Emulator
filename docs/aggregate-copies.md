# Matching aggregate COP/CPS

The v35 ControlLogix 5580 L81E–L85E software profile gives matching TIMER,
COUNTER, CONTROL, STRING and explicit nested basic UDT copies structural
validation and lazy live operands. Existing ladder and ST calls use the same
profile. See [implementation](../source/logixlab/aggregate_copy.py) and
[checks](../source/tests/test_aggregate_copy.py).

```text
COP(SourceRecords[SourceIndex],DestRecords[DestIndex],Length);
CPS(SourceTimers,DestTimers[DestIndex],Length);
```

Both operands must have the identical declared element type. Basic UDTs can
contain BOOL, signed/unsigned integers, REAL, their arrays, basic records,
explicit DINT LEN/SINT DATA strings and nested basic UDTs. Nesting is limited
to 32 levels. Operational members such as PID and AOI aggregate schemas are
outside this profile. Other controller profiles retain legacy copy behavior.

## Selection and complete records

Length is a scalar SINT/INT/DINT tag or an integer immediate in 0..100000.
Preflight validates schemas, shapes, destination permissions, index grammar
and literal bounds without consuming saved lengths, dynamic indices or record
values. Fully static source/destination windows must fit before execution.
False ladder rungs, skipped ST statements and prescan perform no copy and
skip these live operands. Existing ST FOR destination protections remain.

Reached calls capture Length and complete source/destination windows before
writing. Both windows must fit their logical scalar/member/array regions.
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

Each copied scalar member consumes one advance-budget unit. Budget failures,
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
schemas, strict logical windows, unknown propagation and transactional work
limits here are explicit software policies. These checks do not establish
native Studio/controller equivalence.
