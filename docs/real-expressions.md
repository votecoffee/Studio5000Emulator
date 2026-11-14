# Mixed REAL ladder expressions

The bounded v35 ControlLogix 5580 profile supports wide integer tags and typed
decimal/radix integer constants in selected REAL CPT, CMP, FAL and FSC expressions.
A REAL tag, an unsuffixed floating literal, a CPT/FAL REAL destination or one of
the REAL-selecting math functions below selects float32 calculation. This
extension requires a wide integer source/result tag, typed integer literal or
signed full DINT radix word; existing narrow expressions retain their established
interpreter. Integer suffixes alone do not select REAL.

```text
CPT(RealResult,UnsignedInput+0.5);
CPT(IntegerResult,16777217U-16777216.0);
CPT(RealResult,16#FFFFFFFF+0.5);
CMP((UnsignedInput+0.5=16777216U)&&!Inhibited)OTE(Matched);
FAL(Calc,?,?,ALL,RealValues[Calc.POS],RealValues[Calc.POS]+1UL);
FSC(Find,?,?,ALL,IntegerValues[Find.POS]>=4U+0.0);
```

All eight integer source types and REAL can participate. Bounded DINT and
finite REAL literals retain their declared rules. L/U/UL decimal and radix
constants are checked at declared width and sign before float32 conversion.
Immediate unary signs are range-checked before promotion: `-1UL` remains invalid,
while `0.0-1UL` performs a valid floating subtraction. An LREAL tag, floating
L/l literal or LREAL destination retains binary64 priority.

Each required numeric source and each arithmetic/function result converts to
finite REAL. The operators are +, -, *, /, MOD and bounded **; existing numeric
math functions and expression aliases remain available. MOD follows the
dividend's sign and SQR uses absolute input. Numeric bitwise operations and
FRD/TOD do not belong to this floating profile. Integer-only expressions without
a REAL-selecting function keep their exact calculations and type/range rules.

16777217U becomes 16777216 before computation. Consequently
`(16777217U+1U)-16777216U` produces zero in a REAL destination. Float32
intermediates distinguish this from evaluating exact integers and rounding only
at the end. Results convert once to the destination: integer results use
nearest-even rounding and must fit; REAL results retain float32 precision.

CMP/FSC support six numeric relations, scalar BOOL tags and eager Boolean
composition. Both sides are consumed, including when one Boolean result already
determines the outcome. False/prescan paths skip saved values and live indices.
Full writes establish unknown destinations. Existing aliases, selected members,
captured AOI bindings and whole-advance rollback remain.

FAL/FSC retain ALL, numeric and INC progress rules. Required unknowns, bounds,
domains, integer range errors and later faults roll back the advance. A reached
REAL calculation overflow in FAL instead uses its existing ER/POS/prefix/retry
policy: completed cells remain, the failing cell is intact, and repaired inputs
can retry that position. This does not add native status or fault parity.

Load **Wide expression lab**, set MixedRealIndex=1, enable MixedRealEnabled and
step to run **MixedRealExpressions**. Result=16777216, Difference=0,
DoubleDifference=1, Signed=-0.5, Root=4096, Integer=1 and Selected[1]=0.5;
Match is true. Index 99 or MixedRealLateDivisor=0 demonstrates rollback.
MixedRealInhibit gates the Boolean result while retaining eager numeric reads.

## Functions that select REAL

LN, LOG, SIN, COS, TAN, ASN, ACS, ATN, DEG and RAD select REAL calculation
without a REAL tag, literal or destination. The existing SQRT software expression
alias does likewise. Wide integer sources/results, decimal L/U/UL constants and
signed radix words use the same checked float32 path as explicit REAL operands.
For example, `CPT(Result,SIN(1UL))` rounds the float32 sine result to the integer
destination; `CMP(LOG(100U)=2)` is true. Each numeric node rounds to float32,
including integer arithmetic elsewhere in that expression. LREAL selection still
has priority.

ABS, SQR, TRN and the TRUNC software alias do not select REAL on their own.
Qualified exact integer ABS/SQR calls retain their existing behavior; this does
not add new standalone instruction mnemonics or broaden integer TRN forms.

In **Wide expression lab**, set FunctionRealIndex=1 and FunctionRealEnabled=true.
The FunctionRealExpressions routine uses integer operands/results throughout.
Angle=0 gives Sin=0, Cos=1, Selected[1]=0 and Match=true. Angle=4 gives Sin=-1,
Cos=-1, Selected[1]=-1 and Match=false. Ln=0, Log=1, Tan=2, Degrees=57,
Radians=3, Asin=2, Acos=2, Atan=1 and RootAlias=3. Index=99, LateDivisor=0 or
DomainEnabled=true with DomainSource=2 demonstrates whole-advance rollback.
Repair DomainSource to 1 to obtain DomainResult=2. False gates preserve numeric
outputs and clear Match. Names in this paragraph have the FunctionReal prefix.

Generic expressions, ST/index parsers, legacy narrow/string-only conditions and other
controller profiles remain separate. NaN/infinity and native numerical, math
status, fault, layout and lifecycle parity remain unqualified. Source basis:
installed v35 Immediate values (14454), Data conversions (14451), CPT (14597),
CMP (14592), FAL (14504) and FSC (14515).

See [shared floating evaluator](../source/logixlab/lreal_expressions.py),
[CPT](../source/logixlab/extended.py), [CMP/FSC conditions](../source/logixlab/conditions.py),
[FAL](../source/logixlab/file_arithmetic.py) and
[focused cases](../source/tests/test_real_expressions.py).

## String conditions alongside numeric math

Selected REAL and LREAL CMP/FSC expressions can combine numeric relations with
built-in STRING or declared DINT LEN/SINT DATA string relations. Each comparison
requires matching operand categories: two numbers, two strings, or two BOOLs
(BOOL ordering remains excluded). String capacities may differ. All six string
relations compare active bytes in case-sensitive lexical order, including prefix
and extended byte values. Unused DATA bytes are not consumed.

```text
CMP((UnsignedInput+0.5>0)&&(PartCode=ExpectedCode))OTE(Matched);
FSC(Find,?,?,ALL,(Weights[Find.POS]>1.0L)&&(Codes[Find.POS]=ExpectedCode));
```

Required LEN and active DATA bytes must be known and within the declared string
capacity. True/false Boolean results do not skip the other side: bad indices,
unknown bytes and numeric faults still roll back the whole advance. Existing
false-rung, prescan, file hold/done/inhibit and numeric-continuation rules apply.
Aliases, selected string elements, UDT members and qualified AOI bindings retain
their existing address rules. Strings cannot be math operands or numeric results;
this adds no string literal syntax or native status/fault/layout qualification.
String-only and legacy narrow/generic/ST/index expression paths stay separate.

In **Wide expression lab**, set StringNumericIndex=1 and StringNumericEnabled=true.
StringNumericRealMatch and StringNumericDoubleMatch become true. Change
StringNumericNeedle.DATA[5] from 65 to 66 to make both false, or restore 65 to
match PART-A. The example combines STRING array elements with a declared
CODE_12 string. Index99 or StringNumericLateDivisor=0 demonstrates rollback.
StringNumericInhibit also clears both results while all operands remain required.
