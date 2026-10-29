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

## Remaining cases and faults

Empty FIND sources are invalid. Empty search strings, zero-quantity DELETE and
INSERT positions beyond active length plus one remain unqualified and are
rejected when reached. These restrictions are explicit emulator scope and do
not define native controller edge behavior.

Unknown active bytes/lengths, invalid ranges, result-capacity overflow and a FIND
position that cannot fit its result type stop and roll back the entire modeled
advance. Earlier data, AOI writes, time and scheduler state are restored. Native
minor-fault records, continuation and math/status behavior are separate work.
FBD execution and broader string conversion/encoding support remain unfinished.

## String Lab

Choose **String lab** in the webpage and **Step scan**. The authored
[StringLab.L5X](../source/samples/StringLab.L5X) combines ladder search/editing
with a called ST routine and an explicit 32-byte user string.

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

The baseline was checked against installed Logix Designer v35 help topics
14570 (FIND), 14567 (INSERT) and 14566 (DELETE). Published Rockwell references
also describe [FIND](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/ascii-string-instructions/find-string--find-.html),
[INSERT](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/ascii-string-instructions/insert-string--insert-.html)
and [DELETE](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/ascii-string-instructions/string-delete--delete-.html).
Later documentation does not expand the emulator's firmware/profile claims.
Software tests do not establish native controller or Studio acceptance.
