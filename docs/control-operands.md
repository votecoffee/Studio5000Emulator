# CONTROL operand selection

The v35 ControlLogix 5580 L81E–L85E ladder profile validates BSL/BSR,
FFL/FFU/LFL/LFU and CONTROL RES without consuming dormant payload indices.
Declared types, shapes, permissions, literal bounds, pseudo-operands and the
existing overlap restrictions remain checked. See
[implementation](../source/logixlab/control_operations.py) and
[checks](../source/tests/test_control_operands.py).

```text
XIC(Shift)BSL(Words[0],ShiftControl,Bits[SourceIndex],?);
XIC(Load)FFL(Inputs[SourceIndex],Queue[0],QueueControl,?,?);
XIC(Unload)FFU(Queue[0],Outputs[DestIndex],QueueControl,?,?);
XIC(Reset)RES(Controls[ControlIndex]);
```

This extends [array-start selection](queue-references.md) to the separate
payload references. It does not add new instruction mnemonics, languages,
numeric types or movement algorithms. Other controller profiles retain their
previous validation behavior.

## Shift and queue paths

Structural preflight uses declared shapes instead of saved payload values or
dynamic indices. False shifts and queues skip live payloads. Held shifts and
held queue latches also skip them. A full load does not read its payload;
invalid-state paths keep the existing data-free behavior.

A moving shift edge requires the live source-bit address and a known BOOL.
A moving load edge requires the actual source address and the existing
matching numeric/string/UDT value. An unload writes the actual destination,
including the established typed-zero result on an empty unload edge. Complete
numeric destination writes can establish unknown values. An empty unload also
selects and writes its destination. In whole-project scans, a handler can
[clear a reached array subscript fault](controller-handlers.md#recover-shift-and-queue-array-faults)
and skip the instruction. The CONTROL state and any moved queue elements are
restored before the handler runs.

Prescan still selects actual CONTROL records. Queue prescan needs known LEN
and POS for status; runtime queue calls retain those reads even when false or
held. Shift/queue CONTROL indices are not universally skipped. Existing edge
latches, bounds, guard preservation and invalid-state policies are unchanged.
Aliases and supported AOI local/InOut arrays retain their own binding rules.

## CONTROL reset

CONTROL RES has no reset effect during prescan or on a false rung. These paths
skip its live dynamic index after structural validation. A true reset selects
the actual writable scalar CONTROL, sets POS=0 and all represented status
flags false, and preserves LEN, including an unknown LEN. Unknown old POS/flags
are replaced without being consumed as inputs. Other records remain unchanged.

The reset captures the canonical CONTROL identity before writing POS or flags.
It uses that identity to remove incremental file progress, including when
the index expression reads a field that RES clears. Aliases and existing AOI
local/InOut references resolve to the same storage. A
[cleared Type 4 Code 20](controller-handlers.md#recover-timer-counter-and-reset-array-faults)
skips the reset in a whole-project scan. Unrecovered faults and later errors
restore values, flags, incremental progress, time, scheduling and bindings
within the modeled advance. Completed prescan is a separate lifecycle boundary.

[TIMER/COUNTER reset](ladder-counters.md) keeps its separate contract. General
CONTROL consumers such as sequencers, searches, sorting and statistics keep
their own validation and lifecycle requirements. This change does not qualify
native packed layouts, hidden state, status/fault classification, partial
effects or full controller parity.

## Control lab

Choose **Control lab**, then step once. The called **IndirectOperands** ladder
routine has four gated examples. PayloadIndex, OutputIndex and ResetControlIndex
start at 99; source values and ResetControls are unknown. Disabled examples
leave them dormant.

| Example | Setup and result |
| --- | --- |
| IndexedShift | Set PayloadIndex=1 and PayloadBits[1]=true, then enable. One edge shifts the low bit of IndexedBits[0]; held true does not repeat or read a new payload index. |
| IndexedLoad | Set PayloadIndex=1 and PayloadValues[1]=67, then enable. One edge loads IndexedQueue and advances IndexedQueueControl.POS. |
| IndexedUnload | Disable IndexedLoad, set OutputIndex=1, then enable. One edge writes 67 to UnloadedValues[1] and clears the vacated queue slot. |
| IndexedReset | Set ResetControlIndex=1 and enable. ResetControls[1].POS becomes 0, its flags false and its LEN remains unknown. |

Each gate must return false before its next edge. IndexedQueue[2]=999 and
IndexedBits[1..2]=77,999 remain guards. Unknown numeric source data or a live
invalid index faults transactionally; correct the input and retry. Disable
IndexedReset before returning its index to 99. See
[ControlLab.L5X](../source/samples/ControlLab.L5X).

Rockwell's [RES reference](https://www.rockwellautomation.com/en-ro/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/timer-and-counter-instructions/reset--res-.html)
describes resetting CONTROL position/status on true execution. Structural
unknown handling, canonical file-progress clearing and transactional boundaries
here are explicit software policies, not native equivalence evidence.
