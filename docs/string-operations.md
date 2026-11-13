# String search and editing

LogixLab models `FIND(Source,Search,Start,Result)`,
`INSERT(SourceA,SourceB,Start,Dest)` and `DELETE(Source,Qty,Start,Dest)` in ladder
and Structured Text. Types and writable destinations are checked before running;
values and ranges are checked when the instruction executes.
See [string_operations.py](../source/logixlab/string_operations.py).

## Supported behavior

- FIND performs a case-sensitive search starting at a one-based position. It
  writes the first matching position or zero when absent. Start must be within
  the source DATA capacity; a valid Start beyond active text returns zero.
- INSERT adds SourceB before Start in SourceA. Supported positions range from
  one through active length plus one, subject to the source DATA capacity.
  This includes ordinary prepend, interior insertion and append operations.
- DELETE removes a positive quantity beginning at Start. The entire deletion
  must fit within active source text. Deleting all active text produces an
  empty destination.

Operands can use STRING or explicit user types with scalar DINT LEN and a
one-dimensional SINT DATA array. Scalars, array elements, UDT members, aliases
and existing AOI InOut bindings share the same storage. Types may have different
capacities; result length must fit the destination.

Positions, quantities and FIND results use SINT/INT/DINT tags; inputs also accept
bounded DINT immediates. General expression operands, wide/unsigned types, BOOL,
REAL, whole arrays and constant destinations are blocked. New calls participate
in the existing ST FOR checks that protect tags used by bounds and step values.

Source text is captured before writing, so destinations can alias either source.
Writes update LEN and active result bytes, preserving unused backing bytes,
including unknown unused bytes. Represented NUL and high bytes are ordinary
single-byte data; positions count bytes. False ladder rungs, unreached ST branches
and prescan retain destinations. Reached calls execute on every scan.

## Operand selection

