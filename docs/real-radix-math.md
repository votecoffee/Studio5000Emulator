# Radix sources in REAL ladder math

The bounded v35 ControlLogix 5580 profile accepts binary, octal and hexadecimal
integer words in nineteen standalone ladder math forms and REAL-tag comparisons.
This extends the existing REAL calculation selectors; it does not select a
floating calculation solely because an integer constant has a suffix.

The math forms are ADD, SUB, MUL, DIV, MOD, NEG, ABS, XPY, SQR, LN, LOG, DEG,
RAD, SIN, COS, TAN, ASN, ACS and ATN. A scalar REAL destination selects float32
calculation. A REAL source tag or unsuffixed floating constant also selects
float32 for [all eight integer destination types](real-narrow-results.md). An LREAL
source or floating L/l literal retains binary64 priority. Integer-only forms
retain their separate calculation and type rules.

```text
ADD(RealValue,16#FFFFFFFF,RealResult);
SUB(16#1000001U,16777216.0,RealResult);
SQR(16#1000001U,RealRoot);
DIV(16#3U,2.0,WideIntegerResult);
EQU(RealValue,16#1000001U)OTE(RoundedEqual);
LIM(16#FFFFFFFF,RealValue,2#11U)OTE(InRange);
```

Words decode at declared width before conversion: no suffix means signed DINT,
L means LINT, U means UDINT, and UL means ULINT. Existing case and digit-group
rules apply. Thus 16#FFFFFFFF means -1, whereas 16#FFFFFFFFL means 4294967295.
The latter rounds to REAL 4294967296. Every required source converts to finite
float32 before calculation/comparison; math results round to float32 before
destination conversion. Integer results use the existing nearest-even rounding
and range checks.

16777217U rounds to 16777216 before REAL math. The subtraction above produces
zero, and SQR produces 4096. An LREAL literal in the subtraction instead retains
binary64 calculation and can produce one before the result converts to REAL.
ULINT's largest word rounds to REAL 18446744073709551616, which cannot be stored
back into ULINT. The representable value 16#FFFFFF0000000000UL can be stored.
Integer-only math and comparisons retain their exact integer interpretation.

EQU, NEQ, LES, LEQ, GRT, GEQ and LIM require an actual REAL tag for the REAL
comparison profile, after LREAL priority. Both relation positions and all LIM
positions accept words. Inclusive, reversed and collapsed limits use converted
values. Constant-only floating comparisons retain their existing separate scope.
Every required input is consumed on reached calls, even under a zero product or
already decisive bound.

Structural preflight still rejects malformed/overwide words, negative-prefix
radix text, expressions in scalar operands, BOOL/aggregate sources, constant
destinations and unsupported targets. False rungs and prescan skip saved values
and live indices. Full writes can establish unknown destinations; aliases,
selected members and supported AOI copied inputs/InOut/local storage retain
their binding and rollback behavior. Reached unknowns, invalid indices, domains,
overflow and later faults use the existing whole-advance rollback policy.

The ladder viewer preserves source spelling and displays decoded signed radix
values in the newly supported math contexts. The report's REAL math and
comparison profiles expose bases, declared types and scope.

Load **Wide expression lab**, set RealRadixIndex=1, enable RealRadixEnabled
and step to run **RealRadixBlocks**. Sum=4, Unsigned=18446744073709551616,
Signed=-1, Loss=0, Root=4096, Power=2, Quotient=1.5 and Selected[1]=2.
Match, Rounded and Range are true. Index 99 or RealRadixLateDivisor=0
demonstrates rollback; disabling the gate skips those invalid operands.

Default numeric helpers, other instruction consumers, expression/file/ST/FBD
forms and controller profiles remain separate. Native numerical, status,
fault and lifecycle parity is unverified. The source basis is installed v35
Immediate values (14454), Data conversions (14451), ADD (14623), XPY (14478),
SQR (14617), EQU (14589) and LIM (14610).

See [source decoding](../source/logixlab/numeric_storage.py),
[math](../source/logixlab/scalar_math.py),
[comparisons](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_real_radix_math.py).
