# Function block selector execution

The v35 ControlLogix 5580 software profile executes a limited FBD graph containing
`SEL` and `MUX`. Choose **FBD selector lab** to try manual/automatic selection
feeding an eight-channel selector. This is the first graph execution profile;
other FBD instructions and complete native graph semantics remain unfinished.

## Supported graph

One unprotected `FBDContent` containing one `Sheet` supports `IRef`, `ORef`,
`Block` and `Wire`. SEL uses a logical `SELECT` record; MUX uses `MULTIPLEXER`.
Drawing IDs must be unique unsigned integers. Coordinates are bounded to 10000;
admission is limited to 512 nodes and 4096 wires. Descriptions do not affect execution.

References accept static scalar BOOL, DINT and REAL tags/members or typed input
literals. Program-local tags, aliases and static nested/array members work.
Wire types must match exactly; conversions, expression references and bit/indirect
references are blocked. Every ORef needs one input. Unwired block input pins use
the record's current value. Unwired EnableIn is true on each reached invocation.

IRefs are sampled once before blocks execute. Acyclic wire dependencies determine
block order, with numeric drawing ID as a deterministic tie rule. Block outputs
are captured after each block; ORefs are written after all blocks. This software
policy has not been compared with native execution order. Backing records must
be distinct. Output references cannot overlap one another, inputs or backing
records; implicit dependencies through backing-tag reads are rejected.

## Selector behavior

| Block | Behavior |
| --- | --- |
| SEL | SelectorIn false selects In1; true selects In2. |
| MUX | Selector 1 through 8 selects the corresponding REAL input. Invalid selectors set Status to 3 and retain the previous enabled output. |
| Connected EnableIn false | Clear enables and retain outputs, status and hidden output history. |

An enabled invalid MUX selector uses zero before its first enabled execution.
Subsequent invalid selectors use retained internal output, independently of
direct writes to the visible Out member. Status aliases `InstructFault` and
`SelectorInv` address bits 0 and 1. A valid selection clears those diagnostics.
Only consumed selectors, connected enables and selected values must be known;
unknown unselected inputs can travel on wires. An unknown published output or
nonfinite consumed REAL faults the advance instead of becoming a known zero.

Prescan clears enables without copying inputs or publishing outputs. Run entry
clears hidden output history. Skipped routine calls retain state. Existing RLL/ST
callers, routine harnesses and Standard Continuous/Periodic/instruction-only Event
tasks can execute these graphs. Nodes and wires share the instruction budget.
Whole-advance rollback includes values, selector history and scheduling state;
detached replacement of a supported RLL caller retains graph history.

## Lab

`SelectorLab.L5X` contains 14 root tags, a ladder caller and one FBD sheet with ten
drawing nodes, two blocks and eleven wires. Initially SelectedOutput and
MultiplexedOutput become 10. Set ManualMode to select ManualValue (initially 25).
Channel 1 selects SEL output; channel 2 selects ManualValue; channels 3–8 select
the corresponding values stored in ChannelChoice. Channel 0 holds the prior
MUX output and sets SelectorStatus to 3. BlockEnable disables both blocks;
ExecuteGraph skips the complete call. FaultDivisor zero demonstrates rollback
after the graph has run; restore it to 1 to retry with current inputs.

The webpage displays the graph and highlights enabled blocks from the last scan.
This sample validates the software importer/runtime and HTTP app. Native Studio
import/Verify, controller execution, upload/download and FBD online edits have
not been tested by this increment.

## Remaining work and references

Multiple sheets, named connectors, feedback wires, explicit execution orders,
other blocks/functions, FBD calls/AOIs, decorations beyond descriptions, packed
layouts, broader conversions/references and full native lifecycle/status/fault
parity remain blocked or unqualified. SEL/MUX are not enabled as RLL or ST calls.

The installed v35 SEL/MUX help (14826.htm / 14819.htm) supplies the logical field
and selection descriptions. Its language descriptions are inconsistent with the
family overview; this profile implements the documented FBD form only. XML
element names and wire pins follow Rockwell's
[Import/Export manual, chapter 10](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf).
See [execution coverage](emulation-coverage.md) for the remaining emulator work.
