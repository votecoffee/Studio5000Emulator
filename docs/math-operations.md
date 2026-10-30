# Common REAL math

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
Destinations must be writable scalar REAL. Existing array elements, indirect
indices, UDT members, aliases and supported AOI bindings are available. Integer
destinations, wide/unsigned sources and LREAL remain unqualified.

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

Prescan and false rungs retain destination data. True rungs evaluate on every
execution. Unknown required values, domain errors, nonfinite results and
overflow stop and roll back the entire modeled advance, including data, time
and task scheduling. Native NaN/infinity results, configurable minor faults,
math-status flags, underflow status and partial side effects remain unfinished.

## Expressions and languages

The installed v35 reference specifies taking the absolute value before a square
root. Existing CPT SQR and ST SQRT functions now share that rule: negative -16
produces 4 rather than a domain fault.

ST uses expression assignments such as `Dest:=SQRT(Source);`,
`Dest:=SIN(Source);`, `Dest:=ACOS(Source);` or `Dest:=X**Y;`. Standalone math
instruction calls remain ladder forms. Existing expression type/range/grammar
limits still apply separately. Use v35 SQR/ACS/ASN/ATN/XPY for ladder blocks;
SQRT/ACOS/ASIN/ATAN remain expression aliases in this model. FBD execution is
still unsupported.

## Math Lab

Choose **Math lab** and **Step scan**. Root, CptRoot and StRoot agree on the
negative input. Inspect logarithms, power, degree/radian round trips, ordinary
trigonometry and inverse trigonometry. AllOK compares the ladder/CPT/ST root
and angle results. Disable Enable and change inputs to retain ladder values
while the called ST routine continues; re-enable to update ladder results.
The same sample now compares [integer division and REAL promotion](integer-expressions.md)
through ladder, CPT/CMP and a called ST routine. Independent StDivisor can
diverge from Divisor and demonstrates later-ST failure/recovery.
See [MathLab.L5X](../source/samples/MathLab.L5X) and
[implementation](../source/logixlab/real_math.py).

The baseline uses installed v35 help 14617 (SQR), 14478–14480 (power/logs),
14663/14676 (DEG/RAD), 14748–14752 and 14768 (trigonometry). The published
Rockwell [General Instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provides additional context; newer instruction mnemonics do not expand this
v35 profile. Software tests do not establish native controller or Studio acceptance.
