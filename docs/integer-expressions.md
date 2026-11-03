# Integer expression division

[Ladder wide CPT/CMP/MEQ](ladder-wide-expressions.md) now have a separate
v35 5580 profile: CPT arithmetic remains homogeneous; CMP has a separate
[direct mixed integer condition profile](ladder-wide-expressions.md#mixed-integer-cmp),
and tag-only MEQ accepts mixed integer types. The rules below describe the narrow expression
model; file-expression consumers remain narrow.

App `26.1029.231505` adds integer division to the existing narrow ST, CPT and
CMP expression models. FAL uses the CPT evaluator and FSC uses the CMP evaluator,
so their supported integer expressions gain the same operation.

```text
CPT(Quotient,Dividend/Divisor);
CMP(Dividend/Divisor=Expected)OTE(Matches);
Quotient:=Dividend/Divisor;
```

## Arithmetic and types

SINT/INT/DINT operands use DINT arithmetic intermediates. An integer expression
divides exactly and truncates the quotient toward zero: 7/2 is 3, -7/2 is -3,
and -7/3 is -2. MOD retains the dividend's remainder sign: -7 MOD 3 is -1.
Every arithmetic node is evaluated before the next operator, so (1/2)+(1/2)
is zero in integer arithmetic. Integer calculations do not pass through a float.
The full negative DINT literal -2147483648 is accepted before division.

The destination still applies its existing type/range rules. A result that
does not fit SINT/INT fails on storage. DINT intermediates must fit even when
later arithmetic would reduce the final result. INT_MIN/-1 is an overflow.
The separate [homogeneous wide ST profile](wide-st.md) retains its own limits.

## REAL promotion

| Consumer | REAL promotion rule in this model | Integer 7/2 with a REAL destination |
| --- | --- | --- |
| CPT and FAL | A REAL operand, REAL-producing function or REAL destination promotes the expression | 3.5 |
| ST | A REAL operand or REAL-producing function promotes the expression; the destination converts the evaluated result | 3.0 |
| CMP and FSC | A REAL operand or REAL-producing function promotes the comparison expression | No numeric destination |

Use an explicit REAL operand when a fractional result is needed. In ST,
Result:=(Dividend+0.0)/Divisor retains a REAL quotient. Existing float32 rounding
and REAL-to-integer conversion rules remain; 7.0/2 assigned to DINT rounds 3.5
to 4. A REAL literal in a comparison also promotes its numeric operands.

## Operand selection

For numeric CPT and CMP in Standard v35 ControlLogix 5580 projects, import
preflight checks declared scalar types, expression/index grammar, references,
destination permissions and the existing literal/conversion rules structurally.
Saved scalar values and dynamic indices are not consumed during that check.
Unknown input/result array elements or UDT members and unknown/out-of-range
saved dynamic indices can remain until execution reaches them. Literal
out-of-range indices, invalid shapes/references, read-only destinations and
unsupported operand forms remain blockers even on false rungs.

False rungs and ordinary prescan skip live calculation operands. CPT retains
its destination; CMP propagates false so downstream OTE coils clear. Enabled
calculations retain their existing address checks, consume required operands
and evaluate logical operands eagerly. A zero multiplier, true OR operand or
false AND operand does not conceal missing data. Full CPT writes can establish
unknown scalar results; untouched elements and members remain unknown. Runtime
faults restore prior writes/coils, unknown state, task/time state and AOI bindings.
Completed deferred prescan remains a separate lifecycle boundary.

The selection rule covers existing signed/unsigned integer and finite REAL
profiles, plus BOOL references in supported CMP composition. Calculations,
intermediate widths, rounding, type promotion and supported syntax do not expand.
String CMP, ST, FAL/FSC, direct expression evaluators, array-index consumers,
other controller profiles and native fault/status/lifecycle parity remain separate.
The report describes the boundary under
`integer_expression_execution.ladder_selection`.

In **Ladder wide expression lab**, the `ExecuteIndexed` section begins disabled,
with `ExpressionIndex` 99 and four unknown arrays. Set the index to 0, write
`ExpressionValues[0]` as 9007199254740993 and `ExpressionNarrow[0]` as 5, then
enable the section and step. `ExpressionResults[0]` becomes 9007199254740995,
`ExpressionNarrowResults[0]` becomes 6, and both expression-match coils become
true. Unwritten siblings remain unknown. Disable the section to retain results
and clear those coils, even with the index set back to 99. Enabling before
initializing both inputs demonstrates a runtime fault with earlier work rolled
back; provide the missing input and retry. These are software-model checks.

## Execution and failures

False ladder rungs and skipped ST bodies do not evaluate their arithmetic.
Reached expressions evaluate operands eagerly: a false logical operand cannot
hide an unknown value or a zero divisor in another operand. Integer division
can be used in supported ST conditions, CASE selectors and FOR bounds.

Zero divisors, required unknown values, intermediate/destination overflow,
invalid references and budget failures roll back the whole simulation advance.
This includes earlier writes, scheduler state and any INC progress. A failed
incremental FAL iteration can be retried at the same element after correcting
its input; earlier successful advances remain committed.

Array-index division, integer CPT/CMP power, wider CPT/CMP/file-expression
types, the complete numeric promotion/conversion matrix and native math flags,
fault classification, partial effects and intermediate parity remain unfinished.
These checks qualify software behavior; native controller/Studio acceptance
of these new forms has not been demonstrated.

## Math Lab

Choose **Math lab** and step. Dividend=-7 and Divisor=3 produce -2 and -1 in
the ladder/CPT/ST quotient and remainder fields. CmpMatches and
IntegerMathMatches are true. CptRealQuotient and StRealQuotient are approximately
-2.3333333; StRealDestination is -2.0 because its expression is integer.

StDivisor is an independent ST input. Set it to 2 to inspect a mismatch, then
restore it to 3. Zero causes a later ST failure after ladder work; correct it
before retrying. The earlier root/log/trig examples retain their behavior.
See [MathLab.L5X](../source/samples/MathLab.L5X),
[shared quotient implementation](../source/logixlab/integer_math.py),
[CPT expressions](../source/logixlab/expressions.py),
[CMP expressions](../source/logixlab/conditions.py) and
[ST expressions](../source/logixlab/st_expression.py).

Rockwell's [CPT reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/compute-math-instructions/compute--cpt-.html)
and [Structured Text manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm007_-en-p.pdf)
provide language and promotion context. Their complete type/conversion matrix
is broader than this bounded implementation.
