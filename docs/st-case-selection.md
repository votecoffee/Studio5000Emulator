# Numeric CASE selection in Structured Text

App `26.1030.000222` supports CASE expressions using the existing narrow
integer or REAL expression profile. Branch labels are immediate numeric
values, comma-separated lists, ascending inclusive ranges, or combinations.

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
by whitespace. Tags, expressions, BOOL/string values and typed L/U/UL labels
are rejected as branch labels.

The expression determines the comparison profile. A REAL operand or literal in
the expression selects modeled float32 arithmetic. REAL labels are converted to
float32 before comparison; integer labels in that context are also converted to
float32. Labels do not promote an integer expression. Thus `CASE 5/2 OF` selects
integer 2, while `CASE 5.0/2 OF` can select REAL 2.5.

REAL comparisons use the stored float32 values with no added tolerance. For
example, 16777217.0 and 16777216.0 round to the same float32 value, so whichever
label appears first wins. Ranges are usually more useful than exact equality
for calculated REAL values. Nonfinite or overflowing REAL labels, descending
ranges and malformed forms block execution, including in unreachable code.

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

Wide integer selectors and typed labels, additional literal/conversion forms,
nonfinite REAL execution and native compiler/status/fault parity remain
unqualified. The emulator uses its existing DINT/float32 expression rules;
software tests do not establish native Studio/controller acceptance.

The installed v35 CASE_OF help and Rockwell's
[CASE_OF reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/structured-text-attributes/case_of.html)
describe the narrow/REAL operands, immediate labels, ranges and first-match
behavior used for this bounded implementation.