For v35 ControlLogix 5580 (1756-L81E through L85E), ladder CONCAT, MID, DTOS,
STOD, FIND, INSERT, DELETE, LOWER, UPPER, STOR and RTOS validate declared
operand shapes, index grammar and destination permissions without consuming
saved values or dynamic indices. The same preflight covers six direct string
relations and string-bearing CMP. See [DTOS with REAL input](string-conversions.md#dtos-with-real-input)
for its source types.
Shared call validation is also used by existing ST calls; this adds no ST syntax.

Unknown LEN, active DATA, numeric inputs and dynamic index values can remain
at import. False rungs and prescan skip those operands. Reached calls still
resolve actual addresses and require every consumed source value, including
active string bytes, numeric conversions, positions and quantities. MID reads
its source LEN and the selected DATA bytes; FIND captures the active suffix
from Start. String comparisons do not fold identical
references; CMP consumes both logical operands even when one determines the result.

Full logical string writes establish unknown LEN/active DATA and preserve unused
bytes and other array elements. Numeric results can likewise establish unknown
scalars. Destination permissions, runtime ranges and result capacity still apply.
Aliases, explicit user strings/UDT members and existing AOI InOut/local bindings
use this selection. A cleared Type 4 Code 20 in a reached ladder string call
[skips its result write](controller-handlers.md#recover-string-operation-and-conversion-array-faults).
Other errors follow scan rollback, which restores earlier writes, AOI bindings
and the modeled advance. AOI call-argument binding retains its separate contract.
The software profile uses single-byte strings. Native fault and status handling remains separate.

## FIND search suffixes

App `26.1112.232348` captures only the active source suffix beginning at Start
in existing ladder and ST FIND calls. Source bytes before Start and inactive
DATA may be unknown. Source LEN must still be known, valid and nonzero; the
complete active search string and every byte of the selected source suffix
must be known. An unknown later suffix byte still faults even if an earlier
match exists. Empty search strings remain unqualified.

Results are one-based positions in the original source, not offsets into the
suffix. A valid Start beyond active LEN returns zero without reading source
DATA; Start must still fit the declared source capacity. Result permissions,
range conversion, false/prescan selection and whole-advance rollback are unchanged.
This is a bounded unknown-data policy, not native fault or execution parity.

Enable `FindWindow` in **String lab** and step. FindSource has four unknown
prefix bytes followed by `ABAB`; FindNeedle is `AB`. With FindStart at 5,
FindResult is 5. Set FindStart to 6 for result 7, or 9 for result zero. Setting
it to 1 reaches the unknown prefix and rolls back; restore 5 to retry.

## DELETE retained windows

App `26.1112.215103` reads only the retained prefix and suffix of a DELETE source
in ladder and existing Structured Text calls. Source LEN, Start and Qty must be
known and valid. Qty remains positive, Start is within source DATA capacity,
and the entire deletion fits within active LEN. The removed bytes may be unknown
in a partial export; inactive bytes are also unused. Retained bytes must be known.

Deleting all active text can therefore establish an empty destination even when
every active source byte is unknown. The source is captured before any write,
including aliases and AOI InOut bindings. Writes update LEN and result bytes,
preserve unused destination bytes, and require the result to fit its capacity.
Unknown retained bytes, invalid metadata/indices/ranges, capacity errors and later
faults retain whole-advance rollback. False rungs and prescan skip live operands;
unreached ST branches remain dormant. This is an unknown-data rule of the software
model, not evidence of native fault, read-access or partial-effect equivalence.

In **String lab**, enable `DeleteWindow` and Step. `DeleteSource` has LEN 8,
known `AB`/`CD` ends and four unknown middle bytes. Default DeleteStart=3 and
DeleteQty=4 produce `ABCD` in `DeleteResult`; its last backing byte remains `!`.
Set DeleteQty=3 to leave an unknown byte in the result and observe rollback.
Restore 4 to retry. Set DeleteStart=1 and DeleteQty=8 to delete the entire text.
The gate defaults false, preserving the original example's normal scan.

The range basis is installed v35 DELETE help 14566 and the published
[Rockwell DELETE reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/ascii-string-instructions/string-delete--delete-.html).
No zero-quantity, new type, encoding, instruction language or native status
support is added. See [focused cases](../source/tests/test_delete_windows.py).

## MID copy windows

`MID(Source,Qty,Start,Dest)` in ladder and Structured Text requires Start
within the source's declared DATA capacity and the entire requested window
within the active LEN. Qty zero writes an empty string and still checks the
source LEN and Start. MID reads only the selected DATA bytes, so an export
may omit other bytes. Missing selected bytes or an invalid range roll back the
advance. Aliased destinations use the selected source bytes from before the
write. See installed v35 help 14579 and the [MID reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/ascii-string-instructions/middle-string--mid-.html).

In String Lab, set `MidWindow` true and step. The default `MidStart=2` and
`MidQty=2` copy `BC` into `MidDest` from a partially populated source.
Set MidStart to 1 to observe rollback on an unknown byte. Set MidQty to 0 and
MidStart to 6 to clear the result with a valid empty window.

## Remaining cases and faults

Empty FIND sources are invalid. Empty search strings, zero-quantity DELETE and
INSERT positions beyond active length plus one remain unqualified and are
rejected when reached. These restrictions are explicit emulator scope and do
not define native controller edge behavior.

Unknown active bytes/lengths, invalid ranges, result-capacity overflow and a FIND
position that cannot fit its result type stop and roll back the entire modeled
advance. Earlier data, AOI writes, time and scheduler state are restored. Native
minor-fault records, continuation and math/status behavior are separate work.
See [LOWER/UPPER and STOR/RTOS](string-conversions.md) for case and REAL
conversions. FBD execution and broader conversion/encoding behavior remain unfinished.

## Ladder string MOV

App `26.1105.175855` supports `MOV(Source,Destination)` with scalar STRING or
user-defined strings in the v35 ControlLogix 5580 ladder profile. Source may be
a tag or one single-quoted literal. A user string has a DINT LEN and a fixed
one-dimensional SINT DATA array. Aliases, selected array elements, UDT members
and supported AOI bindings use their declared string capacities.

The destination receives the active source prefix that fits its DATA capacity.
MOV updates LEN, preserves unused destination DATA, and consumes no source
bytes past the copied prefix. A zero-length source sets LEN to zero. MOV
reads the source before it writes, including when the operands alias one
string. Unknown copied bytes or invalid LEN and live indices fault and roll
back the full advance. False rungs and ordinary prescan skip live data and
indices. The emulator models clipping and leaves native S:V and minor-fault
behavior unqualified.

Quoted literals accept punctuation, including commas and parentheses. Use
`$'` for a quote, `$$` for a dollar sign, or `$hh` for a hexadecimal byte.
The represented control escapes are `$T`, `$L`/`$I`, `$R` and `$P`.
This is the single-byte profile. String CLR and native status behavior remain
outside it. The source basis is installed v35 MOV (14688) and Character string
literals (267909). [Rockwell move reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/move-logical-instructions/move--move-.html).

In **String lab**, set `MoveStringIndex` to 0 and write a value to
`IndexedSource[0]`. Enable `MoveStrings` and step. `MoveShort` holds the first
32 bytes of `MoveSource`. `MoveLiteral` contains `Line [1], (ready); 'OK' $`,
and `MoveSelected` holds the indexed source. Set `MoveStringIndex` to 99
while enabled to see the later bounds fault roll back the earlier two moves.

## Ladder string comparison literals

App `26.1105.181607` adds single-quoted literals to either operand of ladder
`EQU`, `NEQ`, `LES`, `LEQ`, `GRT` and `GEQ` in the v35 ControlLogix
5580 profile. Either operand can also be a scalar STRING or user-defined
string tag. For example, `EQU(Status,'RUN')` tests a status tag,
`LES('AB',Recipe)` checks that a recipe sorts after the prefix, and
`NEQ('A','a')` checks case. Quoting and supported byte escapes match
[ladder string MOV](#ladder-string-mov).

Ordering compares active bytes as unsigned values. Equal prefixes sort by
length, with the shorter string first. An embedded `$00` is a byte within
the string. A true rung requires valid tag LEN and all active bytes. False
rungs and prescan skip live values and indirect indices. Malformed literals
and mixed string/numeric types block preflight. A reached fault restores
earlier coils and other writes from the advance.

In **String lab**, set `CompareStringIndex` to 0, write `ABC` to
`IndexedSource[0]`, and enable `CompareStrings`. All three comparison coils
turn on. Change the indexed value to `AB` and step to clear `ComparePrefix`.
The ladder inspector shows decoded literal values. An enabled index of 99
faults and rolls back the earlier equality coil.

The installed v35 standalone comparison topics list immediate string operands.
`CMP` and `FSC` use string tags in their expression grammar. Native Studio
acceptance remains unverified. [Rockwell equality reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/compare-instructions/equal-to--eq-.html)
[Rockwell CMP reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compare-instructions/compare--cmp-.html)
[Rockwell FSC reference](https://www.rockwellautomation.com/en-no/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-search-and-compare-fsc.html)

## String Lab

Choose **String lab** in the webpage and **Step scan**. The authored
[StringLab.L5X](../source/samples/StringLab.L5X) combines ladder search/editing
with a called ST routine and an explicit 32-byte user string. It also includes
[case and REAL conversion examples](string-conversions.md#string-lab).

| Tag | Expected first-scan result |
| --- | --- |
| SourceText | `PART=ABC;STATE=IDLE` |
| Location / StPosition | `10` |
| MissingPos | `0` |
| RllEdited | `PART=ABC;<OK>STATE=IDLE` |
| Cleaned / StEdited | Same as SourceText |
| AllOK | true |

Changing SearchText to `PART` makes both positions one and AllOK false on the
next scan. Enable gates the ladder FIND, allowing retained output to be observed.

The lab also has six indexed ladder rungs, disabled by IndexedStrings at import.
StringIndex starts at 99 and the three-element string/result arrays are unknown.
Step once to observe that these dormant operands do not block execution. Set
StringIndex to 0, write `ABC STATE` to IndexedSource[0], enable IndexedStrings
and step again:

| Tag | Result |
| --- | --- |
| IndexedJoined[0] | `ABC STATE<OK>` |
| IndexedSlice[0] | `STATE` |
| IndexedLower[0] | `abc state<ok>` |
| IndexedPosition[0] | `5` |
| IndexedNumber[0] | `5` |
| IndexedMatch | true |

Unused DATA and sibling elements remain unknown. Disable IndexedStrings before
setting StringIndex back to 99 to retain outputs; enabling it at that index
faults and rolls back the scan. Restore index 0 to resume.

The baseline was checked against installed Logix Designer v35 help topics
14570 (FIND), 14567 (INSERT) and 14566 (DELETE). Published Rockwell references
also describe [FIND](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/ascii-string-instructions/find-string--find-.html),
[INSERT](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/ascii-string-instructions/insert-string--insert-.html)
and [DELETE](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/ascii-string-instructions/string-delete--delete-.html).
Later documentation does not expand the emulator's firmware/profile claims.
Software tests do not establish native controller or Studio acceptance.
