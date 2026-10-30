# Structured Text low-pass filter software model

App `26.1030.140207` adds a bounded v35 ControlLogix 5580 ST LPF model using a
logical FILTER_LOW_PASS record. **Its bilinear recurrence is an explicit software
approximation, not a verified reproduction of Rockwell's discrete algorithm.**
The installed help specifies continuous transfer functions and parameter limits;
it does not establish the native sampled recurrence, coefficients or precision.

Choose **Filter lab**, or launch with `--sample FilterLab`. Input, Cutoff,
FilterOrder, InitializeFilter, TimingMode, SampleTime and CallFilter control the
example. Filtered, ElapsedSeconds and the diagnostic flags show the results.
FaultDivisor provides a later arithmetic error for rollback checks.

```text
LPF(FilterState);
```

The logical record has BOOL EnableIn, Initialize and EnableOut; REAL In, WLag,
Order, OversampleDT, Out and DeltaT; and DINT TimingMode, RTSTime, RTSTimeStamp
and Status. Order is REAL in the v35 reference. Defaults are EnableIn true,
Order 1, RTSTime 1 and other values zero. Missing exported members stay unknown.
Record shapes do not establish saved values or native packed layouts.

## Solver and initialization

WLag is in radians/second. The model starts from these continuous transfer
functions, with cutoff w:

- Order 1: w / (s + w).
- Order 2: w^2 / (s^2 + sqrt(2) w s + w^2).
- Order 3: w^3 / (s^3 + 2 w s^2 + 2 w^2 s + w^3).

It substitutes s = (2/DeltaT)(1-z^-1)/(1+z^-1), without prewarping. Order 1 uses
one first-order section; order 2 uses a Butterworth biquad; order 3 cascades one
first-order section and a biquad with damping coefficient one. Public inputs and
results are float32. Coefficients and hidden section histories use host doubles.
This arithmetic, section ordering and rounding are software choices.

For example, order 1 with WLag=16 and DeltaT=0.125 has a zero feedback coefficient
and averages the current and previous input. Starting at zero, a step to 10 gives
5, then 10. Higher orders can overshoot before settling. This example validates
the documented software recurrence; it does not demonstrate native parity.

The first call, Initialize true, and a change of effective order seed every
section from current In and set Out=In. Held Initialize repeats that operation.
Recalculating cutoff or DeltaT for the same order preserves section history.
These startup/transition policies remain unverified against a controller.

## Timing and diagnostics

Mode 0 uses the configured Periodic task period. Continuous, Event and harness
execution uses elapsed whole simulated milliseconds since the last reached call;
its first elapsed interval is zero. Mode 1 uses OversampleDT on every reached
call, independent of the simulation advance duration. Skipped calls retain
values/history. Repeated Periodic or oversample calls can advance at one timestamp;
a repeated elapsed-time call with zero interval holds.

OversampleDT zero disables filtering without setting DeltaTInv. A negative
interval or one above float32(4194.303) seconds sets DeltaT=0 and Status.0/.31.
Other invalid mode numbers hold with Status.0/.27; mode 2 faults explicitly as
unsupported real-time sampling. Module timestamps and RTS diagnostics are stored
logical fields/aliases, without an implemented timestamp algorithm.

Initialization still seeds from input while an interval is zero or invalid.
Otherwise disabled timing holds output and section state. Each reached call
refreshes the simulated timestamp. In, Initialize, Order, WLag and TimingMode
must be known; OversampleDT is read only in mode 1. Unused RTS fields may remain
unknown. ST calls force both enable bits true; saved EnableIn does not gate them.

Exact REAL order values 1, 2 and 3 select those solvers. Other finite values use
order 1 with Status.0/.2. With positive DeltaT, the effective cutoff is clamped
between the order-specific lower bound and the upper bound:

| Order | Lower bound, rad/s | Upper bound, rad/s |
| --- | --- | --- |
| 1 | 0.0000001 / DeltaT | 0.7 pi / DeltaT |
| 2 | 0.00001 / DeltaT | 0.7 pi / DeltaT |
| 3 | 0.001 / DeltaT | 0.7 pi / DeltaT |

Clamping sets Status.0/.1. The model retains requested WLag and Order in the
visible record and applies bounds/fallback internally. With zero interval, cutoff
bounds are not evaluated. Native parameter writeback, diagnostic ordering and
mode transitions remain unverified.

BOOL aliases share the signed Status backing word: InstructFault bit 0, WLagInv
1, OrderInv 2, TimingModeInv 27, RTSMissed 28, RTSTimeInv 29, RTSTimeStampInv 30
and DeltaTInv 31. Successful valid calls clear the modeled diagnostic bits.

## Lifecycle and limits

Section histories and last output/time belong to the resolved record. Direct
Out writes do not replace them. Scalars, members, arrays/indirect elements,
aliases, program-local records and supported AOI InOut bindings use the same
model. Run entry clears history; the next call seeds again. Prescan clears the
enable pair while preserving visible outputs. Supported detached routine
replacement preserves existing histories.

Unknown required values, nonfinite/out-of-range inputs, output overflow,
instruction-budget exhaustion or a later error roll back the entire advance:
outputs/status, sections, clocks and scheduling. Failed prescan restores prior
state too. Native invalid-value propagation, automatic recovery, EnableOut
overflow behavior and controller minor/major fault classification are unfinished.

LPF remains a partial software model. Native recurrence/coefficient/precision/
transition equivalence, real-time sampling, FBD graphs, packed layouts, other
controller profiles, HPF/NTCH and full lifecycle/status/fault handling remain
open. Studio transfer and online-edit acceptance are separate.

Continuous forms, parameter bounds and timing were checked against installed
Studio v35 help (LPF and Timing Modes) and Rockwell's
[Advanced Process Control and Drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
The chosen substitution is described by the
[SciPy bilinear-transform documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.bilinear.html).
No SciPy runtime dependency or vendor help assets are included; the sample and
implementation are authored for this repository.
