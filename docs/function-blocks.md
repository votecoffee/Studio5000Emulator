# Function block signal execution

The v35 ControlLogix 5580 software profile executes a limited FBD graph containing
`SEL`, `MUX`, `SCL`, `HLL`, `SNEG`, `SSUM` and the six
[timer/counter/one-shot blocks](fbd-stateful.md). Choose **FBD selector lab** for
manual/automatic selection or **FBD signal lab** for a scale/limit/negate/sum chain.
[Boolean logic/memory](fbd-boolean.md), [rate limiting/extrema](fbd-rate-capture.md)
and [accumulation/integration](fbd-accumulation.md) bring the inventory to 25 blocks. Other FBD instructions and complete native
graph semantics remain unfinished.

## Supported graph

One unprotected `FBDContent` containing one `Sheet` supports `IRef`, `ORef`,
`Block` and `Wire`. SEL uses a logical `SELECT` record; MUX uses `MULTIPLEXER`.
SCL uses `SCALE`; HLL/SNEG/SSUM reuse `HL_LIMIT`, `SELECTABLE_NEGATE` and
`SELECTED_SUMMER`. Their numerical/status calculations are shared with the
[existing ST models](st-signals.md), including [scaling](st-scaling.md).
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

[Boolean logic and memory](fbd-boolean.md) adds BAND/BOR/BNOT/BXOR and
DFF/JKFF/RESD/SETD, with strict BOOL pins and shared latch/clock state.

## Block behavior

| Block | Behavior |
| --- | --- |
| SEL | SelectorIn false selects In1; true selects In2. |
| MUX | Selector 1 through 8 selects the corresponding REAL input. Invalid selectors set Status to 3 and retain the previous enabled output. |
| SCL | Scale raw values into engineering units, optionally clamp raw excursions, and report strict raw-limit alarms/invalid ranges. |
| HLL | Both/high/low limiting with inclusive active alarms and selector/range diagnostics. |
| SNEG | Select the input or its negation. |
| SSUM | Sum selected input/gain pairs in index order, then add Bias. |
| TONR / TOFR / RTOR | Shared logical timer models with explicit elapsed-time and reset/pause/off-delay policies. |
| UPDN / INTG | Shared per-call accumulation and trapezoidal integration with initialization, holds, limits and diagnostics. |
| RLIM | Shared ramp/bypass and simulated/oversample timing, with BOOL diagnostics; RTS remains blocked. |
| MAXC / MINC | Retained finite REAL extrema and level-sensitive reset baselines. |
| CTUD | Sampled up/down count edges, reset, DINT wrap and done/overflow/underflow state. |
| OSRI / OSFI | Sampled rising/falling pulses and startup suppression. |
| Connected EnableIn false | Clear enables and retain outputs, status and hidden output history. |

Status aliases are BOOL source pins: MUX InstructFault/SelectorInv; SCL
InstructFault/InRawRangeInv; HLL InstructFault/LimitsInv/SelectLimitInv. They can
drive BOOL ORefs or downstream BOOL inputs. They cannot be driven as inputs.
Unknown Status bits remain unknown and cannot be published as FALSE.
FBD_TIMER additionally exposes InstructFault/PresetInv as BOOL output pins.

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

## Signal lab

`FBDSignalLab.L5X` contains 37 root tags, four blocks, 33 drawing nodes and 35
wires. RawInput 5 in the raw range 0–10 maps to Scaled 50 in the engineering
range 0–100. Limits 20/80 leave it unchanged; Negate false passes 50; selected
Trim 2 with Gain 1 and Bias 1 produces Summed 53. Change Negate, selection bits,
limits, ranges, gains and bias to exercise the chain. RawMax 0 holds the prior
scaled output and asserts BOOL diagnostics; invalid LimitMode asserts ModeInvalid.
BlockEnable gates all four blocks; ExecuteGraph skips the routine; FaultDivisor
zero demonstrates whole-advance rollback. Restore it to 1 to retry.

These four adapters add FBD forms to existing models; the 222-type inventory
now contains 44 bounded models. There are twenty-five FBD blocks, with nineteen names shared
with the existing twenty-seven ST-call dispatch entries. RLL remains 101.
Native startup/output-write/disabled/postscan behavior, intermediate precision
and full controller fault/status parity remain unqualified.

## Timer/counter lab

Choose **FBD timer/counter lab** for `FBDStateLab.L5X`: six blocks, 38 root tags,
34 drawing nodes and 39 wires. Rising pulses count toward CountPreset; CountDone
starts OnDelay. TimerInput separately drives retained and off-delay timers. See
[the stateful contract](fbd-stateful.md) for lifecycle, timing and retry behavior.

## Rate/capture lab

Choose **FBD rate/capture lab** for `FBDTrendLab.L5X`: RLIM feeds MAXC/MINC over
23 nodes and 25 wires. See [the rate/capture contract](fbd-rate-capture.md) for
timing modes, reset baselines, enable gaps, BOOL diagnostics and retry behavior.

## Accumulation lab

Choose **FBD accumulation lab** for `FBDTotalLab.L5X`: UPDN and INTG over 29 nodes
and 28 wires. See [the accumulation contract](fbd-accumulation.md) for shared ST
history, startup, initialization, holds, limits, diagnostic pins and rollback.

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
