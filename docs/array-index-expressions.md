# Array-index expressions

App `26.1104.102844` extends references in the v35 ControlLogix 5580 software
profile. SINT, INT and DINT expressions can use `+`, `-`, `*`, `/`, `AND`, `OR`,
`XOR`, `NOT` and parentheses inside array subscripts. Division truncates toward
zero without a floating-point conversion. Every intermediate must fit DINT.
The existing expression precedence applies; use parentheses for clarity.

```text
MOV(Input[Position/Stride],Output[Position/Stride]);
MOV(Input[Position AND 3],Selected);
MOV(Input[(NOT Position) AND 7],Selected);
MOV(Input[(Position XOR 3) OR 1],Selected);
```

A single scalar integer tag may also be a subscript: SINT, INT, DINT, LINT,
USINT, UINT, UDINT or ULINT. Its exact declared value is checked against the
array boundary; it is not rounded through REAL or truncated to DINT. Aliases,
UDT members and selected integer array elements can supply that tag value.
This does not enable wide arithmetic expressions: `Input[WideIndex]` qualifies,
while `Input[WideIndex+0]` remains excluded, even if its saved value is small.

```text
MOV(Input[UnsignedIndex],Selected);
MOV(Input[IndexRecord.Selected],Selected);
MOV(Matrix[Position/Stride,UnsignedIndex],Selected);
```

References retain each consumer's existing operand rules. This supports source
and destination elements in existing ladder MOV, arithmetic, bit transfers,
copies, fills, CPT/CMP and other qualified consumers. Existing ST assignments
and supported AOI references share the resolver; no new instruction or language
form is added. Consumer-specific static-start, overlap, shape and permission
restrictions still apply.

Structural preflight validates types, references and grammar without evaluating
saved indices or divisors. False ladder rungs, prescan and skipped ST branches
can retain unknown indices, zero divisors and dormant out-of-range values.
Reached references consume all required values. A zero bit mask does not hide
an index-expression divide-by-zero or unknown operand. Full writes establish
selected unknown destinations and preserve neighboring values.

Unknown required data, zero divisors, DINT intermediate overflow, negative or
oversized indices and later failures roll back the whole advance, including
earlier writes, task progress/timing and warm AOI local/external state/bindings.
Division of DINT minimum by -1 overflows before selection. These are modeled
transactional faults; native major/minor fault classification, partial effects,
operand sampling, performance and lifecycle parity remain unqualified.

Subscript MOD, functions such as SQR/FRD/TOD, power, comparisons, floating/BOOL
operands, wide arithmetic subexpressions and larger/typed literals remain
excluded. Other controller profiles retain their existing restrictions. This
extension adds no new FBD or SFC forms or native Studio/controller acceptance.

Open **Bit lab**, set IndexMathDivisor to 2, enable IndexMathEnabled and Step.
Results 1 through 5 become 33, 33, 55, 10 and 33; IndexMathCheck is true. Guards
at indices 0 and 6 remain 101 and 999. The selected source expressions show
division, AND, XOR/OR, NOT and a ULINT tag index.

Set Divisor to zero, Wide to 4294967296 or LateDivisor to zero to demonstrate
independent rollback; restore them to 2, 3 and 1. External writes affect the
next Step. Disable the section before returning Divisor to zero; stored results
remain, and the section's check coil clears.

Source basis: installed v35 help 14431, **Index Through Arrays**, which lists
the supported native index operators and distinguishes extended tag indices
from expressions. SQR/FRD/TOD from that list remain future model work. Software
checks and this sample do not prove native numerical or lifecycle equivalence.

See [resolver](../source/logixlab/model.py),
[expression evaluation](../source/logixlab/expressions.py),
[focused cases](../source/tests/test_array_index_expressions.py) and
[BitLab.L5X](../source/samples/BitLab.L5X).
