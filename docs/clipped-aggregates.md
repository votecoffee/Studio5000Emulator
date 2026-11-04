# Clipped aggregate operations

For the v35 L81E–L85E software profile, oversized matching COP/CPS and zero FLL
stop at the selected logical array/member or scalar. A copy stops at the shorter
remaining source or destination. Complete TIMER, COUNTER, CONTROL, STRING,
explicit user strings and nested basic UDT records retain their existing
[copy](aggregate-copies.md) and [zero-fill](aggregate-fill.md) rules.

```text
FLL(0,Records[2],100000);
COP(Records[2],Copies[1],100000);
CPS(Records[2],Synced[1],100000);
```

For three-element arrays, the fill changes only Records[2]; each copy writes
only destination element 1 because just one source element remains. Destination
elements 0 and 2 retain their previous values. A scalar accepts one record.
Multidimensional arrays traverse row-major; a selected member array stops before
its sibling members. These are logical boundaries, without inferred native ABI.

## Captured operands and work

Length remains a scalar SINT/INT/DINT or immediate in 0..100000. Types, schemas,
permissions and starting addresses still require validation. False ladder rungs,
skipped ST statements and prescan skip live indices and saved lengths. A reached
zero-length copy resolves both live addresses without reading records; a
zero-length fill resolves its destination and skips the source value/index.

Reached calls capture length and complete clipped address windows before stores,
including when those stores overwrite fields used to choose the windows. Copies
retain sequential overlap propagation. Full writes preserve logical unknowns
and all string DATA beyond LEN; stored records own independent nested storage.
Only actual scalar members copied/filled consume the work budget. Invalid live
operands, budget exhaustion or a later fault roll back the modeled advance,
including earlier writes, AOI bindings, time and scheduling.

## Existing ST calls

COP/CPS use the same record rules in ladder and ST. The existing emulator ST
FLL extension shares zero-fill behavior; installed v35 help does not list native
ST FLL availability. This revision adds no language availability.

ST FOR analysis includes every destination record. A direct static copy uses
the source-limited clipped destination window; a static fill uses its clipped
window. Literal zero has no write effect. Changing lengths/indices, aliases and
AOI bindings conservatively cover their enclosing array, protecting loop control,
bounds and step from writes that a saved selection might hide.

## Data lab

Choose **Data lab**, then step with ClipRecordFill/ClipRecordCopy false. The saved
ClipRecordIndex=99 remains dormant. Set ClipRecordIndex=2, enable ClipRecordFill
and step. ClipRecordSources[2] becomes a typed zero record; source Counts 10 and
20 remain. Disable the fill, enable ClipRecordCopy and step: both ClipRecordCopies
and ClipRecordSync have Counts [101,0,999]. Source limiting preserves the final
999 despite the requested length of 100000. Change ClipRecordSources[2].Count
to 77 and step again to obtain [101,77,999]. Disable copies before selecting 99;
reaching the bad index faults and rolls back the advance.

See [DataLab.L5X](../source/samples/DataLab.L5X) and
[focused tests](../source/tests/test_clipped_aggregates.py).

Installed v35 help 14512 (FLL) and 14516 (COP/CPS) describe byte-count clipping
at native base-tag ends, with source limits for 5580 copies. This software profile
clips logical complete records within the selected region. Packed layouts,
cross-member/base-tag traversal, mixed or operational/AOI aggregate schemas,
private instruction histories, CPS synchronization and native fault/lifecycle
equivalence remain unqualified. FBD/SFC and other controller profiles are unchanged.
