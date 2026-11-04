# Tagged LREAL ladder arithmetic and comparisons

App `26.1104.005430` adds finite binary64 execution for these ladder forms in the
v35 ControlLogix 5580 software profile:

| Family | Instructions |
| --- | --- |
| Basic arithmetic | ADD, SUB, MUL, DIV, MOD, NEG, ABS |
| Direct ordering | EQU, NEQ, LES, LEQ, GRT, GEQ |
| Limits | LIM |

Every operand must be a scalar LREAL tag, including arithmetic destinations.
Selected array elements, aliases and explicit UDT members retain their declared
type. Immediate constants and mixed integer/REAL/LREAL forms remain blocked even
when their saved values happen to fit. Existing [MOV conversions](lreal-storage.md)
can prepare matching LREAL source tags. No new mnemonic or language is added.

```text
ADD(DoubleA,DoubleB,DoubleSum);
SUB(DoubleA,DoubleB,DoubleDifference);
MOD(DoubleA,DoubleB,DoubleRemainder);
GRT(DoubleA,DoubleB)OTE(IsGreater);
LIM(DoubleLow,DoubleA,DoubleHigh)OTE(InRange);
```

## Calculation policy

Sources and results use finite host binary64 values without a REAL/float32
intermediate. With DoubleA=1.0000000000000002 and DoubleB=1.0, SUB and MOD retain
2^-52, and GRT is true. ADD rounds to 2.0 at binary64 precision. Decimal inputs
and products are rounded binary representations; decimal arithmetic is not
implied. Exact comparisons use stored values without an added tolerance.

DIV uses floating division. MOD uses host `fmod`, retains the dividend's sign,
and avoids forming an overflowing quotient for tiny divisors. Signed zero and
representable subnormals are retained. NEG reverses the sign of zero; ABS produces
positive zero. LIM includes its endpoints; when Low exceeds High, values at or
outside those endpoints pass, matching the existing scalar limit policy.

Zero DIV/MOD divisors, required unknown values and nonfinite results fault and
roll back the whole advance. The model does not emulate native minor-fault
continuation, overflow result bits, math flags, hardware rounding modes or timing.
Host results, especially subnormal and remainder details, are not a native
controller conformance claim.

## Selection, aliases and AOIs

Preflight checks declared scalar types, write permissions, reference grammar and
fixed bounds without consuming saved values or dynamic indices. False rungs and
prescan skip live arithmetic/comparison operands. Arithmetic retains its output;
a downstream OTE follows false power. Reached operations consume all sources.
Complete result writes establish unknown selected cells while retaining siblings.

Source values are read before the result is written, including overlapping
source/destination aliases. Later faults restore tags, task releases, committed
timing histories and existing AOI local/external values and bindings together.
Run-entry prescan retains its separate existing initialization boundary; these
rollback statements apply to the subsequent advance. Focused cases cover matching
LREAL AOI InOut arrays and represented local arrays.
Copied LREAL Input/Output parameters and broader AOI forms remain unqualified.

## Integer lab

Open **Integer lab**. `EnableDoubleMath=false` leaves `DoubleMathIndex=99`
dormant and `DoubleMathResults[1]` unknown. Set the index to 1, enable the section,
then Step. The default inputs produce:

| Result | Value |
| --- | --- |
| DoubleSum / selected result | 2.0 |
| DoubleDifference / DoubleRemainder | 2^-52 |
| DoubleProduct / DoubleQuotient / DoubleAbsolute | 1.0000000000000002 |
| DoubleNegated | -1.0000000000000002 |
| DoubleEq / DoubleLt / DoubleLe | false |
| DoubleNe / DoubleGt / DoubleGe / DoubleInLimits | true |

The array guard values remain 101.125 and 999.5. Set DoubleB to zero for a
division fault after earlier arithmetic, or DoubleMathDivisor to zero for a late
fault after the comparisons. Restore the corresponding value to 1 before
continuing. Disable the section before returning its index to 99. The earlier
DoubleStorage example remains independently gated.

See [IntegerLab.L5X](../source/samples/IntegerLab.L5X),
[arithmetic](../source/logixlab/scalar_math.py),
[comparisons](../source/logixlab/comparisons.py) and
[focused cases](../source/tests/test_lreal_math.py).

The source basis is the installed v35 instruction help, including ADD14623,
MOD14620, EQU14589 and LIM14610. Published Rockwell
[ADD](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/add--add-.html)
and [MOD](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/modulo--mod-.html)
references give related context. Mixed types/immediates, ST expressions, CPT/CMP,
advanced math, bitwise LREAL operations, aggregate byte layouts and native
precision/status/fault/lifecycle equivalence remain separate work.
