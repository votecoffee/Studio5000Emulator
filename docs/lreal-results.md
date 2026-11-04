# Numeric results from LREAL CPT expressions

The bounded v35 ControlLogix 5580 CPT profile can store an LREAL expression's
result in SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL.
Any LREAL operand selects the existing finite binary64 evaluator, regardless
of the destination type. An LREAL destination also selects binary64 when the
expression has no LREAL source. Other expressions retain their previous rules.

```text
CPT(IntegerResult,DoubleValue/2);
CPT(RealResult,DoubleValue+1);
CPT(Selected[Index],SQR(DoubleValue)+SQR(DoubleValue));
```

## Final conversion

The expression completes in binary64 before the final destination conversion.
Operands and intermediate nodes are not rounded to the destination's type.
For example, an LREAL source of 3.5 minus 1 produces 2.5, then stores DINT 2.
An LREAL source of 16777217 stores the exact DINT 16777217; converting it to
REAL first would lose that distinction.

| Destination | Bounded software conversion |
| --- | --- |
| Eight integer types | Round the final binary64 value to nearest, ties to even; the integer must fit the declared signed/unsigned range. |
| REAL | Round the final binary64 value once to finite float32; subnormal underflow and signed zero follow the existing storage conversion. |
| LREAL | Retain the finite binary64 result. |

Positive 2.5 becomes integer 2 and 3.5 becomes 4. Signed integer destinations
also accept -2.5 as -2 and -3.5 as -4. Unsigned destinations permit a negative
fraction only when its rounded result is zero; a result below zero faults.
Arithmetic overflow does not wrap to the low destination bits. This differs
from the model's integer-to-integer MOV conversion.

The binary64 source must itself represent the intended value. In particular,
rounding an authored LREAL value to 2^63 or 2^64 exceeds the LINT or ULINT upper
bound; the original maximum integer cannot be recovered from that double.
REAL overflow likewise faults rather than supplying native overflow result
bits. These are representable-result software rules; native status, saturation,
fault classification and partial-write behavior remain unverified.

The original [LREAL expression](lreal-expressions.md) rules still govern math,
source precision, DINT immediates, functions and operators. A nonfinite
intermediate fails before a later operation could reduce the final magnitude.
[REAL/LREAL floating constants](lreal-literals.md) now have their own scoped
profile. [Decimal L/U/UL constants](lreal-integer-literals.md) now check their
declared integer range before binary64 calculation and final conversion. Typed
radix forms, separators, BCD, numeric bitwise and other language forms remain separate. BOOL and aggregate destinations remain excluded.

## Selection, AOIs and faults

Structural preflight checks declared shape, type, index grammar and write
permissions without consuming saved numeric values or dynamic indices. False
rungs and prescan retain destinations. Reached calls require their inputs;
complete writes can establish unknown scalar/array/member results. Supported
aliases, function indices and exact AOI InOut/local bindings retain their rules.

CPT can convert an LREAL copied AOI input into an integer or REAL parameter,
local or InOut cell. The AOI caller's Output and InOut types must still match
their declarations exactly; this instruction does not add call binding
conversions. Input copy timing and existing prescan/EnableInFalse behavior
remain unchanged.

Required unknowns, bad indices, range/domain/zero errors and later instruction
faults roll back earlier results, AOI copied values/bindings, local storage,
trace and scheduler/timing state for the complete modeled advance. Prior
successful advances and completed prescan remain separate events. Native
controller/Studio numerical, status, fault, packed-layout and lifecycle parity
require separate qualification.

## Wide expression lab

Open Wide expression lab and step once with R64Enabled false. Enable it to run
Binary64Results. R64Source=3.5 stores integer 4 in all eight integer result tags
and 3.5 in the REAL/LREAL tags. R64Selected[1] establishes DINT 16777217 from
R64Value, while its first cell remains unknown and its last guard remains 902.
R64Converted compares the rounded integer and floating results.

R64IntegerFault enables an overflowing SINT result; R64RealFault enables an
overflowing REAL conversion. Clear each flag to recover. Change R64Source to
7.5, R64Index to 0 and R64LateDivisor to 0 to fail after earlier conversions.
The old integer results remain 4 and the selected first cell stays unknown.
Restore the divisor to 1 and retry to store integer 8 and establish the cell.
Disable R64Enabled before leaving an invalid index dormant.

See [sample](../source/samples/WideExpressionLab.L5X),
[evaluator](../source/logixlab/lreal_expressions.py) and
[tests](../source/tests/test_lreal_results.py). The source baseline is installed
v35 CPT (14597) and Data Conversions (14451); Rockwell's published
[general instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provides additional context. Software validation does not establish native
controller acceptance.
