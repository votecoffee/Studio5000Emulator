# Array statistics

The explicit v35 ControlLogix 5580 ladder profile supports:

```text
AVE(Array,Dimension,Dest,Control,?,?);
STD(Array,Dimension,Dest,Control,?,?);
```

Sources use SINT/INT/DINT/REAL arrays. AVE accepts writable scalar
SINT/INT/DINT/REAL results; STD requires a writable REAL result.
Scans use live CONTROL.LEN/POS. See [CONTROL import initialization](control-operations.md#literal-len-and-pos-on-import) and
[implementation](../source/logixlab/array_statistics.py).

## Dimension and calculation

Use a fully subscripted element in a one-, two- or three-dimensional
array. Dimension is immediate 0, 1 or 2 and must exist in that array. Only the
selected subscript increases; other subscripts stay fixed. For example,
`AVE(Grid[0,1],0,Mean,Control,?,?)` with LEN=2 averages Grid[0,1] and Grid[1,1].
It does not flatten the array into adjacent rows.

The complete LEN region must fit that dimension within the selected member.
At most 4096 values are processed per operation. Numeric UDT array members and
sibling result members are supported. Constant input arrays are legal;
destinations cannot overlap the source array or the operation's own CONTROL
record, including LEN/POS aliases. Disjoint result and control members may
share the same enclosing tag. [Aliases, indirect starts and RLL
AOI arrays](statistics-references.md) now execute, with explicit latch, index
consumption, dimension, binding and rollback rules.

AVE requires at least one value and calculates the mean. STD requires at least
two and calculates sample deviation: `sqrt(sum((x-mean)^2)/(N-1))`. This follows
the installed v35 formula rather than population deviation. Inputs, accumulation,
intermediate squared differences and results use float32 in this software
profile; native precision and bit-for-bit parity remain unverified.

An integer AVE result rounds the float32 mean to the nearest whole number,
with exact halves going to the nearest even value: 2.5 becomes 2, 3.5 becomes
4, and -2.5 becomes -2. Range checks apply after rounding: SINT -128.5 fits as
-128, while 127.5 rounds outside SINT and rolls back the advance. No native
overflow bits or arithmetic flags are synthesized.

Integer results retain the same float32 accumulation order as REAL results.
For example, DINT samples [16777216,1,-16777216,2] produce a modeled float32
mean of 0.5 and an integer result of 0; an exact integer sum would differ.
A one-element DINT source of 2147483647 first rounds to 2147483648, so a DINT
result fails its range check. Wider intermediates and native precision remain
unqualified. STD is not widened by the integer AVE profile.

## Operand selection

[Statistics operand selection](statistics-operands.md) adds structural preflight
for result references. False and EN/DN/ER-inhibited calls skip live result
indices; fresh calculations resolve actual results before reading samples and
full writes establish unknown elements. Actual CONTROL addresses/prescan and
existing flag, length and position reads remain required.

## CONTROL transitions

A fresh operation requires POS=0 with EN/DN/ER clear. A true rung completes
the operation in that advance, sets EN/DN, clears ER and sets POS=LEN.
Held EN/DN retains the result; ER inhibits execution until cleared. Partial
POS/resume is not implemented.

Prescan clears AVE EN/DN; when ER is already clear, it also clears the other
logical control flags. AVE retains saved POS. On a false rung, AVE clears
EN/DN/ER/POS only when DN is set and ER is clear, matching the installed v35
false flowchart. Otherwise those values remain unchanged.

STD prescan clears EN/DN/ER and retains POS. Its false rung clears EN/DN/ER/POS.
Both instructions retain LEN and array data. RES can reset logical control state
while retaining LEN and data.

In a whole-project ladder scan, a handler can
[clear a reached array subscript fault](controller-handlers.md#recover-sort-and-statistics-array-faults)
and skip both the result write and CONTROL update. Unknown required values,
short windows, invalid lengths, partial positions, accumulation overflow and
later execution faults roll back the modeled advance, including data, control
flags, time and scheduler state. Native ER/POS fault
side effects, partial results, math flags and fault classifications remain
unfinished. Wider types, partial-state execution and broader AOI forms remain
open. Neither instruction is available as an ST call or FBD instruction.

## Stats Lab

Choose **Stats lab** and **Step scan**. Set Calculate on and step: Average is 5,
sample Deviation is approximately 2.581989, ColumnMean is 7, RowMean is 10,
and Ready is true. The Values guard element remains 999.

Change Values[0] to 14 while Calculate stays true: results remain latched.
Set Calculate off and step, then on and step to recalculate Average=8.
Reset clears the four independent control records while retaining lengths
and sample data. ByteAverage, WordAverage and DintAverage use separate controls
and RoundingValues[0..3], initially [1,2,3,4]: all three results round 2.5 to 2.
Change RoundingValues[0] to 5, rearm Calculate false/true, and the mean 3.5 rounds
to 4. RoundingValues[4] is a guard and remains 777. Reset also resets these three
controls. A mean of 127.5 demonstrates SINT rollback; correct the samples and
retry with the controls still fresh. See [StatsLab.L5X](../source/samples/StatsLab.L5X).

The baseline uses installed v35 help 14507 (AVE), 14501/14536 (STD/formula)
and 14492 (All Mode), including the AVE false flowchart. Rockwell's published
[General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
and published [AVE operands](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-average-ave.html)
provide context. Rounding uses the existing [REAL-to-integer rule](math-operations.md);
newer published types do not expand the v35 profile. These software checks do not establish native
controller or Studio acceptance.
