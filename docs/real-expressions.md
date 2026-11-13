# Mixed REAL ladder expressions

The bounded v35 ControlLogix 5580 profile supports wide integer tags and typed
decimal/radix integer constants in selected REAL CPT, CMP, FAL and FSC expressions.
A REAL tag, an unsuffixed floating literal, or a CPT/FAL REAL destination selects
float32 calculation. This extension requires a wide integer source/result tag,
typed integer literal or signed full DINT radix word; existing narrow expressions retain their
established interpreter. Integer suffixes alone do not select REAL.

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
FRD/TOD do not belong to this floating profile. Integer-only expressions keep
their exact integer calculations and type/range rules.

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

Generic expressions, ST/index parsers, existing mixed string conditions and other
controller profiles remain separate. NaN/infinity and native numerical, math
status, fault, layout and lifecycle parity remain unqualified. Source basis:
installed v35 Immediate values (14454), Data conversions (14451), CPT (14597),
CMP (14592), FAL (14504) and FSC (14515).

See [shared floating evaluator](../source/logixlab/lreal_expressions.py),
[CPT](../source/logixlab/extended.py), [CMP/FSC conditions](../source/logixlab/conditions.py),
[FAL](../source/logixlab/file_arithmetic.py) and
[focused cases](../source/tests/test_real_expressions.py).
