# LREAL ladder expressions

The bounded v35 ControlLogix 5580 model supports finite binary64 calculations
in CPT and comparisons in CMP. An LREAL source or an LREAL CPT destination
selects binary64 for every numeric node, including constant-only subexpressions.
CPT can store representable results in all ten numeric destination types;
[final result conversion](lreal-results.md) follows binary64 evaluation. Numeric sources may use
any of the eight signed/unsigned integer types, REAL or LREAL.

```text
CPT(Result,Source+Other/2);
CPT(Result,(1/2)+(1/2));
CPT(Result,SQR(Source)+SQR(Source));
CMP((Source>Other)&&(Enabled OR (Source=Other)))OTE(Matches);
```

## Arithmetic and comparisons

Supported operators are +, -, *, /, MOD and **, with the existing ladder
precedence and left-to-right equal-order grouping. ABS, SQR, TRN, LN, LOG,
SIN, COS, TAN, ASN, ACS, ATN, DEG and RAD use finite binary64 inputs/results.
SQR takes the argument's absolute value. MOD retains the dividend's sign.
The existing software exponent bound is 1024 in magnitude; fractional and
negative exponents are allowed when their results remain real and finite.

Signed DINT-range integer constants convert directly to binary64. The full
negative DINT literal is supported. Floating, typed and larger integer literals
remain excluded, including inside false rungs. Use declared REAL/LREAL or wide
integer tags for those values. Numeric bitwise operators, FRD/TOD and newer
mnemonic aliases remain separate forms.

Stored REAL tags retain their float32 precision before conversion to binary64.
Integer tags convert directly to binary64, so values beyond its exact integer
range can round. LREAL tags retain binary64 precision, including finite
subnormals and signed zero. Every intermediate must remain finite; an overflow
before a later reducing operation faults the modeled advance.

| Example | Software result |
| --- | --- |
| LREAL destination, (1/2)+(1/2) | 1.0 |
| LREAL source 1.0000000000000002 minus 1 | 2^-52 |
| DINT source 16777217 plus 1 | 16777218.0 |
| Stored REAL source authored as 16777217 plus 1 | 16777217.0 |
| LINT source 9007199254740993 | 9007199254740992.0 |
| ULINT maximum | 18446744073709551616.0 |
| SQR(3)+SQR(3), LREAL destination | approximately 3.4641016151377544 |

CMP supports six numeric relations, BOOL references, BOOL equality/inequality,
logical negation and Boolean composition. Both operands are evaluated eagerly;
an unknown, domain error or zero divisor cannot hide behind an already true or
false Boolean operand. BOOL tags cannot serve as numeric arguments.

## AOIs, selection and recovery

Scalar LREAL AOI Input/Output parameters are supported in this controller
profile. Matching LREAL inputs retain their precision and finite range. Existing
narrow integer/REAL inputs and REAL immediates retain their conversion rules;
a floating immediate first rounds to REAL. Output destinations must match the
declared type exactly. Parameter arrays remain InOut with exact declared
types/dimensions. Existing required input/output transfers still occur during
their established prescan and EnableInFalse phases; no new call sampling policy
is introduced.

Structural preflight checks types, permissions, grammar and supported shapes
without reading saved numeric values or dynamic indices. False/prescan CPT/CMP
calls skip live operands. Complete writes can establish unknown LREAL outputs.
Aliases, UDT members, selected array cells, copied AOI inputs and InOut/local
storage use the same evaluator. Required unknowns, invalid indices, arithmetic
and later instruction faults restore the complete modeled advance, including
earlier writes, warm bindings, trace and scheduler/timing state.

Only direct ladder CPT/CMP opt into this evaluator. Generic condition caches,
ST, FAL/FSC, FBD/SFC and other controller profiles retain their existing limits.
Literal expansion and complete native math flags,
fault records, partial effects, packed layouts and lifecycle equivalence remain
unfinished. Host binary64 calculations are software behavior; these checks do
not establish native numerical or Studio acceptance.

## Wide expression lab

Open Wide expression lab, step once, then set F64Enabled true. The Binary64
routine exposes the table's precision, integer/REAL source rounding and function
examples. F64Results[0] establishes 2^-52; its last cell remains a 901 guard.
F64Matches confirms the precision and mixed-source comparison.

F64DomainFault enables LN of a negative tag; F64OverflowFault enables a nonfinite
product. Clear each flag to recover. Set F64Index=1 and F64LateDivisor=0 to fail
after calculating an unknown selected destination; the cell remains unknown.
Restore the divisor to 1 and retry to establish F64Results[1]=2.0. Disable
F64Enabled before leaving an invalid index or source dormant.

See [sample](../source/samples/WideExpressionLab.L5X),
[evaluator](../source/logixlab/lreal_expressions.py) and
[tests](../source/tests/test_lreal_expressions.py). Installed v35 CPT (14597)
and CMP (14592) help provides the operator/promotion baseline. Rockwell's
[published CPT reference](https://www.rockwellautomation.com/en-hu/docs/factorytalk-design-studio/current/contents-ditamap/instructions/instruction-set/compute-math-instructions/compute--cpt-.html)
provides additional context; installed v35 spellings and the explicit limits
above govern this software profile.
