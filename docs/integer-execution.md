# Integer ladder execution

App `26.1029.072958` adds a homogeneous integer execution profile for Standard
v35 ControlLogix 5580 projects with `1756-L81E` through `1756-L85E` processor
identifiers. These are software-model rules; native runtime equivalence and
math-status/fault parity are not established.

## Try the bundled demo

Choose **Integer lab** in the app, then **Step scan**, or start it from source:

```powershell
py -3.13 -X utf8 source/launch.py --sample IntegerLab --data-dir .local/integer-lab
```

The twenty-root, nine-rung fixture demonstrates exact 64-bit addition, division
and remainder, an unsigned complement and all four unsigned widths. Values
beyond browser-safe integer precision remain decimal text in the tag watch.

## Supported operations

| Types | Ladder operations |
| --- | --- |
| LINT, USINT, UINT, UDINT, ULINT | ADD, SUB, MUL, DIV, MOD, NEG, ABS, AND, OR, XOR, NOT, MOV, CLR |
| The same types | EQU, NEQ, LES, LEQ, GRT, GEQ and LIM |

All tag operands of one operation must have exactly the same declared type,
including the numeric destination. Scalar array elements, members and aliases
use their resolved type. Mixed signed/unsigned widths and REAL conversions
remain blocked for this profile. Existing same-type MOV/CLR and bounded COP/CPS
storage behavior remains available independently of the new processor gate.

Immediate operands must be signed DINT integer literals representable in the
chosen operand type. For example, `ADD(Ticks,1,NextTicks)` accepts two LINT tags;
`ADD(Ticks,OtherDint,NextTicks)` remains blocked. Store larger constants in a
properly declared LINT/ULINT tag instead of assuming a wide immediate literal.
Unsigned operations reject negative immediates. Typed literals and broader
promotion/conversion rules remain future work.

Addition, subtraction, multiplication, division, remainder and comparisons use
integer calculations throughout. A value such as `9007199254740993` therefore
retains its exact bits rather than being rounded through floating point.
AND/OR/XOR/NOT use the declared width; unsigned NOT produces an unsigned result,
while signed LINT bitwise results retain two's-complement interpretation.

## Division and failures

RLL DIV with integer sources and an integer destination now truncates the
quotient toward zero. This also corrects the existing narrow integer path:
`DIV(7,2,Result)` returns `3`, and `DIV(-7,2,Result)` returns `-3`.
Integer division never converts a 64-bit operand to a Python float. MOD uses
that same quotient, preserving the dividend's remainder sign.

A REAL source still follows the existing REAL-to-integer conversion path;
`DIV(7.0,2,Result)` with a DINT destination rounds `3.5` to `4`.

Overflow, unsigned underflow, an unrepresentable NEG/ABS result or division by
zero stops and rolls back the modeled scan. The emulator does not yet reproduce
controller overflow flags or native minor-fault destination effects. False
rungs do not execute these arithmetic operations. Writes can establish unknown
destination values without first reading the old value; reached unknown sources
still fault and preserve the prior scan state.

## Coverage and remaining work

The exported coverage report includes `integer_execution`, identifying the
profile, eligible controller identifiers, operand types, instructions and limits.
The Coverage page also lists the bounded integer profile among model limits.

Seventeen focused execution cases cover every new type, values beyond floating
integer precision, signed/unsigned limits, exact quotient/remainder, comparisons,
wrapped LIM ranges, complements, false rungs, unknown data, rollback, mixed-type
rejections and the processor/firmware gate. These are model-level checks.

Wide/unsigned ST and CPT/CMP expressions, MEQ forms, mixed-type promotions,
complete conversions, math flags, LREAL and time types remain unfinished.
Other controller families need explicit qualification. See the
[full capability checklist](emulation-coverage.md) and
[implementation](../source/logixlab/integer_math.py).
