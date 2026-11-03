# Ladder timer state selection

The v35 ControlLogix 5580 L81E–L85E software profile supports bounded TON,
TOF and RTO over scalar writable TIMER records. Selected array elements,
aliases, explicit UDT members and existing AOI local/InOut records use the
same logical fields. Neutral text uses saved PRE/ACC:

```text
TON(Timer,?,?);
TOF(Timer,?,?);
RTO(Timer,?,?);
```

See [runtime.py](../source/logixlab/runtime.py) and
[checks](../source/tests/test_ladder_timers.py).

## Consumed values

Every reached call requires known nonnegative DINT PRE and ACC. This retains
the model's existing negative-value checks on both rung states. Unknown,
negative or out-of-range values fail explicitly; an upcoming output write
does not bypass that check. Old TT is not consumed.

| Instruction and input power | Saved EN/DN selection |
| --- | --- |
| True TON/RTO | Both EN and DN must be known BOOLs: EN determines startup elapsed time and DN determines whether accumulation is paused. |
| False TON | Establishes EN/TT/DN false and ACC zero without reading old EN/DN. |
| False RTO | Establishes EN/TT false; retains ACC/DN, including unknown DN. |
| True TOF | Establishes EN/DN true, TT false and ACC zero without reading old EN/DN. |
| False TOF | Both EN and DN must be known BOOLs to select falling-edge timing and continued off-delay accumulation. |

Unknown history cannot be treated as false to infer a timing decision. For
example, a partially exported RTO can retain known ACC and unknown DN through
prescan and a false rung. Enabling it then faults until DN is established,
such as through [TIMER RES](ladder-counters.md#reset-selection).

Structural preflight checks shape, type, permissions, index grammar and neutral
operands without consuming saved fields. Prescan still needs actual timer
addresses. It clears EN/TT; TON/TOF also clear ACC/DN, while RTO retains them.
An unknown or invalid selected index at prescan remains a blocker even for a
false rung. Actual execution also requires a valid timer address.

## Existing clock policy

State validation retains the existing deterministic millisecond recurrence.
The first enabled TON/RTO call accumulates zero elapsed time; later calls add
time since the timer record's last execution. DN true pauses accumulation and
clears TT. False TON clears its accumulated state; false RTO retains it.
TOF true establishes its enabled state, and the first false call starts its
off-delay at zero elapsed time. Later false calls accumulate until PRE.

Aliases share the resolved record's clock identity. Other array elements and
AOI instances keep independent histories. An entirely skipped routine retains
the existing elapsed-since-last-call policy; this is not a newly qualified
native skipped-execution contract. Clock sources, precision, overshoot, timing
limits, native status/fault/retention and full controller parity remain separate.

Unknown consumed fields, invalid indices, accumulator overflow and later faults
restore values, clock history, AOI bindings, time and scheduling within the
modeled advance. Completed prescan is a separate lifecycle boundary. No new ST
or FBD forms are introduced; [ST timer calls](st-timers.md) retain their own
FBD_TIMER contract. Other controller profiles keep their previous path.

## Timer lab

Choose **Timer lab**. The original ST timers remain available. The optional
LadderTiming routine adds TON, TOF and RTO over three TIMER records with PRE=30.
The ladder presets are separate from the ST example's Preset input.

1. Set LadderReset and LadderTimers true and step. The reset initializes the
   ladder records, including LadderRetained's previously unknown DN. Clear
   LadderReset afterward.
2. Keep TimerEnable true and step at 10 ms. LadderOn and LadderRetained progress
   through ACC 0, 10, 20 and 30; reaching 30 sets DN and clears TT.
3. Set TimerEnable false. LadderOn clears, LadderRetained retains its state,
   and LadderOff times its off-delay through ACC 0, 10, 20 and 30 before clearing DN.

To try pause/resume, raise LadderRetained.PRE, clear its DN to resume, then set
DN true to pause. Disabling LadderTimers skips its routine and retains fields.
Enabling the initially retained timer without establishing DN reports an
explicit unknown-history fault and rolls back the scan; initialize it and retry.
See [TimerLab.L5X](../source/samples/TimerLab.L5X).

The reference basis is installed Logix Designer v35 help 14742 (TON), 14744
(TOF) and 14747 (RTO), including millisecond units, EN/TT/DN and prescan.
Unknown-value selection and transactional rollback are explicit software-model
policies. These checks do not establish native Studio/controller equivalence.
