# Boolean function blocks

The v35 ControlLogix 5580 software graph supports BAND, BOR, BNOT and BXOR over
four logical FBD_BOOLEAN records. DFF, JKFF, RESD and SETD also execute through
the existing [Boolean-memory models](st-digital-memory.md). These eight FBD forms
were added after the first twelve forms. With [rate/capture blocks](fbd-rate-capture.md),
the graph inventory is 33 blocks, including [accumulation](fbd-accumulation.md); RLL remains 101 and ST calls 27.

| Block | Logical type | Inputs besides EnableIn | Outputs besides EnableOut |
| --- | --- | --- | --- |
| BAND | FBD_BOOLEAN_AND | In1 through In8 | Out |
| BOR | FBD_BOOLEAN_OR | In1 through In8 | Out |
| BNOT | FBD_BOOLEAN_NOT | In | Out |
| BXOR | FBD_BOOLEAN_XOR | In1, In2 | Out |
| DFF | FLIP_FLOP_D | D, Clear, Clock | Q, QNot |
| JKFF | FLIP_FLOP_JK | Clear, Clock | Q, QNot |
| RESD | DOMINANT_RESET | Set, Reset | Out, OutNot |
| SETD | DOMINANT_SET | Set, Reset | Out, OutNot |

Every pin is BOOL. BAND requires all eight inputs true; BOR requires at least one;
BNOT complements its input; BXOR reports differing inputs. Every declared input
must be known when enabled, even if another input would determine the result.
Unknown values are not coerced to false through short-circuit evaluation.

Unwired inputs use their current represented record values. Declaration shapes
use true BAND/BNOT input seeds and false BOR/BXOR inputs, following installed v35
help; BOR's EnableIn shape is false. These shapes do not replace omitted saved
members. Import requires saved data; partial decorated records retain unknowns.

DFF samples D on a reached rising Clock; JKFF toggles. Clear wins and still
samples Clock. Initial prior Clock is true, suppressing a startup high edge.
RESD gives Reset priority; SETD gives Set priority. Initial retained values are
false and true respectively. Complements are recomputed on enabled calls.
Direct output writes do not replace hidden retained state.

Connected false EnableIn clears enables and skips the algorithm, retaining
outputs/history. Unwired EnableIn is true. Disabled Clear is not asynchronous;
the next enabled call handles it. Skips retain sampled clocks; hidden transitions
are not reconstructed. ST/FBD digital sites share resolved-record history.
Run clears hidden state; prescan clears enables without executing algorithms.
Whole-advance rollback and detached RLL caller replacement preserve values/history.

Choose **FBD Boolean lab** for `FBDLogicLab.L5X`: 32 roots, eight blocks, 28 drawing
nodes and 37 wires. A/B drive AND/OR/XOR; NOT of ResetInput also gates AND.
Clock, DInput and Clear drive flip-flops; SetInput/ResetInput drive both latches.
BlockEnable gates blocks, ExecuteGraph skips the call, and FaultDivisor zero
demonstrates a late fault. Restore it to 1 to retry without a duplicate toggle.

The [single-sheet graph rules](function-blocks.md) still apply. Boolean names are
enabled as FBD **Block** forms only; tagless FBD Function and ST/RLL forms remain
blocked. Integer bitwise instructions are separate. Native initialization,
postscan, disabled behavior, packed layouts and complete fault/status parity
remain unqualified; this sample has not been imported/verified in native Studio.
Installed v35 help 14793/14794/14808/14809 and Rockwell's
[general-instruction manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
describe the Boolean records and their language forms.
