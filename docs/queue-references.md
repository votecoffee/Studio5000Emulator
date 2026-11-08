# Shift and queue starting references

App `26.1102.081249` adds alias and indirect array starts for ladder `BSL`,
`BSR`, `FFL`, `FFU`, `LFL` and `LFU` in the Standard v35 ControlLogix 5580
profile (`1756-L81E` through `1756-L85E`). The existing static forms, CONTROL
fields, edge rules and payload types remain available.

## Forms and boundaries

```text
XIC(Load)FFL(Incoming,Buffer[StartIndex],QueueControl,?,?);
XIC(Unload)FFU(Buffer[StartIndex],Outgoing,QueueControl,?,?);
XIC(Push)LFL(Incoming,StackStartAlias,StackControl,?,?);
XIC(ShiftLeft)BSL(Bits[BitIndex+1],ShiftControl,BitIn,?);
```

An alias can resolve through other aliases to an array or selected array
element. Program-local aliases and explicit Program references use the same
resolver. Indices use the existing bounded SINT/INT/DINT `+`, `-`, `*` and
parenthesis grammar; BOOL, REAL, wide integers and index division remain
blocked. Nonnegative literal indices retain their preflight bounds checks;
evaluated expressions are checked when execution needs the region.

The start is resolved anew when an operation needs its region. FIFO/LIFO
positions are relative to that selected start. Changing the start while a
queue contains data changes the referenced window; no hidden queue copy or
automatic relocation occurs. Keep paired load/unload starts consistent.

Existing selected-array/member boundaries and the 4096-element limit still
apply. A selected UDT array member cannot spill into a neighboring member.
Multidimensional starts use the existing flat region order. Aliases retain
the base tag's constant protection. FIFO/LIFO keep their exact payload-type
requirements, unload/base-tag overlap restrictions and logical record copies.

## Preflight, edges and faults

Preflight checks reference syntax, types, writable storage and shapes without
consuming the value of a dynamic start index. When execution needs the array,
v35 5580 FFL/LFL check the current load slot within the selected array or
structure member. Shifts and unloads check their complete window. A false call can rearm
its latch even if that index is currently unknown or out of range. A held
true call does not repeat the operation or read that start again.

The existing state-dependent rules remain: a full load does not need an
array region; an empty unload still checks its configured region before
writing a typed zero destination. Other operands and CONTROL fields retain
their existing validation and known-value requirements.

A reached out-of-bounds subscript, v35 5580 shift or unload past a standalone
array, or BSL, LFU, FFL or LFL past a member array can
[use ladder fault recovery](controller-handlers.md#recover-shift-and-queue-array-faults).
An uncleared fault, BSR or FFU member overrun, unknown required data or later error
rolls back the entire advance, including array data, outputs, CONTROL state,
time, scheduler and trace. Correct the input and retry the pending edge.
Run entry preserves FIFO/LIFO startup inhibition and shift prescan rules.

These are bounded software semantics. Native index-fault classification,
partial effects, exact lifecycle behavior and Studio import acceptance still
need qualification.

## Queue Reference Lab

Choose **Queue reference lab**, then step once to rearm the queue controls.
[QueueReferenceLab.L5X](../source/samples/QueueReferenceLab.L5X) has 24 roots,
eight rungs and only ladder routines.

- Pulse `Load` with different `Incoming` values, then pulse `Unload` to inspect
  FIFO order through `Outgoing`. `StartIndex` defaults to one.
- Pulse `Push` and `Pop` to inspect LIFO order through `Popped`. These operations
  use the `StackStart` alias of `Stack[1]`.
- Pulse `ShiftLeft` to shift through the `BitStart` alias, or `ShiftRight` to
  use `Bits[BitIndex]`. Both defaults select a 33-bit region starting at element one.
- Set `StartIndex` out of range while `Load` is held true: the held operation
  retains its data. Rearm `Load` false, then true to exercise the reached fault.
  Correct the index and retry.
- Set `FaultDivisor` to zero to exercise rollback after queue and shift writes.
  Restore it to one before retrying.

Toggle each pulse false and step before its next true step. Guard elements
`Buffer[0]/[6]`, `Stack[0]/[5]` and `Bits[0]/[3]` begin as
`101/999`, `102/998` and `103/777`; valid default windows leave them intact.

## Remaining work

[One-dimensional AOI queues/shifts](aoi-queues.md) now support exact InOut and
represented local arrays. Broader AOI array shapes, wider scalar FIFO payloads,
mixed conversions, other
predefined records, full CONTROL lifecycle/status/fault parity and native
layouts remain unfinished. Separate sequencer, statistics, sorting and bit
diagnostic consumers retain their prior reference restrictions. This change
adds no ST, FBD or SFC forms.

The implementation follows installed v35 shift/queue help and Index Through
Arrays. Rockwell's [array indexing reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html),
[FFL operand reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/array--file--shift-instructions/fifo-load--ffl-.html)
and [General Instructions manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provide context. Later references do not extend this emulator's v35 profile claims.

Payload and CONTROL-reset selection is documented in [CONTROL operands](control-operands.md).
The array-start rules above remain; payload indices now wait until a data path
needs them. Actual shift/queue prescan and runtime CONTROL selection remain.
