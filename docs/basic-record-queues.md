# Basic record FIFO/LIFO payloads

The v35 ControlLogix 5580 software profile supports matching TIMER, COUNTER and
CONTROL payloads in ladder FFL/FFU/LFL/LFU. Explicit UDTs may contain those
records and their arrays, alongside the existing basic fields, strings and
nested UDTs. See [record queues](record-queues.md) for the shared copy contract.

```text
XIC(LoadSnapshot)FFL(SourceTimer,TimerQueue[Index],QueueControl,?,?);
XIC(UnloadSnapshot)FFU(TimerQueue[Index],SavedTimer,QueueControl,?,?);
```

The source/destination and array element types must match exactly. A TIMER
cannot be queued as COUNTER, or converted through a scalar numeric operand.
Other operational predefined schemas, data-only inferred records and AOI
instance payloads remain unqualified. Narrow numeric queues keep their existing
SINT/INT/DINT/REAL profile; this change adds no scalar LINT/unsigned forms.

## Snapshots and clearing

Payloads are complete logical tag data. PRE/ACC, LEN/POS and represented BOOL
flags copy unchanged, including unknown fields. Queue transfers do not execute
the copied instruction or interpret its flags, timing values or progress.
Snapshots own separate nested storage, so later source or queue edits do not
change an already queued or unloaded record.

FIFO unload returns element zero and shifts the configured region, including
unused represented slots. LIFO unload returns POS-1 and clears only that slot.
Both clear vacated records using the declared logical default: numeric members
zero and BOOL members false. An empty unload edge establishes the same default
output. Source and destination timer clocks, counter edge histories, incremental
file progress and other private runtime state are not copied or reset.

Unknown members remain unknown. A whole unknown record faults if actually read.
FIFO still requires its complete configured region; LIFO reads only its selected
payload. Existing false/held/full-path operand skips, prescan EN/EU initialization,
saved queue LEN/POS, bounds and transactional rollback remain in force.

## Storage and scope

Aliases, selected array/member windows and supported one-dimensional AOI InOut
or local arrays use the existing resolver. AOI bindings remain exact declared
types; aggregate Input/Output parameter support is unchanged. Queue CONTROL
storage must stay separate from payload and array storage. A CONTROL used as
payload cannot simultaneously control its own transfer. Existing conservative
same-base and unload destination guards remain.

## Record lab

Choose **Record lab**, then step with SnapshotLoad/SnapshotUnload false. The
saved SnapshotIndex=99 remains dormant. Set SnapshotIndex=1 and pulse SnapshotLoad:
one TIMER, COUNTER, CONTROL and QueuedSnapshot UDT load into independent regions.
The TIMER FIFO holds ACC125; the COUNTER LIFO holds ACC3; the CONTROL FIFO holds
LEN7/POS2; the UDT FIFO holds Id42 and copies all three nested record types.
Indices0/3 are guards, while queue LEN2 selects indices1/2.

Set SnapshotLoad false and step before another load. Change source members to
make a different snapshot; queued values retain their earlier contents. Pulse
SnapshotUnload to return the oldest FIFO payloads and newest COUNTER LIFO payload.
Empty unloads produce typed defaults. A reached invalid index or FaultDivisor=0
rolls back all queue operations in that advance; correct the input and retry.
The called **BasicRecordQueues** routine exposes all eight transfer instructions.

See [RecordLab.L5X](../source/samples/RecordLab.L5X),
[payload implementation](../source/logixlab/fifo_values.py) and
[focused tests](../source/tests/test_basic_record_queues.py).

Installed v35 help14526–14529 lists structure operands. This profile models
logical basic-record data transfers; packed byte layouts, hidden state, native
status/fault/lifecycle behavior and Studio/controller acceptance remain
unqualified. No new ST/FBD forms or controller profiles are introduced.
