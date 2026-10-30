# Typed integer literals in Structured Text

App `26.1029.234052` adds decimal integer suffixes to the bounded v35 ControlLogix
5580 [wide ST profile](wide-st.md). Constants retain their declared type and
exact integer value during parsing, validation and execution.

| Suffix | Type | Examples |
| --- | --- | --- |
| L | LINT | `9007199254740993L`, `-9223372036854775808L` |
| U | UDINT | `4294967295U`, `0U` |
| UL | ULINT | `18446744073709551615UL`, `0UL` |

Suffixes are case-insensitive and directly follow decimal digits. Unary signs
are range-checked with the magnitude, so the signed minimum is valid without
first treating its magnitude as a positive LINT. Negative nonzero U/UL values
and values beyond the declared range are rejected during validation, including
inside unreachable branches.

```text
SignedValue:=-9223372036854775808L;
UnsignedValue:=18446744073709551615UL;
DwordValue:=4294967295U;
Quotient:=18446744073709551615UL/3UL;
IF SignedValue=-9223372036854775808L THEN Ready:=TRUE; END_IF;
```

## Type rules and execution

Numeric tag operands, suffixed literals and numeric destination must share the
same wide type. A typed literal can select the type of a literal-only comparison
without a numeric destination. Untyped signed DINT constants retain the existing
representability rule; `1UL+2` is supported, while `1L+1U` is a mixed-type form.
Assigning `1U` to UINT or USINT remains unqualified.

The existing exact arithmetic, finite-width bitwise operations, ABS, relations,
BOOL logic and IF/WHILE/REPEAT behavior apply. No floating conversion rounds a
large literal. LINT/ULINT watch values travel as decimal text, including small
values. Typed constants also work in supported aliases/member destinations and
AOI expression bindings; nonretentive assignment prescan is unchanged.

Malformed or out-of-range literals block execution before a scan. Arithmetic
on valid constants can still fail at runtime, such as a zero divisor or a sum
outside its type. These failures roll back the whole advance. Skipped bodies
do not evaluate their arithmetic; reached BOOL operands remain eager.

## Integer Lab

Choose **Integer lab** and step. The existing ladder/ST comparisons remain.
New fields show the full LINT minimum, ULINT maximum, UDINT maximum and
`NOT 0UL`. StLiteralQuotient is exactly 6148914691236517205 with the default
StLiteralDivisor=3. StLiteralCheck is true when StLiteralOffset=0.

Set StLiteralOffset to 1 to observe the signed value increment and the check
become false. Restore it to 0. Offset -1 overflows the signed minimum; divisor
zero causes a later divide fault. Correct the input before retrying. See
[IntegerLab.L5X](../source/samples/IntegerLab.L5X),
[literal scanner](../source/logixlab/st_literals.py) and
[typed evaluator](../source/logixlab/wide_st.py).

## Remaining forms

This increment accepts decimal digits with L/U/UL only. Typed radix, fractional,
exponent, grouped-digit or prefix forms, mixed numeric conversions, typed
instruction-call arguments, wide FOR/CASE/index forms and typed CASE labels
remain unqualified. CPT/CMP and ladder operand lexers retain their own formats.
Power/other wide functions and native precision/status/fault/intermediate parity
remain unfinished. Software checks do not establish native Studio/controller
acceptance of these new forms.

Rockwell's [Structured Text manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm007_-en-p.pdf)
provides the integer-suffix language context. Its full type/conversion matrix
is broader than this bounded implementation.
