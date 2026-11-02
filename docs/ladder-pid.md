# Ladder PID: proportional and integral software profile

The Standard v35 ControlLogix 5580 profile executes a bounded ladder `PID` with
proportional/integral control, scaling, automatic output limits, software manual
tracking and alarm hysteresis. This is a deterministic simulator solver. Native
discrete equations, startup, rounding, fault behavior and packed layouts remain
unqualified. The separate [ST PI regulator](st-pi-regulation.md) uses `PROP_INT`.

## Operands and represented data

```text
XIC(Execute)PID(Loop,PV,0,CV,0,0,0);
```

`Loop` is a writable logical `PID`; PV and CV are scalar REAL tags. Aliases,
program scope and ordinary nested records/arrays can resolve through the shared
memory model. PV/CV cannot overlap the PID record. Tieback, master-loop and both
inhold operands must be literal `0`. Integer operands, ST/AOI forms and other
optional-operand forms remain blocked. Use one true execution of a record at
each modeled task-release time; a repeated true call at the same time faults.

The logical record has DINT `CTL`, the REAL members named in the v35 reference,
and REAL `DATA[17]`. Named flags such as `.EN`, `.SWM`, `.CA`, `.PE`, `.INI`,
`.NOBC` and alarm bits are views of the same signed CTL word. Unmodeled/reserved
bits are preserved. The current import profile expects represented `CTL`, not a
set of separate decorated BOOL aliases. Missing saved fields remain unknown;
schema defaults do not establish saved values. Required unknown inputs fault
when consumed. Unused DATA entries may remain unknown.

## Calculation

Every reached true call makes one update using `UPD` seconds. Actual task or
scan elapsed time does not replace UPD. Authors must arrange the intended call
rate; a [Periodic task](task-scheduling.md) is a suitable source of releases.

1. Linearly scale the raw PV from MINI..MAXI to MINS..MAXS, without clamping PV.
2. Compute engineering error `SP-PV`, or `PV-SP` when CA is set. Convert it to
   percent error `e = error * 100 / (MAXS-MINS)`.
3. Compute `P = KP * e`. With independent gains (PE clear), propose
   `I = previous I + KI * e * UPD`. With dependent gains (PE set), use
   `I = previous I + KP * e * UPD / (60 * KI)`. KI zero disables integration
   and clears the active integral; zero effective dependent gain does likewise.
4. Add BIAS, P and I. Clip an outward integral increment to the remaining
   automatic output headroom; freeze it if already beyond that limit. Retain
   changes that move away from a limit.
   Clamp the resulting output percentage to MINO..MAXO.
5. Scale OUT percent into MINCV..MAXCV and write CV. SO follows OUT in auto.

This explicitly chooses rectangular integration and conditional anti-windup;
it does not claim these are the controller's exact implementation. Public
REAL values, P, percent error and retained I use float32; intermediate products
use host precision. Overflow/nonfinite values fault the modeled advance.

KP/KI must be nonnegative, UPD positive, scaling spans positive, and SP within
the engineering range. Automatic limits require `0 <= MINO < MAXO <= 100`;
equal limits reset to 0/100. Inclusive limit flags describe the final unclamped
sum, including equality. Runtime validation faults use whole-advance rollback,
not native minor-fault records or partial controller effects.

## Manual, lifecycle and diagnostics

SWM selects software manual: clamp SO into 0..100 and scale it into CV, even
outside the automatic MINO/MAXO limits. When integration is enabled, back-calculate
I to `OUT-BIAS-P`. With KI zero, back-calculate BIAS to `OUT-P` unless NOBC is
set. The first auto call after a manual sample holds I, avoiding an additional
integral increment at transfer with unchanged inputs. Full native bumpless and
manual-limit behavior remains unqualified.

Prescan and reached false calls clear EN and retain output/history. False calls
skip numeric input consumption. Skipped routines retain everything. A first
true call, or clearing INI, establishes zero I before the update; saved DATA
does not seed hidden solver history. Entering Run clears that history. External
DATA writes do not replace it. DATA indices 0/2/3/4/14 mirror I/PV/error/SP/CV;
other entries are retained without inventing native coefficients.

PVHA/PVLA and DVPA/DVNA use strict initial comparisons against PVH/PVL and
DVP/DVN. A latched alarm remains through equality at its limit minus/plus the
nonnegative PVDB/DVDB hysteresis band. ERR includes the selected control-action
sign. EWD and SPOR are cleared on successful calls; unsupported deadband and
out-of-range SP instead fault. These alarm-boundary choices need native testing.

Later faults roll back record fields, CV, hidden I/manual history, trace, time
and task state together. Previously committed updates remain committed.

## Try it

Load **PID lab** in the webpage. The all-ladder synthetic `PIDLab` starts with
Execute false, PV 20, SP 50, KP 1, KI 0.5, UPD 1 and 0..100 scaling/limits.
Set Execute true and step: CV becomes 45, then 60. Set Loop.SWM true and Loop.SO
70: CV becomes 70. Clear SWM: the first auto step holds 70, then reaches 85.
Set FaultDivisor zero to exercise rollback; correct it to one before retrying.

## Remaining

Nonzero KD or DB, cascade flags CT/CL, PV tracking PVT and hardware manual MO
fault explicitly. Derivative/filtering, deadband/zero crossing, tieback/inhold,
saved active state, additional languages/operands, native coefficients/status/
fault/precision/lifecycle behavior and DATA/layout interpretation remain open.
This does not implement PIDE, PPID or functional safety.

Reference basis: installed Studio 5000 v35 PID help and the published
[PID operand/record reference](https://www.rockwellautomation.com/en-ro/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/special-instructions/proportional-integral-derivative--pid-.html),
[configuration/scaling guidance](https://www.rockwellautomation.com/en-ro/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/special-instructions/proportional-integral-derivative--pid-/using-pid-instructions.html)
and [timing guidance](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/proportional-integral-derivative--pid-/pid-instruction-timing.html).
