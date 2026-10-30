# Structured Text timers

App `26.1030.084708` adds TONR, TOFR and RTOR calls for the bounded v35
ControlLogix 5580 profile. Each takes one writable FBD_TIMER record. These are
ST-only calls in this implementation; they do not add ladder instructions or
FBD graph execution. The RLL dispatch inventory remains 99 entries.

```text
OnDelay.PRE := 500;
OnDelay.TimerEnable := Input;
OnDelay.Reset := ResetTimers;
TONR(OnDelay);
Output := OnDelay.DN;
```

The logical record has BOOL EnableIn, TimerEnable, Reset, EnableOut, EN, TT and
DN fields, and DINT PRE, ACC and Status fields. ACC and PRE count milliseconds.
InstructFault and PresetInv are aliases of Status.0 and Status.1, sharing the
same backing value rather than independent flags. Missing exported fields
remain unknown; the schema does not invent saved values.

## Executed calls and elapsed time

An executed ST call sets EnableIn; its stored value is not an ST execution gate.
Use TimerEnable or an ST conditional to control behavior. Each record has an
independent simulated elapsed-time history, tied to its resolved storage.
Aliases, array elements, represented UDT members, program locals and existing
AOI InOut bindings use the same memory/reference rules as other supported calls.

Timing uses integer simulated milliseconds between reached calls while the
timer was actively timing. Repeated calls at the same release timestamp do not
double-count elapsed time. Skipping an active timer retains its outputs and
history; the next reached call includes the skipped interval. A called timer
that stops timing pauses that history. Resuming starts from that call, without
charging an earlier disabled interval.

The model saturates active ACC at PRE. Native overshoot, clock rollover, hidden
timestamp precision and long skipped-interval parity remain unqualified.
Different timer instruction kinds sharing one record are rejected during
execution rather than given an invented mixed state.

## Timer behavior

| Call | TimerEnable true | TimerEnable false | Reset true |
| --- | --- | --- | --- |
| TONR | Start/continue on delay; DN at PRE | Clear ACC, EN, TT and DN | Clear ACC, EN, TT and DN |
| RTOR | Start/continue retained on delay; DN at PRE | Retain ACC/DN; clear EN/TT | Clear ACC, EN, TT and DN |
| TOFR | Arm the off delay; ACC=0, EN/DN=true, TT=false | After arming, time with DN/TT true until PRE; then clear them | ACC=PRE; clear EN/TT/DN and disarm |

Reset has priority over TimerEnable. TONR/RTOR restart after Reset clears when
enabled. TOFR reset while TimerEnable is false requires a later true enable
before another off delay. An initially false TOFR does not start timing.

On the first valid call after initialization, EN/TT/DN are cleared; TONR also
initializes ACC to zero. RTOR and TOFR retain represented ACC before the normal
algorithm applies. Prescan clears EnableIn/EnableOut only. Run entry resets the
elapsed-time history; first-call initialization happens when the site executes.
Deferred import preview preserves saved values until Run entry.

## Status and failures

The current instruction-status policy sets Status=3 and EnableOut=false for a
negative PRE, leaves the timer outputs/ACC unchanged, and pauses timing. A
valid call clears Status and sets EnableOut=true. This is an instruction result,
so a negative preset alone does not fault the entire simulated scan.

Required unknown PRE, TimerEnable, Reset or accumulator values fault. Writes
such as TONR initialization or Reset can establish an unknown ACC. Fields not
needed by a path remain unknown rather than being treated as zero or false.
Negative retained ACC is rejected when timing requires it.

Values and hidden elapsed-time history share the existing whole-advance rollback.
A later fault or budget failure restores both, including task phases and scan
counts. Prescan failures also restore the prior values/history. Supported routine
replacement retains the elapsed-time history with the rest of engine state.
FOR dependency checks treat the timer record as written by the call.

The profile rejects wrong operand counts, scalar/non-FBD_TIMER arguments,
constant records, redefined FBD_TIMER schemas and other controller profiles.
Ladder RES is not a reset operation for this type; use the Reset member.
Native status/fault classification, packed layouts/transfers and complete
firmware/controller equivalence remain unverified.

## Try Timer Lab

Choose **Timer lab** and step. TimerEnable starts true and Preset is 30 ms.
On and Retained reach DN after timing; Off is armed with DN=true. Set
TimerEnable=false and step repeatedly: On resets, Retained keeps its ACC, and
Off times before dropping DN. ResetTimers resets all three, with Off.ACC=PRE.

CallTimers=false skips the calls. Re-enabling it demonstrates elapsed time
across skipped scans. Preset=-1 demonstrates instruction status; restoring a
valid preset resumes the model. FaultDivisor=0 introduces a late scan fault.
Correct it to 1 before retrying; timer values, clocks and TimerCalls then commit
once. [TimerLab.L5X](../source/samples/TimerLab.L5X),
[implementation](../source/logixlab/st_timers.py) and
[checks](../source/tests/test_st_timers.py) describe the exact scope.

The installed v35 help and Rockwell's
[TONR](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/timer-and-counter-instructions/timer-on-delay-with-reset--tonr-.html),
[TOFR](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/timer-and-counter-instructions/timer-off-delay-with-reset--tofr-.html)
and [RTOR](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/timer-and-counter-instructions/retentive-timer-on-with-reset--rtor-.html)
references provide the instruction syntax and behavior. The software checks
remain separate from native Studio/controller acceptance.
