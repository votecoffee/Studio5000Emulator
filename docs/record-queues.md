# String and UDT FIFO/LIFO payloads

App `26.1030.070834` extends ladder FFL/FFU/LFL/LFU to matching declared strings
and explicit user-defined records in the v35 ControlLogix 5580 software profile.
Numeric queue behavior and the existing logical CONTROL contract remain.

```text
XIC(LoadPart)FFL(IncomingPart,PartQueue[0],PartControl,?,?);
XIC(UnloadPart)FFU(PartQueue[0],OutgoingPart,PartControl,?,?);
XIC(PushPart)LFL(IncomingPart,PartStack[0],StackControl,?,?);
XIC(PopPart)LFU(PartStack[0],PoppedPart,StackControl,?,?);
```

Source/destination and queue element must have the exact same declared type.
STRING and explicit custom LEN/DATA string types are supported. Qualified UDTs
can contain represented integer/REAL/LREAL/BOOL and time/date fields, arrays, strings and nested
explicit UDTs. Nested 64-bit values stay exact because the operation copies
logical values without numeric conversion.

[Basic TIMER/COUNTER/CONTROL records](basic-record-queues.md), including nested
UDT members and their arrays, now use the same matching logical-copy rules.
AOI instance types, other operational predefined records and inferred data-only
schemas remain unqualified.
Mixed-type conversions and aggregate/string immediates remain blocked. Existing
numeric immediates retain their earlier rules. These are ladder forms; ST/FBD
forms remain unfinished. [One-dimensional AOI queues](aoi-queues.md) now accept
exact InOut arrays and represented local arrays with disjoint instance storage. [Alias and indirect starts](queue-references.md)
now use the same typed payload copies in the v35 5580 ladder queue profile.

## Precise positions and timestamps

App `26.1112.205241` adds LREAL and TIME32/TIME/LTIME/DT/LDT members inside
explicit UDT queue payloads. Matching FFL/FFU/LFL/LFU copies retain binary64
positions and exact timestamp/duration ticks, including nested records and arrays.
No float32 or integer-width conversion occurs inside these logical copies.
Unknown represented fields remain unknown; clearing establishes typed zeros.

The **Record lab** PartRecord now includes Position (LREAL) and Timestamp (LDT).
Set IncomingPart.Position to 1.0000000000000002 and its Timestamp to
1794483000000000123 nanosecond ticks, then pulse LoadPart/UnloadPart. The output
retains both values. Timestamps are exposed as exact decimal text in the API.
Position remains binary64. Guard records and the independent stack retain their
existing bounds and edge rules.

This extends represented UDT contents; scalar wide/time/date queues, implicit
type conversion, operational/AOI record payloads and native packed ABI remain
outside this profile. Native queue timing/status/layout acceptance is separate.

## Copying and clearing

FFL/LFL snapshot the source into the current POS, then increment POS. Subsequent
source edits do not change the stored record. FFU returns element zero, shifts
the entire configured LEN region down, clears its final element and decrements
POS. LFU returns POS-1 and clears only that element, leaving lower slots intact.
The destination receives a detached copy.

Clearing uses a typed zero element: numeric fields become zero, BOOL fields
false, and strings receive LEN=0 with their complete declared DATA array zeroed.
Nested arrays/records clear recursively. An empty unload edge establishes the
same typed zero destination. Array elements after the configured region remain
unchanged.

Whole logical copies retain represented unknown members and string backing
bytes as unknown. They neither infer omitted data nor repair a string's LEN or
interpret its text. Reading an unknown member or invalid string still fails by
the usual rules. An unknown whole source record faults when actually read;
an unload can establish a previously unknown whole destination. The change log
then records individual leaf transitions from unknown to known.

## Control, bounds and overlap

Saved CONTROL.LEN/POS, independent EN/EU edges, prescan, full/empty flags and
RES follow the [existing queue contract](control-operations.md). An initial or
held true rung does not repeat transfers. A false scan rearms the corresponding
edge. RES retains queue data while clearing CONTROL progress.

Static starting indices and the selected array/member boundary are enforced,
with the existing 4,096-element software limit. Aggregate arrays and CONTROL
must have separate base tags; aggregate payload and CONTROL storage cannot
overlap. Unload destinations outside AOIs cannot share the queue base tag;
the bounded AOI profile permits disjoint instance members, while keeping
destinations within the selected array member blocked. Scalar payload
aliases and Program-local sources remain supported.

Unknown whole sources, bounds errors and later instruction faults roll back
records, CONTROL flags/position, time, change history and task scheduling together.
No partial movement is committed. Native fault handling, hidden byte layouts,
record padding, CONTROL templates and full scan/invalid-state parity are not
established by these logical transfers.

## Record Lab

Choose **Record lab**, then step once to rearm. Pulse LoadPart to enqueue
IncomingPart, or PushPart to put it on the independent stack. Edit Id, Lot,
Accepted, Name, Readings, Position or Timestamp between pulses. Pulse UnloadPart for FIFO order and
PopPart for reverse order. Each pulse requires a false scan before the next true
scan. Guard records at element 3 retain IDs 999 and 888.

LoadText/UnloadText control a separate LabelText FIFO; its element-3 guard is
`KEEP`. Strings have a declared capacity of 16 bytes. FaultDivisor defaults to
1; setting it to 0 faults after queue operations, demonstrating whole-advance
rollback. Restore it before retrying the edge.

See [RecordLab.L5X](../source/samples/RecordLab.L5X),
[payload rules](../source/logixlab/fifo_values.py) and
[queue execution](../source/logixlab/control_operations.py).

The installed v35 FFL/FFU/LFL/LFU help lists string and structure operands.
Rockwell's [General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provides context. Software checks do not establish native Studio/controller
acceptance of this bounded implementation.
