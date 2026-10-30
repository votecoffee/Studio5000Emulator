# Stateful function blocks

The bounded v35 ControlLogix 5580 graph executes TONR, TOFR, RTOR, CTUD, OSRI and
OSFI alongside the existing selector/signal blocks. Their logical records and
algorithms are shared with the [ST timers](st-timers.md), [counter](st-counter.md)
and [one-shots](st-oneshot.md). This adds FBD forms without adding data types or
changing the RLL/ST dispatch counts. Native controller equivalence is unverified.

Choose **FBD timer/counter lab** for an executable example.

## Values and wires

| Block | Record | Input pins besides EnableIn | Output pins besides EnableOut |
| --- | --- | --- | --- |
| TONR / TOFR / RTOR | FBD_TIMER | TimerEnable, PRE, Reset | ACC, EN, TT, DN, Status, InstructFault, PresetInv |
| CTUD | FBD_COUNTER | CUEnable, CDEnable, PRE, Reset | ACC, CU, CD, DN, OV, UN |
| OSRI / OSFI | FBD_ONESHOT | InputBit | OutputBit |

PRE, ACC and Status are DINT; all other pins are BOOL. Timers use integer simulated
milliseconds. InstructFault/PresetInv are BOOL aliases of Status.0/.1, with the
same unknown-value protection as other diagnostic pins. Output pins cannot be
driven. The existing [graph limits and reference rules](function-blocks.md) apply.

## Enable, elapsed time and edges

A connected false EnableIn clears enables and skips the algorithm. Other public
outputs and hidden histories retain. An unwired EnableIn is true. Skipped routine
calls likewise preserve state. Inputs are still copied onto reached blocks before
enable gating; changing them does not itself sample edges or advance a timer.

An active timer's next enabled execution computes elapsed time since its previous
enabled execution. If TimerEnable still requests timing, that interval includes
disabled/skipped calls. Repeated calls at one timestamp add no extra time. This
explicit software policy has not been qualified against native FBD disable timing.

TimerEnable is a separate input evaluated only when the block executes:

- TONR clears its non-retentive accumulator and timing/done flags when false.
- RTOR pauses while false, retaining ACC/DN. A later true call resumes without
  charging that paused interval.
- TOFR arms while true, then times its off delay while false. An unarmed false
  input does not start timing. Reset disarms it and assigns ACC=PRE.

Reset has priority over normal timer operation. Active accumulation saturates at
PRE in this profile. Negative PRE sets Status=3 and EnableOut=false, retains
timer outputs, and pauses timing without a whole-scan fault. A valid call clears
diagnostics and resumes according to the existing timer model.

CTUD counts sampled rising CUEnable/CDEnable transitions, up before down. Initial
execution primes both levels without counting. DINT arithmetic wraps; OV/UN retain
until Reset or explicit writes. Reset assigns zero, clears overflow/underflow and
consumes current input levels. DN is ACC >= PRE, including negative presets.

OSRI/OSFI produce one enabled-call pulse on sampled rising/falling edges. Their
initial previous levels suppress startup pulses. Disabled calls can hold a prior
pulse; re-enabled calls compare current input with the last sampled value. Hidden
intermediate transitions are not reconstructed.

## Lifecycle and failure

Prescan clears enables without executing algorithms, copying wires or publishing
ORefs. Run entry clears clock/edge histories; first reached calls apply their
normal initialization. TONR establishes ACC zero; RTOR retains represented ACC;
CTUD retains its saved count. Disabled first calls do not initialize histories.

ST and FBD sites share history for the same resolved record and instruction kind.
Mixed timer kinds or OSRI/OSFI kinds on one record remain blocked at execution;
duplicate backing records within a graph remain preflight blockers. Existing
routine harnesses and Standard Continuous/Periodic/instruction-only Event tasks
can execute these blocks. A sole Periodic task still requires its configured
scan interval.

Whole-advance rollback covers values, clocks, counter edges, one-shot edges,
traces and scheduling state. Detached replacement of a supported RLL caller
preserves these histories. Required unknown inputs and unrepresentable operations
fault; they do not become known zeros. Skipped/disabled paths do not read their
algorithm inputs, but an unknown published output still faults.

## Lab

`FBDStateLab.L5X` contains 38 root tags, six blocks, 34 drawing nodes and 39 wires.
Start with Input false. Each false-to-true Input transition produces RisingPulse
and increments Count; a true-to-false transition produces FallingPulse. At
CountPreset (initially 2), CountDone starts the TONR OnDelay; OnDone follows after
OnPreset milliseconds (initially 30). CountDown and CounterReset control CTUD.

TimerInput separately drives RTOR Retained and TOFR OffDelay. Retained starts with
represented ACC 5 and PRE 50; OffDelay PRE is 20. ResetTimers controls all timers.
BlockEnable and ExecuteGraph demonstrate disabled and skipped intervals.
OnPreset negative demonstrates BOOL instruction diagnostics. FaultDivisor zero
demonstrates a later ladder fault rolling back all six blocks; restore it to 1
to retry without duplicate edges or elapsed time.

The sample is authored for this software runtime. Native Studio import/Verify,
controller execution, transfer and online-edit acceptance were not tested.
Remaining work includes native clock rollover/overshoot, disable/startup/postscan
qualification, packed layouts, full status/fault parity, other controller profiles
and the broader FBD graph forms listed in the [coverage checklist](emulation-coverage.md).

Instruction availability and logical fields can be compared with Rockwell's
[general-instruction manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
and the installed v35 help. The software timing and unknown-value policies above
remain explicit limits of this implementation.
