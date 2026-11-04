# Numeric FIFO and LIFO conversions

The v35 ControlLogix 5580 software profile supports different numeric payload
and array types in ladder `FFL`, `FFU`, `LFL` and `LFU`. Each operand may be a
scalar SINT, INT, DINT or REAL element. Existing array/CONTROL bounds, edge
latches, saved LEN/POS, unknown-value requirements and rollback still apply.
Other controller/firmware profiles retain their matching-type numeric rules.

## Conversion rules

| Operation | Conversion |
| --- | --- |
| FFL/LFL | Convert Source to the selected FIFO/LIFO array element type before storing it at POS. |
| FFU/LFU | Convert the unloaded element to Destination's declared type; shift or clear the backing array in its original type. |
| Empty FFU/LFU | Write a typed zero to Destination without reading any numeric array values. |

Integer widening sign-extends signed values; integer narrowing keeps the low
destination bits. REAL sources and results use float32 representation. REAL to
integer conversion rounds to nearest, ties to even, and requires a result that
fits the destination. This shares the [numeric MOV model](numeric-storage.md).
For example, REAL 3.5 loads as INT 4; DINT 4660 loads as SINT 52; SINT -1 unloads
as DINT -1. DINT 16777217 converts to REAL 16777216.

Load immediates are bounded signed-DINT integers or finite REAL constants.
Different numeric types do not permit BOOL, LINT, unsigned, LREAL, string or
record conversions. Existing [string/UDT queues](record-queues.md) still require
the exact same declared record type. AOI call parameters and InOut array
bindings retain their exact declared types; the instruction converts between
independently typed operands inside the AOI. No AOI binding conversion is added.

## Selection and failures

Preflight checks declared scalar types, index grammar, shape and destination
permissions without reading saved payload values or dynamic indices. False,
held and full-load paths skip unused payloads. A data-moving edge checks the
actual selected source/destination; complete writes can establish unknown
array elements or scalar destinations. Empty unload still requires a valid
destination address and array region. Existing FIFO whole-region reads and
LIFO selected-slot reads retain their separate requirements.

Required unknowns, invalid selected indices, excluded REAL results and later
instruction failures roll back values, CONTROL state, AOI bindings, trace,
time and task scheduling for the whole modeled advance. Native partial effects,
overflow result bits, arithmetic/fault status, scheduling and lifecycle parity
are not qualified by these software tests. Native byte layouts and broader
controller or language forms remain separate work. These are RLL instructions;
their availability in ST/FBD is unchanged.

## Control Lab

Choose **Control lab** and step once to rearm its queue latches. Open the called
**NumericQueues** routine in the read-only logic viewer.

- Pulse `MixedLoad` to load REAL `MixedSource` into INT `MixedQueue`.
  Its default 3.5 becomes 4. Pulse `MixedUnload` to return it in SINT `MixedResult`.
- Pulse `MixedPush` to load DINT `MixedStackSource` into SINT `MixedStack`.
  Its default 4660 becomes 52. Pulse `MixedPop` to return it in REAL `MixedStackResult`.
- Set each trigger false and step before its next rising edge. Holding it true
  retains the queue position. The fourth array elements are guards.
- A reached load of REAL 40000 into the INT queue faults and rolls back. Set the
  source to 3.5 to retry the same edge successfully.

The baseline follows installed v35 help 14529/14528/14527/14526 and Rockwell's
published [FFU reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/array--file--shift-instructions/fifo-unload--ffu-.html).
The installed v35 definitions determine this profile; current online help is
additional context and does not establish native controller acceptance.
