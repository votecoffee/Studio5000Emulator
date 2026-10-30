# Structured Text accumulation

`UPDN(State)` and `INTG(State)` execute with finite REAL operands in the v35
ControlLogix 5580 L81E–L85E software profile. Choose **Accumulator lab** on the
webpage or launch with `--sample AccumulatorLab` for a synthetic example.

These are bounded software models. The equation and logical schemas were checked
against installed Studio v35 help and Rockwell's
[process control and drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
Native startup, precision and interacting conditions remain unqualified; FBD
graph execution, packed layouts and other controller profiles remain unfinished.

## Records

| Type | Members |
| --- | --- |
| UP_DOWN_ACCUM | BOOL EnableIn, Initialize, Hold, EnableOut; REAL InPlus, InMinus, InitialValue, Out |
| INTEGRATOR | BOOL EnableIn, Initialize, HoldHigh, HoldLow, EnableOut, HighAlarm, LowAlarm; REAL In, InitialValue, IGain, HighLimit, LowLimit, OversampleDT, Out, DeltaT; DINT TimingMode, RTSTime, RTSTimeStamp, Status |

Defaults enable EnableIn; all other inputs are zero/false except INTG RTSTime=1,
HighLimit=maximum finite REAL and LowLimit=its negative. Missing saved input
values stay unknown. Required unknown or incorrectly typed inputs fault execution.
Constant destinations, redefined records, wrong types and RLL calls are blocked.

## UPDN

Initialize overrides Hold and assigns InitialValue on every reached call. With
Initialize clear, Hold retains the hidden accumulator. Otherwise:

`Out = previous accumulator + InPlus - InMinus`

Both inputs may be negative. Startup establishes a zero accumulator before
applying the current inputs. Each reached call adds once, including multiple
calls at one timestamp. InitialValue is read only during initialization; Hold is
read only otherwise; InPlus/InMinus are read only when accumulation is active.

## INTG

The model uses the documented trapezoidal equation:

`Out = previous Out + IGain * (In + previous In) / 2 * DeltaT`

The first reached software call establishes zero output and input history,
without integrating. Initialize overrides that startup behavior, assigning
InitialValue and capturing In. Later positive intervals apply the equation.
HoldHigh prevents an increase; HoldLow prevents a decrease. Both hold the output
when asserted together. Valid positive intervals still sample In while held.
Calculated output is clamped to LowLimit/HighLimit and retained after clamping,
so continued saturation does not accumulate a hidden excess.

Alarms use inclusive comparisons. HighLimit <= LowLimit sets both alarms,
Status.0/.2 and Out=LowLimit. Negative IGain is written as zero with Status.0/.1
and holds the previous output for that call. This software profile gives
Initialize precedence over invalid limits and negative gain; initialization may
place Out outside limits. Otherwise invalid limits precede the negative-gain
hold. These combinations, startup/input-history choices and native hold/limit
ordering need controller comparison.

TimingMode 0 uses the configured Periodic task interval; other supported task
contexts use elapsed whole simulated milliseconds between reached calls.
TimingMode 1 uses OversampleDT on each call, including repeated calls at one
timestamp. Zero holds calculation and input history. Negative intervals or
intervals above float32(4194.303) set DeltaT=0 and Status.0/.31. Modes outside
0..2 set DeltaT=0 and Status.0/.27. Mode 2 faults as unsupported; module
timestamps and RTS status behavior remain unfinished.

Status aliases share the backing DINT: InstructFault=.0, IGainInv=.1,
HighLowLimsInv=.2, TimingModeInv=.27, RTSMissed=.28, RTSTimeInv=.29,
RTSTimeStampInv=.30 and DeltaTInv=.31. Diagnostics are recomputed per call.
Unused OversampleDT/RTS fields can remain unknown. In is always required for
INTG, including initialization and holds.

## State and failures

Outputs and stored histories are float32; expression intermediates use host
doubles. Native intermediate rounding and nonfinite/overflow behavior remain
unverified. The finite model faults transactionally on unrepresentable values.

Reached calls force the enable pair true; prescan clears it. Skipped calls
retain values and history. Direct writes to visible Out do not replace hidden
accumulator history. Run entry clears histories; the next reached call applies
startup. Aliases, nested/array members, local tags, AOI InOut bindings, loops and
supported task contexts resolve to the same per-record state. Shared records
are updated in task dispatch order.

Advance failure restores values, histories, time and scheduler state together.
Supported detached routine replacement preserves history. Software tests and
the public lab do not establish native Studio transfer or online-edit acceptance.
