# FBD comparisons and limit testing

EQU, NEQ, GRT, GEQ, LES, LEQ and LIM execute as FBD Blocks in the bounded v35
ControlLogix 5580 finite REAL profile. FBD_COMPARE and FBD_LIMIT now have dedicated
logical models with BOOL results. Missing saved fields stay unknown; declaration
shapes do not replace exported omissions.

| Block | Logical record | REAL inputs | BOOL outputs |
| --- | --- | --- | --- |
| EQU / NEQ / GRT / GEQ / LES / LEQ | FBD_COMPARE | SourceA, SourceB | EnableOut, Dest |
| LIM | FBD_LIMIT | LowLimit, Test, HighLimit | EnableOut, Dest |

Both records also contain BOOL EnableIn. Binary comparisons use their named
relation over represented float32 inputs, without an equality tolerance. Signed
zero values compare equal. Rounding can make two supplied numbers represent the
same REAL value. Integer/wide/string comparisons and tagless Function forms are
not included in these Block models.

LIM includes both boundaries. With LowLimit <= HighLimit, Dest is true when
LowLimit <= Test <= HighLimit. Reversed limits select the outside region:
Test >= LowLimit or Test <= HighLimit. Equal limits select their exact value.
Every required operand must be known and finite, even if another operand could
determine the answer. Unknown values never become an inferred FALSE or TRUE.
Native NaN/infinity comparison rules are excluded; those cases fail and roll
back the simulation advance instead of producing a substitute condition.

Prescan retains comparison enables/Dest, following the installed v35 N/A tables.
Connected false EnableIn clears EnableOut and retains Dest; unwired EnableIn is
true. Skipped calls retain visible results. Direct Dest writes can survive a
disabled/skipped call and are replaced on the next enabled comparison. The new
blocks have no hidden state. Run entry preserves their represented fields while
existing selector/timer families apply their own lifecycle rules.

Dest and EnableOut can drive BOOL ORefs, selector controls, timer controls and
other qualified BOOL pins. Exact wire types remain required. Whole-advance
rollback includes comparison flags, earlier/later graph changes, downstream
selector/timer histories, time, trace and scheduling. Supported detached RLL
caller replacement preserves that state. The [single-sheet graph rules](function-blocks.md)
still apply.

Choose **FBD comparison lab** for `FBDCompareLab.L5X`: 33 roots, nine blocks,
29 drawing nodes and 41 wires. A/B feed all six relations. GRT drives a SEL
between OffValue 0 and OnValue 100. LIM tests A against LowLimit 0/HighLimit 10
and drives a 20 ms TONR. With initial A 6/B 2, SelectedValue is 100 and the
third 10 ms step reports TimerDone. BlockEnable gates all blocks; ExecuteGraph
skips the routine; ResetTimer resets the timer separately from comparison truth.
FaultDivisor zero demonstrates a late error; restore it to 1 to retry.

The graph inventory is 40 blocks: 21 shared ST-call names, 13 common RLL
arithmetic/comparison names and six FBD-only forms. RLL remains 101 and ST calls
27. Later-version mnemonic aliases are not enabled by this v35 increment.
The 222-entry type catalog now has 48 dedicated bounded models and 174 entries
without one; this does not establish complete emulation of those types.

Schemas, BOOL pins and lifecycle tables were checked against installed v35 help
14588.htm, 14589.htm, 14596.htm, 14599.htm, 14604.htm, 14608.htm and 14610.htm,
with Rockwell's [general-instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
as corroboration. Full native lifecycle/nonfinite/fault behavior, packed layouts,
Studio import/Verify and transfer/edit parity remain unqualified.
