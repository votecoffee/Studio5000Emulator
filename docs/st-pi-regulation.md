# Structured Text PI regulation

`PI(State)` runs with a logical PROP_INT record in the bounded v35 ControlLogix
5580 L81E–L85E software profile. Choose **Regulator lab**, or launch with
`--sample RegulatorLab`, for a controller driving a simple first-order process.
Disable SimulatePlant to supply Feedback from an external device simulator.

Schemas and equations were checked against installed Studio v35 PI help and
Rockwell's [process control and drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
This is a software profile. Native coefficients, shaping equations, parameter
thresholds, intermediate rounding and interacting-condition behavior remain
unqualified. The separate PID/PIDE families, FBD graphs and packed native
PROP_INT layout remain unfinished.

## Logical record

| Type | Members |
| --- | --- |
| BOOL | EnableIn, Initialize, HoldHigh, HoldLow, NonLinearMode, ParabolicLinear, EnableOut, HighAlarm, LowAlarm |
| REAL | In, InitialValue, Kp, Wld, HighLimit, LowLimit, ShapeKpPlus, ShapeKpMinus, KpInRange, ShapeWldPlus, ShapeWldMinus, WldInRange, OversampleDT, Out, DeltaT |
| DINT | TimingMode, RTSTime, RTSTimeStamp, Status |

Defaults enable EnableIn, use shape multipliers of one, maximum finite REAL for
the positive output/range limits and its negative for LowLimit, and RTSTime=1.
Other inputs are zero/false except Kp, which uses the profile's minimum gain.
This model uses the float32 minimum normal, 2^-126, as the positive gain/range
floor. Native thresholds still need qualification. Missing saved inputs remain
unknown; required unknown or nonfinite values fault execution.

## Linear control

With NonLinearMode clear, for a positive interval after startup:

`PTerm = Kp * In`

`ITerm = previous ITerm + Kp * Wld * (In + previous In) / 2 * DeltaT`

`Out = PTerm + ITerm`

In is the signed process error supplied by the caller. Kp affects both terms.
The model internally bounds Kp to its positive finite range and Wld between its
positive floor and 0.7*pi/DeltaT. With no positive interval, the upper frequency
bound is deferred. Requested input members are retained and diagnostics report
clipping. Wld=0 is diagnosed and uses the small positive floor internally.

The first reached software call establishes zero integral/input/output history
without calculating a control output. Initialize overrides that startup path:
InitialValue is clamped into the output limits and assigned to both Out and the
integrator; the current integral input is captured. Held Initialize reloads on
each reached call. Native startup/Initialize precedence remains unqualified.

## Holds, limits and windup

HoldHigh prevents an integral increase; HoldLow prevents a decrease. They do
not freeze proportional action. Both hold the integral when true together.
The integrator and output are limited to LowLimit/HighLimit. Inclusive output
saturation restores the prior integral, then clamps it to the current limits,
so continued saturation does not accumulate a hidden excess.

HighLimit <= LowLimit takes precedence over initialization and calculation:
Out and the integrator become LowLimit, both alarms are true, the previous
integral input becomes zero and Status.0/.3 are set. With valid limits, alarms
are inclusive. Disabled timing holds history/output, while changed output
limits still clamp them. These ordering choices need native comparison.

## Gain shaping

NonLinearMode enables separate positive/negative shape multipliers. The profile
validates both quadrants while enabled. ShapeKpPlus/Minus are bounded to 0.1–10;
ShapeWldPlus/Minus to 0–10; KpInRange/WldInRange to positive finite values.
Inactive shaping parameters and ParabolicLinear can remain unknown when
NonLinearMode is clear.

The proportional input ratio is min(1,abs(In)/KpInRange). Its shaping ratio is
0.5 times that ratio in linear shaping, or 0.333 times its square in parabolic
shaping. Effective Kp is Kp times (1 + (selected ShapeKp - 1) times shaping
ratio). Inside the range, PTerm is effective Kp times In.

Outside the range, this profile follows the displayed v35 equation literally:
effective Kp times the signed range, plus (In minus signed range) times the
selected ShapeKp multiplier. The second term uses that shape multiplier
directly. The displayed 0.333 coefficient and outside-range extension are
explicit software choices; native coefficient/extension comparison is pending.

The integral input is clamped to +/-WldInRange. Integral frequency is shaped by
1 + (selected ShapeWld - 1) times the clamped absolute input ratio, or its
square in parabolic shaping. The shaped frequency is bounded again, with
WldInv reporting clipping. The integral uses effective Kp, shaped Wld, and the
current/previous clamped integral inputs. Valid positive calls sample that
input even while holding or saturated.

## Timing and status

TimingMode 0 uses the configured Periodic task period or elapsed whole simulated
milliseconds between reached calls. Mode 1 uses OversampleDT each call,
including repeated calls at one timestamp. Zero holds calculation/input history;
intervals outside 0 through float32(4194.303) set DeltaT=0 and Status.0/.31.
Modes outside 0..2 set DeltaT=0 and Status.0/.27. Mode 2 faults as unsupported;
RTS/module timestamps remain unfinished. Initialization and invalid-limit
handling still apply with disabled timing. Unused RTS/oversample values can
remain unknown.

Status aliases share the backing DINT: InstructFault=.0, KpInv=.1, WldInv=.2,
HighLowLimsInv=.3, ShapeKpPlusInv=.4, ShapeKpMinusInv=.5, KpInRangeInv=.6,
ShapeWldPlusInv=.7, ShapeWldMinusInv=.8, WldInRangeInv=.9, TimingModeInv=.27,
RTSMissed=.28, RTSTimeInv=.29, RTSTimeStampInv=.30 and DeltaTInv=.31.
Diagnostics are recomputed on each reached call.

## Lifecycle and lab process

Reached ST calls force the enable pair true; prescan clears it. Skips retain
values/history. Run entry resets hidden histories. Direct Out writes do not
replace the held output/integrator. Resolved aliases, nested/array members,
program-local tags, AOI InOut bindings, loops and supported task contexts share
the same model. Detached routine replacement preserves history.

Public values and stored histories are float32; intermediate coefficients and
products use host doubles. Whole-advance rollback restores integrator/input/
clock/output history, tags, time and scheduler state on any later failure.

Regulator Lab computes Error=Setpoint-Feedback. Its optional process uses one
Euler update per positive PI DeltaT:

`Feedback += (ControlOutput * PlantGain - Feedback) * DeltaT / PlantTimeConstant`

The process is a synthetic demonstration, not a native module/axis or a physical
plant model. A zero time constant deliberately faults the advance for rollback
testing. Native Studio transfer and online-edit acceptance remain separate.
