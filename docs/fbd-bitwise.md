# FBD bitwise and masked operations

AND, OR, XOR, NOT, MEQ and MVMT execute as FBD Blocks in the bounded v35
ControlLogix 5580 DINT profile. Four logical predefined records now have dedicated
models. Exact BOOL/DINT members are represented; missing saved fields remain
unknown. Other operations associated with those records are not automatically enabled.

| Block | Logical record | DINT inputs | Dest type |
| --- | --- | --- | --- |
| AND / OR / XOR | FBD_LOGICAL | SourceA, SourceB | DINT |
| NOT | FBD_CONVERT | Source | DINT |
| MEQ | FBD_MASK_EQUAL | Source, Mask, Compare | BOOL |
| MVMT | FBD_MASKED_MOVE | Source, Mask, Target | DINT |

Each record also contains BOOL EnableIn and EnableOut. AND/OR/XOR operate on
32-bit patterns; NOT flips all 32 bits. Numeric outputs are signed DINT values.
MEQ compares `(Source & Mask)` with `(Compare & Mask)`, returning a real BOOL.
MVMT combines Source bits selected by Mask with the remaining bits from Target.
It reads Target on every enabled call and never uses the previous Dest as a
baseline. Mask zero returns Target; all bits set returns Source. Negative masks
and the sign bit are supported. Wider, mixed, REAL and tagless Function forms
remain outside this Block profile. ST MVMT calls are still unsupported.

Every required operand must be a known signed DINT, including Source/Compare
with a zero mask and Target with a full mask. The model does not infer a known
result from incomplete data. Invalid/unknown required fields fail and roll back
the whole simulation advance. Existing ladder MVM has its separate documented
no-op/full-replacement operand policy.

Prescan retains enables/Dest for AND/OR/XOR/NOT/MEQ, following their v35 N/A
tables. MVMT prescan clears EnableIn/EnableOut and retains Dest. Connected false
EnableIn clears enables and retains Dest for all six; unwired enable executes.
Skipped routine calls retain values. Direct Dest writes survive disabled/skipped
calls and are overwritten by enabled execution. There is no hidden bitwise state.
Run entry reapplies each family's prescan and resets existing timer/selector history.

Exact typed wires connect DINT results to other bitwise inputs and MEQ's BOOL
result to selectors/timers. Values, enables, outputs, timer/selector history,
later errors, time, task scheduling and trace use the existing whole-advance
transaction. Continuous/Periodic/instruction-only Event tasks, routine harnesses
and supported detached RLL caller replacements use the same models. The
[single-sheet graph rules](function-blocks.md) still apply.

Choose **FBD bitwise lab** for `FBDBitwiseLab.L5X`: 32 roots, eight blocks, 28
nodes and 37 wires. A 170 and B 204 produce AND 136, OR 238, XOR 102 and NOT -103.
Mask 15 merges A with Target 240 to produce 250; masked comparison against 10
returns true. That condition selects 100 and starts a 20 ms TONR. BlockEnable
gates all eight blocks; ExecuteGraph skips the routine; ResetTimer is separate
from the comparison. FaultDivisor zero demonstrates late-error rollback.

The graph inventory is 46 blocks: 21 shared ST-call names, 18 common RLL names
and seven FBD-only forms. RLL remains 101 and ST calls 27. The 222-entry catalog
retains all identities and now has 52 dedicated bounded models and 170 entries
without one. These counts do not establish full type or native controller parity.

Schemas, algorithms and prescan tables were checked against installed v35 help
14670.htm, 14687.htm, 14683.htm, 14669.htm, 14602.htm and 14690.htm, alongside
Rockwell's [general-instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
Native math flags, fault/lifecycle behavior, packed layouts, Studio import/Verify
and transfer/edit qualification remain unfinished or unverified.
