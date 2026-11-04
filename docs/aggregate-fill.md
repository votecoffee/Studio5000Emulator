# Aggregate zero fills

The v35 ControlLogix 5580 L81E–L85E ladder profile supports bounded FLL zero
fills of TIMER, COUNTER, CONTROL, STRING and explicit nested basic UDT records.
Zero values come from declared schemas, so omitted saved BOOLs become false
and REAL members become 0.0. Unknown values do not determine output types.
See [implementation](../source/logixlab/numeric_fill.py) and
[checks](../source/tests/test_aggregate_fill.py).

```text
FLL(0,Records[Start],Length);
```

Source can also be a scalar SINT/INT/DINT tag whose executed value is zero.
Constant sources are allowed. Nonzero patterns, REAL/wider source types and
whole-array sources are outside this profile. Length is scalar SINT/INT/DINT
or an integer immediate in 0..100000.

## Record contents and selection

Supported explicit UDTs can contain BOOL, signed/unsigned integer and REAL
members, their arrays, basic TIMER/COUNTER/CONTROL/string records and other
explicit basic UDTs. Explicit DINT LEN/SINT DATA user strings are included.
Operational records such as PID, AOI instance aggregates and unresolved member
schemas remain excluded. Schema nesting is limited to 32 levels.

Fills replace complete logical records, including all string DATA entries.
TIMER/COUNTER fields receive typed zero/false values. Top-level CONTROL retains
its existing logical-default FLL result; nested CONTROL members receive typed
zeros. This preserves the prior CONTROL contract. Each filled element owns its
own record storage. Unselected elements and surrounding members retain their
values, including unknowns.

Whole arrays and selected elements, row-major multidimensional traversal,
member regions, aliases and existing AOI local/InOut bindings use canonical
storage. Oversized lengths stop at the selected logical region, including a
scalar record. See [clipped aggregate operations](clipped-aggregates.md). Native
base-tag byte clipping, cross-member traversal and packed layouts are unqualified.

Structural preflight checks declared schemas, types, permissions, index grammar
and literal bounds without reading saved source/length values or dynamic indices.
Invalid static starting addresses remain blockers. False ladder rungs and
prescan skip the fill and its live operands. True calls capture the length,
complete destination window and zero source before storing anything, including
when source or length aliases a field that the fill will clear.

Zero length resolves the live destination but skips the source value and its
live index. Positive lengths require a known zero source. Full writes establish
unknown records while retaining the declared member types.

## Work limits and rollback

Each actual scalar member filled consumes one advance-budget unit. A budget failure,
invalid region/index/length, unknown or nonzero consumed source and later
instruction faults restore earlier writes, AOI bindings, time and scheduling
within the modeled advance. Completed prescan is a separate lifecycle boundary.

FLL changes represented tag data. It does not qualify native resets of private
instruction histories, operational state, packed ABIs, native partial effects,
fault continuation or full controller parity. Other controller profiles and
languages retain their previous behavior. [Numeric FLL](numeric-fill.md) keeps
its separate numeric-conversion rules. No new ST/FBD calls are added.

## Data lab

Choose **Data lab** and step once with FillAggregates false. Its aggregate
source, length and selected records remain unknown, and AggregateIndex=99 is
dormant. Set AggregateIndex=1, AggregateLength[0]=1 and AggregateSource[0]=0,
then enable FillAggregates and step:

| Destination | Result |
| --- | --- |
| ZeroRecords[1] | BOOL/BOOL-array members false, integer members zero, REAL 0.0, typed TIMER/COUNTER fields zero/false |
| ZeroTimers[1] | PRE/ACC zero and EN/TT/DN false |
| ZeroCounters[1] | PRE/ACC zero and CU/CD/DN/OV/UN false |
| ZeroStrings[1] | LEN zero and all 82 DATA entries zero |

ZeroRecords[0].Count=111 and ZeroRecords[2].Count=999 remain guards; untouched
timer/counter/string elements stay unknown. Disable FillAggregates before
changing AggregateIndex to 99 to retain results. Re-enable to observe a bounds
fault, correct the input and retry. Unknown consumed length/source and a nonzero
source likewise fault transactionally. See [DataLab.L5X](../source/samples/DataLab.L5X).

Installed Logix Designer v35 help 14512 provides the FLL operand and structure
fill reference. Declared-schema zeroing, logical boundaries and work/rollback
rules are explicit software-model policies; these tests do not establish native
Studio/controller equivalence.
