# Integer expression division

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
