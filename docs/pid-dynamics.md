# Ladder PID derivative and deadband

The [ladder PID software profile](ladder-pid.md) now executes smoothed or unsmoothed
derivative action and control deadband, with or without zero crossing. Existing
REAL operands, controller gates, scaling, limits, manual mode and transactional
rules remain in effect. These are explicit simulator algorithms; native
coefficients, rounding, startup, flags and filter behavior remain unqualified.

## Derivative

Set `Loop.NDF` true for unsmoothed derivative action, or clear it for the
[software smoothing filter](#derivative-smoothing). KP, KI, KD and DB must be
nonnegative. KI zero still clears the active integral.

Let `S = MAXS-MINS`, `dt = UPD` seconds, and use the current scaled engineering
PV and signed engineering error from the main PID profile. Each reached true
call uses the difference from the previous reached true sample:

| Configuration | Derivative term |
| --- | --- |
| Independent, DOE true | `KD * (error-previous error) * 100 / S / dt` |
| Independent, DOE false, reverse action | `-KD * (PV-previous PV) * 100 / S / dt` |
| Independent, DOE false, direct action | `KD * (PV-previous PV) * 100 / S / dt` |
| Dependent gains | Replace KD in the applicable row with `KP * 60 * KD`; rate time is in minutes |

Automatic output sums BIAS, P, I and D before limiting. D uses part of the
available output headroom when clipping an outward integral increment. Public
values and the calculated D term use finite float32; intermediate products use
host precision. UPD controls the difference quotient, independently of elapsed
simulation time. Authors must arrange the intended sampling rate.

The first reached sample, an INI reset, Run reentry and the first auto sample
after software manual produce zero D. Changing DOE, CA or input/engineering
scaling also primes a fresh baseline. Setpoint changes contribute to DOE=true
derivative; a setpoint change alone does not affect DOE=false derivative.
For unsmoothed D, changing gains uses current gains with the last compatible sample. Calls with
KD zero still refresh the baseline.

False or skipped calls do not sample PV/error. After a skipped interval the
next reached call uses the full sample difference divided by one UPD, with no
elapsed-time catch-up. Manual and held-deadband calls refresh the sample while
using zero D. DATA[1] and DATA[7] remain retained, uninterpreted values; this
profile does not invent a native filter accumulator or scaling coefficient.

## Derivative smoothing

App `26.1112.203745` adds a first-order low-pass filter when NDF is clear and KD
is positive. This is an explicit software solver choice, not a recovered native
coefficient or a claim of identical controller response. Let raw D be the term
calculated above. The simulator uses a fixed derivative/filter ratio of 10:

```text
tau = KD / 10                 independent gains, seconds
tau = 60 * KD / 10            dependent gains, KD in minutes
alpha = UPD / (UPD + tau)
filtered D = previous filtered D + alpha * (raw D - previous filtered D)
```

The dependent filter time excludes KP. Increasing KD increases smoothing relative
to raw D. The first sample starts at zero. Enabling smoothing, or changing KD,
UPD, independent/dependent mode, dependent KP, DOE, CA or PV scaling while smoothing
is active, primes a fresh zero baseline. Disabling smoothing immediately uses the
existing unsmoothed sampling rules. KD zero disables D.

Manual/inhold and held-deadband calls clear D while refreshing PV/error samples.
False/skipped calls preserve the filter and do not sample; the next call still
uses one UPD. Run reentry and clearing INI reset the filter. History belongs to
the canonical PID record, including aliases and supported AOI bindings; routine
replacement copies it, and a failed advance rolls it back. DATA[1]/DATA[7] remain
retained and do not seed the solver. Nonfinite/intermediate overflow keeps the
existing atomic failure policy.

In **PID lab**, set KP/KI to zero, BIAS to 50, KD to 10 and NDF false. Enable at
PV 20: CV is 50. Change PV to 21: CV is 45. Leave PV unchanged: CV is 47.5, then
48.75 as D decays. With NDF true, that PV step instead produces CV 40 and then 50.

## Deadband

DB zero disables control deadband. A positive DB is measured in engineering
units on either side of SP. This solver uses the inclusive region
`abs(error) <= DB`; EWD reports an **active output hold**.

- With NOZC true, entering the region immediately holds the previous output
  percentage and integral.
- With NOZC false, calculations continue on entry until error reaches zero or
  changes sign. The output then holds while error remains in the region.
  Crossing directly from outside into the opposite side of the region also
  starts a hold. Leaving the region clears the latch.
- A first call at exact zero counts as a crossing. A first held call uses a
  known represented OUT as its output seed and starts I at zero. Missing OUT
  faults only when this seed is required.
- Changing DB, NOZC, SP, CA or input/engineering scaling rearms zero-crossing
  detection. A new exact-zero sample can immediately hold again. With NOZC
  true, a sample still inside the new region continues to hold.

Held calls refresh PV/error samples and alarms, clear derivative action, retain
I, and hold output percent. KI zero can still clear the active integral. Current
automatic limits clamp a held percentage; current output scaling converts that
percentage into CV. Changing limits or output scaling can therefore change CV
during a hold. Direct writes to OUT/EWD do not replace existing hidden history.

Software manual overrides deadband, updates SO/output and clears the crossing
latch. It still tracks I or BIAS as described by the main PID contract. On
return to auto, NOZC can hold the manual percentage immediately; zero-crossing
mode instead starts new crossing detection. False/skipped calls retain the
latch. Run/INI reset hidden history; a first held call again requires saved OUT.

These boundary, startup, transfer and configuration-change rules are simulator
choices requiring native qualification. EWD is not a complete native status
model. [Hardware manual and narrow integer operands](pid-operands.md) are now supported.
[Manual PV tracking and explicit inhold](pid-restart.md) also execute.
[One-way cascade](pid-cascade.md) and [ladder AOI bodies](aoi-pid.md) also execute.
Cascade feedback, analog module restart/acknowledgement, other operand types,
ST PID forms, native minor faults and packed DATA layouts remain unfinished.

## Try the existing PID lab

For an isolated derivative example, load **PID lab**, set Loop.KP/Loop.KI to
zero, Loop.BIAS to 50, Loop.NDF true and Loop.KD to 2. Set Execute true and
step at PV 20: CV is 50. Change PV to 25 and step: CV is 40; the next unchanged
sample returns CV to 50. Set DOE true to include setpoint changes.

For deadband, reload the lab, set Loop.DB to 2 and Loop.NOZC true. Set Execute
true and step at PV 20: CV is 45. Values PV 49 and 51 hold CV at 45; PV 53
releases it to 10.5. Reload with NOZC false to observe continued calculations
before crossing SP. FaultDivisor zero demonstrates rollback and corrected retry.

Reference basis: installed v35 help 14709/14717/14737/14738 and published
[derivative smoothing guidance](https://www.rockwellautomation.com/en-ro/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/special-instructions/proportional-integral-derivative--pid-/derivative-smoothing--pid-.html)
and [deadband guidance](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/special-instructions/proportional-integral-derivative--pid-/setting-the-deadband--pid-.html).
