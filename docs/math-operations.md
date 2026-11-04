# Common ladder math

The explicit v35 ControlLogix 5580 software profile supports these ladder forms:

```text
SQR(Source,Dest);
XPY(SourceX,SourceY,Dest);
LN(Source,Dest);
LOG(Source,Dest);
DEG(Source,Dest);
RAD(Source,Dest);
SIN(Source,Dest);
COS(Source,Dest);
TAN(Source,Dest);
ASN(Source,Dest);
ACS(Source,Dest);
ATN(Source,Dest);
```

Sources may be scalar SINT/INT/DINT/REAL tags or bounded numeric immediates.
Integer immediates must fit signed DINT; real immediates must fit finite REAL.
Destinations may be writable scalar SINT/INT/DINT/REAL. Existing array elements,
indirect indices, UDT members, aliases and supported AOI local/Output/InOut
bindings are available. Whole aggregates, BOOL/bit targets, constants,
wide/unsigned operands remain unqualified. [Matching-tag LREAL forms](lreal-advanced.md)
use a separate finite binary64 profile without changing the narrow conversions.

## Operand selection

Preflight checks declared scalar types, shapes, index grammar, permissions and
immediate bounds without evaluating saved dynamic indices or reading tag values.
This applies to all twelve forms above, including both XPY sources. Existing
static guards remain: an invalid declared type, missing reference, malformed
index expression, read-only target or excluded literal still blocks execution,
even on a false rung. Nonnegative literal indices outside an array's bounds remain blocked.

Prescan and false rungs skip live source values and indices, retaining unknown
results and existing data. For example, a saved out-of-range or unknown `Index`
does not block `XIC(Enable)SQR(Inputs[Index],Results[Index])` when disabled. On a
true rung, actual source and destination indices must be valid and all required
source values must be known. The same rules apply through aliases, UDT members
and existing AOI local/InOut bindings. The preflight context is restored after
both success and validation failure; runtime checks retain their normal context.

A full result write can establish the selected unknown numeric element/member.
Unwritten siblings remain unknown. A reached unknown/index/domain/range failure
or later instruction fault restores the entire advance, including earlier math
writes, time/task state and existing AOI bindings. These changes affect operand
validation; calculations, rounding and existing finite math bounds are unchanged.

## Calculations

| Family | Modeled result |
| --- | --- |
| SQR | Square root of the source absolute value, including negative inputs |
| XPY | SourceX raised to SourceY; negative bases require an integral exponent |
| LN/LOG | Natural/base-ten log; source must be positive |
| DEG/RAD | Radians to degrees / degrees to radians |
| SIN/COS/TAN | Trigonometric result from a source in radians |
| ASN/ACS/ATN | Inverse trigonometric result in radians; ASN/ACS require -1..1 |

Sources are rounded to float32 before the host math calculation, and the result
is rounded to float32 before writing. This defines a finite software profile;
it does not establish bit-for-bit native math-library or precision parity.
In-place operations capture their inputs before writing. Unknown destinations
can be established by a successful full result write.

For a SINT/INT/DINT destination, the float32 result rounds to the nearest whole
number, with exact halves going to the nearest even integer. Thus SQR(3,Dint)
writes 2 in this 5580 profile, SQR(6.25,Dint) writes 2, and XPY(-2.5,1,Dint)
writes -2. This differs from the integer-source SQR truncation documented for
older 5570 controllers, which remain outside this profile.

Range checks apply after rounding: -128.5 becomes a valid SINT -128, while
127.5 rounds to 128 and faults. Values lost when converting sources/results
to float32 cannot be recovered by an integer destination: XPY(16777217,1,Dint)
writes 16777216. A DINT source of 2147483647 becomes 2147483648 in this pipeline
and therefore faults on a DINT result. These are explicit finite software
boundaries; exact native intermediate precision remains unqualified.

Prescan and false rungs retain destination data. True rungs evaluate on every
execution. Unknown required values, domain errors, nonfinite results and
overflow stop and roll back the entire modeled advance, including data, time
and task scheduling. Native NaN/infinity results, configurable minor faults,
math-status flags, underflow status and partial side effects remain unfinished.
Out-of-range rounded integer results also roll back the advance. The simulator
does not store truncated overflow bits or synthesize native arithmetic flags.

## Expressions and languages

The installed v35 reference specifies taking the absolute value before a square
root. Existing CPT SQR and ST SQRT functions now share that rule: negative -16
produces 4 rather than a domain fault.

ST uses expression assignments such as `Dest:=SQRT(Source);`,
`Dest:=SIN(Source);`, `Dest:=ACOS(Source);` or `Dest:=X**Y;`. Standalone math
instruction calls remain ladder forms. Existing expression type/range/grammar
limits still apply separately. Use v35 SQR/ACS/ASN/ATN/XPY for ladder blocks;
SQRT/ACOS/ASIN/ATAN remain expression aliases in this model. Existing
[FBD REAL-record math](fbd-advanced-math.md) has separate operands and lifecycle;
this increment adds no FBD forms.

## Math Lab

Choose **Math lab** and **Step scan**. Root, CptRoot and StRoot agree on the
negative input. Inspect logarithms, power, degree/radian round trips, ordinary
trigonometry and inverse trigonometry. AllOK compares the ladder/CPT/ST root
and angle results. Disable Enable and change inputs to retain ladder values
while the called ST routine continues; re-enable to update ladder results.
ByteRoot, WordRoot and DintRoot also calculate the negative input at their
respective integer widths. RoundedRoot starts at 2 from RoundingInput 6.25;
RoundedPower starts at -2 from -2.5 raised to 1. All five ladder results retain
values when Enable is false. Raising Input to 40000 makes ByteRoot exceed SINT
and demonstrates whole-advance rollback; correct it to 25 and retry to get 5.

The separate `IndexedMath` section starts disabled with `MathIndex` 99 and
unknown `IndexedRoots`/`IndexedPowers` arrays. Set `MathIndex` to 1, then enable
`IndexedMath`: input 9 produces root 3 and power 81 at element 1, leaving siblings
unknown. Disable the gate and change the index to retain results. An enabled
out-of-range index faults and rolls back; select a valid index and retry.

The same sample also compares [integer division and REAL promotion](integer-expressions.md)
through ladder, CPT/CMP and a called ST routine. Independent StDivisor can
diverge from Divisor and demonstrates later-ST failure/recovery.
See [MathLab.L5X](../source/samples/MathLab.L5X) and
[implementation](../source/logixlab/real_math.py).

The baseline uses installed v35 help 14617 (SQR), 14478–14480 (power/logs),
14663/14676 (DEG/RAD), 14748–14752 and 14768 (trigonometry). The published
Rockwell [General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provides additional context; newer instruction mnemonics do not expand this
v35 profile. Published [SQR rounding by controller family](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/compute-math-instructions/square-root--sqrt-.html)
and [REAL-to-integer conversion](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/real-to-integer.html)
provide additional context for rounding. Their native overflow behavior does
not replace this model's range rollback policy. Software tests do not establish
native controller or Studio acceptance.
