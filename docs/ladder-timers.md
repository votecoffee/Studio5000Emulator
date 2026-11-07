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

## Literal presets on import

The v35 5580 profile accepts DINT PRE and ACC initializers on TON, TOF,
RTO, CTU and CTD in imported Standard ladder routines. Use signed decimal
values or unsigned binary, octal, or hexadecimal patterns up to 32 bits.
Short radix patterns zero-fill to DINT width. For example, 16#FFFF is
65,535 and 16#FFFF_FFFF is -1. Each `?` keeps its corresponding saved
member. TIMER initializers must be nonnegative and COUNTER initializers
can be signed. The target must resolve to one writable record,
such as a base tag, a statically selected array element or a UDT member.
Static aliases can select those records through up to eight hops. Every
subscript must be literal, including subscripts inside AliasFor. AOI bodies
and computed indices use the neutral-text profile. During [routine replacement](supported-routine-edits.md#transaction-and-activation),
the emulator can retain an existing initializer through changes to surrounding
ladder logic. The opcode and operands must match. Live values carry over, and
new or changed initializers must use neutral pseudo-operands.

A fresh emulator image applies the literals once. Scans and Run transitions use
the live members. Ordinary prescan still clears TON/TOF ACC and preserves RTO
ACC. Recreating the initial image reapplies the initializers. Identical values
for the same member can share a backing record. Conflicting values block the
project and preserve the saved image, since L5X routine order does not establish
which value was last edited in Studio.

Rockwell documents download-time initialization in installed v35 help 454960
and its [pseudo-operand initialization reference](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/pseudo-operand-initialization.html).

## Consumed values

Every reached call requires known nonnegative DINT PRE and ACC. True TON/RTO
and false TOF raise [Type 4 Code 34](controller-handlers.md#recover-negative-timing-values)
for negative DINT values during whole-project ladder execution. Other rung
states still reject negative values through scan rollback. Unknown and
out-of-range values remain errors even when the instruction would overwrite
a field. Old TT is not consumed.

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

A cleared [Type 4 Code 20](controller-handlers.md#recover-timer-counter-and-reset-array-faults)
or [Type 4 Code 34](controller-handlers.md#recover-negative-timing-values)
skips the timer in a whole-project scan and retains its last execution time.
Unknown consumed fields, unrecovered faults, accumulator overflow and later
errors restore values, clock history, AOI bindings, time and scheduling within
the modeled advance. Completed prescan is a separate lifecycle boundary. No new ST
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
For explicit initializers, enable LiteralPresets and step with LiteralInput
false. The ladder rungs use LiteralTimerAlias and LiteralCounterAlias to
initialize the backing records using 16#32, 2#1010, 8#4, and
16#FFFF_FFFF. Set LiteralInput true and step twice at 10 ms.
LiteralRetained starts
at PRE=50 and ACC=10, then reaches ACC=20. LiteralCount starts at PRE=4 and
ACC=-1, increments to zero on the rising edge and holds. Changing either live
PRE persists across steps. Reset restores the imported values.
See [TimerLab.L5X](../source/samples/TimerLab.L5X).

The reference basis is installed Logix Designer v35 help 14742 (TON), 14744
(TOF) and 14747 (RTO), including millisecond units, EN/TT/DN and prescan.
Unknown-value selection and transactional rollback are explicit software-model
policies. These checks do not establish native Studio/controller equivalence.
