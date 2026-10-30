# Structured Text curves and transport delay

`FGEN(State,X1,Y1[,X2,Y2])` and `DEDT(State,Storage)` run in the bounded v35
ControlLogix 5580 L81E–L85E software profile. Choose **Curve and delay lab**, or
launch with `--sample CurveDelayLab`, to pass a nonlinear sensor curve through
a configurable process delay.

Logical schemas and algorithms were checked against installed Studio v35 help
and Rockwell's [process control and drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
Native startup, precision, timing transitions and interacting diagnostics remain
unqualified. FBD graphs, packed layouts and other controller profiles remain
unfinished. The public sample is synthetic.

## Records and arrays

| Type | Members |
| --- | --- |
| FUNCTION_GENERATOR | BOOL EnableIn, Select, EnableOut; REAL In, Out; DINT XY1Size, XY2Size, Status |
| DEADTIME | BOOL EnableIn, InFault, EnableOut; REAL In, Deadtime, Gain, Bias, OversampleDT, Out, DeltaT; DINT TimingMode, RTSTime, RTSTimeStamp, Status |

Defaults are zero/false except EnableIn=true, FUNCTION_GENERATOR XY1Size=1, and
DEADTIME Gain=1 and RTSTime=1. Missing saved fields stay unknown.

Arrays must be static references resolving to one-dimensional REAL arrays of
1–4096 elements. Nested member arrays and aliases are supported within that
form. FGEN reads tables, including constant tables; DEDT requires writable
storage. Record destinations must be writable, canonical logical records.
Wrong types, redefinitions and ladder calls are blocked.

## FGEN piecewise conversion

Three operands provide table one; five provide two complete X/Y pairs. Select
chooses table one when false or table two when true. XY1Size/XY2Size specify the
active prefix of the selected pair and must be at least one and no larger than
either array. This software profile validates only the selected table's count
and values. The inactive table can be edited or contain unknown values.

All active X values must be finite and strictly increasing. A one-point table
returns its Y value without requiring In. Otherwise output clamps to the first
or last Y at the endpoints and outside the X range. Inside a segment:

`Out = Ylo + (Yhi - Ylo) * (In - Xlo) / (Xhi - Xlo)`

Only the required Y endpoint or segment endpoints are read. Unused Y values can
remain unknown. Arrays are not modified. Active X ordering is checked even if
In lies outside the curve. Invalid selected size, a missing selected second
pair, or unordered X holds visible Out with diagnostics. Unknown required or
nonfinite data faults the entire advance.

Status aliases share the DINT: InstructFault=.0, XY1SizeInv=.1,
XY2SizeInv=.2, XisOutofOrder=.3. Selected-table-only diagnostics, inactive-table
editing, singleton/conditional reads and intermediate rounding need native
qualification.

## DEDT sampled delay

The signal inserted into storage is `In * Gain + Bias`. Positive intervals use
the nearest sample count to Deadtime/DeltaT, rounding half intervals upward.
For example, 0.625 seconds at 0.25 seconds per sample uses three samples.

The first reached software call validates inputs and timing without moving Out
or storage. The first serviced positive-interval delay uses the saved active
storage prefix. Its oldest element becomes Out, then the prefix shifts toward
older positions and the new scaled input enters element zero. Unknown active
saved samples fault instead of becoming zero.

Growing the active delay fills new positions with the prior oldest sample.
Shrinking discards older samples from the active delay. A transition from zero
active samples grows using the current scaled input. Only the active prefix is
read/written; unused storage tail values remain intact. Initial stored-sample
use, zero-to-positive growth and inactive-tail behavior are explicit software
policies pending native comparison.

Zero delay passes the scaled input. A negative delay, or a delay above storage
capacity times a positive DeltaT, uses zero internally and sets Status.0/.2;
the requested Deadtime member is retained. Invalid delay does not bypass a
disabled interval or input fault. With zero DeltaT, the upper delay bound is
deferred until an executing interval; negative delay is still diagnosed.

InFault=true holds visible Out and storage, sets Status.0/.1, and does not read
In/Gain/Bias. Recovery seeds the active buffer with the current scaled input.
Recovery remains pending through zero/invalid intervals and applies when a
positive interval executes. Native recovery extent/order remains unqualified.

TimingMode 0 uses the configured Periodic task interval or elapsed whole
simulated milliseconds between reached calls. Mode 1 uses OversampleDT each
call, including repeated calls at one timestamp. Zero holds; intervals outside
0 through float32(4194.303) set DeltaT=0 and Status.0/.31. Modes outside 0..2
set DeltaT=0 and Status.0/.27. Mode 2 faults as unsupported. RTS/module
timestamps remain unfinished. Required timing, health and delay inputs must be
known; good-health calls validate In/Gain/Bias even during startup/disabled
timing. Unused RTS/oversample fields can remain unknown.

Status aliases: InstructFault=.0, InFaulted=.1, DeadtimeInv=.2,
TimingModeInv=.27, RTSMissed=.28, RTSTimeInv=.29, RTSTimeStampInv=.30 and
DeltaTInv=.31. TimingModeInv does not shadow the DINT TimingMode member.
Diagnostics are recomputed each reached call.

## Lifecycle and transactions

Reached ST calls force the enable pair true; prescan clears it. Skips retain
values and delay state. Run entry resets the delay length, storage binding,
clock and pending recovery; startup applies on the next reached call. It does
not clear the saved storage array. Changing a record's storage binding or
sharing overlapping storage between DEDT records within one Run is blocked.

Public values and stored samples are float32; curve interpolation and scaled
input expressions use host-double intermediates. Native rounding, intermediate
overflow and nonfinite behavior remain unverified. Point/sample work is charged
to the advance budget. Values, arrays, delay history, time and scheduler state
roll back together on failure. Supported detached routine replacement preserves
delay state. Software tests do not establish native Studio transfer or edit
acceptance.
