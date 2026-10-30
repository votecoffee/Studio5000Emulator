# File sorting

The v35 ControlLogix 5580 software profile supports ascending SRT sorting:

```text
SRT(Array,Dimension,Control,?,?);   // Ladder neutral text
SRT(Array,Dimension,Control);       // Structured Text
```

CONTROL.LEN/POS supply saved values. ST's three operands are normalized to the
same internal instruction shape without reinitializing LEN/POS. Use fully
subscripted static SINT/INT/DINT/REAL arrays with one to three dimensions.
Only the selected dimension varies; the other subscripts stay fixed. Both the
array and CONTROL must be writable. See [implementation](../source/logixlab/array_sort.py).

## Supported operation

The qualified whole-region profile requires positive LEN and POS=0, with at
most 4096 values inside the selected dimension/member. Sorting captures all
required values before writing. Integers retain their exact declared precision;
DINT values do not pass through REAL. REAL values must be finite and known.
Guard elements and other rows, columns or members remain unchanged.

Prescan does not initialize state. Ladder executes on a rising EN condition;
held true retains the array. A false rung clears EN/DN and retains ER/POS.
ER inhibits sorting until cleared. Success sets EN/DN and retains POS=0 in this
software profile. The installed reference does not establish the native final
internal sort cursor; native POS/partial-state parity remains unqualified.

Each executed ST call performs false then true, so repeated calls sort again
without an explicit rearm. An unexecuted IF branch leaves the instruction state
alone. FOR validation treats the whole selected array member as a possible
write when protecting tag-based bounds/step, including guard elements outside
the current LEN. The written CONTROL EN/DN fields are tracked separately;
unchanged LEN/POS may still supply loop bounds.

Unknown values, bounds/length/position errors, nonfinite REAL data and later
faults retain whole-advance data/control/time/scheduler rollback. Native major
faults, partial writes and internal status/cursor behavior remain unfinished.
Alias/indirect/AOI starting arrays, wider/unsigned types and FBD forms are not
qualified. Numeric UDT array members and CONTROL aliases are supported.

## Stats Lab

The existing **Stats lab** now includes sorting alongside AVE/STD:

1. Set Sort and TextSort on, then step. SortValues becomes `[2,4,6,8,999]`.
   Only column one of SortGrid is sorted: `[[6,4,2],[12,10,8]]`.
2. Change SortValues[0] to 10 and SortGrid[0,1] to 20, then step while inputs stay
   on. Ladder retains the changed SortValues order; ST sorts the column again.
3. Set Sort off and step, then on and step. SortValues becomes `[4,6,8,10,999]`.

Reset clears the control records while retaining LEN and backing data. See
[StatsLab.L5X](../source/samples/StatsLab.L5X). The original mean/deviation examples
remain described in [array statistics](array-statistics.md).

The baseline uses installed v35 help 14502. Rockwell's published
[SRT reference](https://www.rockwellautomation.com/en-no/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-sort-srt.html)
also describes the ladder transition and executed ST call behavior. These
bounded software checks do not establish native controller or Studio acceptance.
