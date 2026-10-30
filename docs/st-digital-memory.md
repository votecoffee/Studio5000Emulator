# Structured Text Boolean memory

App `26.1030.142312` adds bounded v35 ControlLogix 5580 ST DFF, JKFF, RESD and
SETD calls. Choose **Digital lab**, or launch with `--sample DigitalLab`. Clock,
DInput and Clear control the flip-flops. SetInput and ResetInput control both
dominant latches. CallLogic skips all four calls. Outputs, complements and
expanded record members show their state; FaultDivisor supplies a late fault.

```text
DFF(DState);
JKFF(ToggleState);
RESD(ResetState);
SETD(SetState);
```

These four models also execute in the limited [FBD graph](fbd-boolean.md)
with connected-enable gating and shared history. General FBD and native
initialization/postscan/layout/fault qualification remain unfinished.

## Logical records

Every member below is BOOL. EnableIn is true in the default shape; inputs default
false. Missing saved members remain unknown rather than being filled from those
defaults. These are named logical records, without a native packed-layout claim.

| Instruction | Type | Members |
| --- | --- | --- |
| DFF | FLIP_FLOP_D | EnableIn, D, Clear, Clock, EnableOut, Q, QNot |
| JKFF | FLIP_FLOP_JK | EnableIn, Clear, Clock, EnableOut, Q, QNot |
| RESD | DOMINANT_RESET | EnableIn, Set, Reset, EnableOut, Out, OutNot |
| SETD | DOMINANT_SET | EnableIn, Set, Reset, EnableOut, Out, OutNot |

The v35 JKFF is a clocked toggle with Clear. Its record has no J or K inputs.
Constant destinations, redefined records, mismatched types and ladder forms are
blocked. Scalars, nested members, arrays/indirect elements, aliases, program-local
tags and supported AOI InOut bindings use resolved per-record histories.

## Flip-flops and dominance

DFF samples D on a reached false-to-true Clock transition. JKFF toggles Q on that
transition. Clear wins over either operation: it clears Q and sets QNot. Clock
history is updated on every reached call, including while Clear is true. Thus
releasing Clear while Clock remains high does not create an edge; a sampled low
and subsequent high are needed. QNot is recomputed as the complement of Q.

DFF/JKFF startup history has previous Clock true and previous Q false. A high
clock on the first call therefore does not capture or toggle. Starting low arms
the next rising edge. D is read only on an uncleared rising edge; Clear and Clock
must always be known because the latter still updates history during Clear.

The latch truth tables are:

| Set | Reset | RESD Out | SETD Out |
| --- | --- | --- | --- |
| false | false | Retain | Retain |
| false | true | false | false |
| true | false | true | true |
| true | true | false | true |

RESD's initial retained output is false. SETD's is true. On the first reached
call this model applies that startup state and then the current inputs. Held
inputs remain level-sensitive. OutNot is always the complement of the computed
Out. A known dominant true input can bypass an unknown subordinate input: Reset
for RESD, Set for SETD. Other required unknown inputs fault the advance.

## Calls, lifecycle and rollback

Reached ST calls force EnableIn and EnableOut true regardless of their saved
values. Skipping a call retains outputs, enable bits and history. Clock pulses
entirely between reached calls are not sampled. Repeated calls at one simulated
timestamp can sample multiple edges if the program actually changes Clock low
and high between them; holding it high does not toggle repeatedly.

The model retains previous clock/output separately from visible output members.
Direct Q/Out/complement writes do not replace that retained state; the next
reached call recomputes outputs. Native output-write interactions and some
startup/skip/lifecycle details still require qualification.

Prescan clears the enable pair while preserving visible output values. Run entry
clears hidden histories; startup applies on the next reached call. Supported
detached routine replacement preserves existing histories. Periodic, Event,
Continuous, harness, AOI and loop execution share the same per-call rules.
Preempting tasks accessing the same record share its history in dispatch order.

Unknown required inputs, malformed raw Boolean values, instruction-budget limits
or a later error roll back the entire advance, including sampled clocks, retained
outputs, tag values, time and scheduler counters. Failed Clear, Set/Reset or clock
transitions cannot affect a corrected retry. Prescan failure restores prior state.

These four models do not establish complete predefined-type or FBD support.
FBD graph execution, native packed layouts, other controller profiles and native
startup/Run/skip/postscan/output-write/status/fault parity remain unfinished.
Studio transfer and online-edit acceptance are separate.

The schemas, truth tables and startup values were checked against installed
Studio v35 DFF/JKFF/RESD/SETD help and Rockwell's
[Advanced Process Control and Drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
The public sample is synthetic; vendor help assets are not included.
