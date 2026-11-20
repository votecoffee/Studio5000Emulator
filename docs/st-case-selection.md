# Numeric CASE selection in Structured Text

CASE supports DINT, exact wide integer, float32 REAL and binary64 LREAL
comparisons. Branch labels are immediate numeric values, comma-separated lists,
ascending inclusive ranges, or combinations.

```text
CASE Temperature / ScaleFactor OF
    -1.0..1.0: State := 10;
    1.0..3.0, 5e0: State := 20;
    ELSE State := -1;
END_CASE;
```

The numeric expression is evaluated once before selecting a body. The first
matching branch executes; overlapping ranges and repeated labels do not cause
fallthrough. A matching empty body also finishes selection. If no label matches,
ELSE executes when present; otherwise no CASE body runs. Changing the selector
inside a body takes effect at the next CASE execution.

## Numeric profiles and labels

SINT, INT and DINT selector operands use the existing DINT expression profile.
Labels for an integer expression must be integers within signed DINT range.
Existing signed radix labels remain available. Decimal, fractional and exponent
labels are available for REAL expressions; signs may be separated from a number
by whitespace. Branch labels must be literals. Typed L/U/UL labels require the
matching wide integer selector type.

The expression determines the comparison profile. Within the narrow
expression profile, a REAL operand or fractional literal selects modeled
float32 arithmetic. REAL labels are converted to
float32 before comparison; integer labels in that context are also converted to
float32. Labels do not promote an integer expression. Thus `CASE 5/2 OF` selects
integer 2, while `CASE 5.0/2 OF` can select REAL 2.5.

REAL comparisons use the stored float32 values with no added tolerance. For
example, 16777217.0 and 16777216.0 round to the same float32 value, so whichever
label appears first wins. Ranges are usually more useful than exact equality
for calculated REAL values. Nonfinite or overflowing REAL labels, descending
ranges and malformed forms block execution, including in unreachable code.

### REAL selectors with wide integer operands

A REAL tag or unsuffixed floating literal in the selector expression selects
[binary32 arithmetic](real-expressions.md#structured-text) when the expression
also contains a wide integer tag or typed integer literal. The modeled v35
ControlLogix 5580 profile checks each integer at its declared width, rounds it
directly to binary32 and rounds each intermediate result to binary32. Use
ordinary REAL labels in this profile.

In **Integer lab**, enable RunStRealWideCase. The default StRealWideCaseInput
9223372586610589697 is one above the midpoint between two REAL values. It
rounds up and selects StRealWideCaseResult=20. Set the input to the midpoint
9223372586610589696 to see the round-to-even result of 10. Set
StRealWideCaseDivisor to zero to fault the advance, then restore it to 1.0.

### Exact wide integer selectors

In the modeled v35 ControlLogix 5580 profile, selectors may use homogeneous
scalar LINT, USINT, UINT, UDINT or ULINT expressions. Selector arithmetic is
checked at the declared width. Untyped labels must fit both DINT and the
selector type. Use L, U or UL on decimal or radix labels to select the full
LINT, UDINT or ULINT range. Suffix matching is case-insensitive. Radix labels
support underscore grouping and signed LINT bit patterns such as
`16#FFFF_FFFF_FFFF_FFFFL` for -1. The exact integer profile requires integer
labels.

```text
CASE PartId OF
    9007199254740992UL: Lane := 10;
    9007199254740993UL..9007199254740995UL, 16#FFFF_FFFF_FFFF_FFFFUL: Lane := 20;
    ELSE Lane := -1;
END_CASE;
```

The adjacent labels above 2^53 remain distinct. In **Integer lab**, set
RunStWideCase and step. The default StWideCaseInput is 9007199254740993, which
selects StWideCaseResult=20. Set the input to 9007199254740992 for result 10,
or 9007199254740996 for ELSE=-1.

### Selectors with mixed integer widths

When a selector mixes integer tag types and includes a wide integer, the
highest-ranked source tag type must cover the full range of every source
type. LINT with DINT and ULINT with UDINT qualify. ULINT with LINT fails
validation because ULINT cannot represent negative LINT values.

Each arithmetic subexpression must include a source tag of the common type.
Typed integer constants and labels must match that type. Intermediates are
checked at the common width, and mixed integer bitwise expressions remain
unqualified. The ranking follows the emulator's
[mixed integer arithmetic](ladder-wide-expressions.md#mixed-integer-arithmetic) rules.

In **Integer lab**, enable RunStMixedIntegerCase. The default LINT input
9007199254740993 and DINT offset 0 select StMixedIntegerCaseResult=20. Set
StMixedIntegerCaseOffset to -1 to select 10. The selector evaluates both
inputs exactly above 2^53.

### Binary64 selectors

An LREAL tag or an L-suffixed fractional or exponent literal in the expression
selects the emulator's binary64 profile for v35 ControlLogix 5580. Mixed numeric
operands follow the [binary64 ST expression rules](lreal-expressions.md#structured-text).
Label-only suffixes leave the selector profile unchanged.

Use L or l after a fraction or exponent to specify a finite binary64 label.
Unsuffixed fractional and exponent labels round to REAL before widening.
Unsuffixed integer labels must fit DINT. Ranges must be ascending both before
and after conversion. An integer token such as `1L` is a LINT label. Use
`1.0L` for an LREAL label.

```text
CASE Reading / Scale OF
    1.0L: Band := 10;
    1.0000000000000002L..1.0000000000000004L, 1e300L: Band := 20;
    ELSE Band := -1;
END_CASE;
```

In **Integer lab**, enable RunStDoubleCase. The default input
1.0000000000000002 yields StDoubleCaseResult=20. Change StDoubleCaseInput to
1.0 to select 10. Set StDoubleCaseDivisor to zero to fault the advance, then
restore it to 1.0 and step again.

### Execution and faults

Selected bodies retain the existing ST call, nested CASE, loop EXIT, prescan
and rollback behavior. An unknown or faulting selector raises a runtime fault;
it does not take ELSE. A fault in the selector or selected body rolls back the
whole advance, including earlier tag writes and scheduled task progress.
Unselected bodies are validated but their arithmetic is not evaluated.

## Try Text Lab

Choose **Text lab** and step. RealCaseInput=2.5 and RealCaseDivisor=1 select
RealCaseResult=20. RealCaseVisits advances once per completed scan. Try input
1.0 to see the first overlapping range win with result 10, input 5.0 for a list
value, or 4.0 for ELSE=-1. A divisor of zero faults late in the routine; restore
it to 1 before retrying. Earlier scan-counter, array, string and AOI work rolls
back on the failed advance.

See [TextLab.L5X](../source/samples/TextLab.L5X),
[label validation](../source/logixlab/st_cases.py) and
[ST execution](../source/logixlab/structured.py). Coverage reports expose the
comparison profile and retain `native_runtime_parity=false`.

## Remaining scope

Mixed integers without a common source type, mixed-width bitwise operations,
additional literal/conversion forms, nonfinite floating execution and native
compiler/status/fault parity remain unqualified. Wide integer, mixed REAL/wide
and LREAL CASE profiles have been tested in the emulator. Native v35 acceptance
remains unverified.

The installed v35 CASE_OF help and Rockwell's
[CASE_OF reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/structured-text-attributes/case_of.html)
describe the narrow/REAL operands, immediate labels, ranges and first-match
behavior used for this bounded implementation.
