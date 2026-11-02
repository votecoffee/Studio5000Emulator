# Sorting references and AOIs

The bounded v35 ControlLogix 5580 SRT profile supports alias chains and indirect
fully subscripted SINT/INT/DINT/REAL arrays in ladder and existing three-operand
ST calls. RLL/ST AOI bodies can use exact one-, two- or three-dimensional InOut
arrays and represented saved locals. [Ordering, CONTROL and call transitions](array-sort.md)
remain unchanged; no new instruction or type identity is added.

```text
SRT(Values[StartIndex],0,Order,?,?);  // Ladder
SRT(Grid[0,Column],0,ColumnOrder);   // ST
```

## Sampling and boundaries

Structural preflight checks the reference shape, dimension and writable target
without consuming dynamic source indices. A reached fresh ladder execution
with EN/ER clear samples the current start. Held EN, ER inhibition and false
calls skip live source indices/data. DN alone does not inhibit sorting. Changing
StartIndex while EN stays true leaves the array unchanged until rearmed.

An executed ST call still performs false then true and therefore sorts again
on every call. An unexecuted conditional branch leaves flags and data alone.
Both languages require positive LEN, POS zero and a complete selected dimension
window of at most 4096 values. Dimensions are not flattened or extended into
neighboring rows/members. The bounded profile rejects CONTROL.POS-dependent
starting subscripts; this is a simulator qualification guard.

The whole input window is captured before writes. Exact declared integer values
and finite REAL values retain the existing ordering profile. Unknown data,
bad indices, oversized windows and later faults roll back the modeled advance.
Both arrays and CONTROL must be writable, including alias targets and AOI actuals.

## ST FOR write protection

FOR validation treats the entire selected array member as a possible write,
including guards outside the current LEN. For a member inside any parent array,
it conservatively covers the entire enclosing parent array, even with literal
parent indices. A placeholder index from structural validation is not evidence
that only parent zero can change. This also covers aliases hiding an indirect
parent, and prevents a later selection from bypassing bounds/step protection.

Consequently a FOR bound or step referring to any field in that parent array
is blocked, including fields that sorting would normally preserve. This
conservative restriction needs further qualification before narrowing. Unrelated
scalar/member bounds remain legal. CONTROL EN/DN writes are tracked separately;
unchanged LEN/POS can still supply loop bounds. Existing AOI-call effects also
apply when an AOI is called from an outer ST loop.

## AOI state

Separate and nested instances use canonical InOut/local storage. Indirect
rebinding selects the newly resolved array; failure restores frames, binding
caches and instance metadata with arrays, CONTROL, trace, time and task state.
Missing saved locals remain unknown. Required copied inputs are consumed before
the body, so unknown copied indices can fault even when SRT itself would skip.

Prescan does not initialize SRT. Saved/held EN, ER and POS remain significant.
An authored EnableInFalse routine can false-call SRT to clear EN/DN, preserving
ER/POS/data; without it a skipped body retains state. Native cursor/partial-state,
fault/precision/layout behavior, broader AOI lifecycle, wider/unsigned types and
FBD remain unfinished. These software checks do not establish native acceptance.

## Try the AOI sort lab

Load **AOI sort lab** and set Sort true. SamplesA becomes `[101,2,4,6,8,999]`,
and SamplesB becomes `[102,103,10,20,30,998]`. Only the selected Grid columns and
Cube lines change. Saved local Scratch arrays sort independently, and Ready
reports the completion flags. SampleView aliases SamplesA.

Keep Sort true and modify a sorted value: the ladder result stays held. Set Sort
false and step, then true and step to sort again. Disable EnabledA to rearm only
its instance through the authored false routine. Change IndexA while held to
select a new window on the next fresh execution. FaultDivisor zero exercises
whole-advance rollback. Guards outside the selected regions remain intact.

Reference basis: installed v35 help 14502 and 3232, plus the published
[SRT reference](https://www.rockwellautomation.com/en-no/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-sort-srt.html).
The parent-array FOR effect and complete-operation POS policy are explicit
simulator choices requiring further native qualification.
