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

## Signed radix words in subscripts

Ladder and Structured Text array subscripts and indirect bit selectors accept
unsuffixed binary, octal and hexadecimal DINT words with space or underscore
grouping. Short words zero-fill. Full 32-bit words use signed DINT
interpretation, so `16#FFFF FFFF` works as a −1 offset. Arithmetic and
bounds checks still apply. A single radix word used as an index is checked
during preflight, like a decimal index. Tag-based expressions check their
result when reached.

```text
Value := Table[Index + 16#FFFF FFFF];
MaskedValue := Table[Index AND 2#00 11];
SelectedBit := Flags.[Index + 8#377 7777 7777];
```

In **Integer lab**, enable `RunStRadixIndex` and step. With
StRadixIndex=2, the three results are 22, 33 and true. Setting the index
to 0 produces a negative offset and faults the advance. Restore it to 2
to retry. The logic viewer resolves the same element or bit from its tag snapshot.
See [Rockwell's index reference](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/index-through-arrays.html)
and [immediate values](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/immediate-values.html).

## Scalar tag indices

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

A bounded cache reuses parsed subscript expressions across scans. Each
access evaluates the expression with the current tag values and scope,
including the existing shape and bounds checks.

Unknown required data, zero divisors, DINT intermediate overflow, negative or
oversized indices and later failures roll back the whole advance, including
earlier writes, task progress/timing and warm AOI local/external state/bindings.
Division of DINT minimum by -1 overflows before selection. In whole-project
ladder scans, eligible instructions can route array bounds and subscript
overflow to a [Type 4 Code 20 handler](controller-handlers.md#recover-an-array-subscript-overflow).
Other reached errors use scan rollback. Native status flags, partial effects,
operand sampling, performance and lifecycle parity remain unqualified.

[Subscript FRD/TOD/SQR](array-index-functions.md) additionally execute using
checked DINT arguments/results. MOD, other functions, power, comparisons, floating/BOOL
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
from expressions. SQR/FRD/TOD from that list now use the separate bounded function profile. Software
checks and this sample do not prove native numerical or lifecycle equivalence.

See [resolver](../source/logixlab/model.py),
[expression evaluation](../source/logixlab/expressions.py),
[focused cases](../source/tests/test_array_index_expressions.py) and
[BitLab.L5X](../source/samples/BitLab.L5X).
