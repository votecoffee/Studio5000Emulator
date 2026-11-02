# Explicit-target bit moves in ST and FBD

BTDT and MVMT execute as one-record Structured Text calls and FBD Blocks in the
bounded v35 ControlLogix 5580 DINT profile. BTDT adds a logical
FBD_BIT_FIELD_DISTRIBUTE record. MVMT shares the existing FBD_MASKED_MOVE model
with its [FBD bitwise form](fbd-bitwise.md). RLL BTD/MVM keep their separate
[operand/width rules](bit-transfer.md); BTDT/MVMT are not enabled as RLL calls.

| Instruction | Logical record | DINT inputs | DINT output |
| --- | --- | --- | --- |
| BTDT | FBD_BIT_FIELD_DISTRIBUTE | Source, SourceBit, Length, DestBit, Target | Dest |
| MVMT | FBD_MASKED_MOVE | Source, Mask, Target | Dest |

Both records also contain BOOL EnableIn and EnableOut. Every enabled call starts
from explicit Target, rather than the previous Dest. Source and Target are not
modified. Results preserve 32-bit patterns and are represented as signed DINT.
MVMT replaces bits selected by Mask. BTDT extracts Length bits starting at
SourceBit, aligns them at DestBit and replaces that destination field. Bits
outside the destination word are discarded without wrapping. Source excess is
zero-filled under this software profile; native source-excess qualification
remains open.

BTDT SourceBit/DestBit must be 0..31 and Length must be 1..32. Parameters are
values read on every call, allowing dynamic field selection. The declaration
shape leaves Length at zero, requiring a valid configured value before execution;
missing saved fields remain unknown. Every required field must be a known signed
DINT, including Target during a full replacement and Source with a zero MVMT
mask. Invalid/unknown values fail and roll back the whole simulation advance.
Native invalid-range/fault behavior and math flags remain unqualified.

Prescan clears EnableIn/EnableOut and retains Dest for both instructions. A
reached ST call sets enables and executes regardless of stored false EnableIn;
skipping the call retains values. FBD connected false EnableIn clears enables
and retains Dest without reading operands; unwired enable executes. Direct Dest
writes survive skipped/disabled calls and are replaced on enabled execution.
No hidden move history is added. Run entry reapplies the prescan rules.

ST loop analysis treats the backing record as written, protecting any loop
bound/step dependency that overlaps it. Typed AOI InOut binding, Program aliases,
nested records/arrays, Periodic/instruction-only Event tasks and routine harnesses
use existing memory/call rules. Values, enables, later errors, time, trace and
scheduling participate in whole-advance rollback. Supported detached RLL caller
replacement preserves results. Postscan and complete native lifecycle behavior
remain unfinished.

Choose **Target bit move lab** for `TargetMoveLab.L5X`: 23 roots, a ladder caller,
one ST routine and one FBD sheet with two blocks, twelve nodes and thirteen wires.
Both languages transfer Word 16#12345678 bits 4..11 into BaseWord 16#230000AA at
bit 16, producing 16#236700AA. MVMT then replaces the low byte, producing
16#23670078. Change offsets, length, mask, word and target to compare results.
BlockEnable gates only FBD; ExecuteText/ExecuteGraph skip calls independently.
FaultDivisor zero demonstrates rollback after both paths execute.

The inventory is 102 RLL entries, 29 ST-call entries and 63 FBD forms: 23 shared
ST-call names, 34 common RLL names and six FBD-only names. All 222 catalog
identities remain; 55 have dedicated bounded models and 167 have none. These
counts do not establish complete type/instruction coverage or native equivalence.

Schemas and lifecycle tables were checked against installed v35 help 14684.htm
and 14690.htm, with Rockwell's
[general-instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
as corroboration. Other types/forms, tagless Functions, packed layouts, native
flags/fault/source-excess/lifecycle behavior and Studio import/Verify/transfer/edit
qualification remain unsupported or unverified.
