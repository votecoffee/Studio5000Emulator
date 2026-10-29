# CONTROL, bit shifts, FIFO and LIFO

LogixLab models a logical CONTROL record and these ladder forms:

```text
BSL(Array,Control,SourceBit,?);
BSR(Array,Control,SourceBit,?);
FFL(Source,FIFO,Control,?,?);
FFU(FIFO,Dest,Control,?,?);
LFL(Source,LIFO,Control,?,?);
LFU(LIFO,Dest,Control,?,?);
RES(Control);
```

Length and position are pseudo-operands. Initialize CONTROL.LEN/POS in saved
data or logic; `?` placeholders do not rewrite them each scan. The logical record
contains DINT LEN/POS and BOOL EN/EU/DN/EM/ER/UL/IN/FD. Unrepresented saved members
remain unknown until a supported operation establishes them.
See [implementation](../source/logixlab/control_operations.py).

## Bit shifts

BSL/BSR operate on a bounded DINT array region. Word zero contains the lowest
bits. A rising EN edge shifts one bit through the low LEN bits; SourceBit fills
the vacated position and UL receives the displaced bit. Bits outside LEN,
including high bits in the final word and following words, remain unchanged.

Prescan and false rungs clear EN/DN/ER/POS and retain array data and UL. A true
rung with EN already set does not shift again. A new edge sets EN, clears other
control bits and then performs the operation. Success sets DN and POS=LEN.
LEN=0 sets DN, POS=0 and UL=SourceBit without changing data; negative LEN sets ER.
An excessive region stops and rolls back the modeled advance.

## FIFO pair

FFL/FFU share a CONTROL with independent EN and EU edge latches. Prescan sets
the respective latch, preventing an initial load/unload until a false scan
rearms it. A held true rung does not repeat data movement.

FFL writes the source at the current POS and increments POS. FFU returns the
first element, shifts the entire configured region down, zeroes its last element
and decrements POS. The software profile writes zero on an empty unload edge.
DN indicates POS>=LEN; EM indicates empty. LEN<=0 or negative POS sets both
status bits without data movement. POS beyond LEN remains outside the qualified
profile and stops execution. Exact native invalid-state/edge parity remains open.

This increment supports matching scalar SINT/INT/DINT/REAL sources, destinations
and arrays, plus representable numeric source immediates. The array region is
limited to its selected member. FIFO strings/structures, conversions, indirect
or alias array starts and AOI array bindings remain unfinished. FFU/LFU
destinations cannot share their array base tag. Shift SourceBit
cannot overlap its CONTROL. These restrictions are checked before execution.

## LIFO pair

LFL/LFU use the same numeric types, bounds and independent EN/EU edge latches
as FIFO. LFL loads at POS and increments it. LFU returns the newest value at
POS-1, zeroes only that slot and decrements POS; lower entries do not shift.
An empty unload edge writes zero. Held true does not repeat either operation.
DN/EM and the bounded invalid-state policy follow the FIFO profile above.

[Sequence lab](../source/samples/SequenceLab.L5X) demonstrates a three-value stack
and [DINT sequencers](sequencer-operations.md). Step once to rearm, then pulse
Push for each StackValue. Pulse Pop to inspect reverse order through Popped.
The fourth array element is a guard and stays 999.

## Reset, observation and limits

RES clears POS and all CONTROL flags, retaining LEN and array data. FLL of DINT
zero can clear a CONTROL record, including LEN, using declared member types.
Scalar, array and nested CONTROL members can be accessed by logic and the UI;
ordinary symbolic CIP access covers individual atomic members. Native CONTROL
templates, packed byte layouts and whole-record wire transfers remain withheld.

All operations stay within a 4096-element software bound. Array starts use static
literal indices. Known words are required for shifts and configured FIFO unload
regions. Unknown data, bounds and conversion failures roll back data, control
state, time and task scheduling. Native fault records, partial side effects and
controller timing are separate work. These are RLL forms; ST/FBD calls remain
blocked and Safety execution is unsupported.

## Control Lab

Choose **Control lab**, then **Step scan** once to rearm the FIFO. Toggle
ShiftLeft or ShiftRight on and step: the 33-bit examples cross word boundaries
while preserving the final word's upper bits and a guard value of 999. Holding
an input on and stepping again retains the result; toggle off and step to rearm.

For the queue, toggle Load and step for each Incoming value. Set Load off before
using Unload. Each unload edge returns the oldest value through Outgoing;
QueueControl.POS/DN/EM show occupancy. Reset clears control state and retains
backing data. See [ControlLab.L5X](../source/samples/ControlLab.L5X).

The baseline was checked against installed v35 help 14533 (BSL), 14525 (BSR),
14529 (FFL), 14528 (FFU), 14527 (LFL), 14526 (LFU), 14733 (RES) and 454960 (pseudo-operands). Published
Rockwell [BSL](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/array--file--shift-instructions/bit-shift-left--bsl-.html)
and [FFL](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/array--file--shift-instructions/fifo-load--ffl-.html)
references provide additional context. Software tests of this bounded logical
profile do not establish native controller or Studio acceptance.
