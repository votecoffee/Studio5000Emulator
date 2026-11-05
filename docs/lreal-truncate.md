# Ladder REAL and LREAL truncation

App `26.1104.013306` extends ladder TRN in the v35 ControlLogix 5580 software
profile. Sources can be scalar REAL or LREAL tags; destinations can be scalar
SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL tags.

```text
TRN(DoubleInput,WholeDouble);
TRN(DoubleInput,WholeDint);
TRN(DoubleInput,SelectedResults[Index]);
TRN(RealInput,WholeDouble);
```

Tagged REAL sources use their stored float32 value. Tagged LREAL sources retain
their stored binary64 precision before truncation toward zero. The integer part
is then converted to the declared destination type. Integer results must fit;
REAL results may round to float32, and LREAL results use finite binary64.

For example, LREAL 16777217.875 truncates to integer 16777217. A DINT or LREAL
destination retains that value; a REAL destination rounds it to 16777216.
LREAL 3.9999999999999996 truncates to 3, while narrowing the source to REAL first
would have produced 4. Existing untyped immediates retain the separate float32
source policy: TRN(16777217.875,DoubleResult) produces LREAL 16777218.
App `26.1105.073842` also accepts floating L/l constants as ladder TRN sources.
`TRN(16777217.875L,Whole)` produces 16777217 in a LINT destination, while
`TRN(16777217.875,Whole)` produces 16777218. Include a decimal point or exponent
before the suffix to select LREAL. The source must be finite, and the truncated
result must fit the destination. **Conversion lab** demonstrates both inputs
when `ImmediateConversions` is enabled.

Signed and unsigned boundaries use the actual stored binary64 value. LINT's
minimum is representable; its positive maximum is not exactly representable as
LREAL. The nearest stored value below 2^63 is 9223372036854774784, and the nearest
below 2^64 is 18446744073709549568. Values at 2^63/2^64 fault when the respective
integer destination cannot represent them. Negative fractions between -1 and 0
truncate to zero before an unsigned destination is checked.

The software solver uses host truncation. Finite very large LREAL values remain
valid for LREAL results; subnormal inputs truncate to zero. Fractional negative
values and negative zero produce positive floating zero through the host integer
intermediate. Native rounding, signed-zero/subnormal handling, saturation,
overflow results, math flags, faults and lifecycle equivalence remain unverified.
NaN/Infinity are outside this model. This does not predict execution time.

Structural preflight checks declared types, scalar shapes, reference grammar,
permissions and static bounds. False rungs and prescan skip live operands.
Selected elements, aliases, explicit UDT members and source/destination overlap
use existing memory rules. Complete writes establish unknown selected outputs
and retain neighboring cells. Unknown consumed sources, bad dynamic indices,
unrepresentable results and later faults roll back the advance, including task
progress, timing histories and AOI local/external values and bindings. Matching
LREAL AOI InOut arrays and represented local arrays have warm-state cases;
broader copied LREAL parameters remain unqualified. Run-entry initialization
retains its separate preceding prescan boundary.

Open **Math lab** and Step with TrnEnabled false. TrnIndex=99 remains dormant and
TrnResults[1] remains unknown. Set the index to 1, enable the section and Step:

- TrnResults[1] and TrnDint become 16777217; TrnReal becomes 16777216.
- TrnLint retains 9007199254740991; TrnUlint retains 18446744073709549568.
- TrnFromReal truncates the existing REAL Input, initially -16.
- TrnResults[0]/[2] retain fractional guards 101.125 and 999.5.

Set TrnDivisor to zero to observe a late failure after the truncations; restore
it to 1 before continuing. Setting TrnSignedInput to 2^63 or TrnUnsignedInput to
2^64 demonstrates range faults. Disable the section before returning its index
to 99. Other Math lab examples remain independently gated.

The source basis is installed v35 help14671, whose ladder operand table lists
REAL/LREAL sources and the ten destination types above. Later published
[Rockwell truncation help](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/math-conversion-instructions/truncate--trn-.html)
uses the newer TRUNC mnemonic. This increment retains v35 TRN. It does not add
that ladder alias, a TRN ST call, LREAL ST TRUNC expressions or new FBD forms.
[SIZE](size-truncate.md) retains its existing destination types and metadata rules.

See [implementation](../source/logixlab/size_truncate.py),
[focused cases](../source/tests/test_lreal_truncate.py) and
[MathLab.L5X](../source/samples/MathLab.L5X).
