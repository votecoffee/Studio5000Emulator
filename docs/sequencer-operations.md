# DINT ladder sequencers

LogixLab models these v35 ControlLogix 5580 forms using logical CONTROL state:

```text
SQO(Array,Mask,Dest,Control,?,?);
SQI(Array,Mask,Source,Control,?,?);
SQL(Array,Source,Control,?,?);
```

Tables and SQO destinations use DINT. SQI/SQL sources use DINT tags or bounded
integer immediates. Masks accept SINT/INT/DINT bit patterns or 32-bit radix
immediates; shorter masks are zero-filled. Other source types remain unsupported.
LEN/POS come from saved CONTROL members; pseudo-operands do not initialize them.
See [implementation](../source/logixlab/sequencer_operations.py) and
[logical CONTROL](control-operations.md).

## Rows and scan behavior

Row zero is the startup row. Cyclic rows run from 1 through LEN, including the
last row, then wrap to one on the next enable edge. The bounded profile requires
the entire configured LEN+1 region to fit within its selected array member,
with at most 4096 elements. This whole-region rule is a software qualification,
not a claim about native bounds checking.

Prescan sets SQO/SQL EN; a false rung clears EN. With EN clear, a true rung
advances POS and sets EN. SQO writes the masked current row to Dest on every
true scan, retaining unmasked destination bits. SQL reloads the current row
from Source on every true scan. Held true therefore updates data without
advancing POS. DN indicates the last cyclic row.

SQI compares the masked current row with Source, passing rung power only on
equality. It does not advance POS or change EN/DN, so it can share the SQO
position to check feedback. A zero mask passes comparison or leaves SQO output
unchanged without requiring known source/destination data.

## Errors and limits

SQO/SQL clear ER on a new enable edge; SQI clears ER on a true evaluation.
Modeled invalid lengths/positions set ER and retain data. Invalid SQI state
also returns false. Physical table bounds set SQO/SQI ER without data movement;
SQL bounds stop and roll back the modeled advance. Resource limits, unknown
required values and later execution faults also roll back data, flags, time
and scheduling. Native fault classification and partial side effects remain
separate work.

Input tables may be constant. SQL tables and CONTROL records must be writable.
Array starts require static literal indices; indirect/alias starts and AOI
array bindings remain unqualified. SQO destinations cannot share the table base
tag. Mixed source types, ST/FBD forms, other controller profiles and native
CONTROL layout/scan/status parity remain unfinished.

## Sequence Lab

Choose **Sequence lab**, then **Step scan** once. Pulse Advance to cycle Outputs
through low-byte patterns 1, 2 and 4, retaining its upper bits. Set Feedback to
the selected pattern to observe Matches. While Advance stays true, changing
the current Patterns row updates Outputs without moving POS.

Pulse Teach to load TeachValue into Learned; change TeachValue and step while
Teach stays true to reload that row. The sample also includes the numeric stack
described in [CONTROL operations](control-operations.md). Guard values remain
999 outside each configured region. See [SequenceLab.L5X](../source/samples/SequenceLab.L5X).

The baseline was checked against installed v35 help 14703 (SQI), 14704 (SQO)
and 14706 (SQL), including their scan flowcharts. Published Rockwell
[SQO](https://www.rockwellautomation.com/en-ua/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/sequencer-instructions/sequencer-output--sqo-.html)
and [SQL](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/sequencer-instructions/sequencer-load--sql-.html)
references provide context for later releases. Tests of this bounded software
profile do not establish native controller or Studio acceptance.
