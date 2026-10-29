# Array statistics

The explicit v35 ControlLogix 5580 ladder profile supports:

```text
AVE(Array,Dimension,Dest,Control,?,?);
STD(Array,Dimension,Dest,Control,?,?);
```

Sources use SINT/INT/DINT/REAL arrays and destinations use writable REAL scalars.
CONTROL.LEN/POS hold saved values; pseudo-operands do not initialize them on
each scan. See [logical CONTROL](control-operations.md) and
[implementation](../source/logixlab/array_statistics.py).

## Dimension and calculation

Use a fully subscripted static element in a one-, two- or three-dimensional
array. Dimension is immediate 0, 1 or 2 and must exist in that array. Only the
selected subscript increases; other subscripts stay fixed. For example,
`AVE(Grid[0,1],0,Mean,Control,?,?)` with LEN=2 averages Grid[0,1] and Grid[1,1].
It does not flatten the array into adjacent rows.

The complete LEN region must fit that dimension within the selected member.
At most 4096 values are processed per operation. Numeric UDT array members and
sibling result members are supported. Constant input arrays are legal;
destinations cannot overlap the source array. Indirect/alias starting arrays
and AOI array bindings remain unqualified.

AVE requires at least one value and calculates the mean. STD requires at least
two and calculates sample deviation: `sqrt(sum((x-mean)^2)/(N-1))`. This follows
the installed v35 formula rather than population deviation. Inputs, accumulation,
intermediate squared differences and results use float32 in this software
profile; native precision and bit-for-bit parity remain unverified.

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

Unknown required values, invalid bounds/lengths, partial positions, accumulation
overflow and later execution faults stop and roll back the whole modeled advance,
including data, control flags, time and scheduler state. Native ER/POS fault
side effects, partial results, math flags and fault classifications remain
unfinished. Integer AVE destinations, wider types and additional reference
forms also remain open. Neither instruction is available as an ST call; FBD
execution remains unsupported.

## Stats Lab

Choose **Stats lab** and **Step scan**. Set Calculate on and step: Average is 5,
sample Deviation is approximately 2.581989, ColumnMean is 7, RowMean is 10,
and Ready is true. The Values guard element remains 999.

Change Values[0] to 14 while Calculate stays true: results remain latched.
Set Calculate off and step, then on and step to recalculate Average=8.
Reset clears the four independent control records while retaining lengths
and sample data. See [StatsLab.L5X](../source/samples/StatsLab.L5X).

The baseline uses installed v35 help 14507 (AVE), 14501/14536 (STD/formula)
and 14492 (All Mode), including the AVE false flowchart. Rockwell's published
[General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provides context. These bounded software checks do not establish native
controller or Studio acceptance.
