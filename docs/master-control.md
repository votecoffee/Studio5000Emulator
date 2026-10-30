# Paired ladder MCR zones

App `26.1030.074205` supports a bounded v35 ControlLogix 5580 Master Control Reset
profile. An opening rung ends with MCR(), followed by body rungs and a paired,
unconditional MCR() ending in the same routine.

```text
XIC(ZoneEnable)MCR();
XIC(ZoneInput)OTE(ZoneOutput);
TON(ZoneTimer,?,?);
OTL(ZoneLatch);
MCR();
ADD(AfterZone,1,AfterZone);
```

The opening conditions select normal or false execution for that invocation.
When enabled, each body rung follows its own conditions. When disabled, every
body instruction receives false rung input, including instructions in parallel
branches. The rungs are still scanned. The ending MCR restores normal execution
for subsequent rungs.

## Effects and scope

Existing false-execution rules apply: OTE clears its bit; TON resets; RTO and
counter accumulators retain their values while their enable/edge state follows
false execution. OTL/OTU, arithmetic writes, RES, JSR and EVENT do not perform
their true-path action. FIFO/shift controls receive their normal false scan.
Required instruction-state reads and existing validation rules remain in force.

The opening result is sampled once when that rung executes. Editing its gate
inside the body affects the next invocation, not the current body's mode.
The zone does not reassert Program first scan when re-enabled.

Zone state is local to each routine invocation. Supported RLL AOI routines use
their own plans. An AOI invoked in a disabled zone receives false power and can
execute its configured EnableInFalse routine normally; its own zones start
independently, and the caller's disabled state resumes afterward. Prescan has
no MCR action and still initializes body instructions lexically.

Trace rows in planned routines include `mcr_forced_false`. Coverage reports
describe the profile and count planned zones. These are software diagnostics;
native override registers, CPU timing and full scan/fault parity are unverified.

## Accepted layout and control flow

MCR has no operands and must be the last unbranched instruction of its rung.
An opener may contain XIC/XIO, AFI, supported comparisons, LIM, MEQ or CMP,
including branches of those condition instructions. Opening-rung side effects
remain unqualified. Endings contain only MCR(). Multiple separate zones work.

JMP within one zone is supported; ordinary jumps can also skip a complete zone.
Skipping a whole zone retains its outputs because its body was not scanned.
Jumps into, out of or between zones are blocked. SBR/RET/TND/BRK inside a zone,
conditional endings, unterminated zones and intended nesting remain unqualified.
Zones are paired in source order; nesting has no separate interpretation.
Malformed forms block before scanning, including in unreachable code.

The existing instruction budget applies even to disabled instructions. Faults
roll back output/control changes, time and scheduling; a retry gets fresh local
zone state. Supported routine replacement rebuilds the zone plan from new logic.
ST/FBD forms, other controller profiles and Safety execution remain unfinished.
This profile does not model physical I/O power control.

## Try Control Lab

Choose **Control lab** and step. ZoneEnable and ZoneInput start true. ZoneOutput
turns on, ZoneLatch latches, ZoneScans counts enabled scans and ZoneTimer runs.
AfterZone counts every successful scan outside the zone.

Set ZoneEnable=false and step. ZoneOutput clears and ZoneTimer resets, while
ZoneLatch and ZoneScans retain their values. AfterZone keeps increasing. On
re-enabling, the counter can detect a new rising input; it does not gain a new
Program first scan. ZoneInput independently controls output/timer/counter rungs
when the zone is enabled.

ZoneDivisor defaults to 1. Zero is harmless to the body division while the zone
is disabled, but faults when enabled. Correct it before retrying. The existing
shift and FIFO examples run before this zone; a later zone fault rolls their
changes back too. See [ControlLab.L5X](../source/samples/ControlLab.L5X),
[zone validation](../source/logixlab/mcr.py) and
[execution](../source/logixlab/runtime.py).

The installed v35 MCR help and Rockwell's
[MCR reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/program-control-instructions/master-control-reset--mcr-.html)
describe false execution, endings and routine/AOI scope. Software checks do not
establish native Studio/controller acceptance of this bounded implementation.
