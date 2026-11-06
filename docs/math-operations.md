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

With a [REAL destination](real-destination-math.md), integer and REAL sources
use float32 calculation. An LREAL input or result selects the
[binary64 profile](lreal-math-literals.md#real-and-integer-results), which
converts the finite result to the declared REAL, LREAL or integer destination.
A REAL tag or floating immediate can select float32 with a
[LINT or unsigned integer result](real-destination-math.md#wide-and-unsigned-integer-results).
Integer-only SQR and XPY with a LINT or unsigned operand use the
[exact integer profile](#wide-integer-roots-and-powers). The existing narrow
integer forms retain scalar SINT/INT/DINT/REAL source rules. Untyped
immediates keep bounded DINT and finite REAL precision.
Array elements, indirect indices, UDT members, aliases and supported AOI
local/Output/InOut bindings use the same scalar destination rules.

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
Unwritten siblings remain unknown. During a whole-project ladder scan, a handler
can [clear a reached array subscript fault](controller-handlers.md#recover-standalone-math-array-faults)
and skip the result write. Unknown consumed values, domain and range failures,
uncleared faults and later instruction errors restore the advance, including
earlier writes, time/task state and existing AOI bindings.

## Calculations

| Family | Modeled result |
| --- | --- |
| SQR | Square root of the source absolute value, including negative inputs |
| XPY | SourceX raised to SourceY; negative bases require an integral exponent |
| LN/LOG | Natural/base-ten log; source must be positive |
| DEG/RAD | Radians to degrees / degrees to radians |
| SIN/COS/TAN | Trigonometric result from a source in radians |
| ASN/ACS/ATN | Inverse trigonometric result in radians; ASN/ACS require -1..1 |

The float32 profile rounds sources to float32 before the host calculation
and rounds the result to float32 before writing. This defines a finite software profile;
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

## Wide integer roots and powers

App `26.1105.082615` adds an exact software profile for ladder SQR and XPY
with scalar integer sources and an integer destination. At least one operand,
including the destination, must be LINT, USINT, UINT, UDINT or ULINT. Decimal
L/U/UL constants select the same types as tags. Untyped integer immediates
must fit signed DINT.

SQR rounds the square root of the exact absolute value to the nearest integer.
For example, 16000000004000000000UL gives 4000000000 and adding one to the source
gives 4000000001. The magnitude of the most negative LINT can be used as a source.

XPY computes a nonnegative integral power with an exact integer result. The
zero exponent yields 1. For a negative exponent, a zero base faults. Bases 1
and -1 retain their value and exponent parity, respectively. The reciprocal
for every other nonzero integer base has magnitude at most one half and
rounds to even zero. The result must fit the destination. Oversized exponents
for a base with magnitude at least two are bounded before exponentiation.

```text
XPY(3,34U,ExactPower);
XPY(-1,18446744073709551615UL,OddPower);
SQR(16000000004000000001UL,ExactRoot);
```

These write 16677181699666569, -1 and 4000000001. Enable
`ExactRootPowerEnabled` in **Integer lab** and step to inspect the results.
Set `ExactRootPowerIndex` to 1 to fill the next unknown array element. Element 2
retains 903. Set `ExactPowerLateDivisor` to zero to demonstrate scan rollback,
then restore it to 1 and retry.

Floating operands retain the precision selection above. All-narrow integer
calls retain the established float32 model. The v35 operand and rounding
references are help 14617 and 14478. Native intermediate precision, flags
and fault status remain unqualified.

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

[Mixed LREAL powers](mixed-lreal-power.md) additionally qualify XPY with numeric
tag sources or signed DINT-range integer constants with a LREAL result. Other advanced math and expression profiles remain separate.

[Unary LREAL results](lreal-unary-sources.md) additionally qualify all ten numeric
source tag types and signed DINT-range constants for eleven standalone unary
math forms. A LREAL destination selects this finite binary64 software profile.

[LREAL arithmetic results](lreal-destination-math.md) additionally select binary64
for basic arithmetic and XPY without a LREAL source, including bounded
constant-only calls. Direct ordering still requires a LREAL input for binary64.
