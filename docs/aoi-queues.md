# Ladder AOI queues and shifts

App `26.1102.083150` adds `BSL`, `BSR`, `FFL`, `FFU`, `LFL` and `LFU` execution
inside supported RLL AOIs for the Standard v35 ControlLogix 5580 profile.
Starting operands select an element of a **one-dimensional** exact-type InOut
array or a represented saved local array. Existing numeric, custom-string and
explicit UDT queue payload rules remain in force, including
[represented LREAL and time/date members](record-queues.md#precise-positions-and-timestamps).

## Scope and storage

```text
XIC(Load)FFL(Value,Buffer[Index],State,?,?);
XIC(Unload)FFU(Buffer[Index],Item,State,?,?);
XIC(Push)LFL(Value,Stack[0],StackState,?,?);
XIC(Pop)LFU(Stack[0],Popped,StackState,?,?);
```

`Buffer` and `State` can be InOut parameters. In this bounded model, caller
types and array dimensions must match the definition exactly. No implicit
conversion, resizing or variable-sized array contract is inferred. Local
`Stack` and `StackState` use the current instance's represented storage.

Subscript expressions are evaluated in the AOI frame before following a
parameter/local binding. An AOI's `Buffer[Index]` uses that instance's Index,
including when a controller tag happens to have the same name. Nested AOIs,
nested subscript references and indirect integer-bit selections follow the
same scope rule. This shared resolver correction also applies to existing ST
array-reference forms; it introduces no new ST instruction calls.

Local tags share an instance base in the logical model. Queue arrays, CONTROL
records and unload results may occupy disjoint members of that instance.
An unload destination inside the same selected array member remains blocked,
including a guard element beyond LEN. Control/payload overlap checks and base
constant protection remain active. Outside AOIs, the prior conservative
same-base restrictions remain unchanged.

The first element must be explicitly selected, such as `Buffer[0]` or
`Buffer[Index]`. Whole arrays, multidimensional starts and partially selected
subarrays remain outside this AOI profile. [AOI FAL/FSC](aoi-file-operations.md)
have a separate bounded expression profile. Other file, sequencer, statistics,
sorting and bit-diagnostic consumers keep their earlier restrictions.

## Lifecycle and faults

The caller's AOI mode controls whether Logic or EnableInFalse executes. A
skipped AOI without EnableInFalse retains its instruction latches. The lab's
explicit EnableInFalse routine executes false queue/shift calls to rearm them;
that is authored logic, not automatic rearming by the emulator.

Automatic prescan preserves the existing FIFO/LIFO startup inhibition and shift
initialization. Saved local values omitted from an export stay unknown;
definition DefaultData never substitutes for saved instance state. Explicit
logic or a Prescan routine can establish unknown buffer elements. Required
CONTROL fields must be known when their prescan or execution path reads them.

False and latched queue/shift calls structurally check starts without consuming
dynamic index values. Actual bounds and windows are checked when needed.
Empty unloads retain their existing region check. Invalid references, unknown
required data, budgets and later faults roll back the whole advance, including
earlier instances, copied parameters, local/external values, CONTROL latches,
time, trace, scheduling and AOI binding metadata. Correcting an input permits
retry of the pending edge.

## AOI Queue Lab

Choose **AOI queue lab** or load [AOIQueueLab.L5X](../source/samples/AOIQueueLab.L5X).
The synthetic fixture has 22 roots, two instances, four main rungs and eleven
AOI Logic/EnableInFalse rungs. All routines are ladder.

Step once to rearm. Pulse `Load`, `Push` or `Shift` by stepping false before
each true step. The instances use different input values and FIFO start indices:

| State after the first pulse | Driver A | Driver B |
| --- | --- | --- |
| FIFO write | BufferA[1] = 11 | BufferB[2] = 22 |
| Local stack write | Stack[0] = 11 | Stack[0] = 22 |
| Shift output | Word = 1 | Word = 1 |

Pulse `Unload` for FIFO order and `Pop` for reverse stack order. `EnabledA` and
`EnabledB` gate whole AOI calls. The lab enables EnableInFalse to rearm that
instance while disabled. Its local Popped/Word outputs and local arrays are
visible through the emulator's logical inspection model.

Change `IndexB` to an invalid value on a reached edge, or set `FaultDivisor`
to zero, to exercise rollback across both instances. Restore a valid input
before retrying. Guards at BufferA[0]/[5], BufferB[0]/[5], each Stack[3] and
each Bits[2] are outside the default regions.

## Qualification and remaining work

Focused model and HTTP checks cover independent/nested instances, changing
InOut banks, local FIFO/LIFO/string/UDT storage, frame-scoped indices, Run and
EnableInFalse behavior, unknown saved fields, Event/Periodic/routine modes and
fault recovery. This is software-model evidence, not native Studio acceptance.

Broader AOI dimensions/binding contracts, alias/constant/nullable parameters,
other predefined payloads, general Postscan/SFC behavior, native packed layouts,
fault/status/partial-effect parity and full ladder/ST coverage remain unfinished.
This increment adds no FBD or SFC features.

The installed v35 Using an Add-On Instruction and Parameter/Local Tag help was
reviewed alongside Rockwell's [Add-On Instructions manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm010_-en-p.pdf)
and [parameter/local-tag reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/add-on-instructions/parameter-local-tag-properties-dialog-box.html).
The emulator's exact-dimension and one-dimensional-start restrictions are
deliberately narrower than the complete native binding rules.
