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
rung. Negative presets and counts are valid. A true rung requires a known BOOL
CU/CD history bit. A false rung establishes that instruction's edge bit as
false without consuming its prior value.

A false-to-true edge increments or decrements once. Held true does not repeat.
CTU wraps maximum to minimum and sets OV. CTD wraps minimum to maximum and
sets UN. While either flag is set, false rungs, held true rungs and ordinary
count edges retain DN. If the opposite flag is already set at a wrap, the
instruction clears both flags and immediately sets DN from ACC >= PRE.
With neither flag set, each reached call compares ACC with PRE.

The emulator keeps its existing treatment of omitted OV/UN values. An unknown
flag alone does not inhibit the DN comparison or cancel a new wrap latch.
Untouched fields retain their saved values, including unknowns.

Structural preflight checks record shape, declared type, reference grammar,
permissions and neutral operands without requiring saved field values. Counter
prescan resolves actual addresses and establishes CU/CD true to suppress
startup edges. An out-of-bounds selection
[skips that instruction during prescan](controller-handlers.md#skip-timer-and-counter-array-faults-during-prescan).
Unknown indices and errors caught by structural validation still block
initialization. Reached counter operations need a valid address and their
consumed values.

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
[CONTROL RES](control-operands.md#control-reset) has its own field rules.

A [cleared Type 4 Code 20](controller-handlers.md#recover-timer-counter-and-reset-array-faults)
skips a count or reset in a whole-project scan and preserves the records.
Unrecovered faults and later errors restore prior values, counts, flags,
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
(CTD) and 14733 (RES), and the [published CTU and CTD flowcharts](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
Unknown-value handling and transactional rollback are
explicit software-model policies; tests do not establish native equivalence.
