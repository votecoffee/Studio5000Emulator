# Sequencer operand selection

The v35 ControlLogix 5580 L81E–L85E ladder profile validates SQI/SQO/SQL
without consuming saved mask or payload indices. Declared types, scalar shapes,
permissions, literal bounds, pseudo-operands and existing overlap restrictions
remain checked. See [implementation](../source/logixlab/sequencer_operations.py)
and [checks](../source/tests/test_sequencer_operands.py).

```text
XIC(Advance)SQO(Table[0],Masks[MaskIndex],Outputs[OutputIndex],State,?,?);
XIC(Check)SQI(Table[0],Masks[MaskIndex],Inputs[SourceIndex],State,?,?);
XIC(Teach)SQL(Learned[0],Values[SourceIndex],TeachState,?,?);
```

This extends [table-start selection](sequencer-references.md) to masks and
separate scalar payloads. DINT tables, SQO destinations and SQI/SQL source rules
remain; masks retain SINT/INT/DINT tags and bounded immediate patterns. No new
types, conversion algorithms, instruction mnemonics or ST/FBD/SFC forms are added.

## Paths that consume operands

Preflight checks declared shapes without live dynamic indices or saved numeric
data. False calls skip live masks and payloads. Existing invalid CONTROL-state
paths also skip them while applying their established ER/data-retention policy.

Reached data paths still resolve and check the complete configured table
window, including startup row zero. They then read the actual mask. A zero
mask skips table-row values and live compared-source/SQO-output references;
the table address and window must already be valid. A nonzero mask requires
the selected known table row and the actual compared input or writable output.
Full-mask SQO writes establish unknown destinations. Partial masks require
known old output bits to preserve them.

SQL reads its actual source when it writes the current row. Held true SQL
calls reload current data, and held true SQO calls reapply the current row and
mask to the current destination. Their POS does not advance again without a
new enable edge. A changed indirect payload or mask index therefore matters
on a held true call; these are not queue load/unload latches.

Actual CONTROL addresses remain required at runtime, including false calls.
SQO/SQL prescan selects the actual control and sets EN; SQI has no prescan
write. The existing runtime LEN/POS/EN reads and row/edge rules remain. These
changes do not make every false CONTROL index dormant.

## Boundaries and recovery

Aliases, constant sources and supported AOI local/InOut references retain
canonical storage and frame scope. Data, flags, time, scheduler and AOI bindings
roll back within the modeled advance when a consumed index/value, a SQL window
or a later instruction faults. Completed prescan is a separate boundary.

SQI/SQO keep their existing ER policy for valid starts with short configured
table windows; SQL window failures stop the advance. Live invalid starting
indices still fault. No packed layouts, native invalid-state/fault/status,
partial effects or full controller parity are qualified here. Other profiles
and broader source types remain outside this sequencer execution profile.

## Sequence lab

Choose **Sequence lab** and step once. Its called **IndirectOperands** routine
has three gated examples. MaskIndex, OutputIndex and SourceIndex start at 99;
saved mask/input/output values are unknown. Disabled examples skip them.

Set MaskIndex=1, Masks[1]=-1, OutputIndex=1, SourceIndex=1,
FeedbackInputs[1]=1 and TeachInputs[1]=67. Enable IndexedAdvance, IndexedCompare
and IndexedTeach, then step:

| Value | Result |
| --- | --- |
| IndexedOutputs[1] | 1 from the current pattern row |
| IndexedMatches | true |
| IndexedLearned[1] | 67 |
| IndexedSequenceControl.POS / IndexedTeachControl.POS | 1 / 1 |

While those gates stay true, change IndexedPatterns[1]=4,
FeedbackInputs[1]=4 and TeachInputs[1]=77. Another step reapplies/reloads those
values with both positions still 1. Guards 999 and the startup learned value
111 remain. Disable IndexedTeach, then set Masks[1]=0 and both payload indices
to 99: output remains unchanged and comparison passes after table checks.
Restore the indices before restoring a nonzero mask. Unknown required values
or invalid live indices fault transactionally and can be corrected and retried.
See [SequenceLab.L5X](../source/samples/SequenceLab.L5X).

Rockwell's [SQO reference](https://www.rockwellautomation.com/en-ua/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/sequencer-instructions/sequencer-output--sqo-.html)
describes enable-edge positioning and enabled masked output updates. Structural
unknown handling, zero-mask address selection and transactional boundaries here
are explicit software policies, not native Studio/controller acceptance.

[Sequencer source types](sequencer-sources.md) add explicit narrow payload and
full-pattern rules; no FIFO REAL conversion or non-DINT SQO result is admitted.
Structural/lazy selection and rollback above remain unchanged.
