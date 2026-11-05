# Ladder counters and timer/counter resets

The v35 ControlLogix 5580 L81E–L85E software profile supports bounded CTU,
CTD and TIMER/COUNTER RES behavior. Neutral text uses the saved record fields:

```text
CTU(Counter,?,?);
CTD(Counter,?,?);
RES(CounterOrTimer);
```

Operands select one writable COUNTER or TIMER record, including scalar tags,
selected array elements, explicit UDT members, aliases and existing AOI local/
InOut bindings. COUNTER and TIMER retain their logical member schemas; this
does not qualify native packed layouts. See [runtime.py](../source/logixlab/runtime.py)
and [checks](../source/tests/test_ladder_counters.py).

Imported Standard ladder CTU/CTD can use signed decimal DINT
[PRE/ACC initializers](ladder-timers.md#literal-presets-on-import).
Counting uses the live members after initialization.

## Counting and unknown values

Each reached CTU/CTD requires known signed DINT PRE and ACC, including a false
rung, because it computes DN from ACC >= PRE. Negative presets and counts are
valid. A true rung requires a known BOOL CU/CD history bit; unknown history
cannot be treated as false to create a count. A false rung establishes that
instruction's edge bit as false without consuming its prior value.

A false-to-true edge increments or decrements once. Held true does not repeat.
Signed DINT wrap retains the existing model: CTU wraps maximum to minimum and
sets OV; CTD wraps minimum to maximum and sets UN. Unread opposite-edge and
overflow/underflow flags retain their values, including unknowns. DN and the
executed instruction's edge flag are complete BOOL writes.

Structural preflight checks record shape, declared type, reference grammar,
permissions and neutral operands without requiring saved field values. Counter
prescan still resolves actual addresses and establishes CU/CD true to suppress
startup edges. A bad or unknown selected counter index at prescan remains a
blocker, even if its rung would be false. Reached counter operations likewise
need a valid record address and their consumed values.

## Reset selection

RES preserves PRE and establishes ACC=0 and all timer/counter status bits false.
It does not need old ACC/status values or a known preset. An unknown or negative
PRE remains unchanged. False RES and ordinary RES prescan do not consume live
indices or record values. True RES resolves the actual writable record address;
an invalid or unknown index faults. Static literal-index/type/permission errors
remain blockers regardless of rung power.

A reset can initialize an unknown counter accumulator and edge/status fields.
Counting still requires its preset to be known. RES does not operate on
FBD_COUNTER; [ST CTUD](st-counter.md) uses that type's Reset input instead.
The existing CONTROL RES contract is separate and unchanged.

Counter/reset faults and later faults restore prior values, counts, flags,
AOI bindings, time and scheduling within the modeled advance. Completed prescan
is a separate lifecycle boundary. Other controller profiles, timer clock
algorithms, Postscan, native faults/status/retention and full native execution
parity remain unfinished. No new ST or FBD forms are introduced.

## Counter lab

Choose **Counter lab**. Its original ST CTUD example remains enabled. Two called
ladder routines add these examples:

1. Set LadderCounter and ResetCount true and step. LadderCounts[0] receives
   ACC=0 and false edge/status bits while PRE remains 3. Clear ResetCount.
2. Toggle UpInput false/true with a step after each change. The ladder count
   advances once per edge; three increments set LadderDone. DownInput decrements
   and clears LadderDone when the count falls below PRE. Held inputs count once.
3. ResetIndex initially equals 99. Set it to 0, set ResetRecord true and step.
   ResetCounters[0] and ResetTimers[0] receive ACC=0 and false flags; PRE remains
   unknown. Sibling records stay unknown. Clear ResetRecord afterward.

Enabling LadderCounter before initialization reports unknown ACC and rolls back
the scan. Set ResetCount true and retry to initialize it. Enabling ResetRecord
at index 99 faults; correct the index and retry. CounterIndex must remain valid
for counter prescan and execution. Disabling LadderCounter skips its routine
and retains its count/output. See [CounterLab.L5X](../source/samples/CounterLab.L5X).

The reference basis is installed Logix Designer v35 help 14736 (CTU), 14730
(CTD) and 14733 (RES): edge counting, prescan initialization, signed boundaries
and reset effects. Unknown-value handling and transactional rollback are
explicit software-model policies; tests do not establish native equivalence.
