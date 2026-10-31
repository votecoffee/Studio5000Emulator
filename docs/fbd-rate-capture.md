# FBD rate limiting and extrema

RLIM, MAXC and MINC execute as FBD Blocks in the bounded v35 ControlLogix 5580
software graph. They share the existing [rate-limiter](st-rate-limiter.md) and
[capture](st-capture.md) algorithms and per-record history with ST calls. This
adds three graph forms. With [accumulation/integration](fbd-accumulation.md), the
FBD inventory is 33 blocks: 21 shared ST-call names, six common RLL arithmetic
names and six available only as FBD forms.
RLL remains 101 and ST calls 27.

| Block | Logical record | Algorithm inputs besides EnableIn | Outputs besides EnableOut |
| --- | --- | --- | --- |
| RLIM | RATE_LIMITER | In, IncRate, DecRate, ByPass, TimingMode, OversampleDT, RTSTime, RTSTimeStamp | Out, DeltaT, Status and its BOOL aliases |
| MAXC | MAXIMUM_CAPTURE | In, Reset, ResetValue | Out |
| MINC | MINIMUM_CAPTURE | In, Reset, ResetValue | Out |

RLIM initializes its hidden previous output from the first reached input. Later
calls approach In using separate increase/decrease rates in units per second.
ByPass copies In and replaces that baseline. Explicit Out writes do not replace
history. Mode 0 uses the configured Periodic task period, or elapsed simulated
time between reached calls in Continuous/Event/harness execution. Mode 1 uses
the positive finite OversampleDT on each call. Mode 2 remains unsupported and
faults only when the enabled block is reached.

Negative rates become zero with signed DINT diagnostics. Invalid timing mode or
oversample interval holds the established output with DeltaT zero and diagnostic
bits. A valid call clears those diagnostics. InstructFault, IncRateInv,
DecRateInv, TimingModeInv and DeltaTInv can drive BOOL wires. RTS status aliases
are addressable, but module timestamp/RTS behavior remains unimplemented.

MAXC/MINC initialize from the first consumed input, then retain the greatest or
least finite REAL respectively. Reached Reset takes priority and uses ResetValue
on every reset call; it replaces the retained baseline. Only that selected value
must be known. Direct Out writes do not replace hidden extrema.

Connected false EnableIn clears both enable bits and retains outputs, diagnostics
and history. It skips the algorithm, including reset and timing validation.
Unwired EnableIn is true. An independently enabled downstream block can consume
the held output of a disabled upstream block. Skipped graphs retain history.
On resuming, Continuous/harness timing includes the elapsed skipped/disabled gap;
Periodic uses one configured period, and oversample uses one supplied interval.
Repeated Continuous calls at one timestamp add no time; Periodic and oversample
calls each apply their configured interval. These are explicit software policies.

Prescan clears enables. Run entry clears hidden history; first reached calls
initialize again. Whole-advance rollback includes wires, outputs, diagnostic rate
corrections, clocks and extrema. A supported detached RLL caller replacement
preserves that state. Native lifecycle/timing/precision/packed-layout and complete
status/fault parity remain unqualified. General graph restrictions still follow
the [single-sheet rules](function-blocks.md).

Choose **FBD rate/capture lab** for `FBDTrendLab.L5X`: 27 roots, three blocks,
23 drawing nodes and 25 wires. Signal feeds RLIM, whose Out feeds MAXC and MINC.
The first step initializes all three to Signal. Mode 1 with SampleTime 0.25 uses
250 ms per reached call; initial rates 2/4 change output by at most 0.5/1.0.
ResetCapture seeds Maximum/Minimum from MaximumReset/MinimumReset (10/-10).
BlockEnable gates all three; ExecuteGraph skips their routine. FaultDivisor zero
demonstrates a late fault; restore it to 1 to retry without consuming extra time.

Operands, language availability and output pins were checked against installed
v35 help 14818.htm, 14836.htm and 14837.htm. The existing software models retain
their documented native-qualification gaps. The synthetic L5X has no native
Studio import/Verify, transfer or online-edit acceptance claim.
