# BCD operators in CMP

App `26.1104.120940` adds FRD/TOD operators to integer ladder CMP expressions
in Standard v35 ControlLogix 5580 projects (`1756-L81E` through `1756-L85E`).
Numeric inputs and comparison operands are scalar SINT, INT or DINT tags or
bounded integer literals; arithmetic intermediates are checked DINT values.
BOOL tags can participate in the existing Boolean composition rules.

```text
CMP(FRD(Packed)=Expected)OTE(Matches);
CMP(FRD(TOD(Decimal))=Decimal)OTE(RoundTrip);
CMP(Enabled&&!(TOD(Decimal)/Divisor=0))OTE(Ready);
CMP(FRD(Rows[Index])=21)OTE(SelectedMatch);
```

Conversions use the existing [CPT BCD rules](cpt-bcd.md). Narrow signed numeric
values promote before FRD decodes eight weighted nibbles, including A-F.
FRD(16#1A)=20 and FRD(-1)=166666665, even for a SINT/INT source. TOD accepts
0..99999999 and returns a signed DINT pattern: TOD(99999999)=-1717986919.
FRD(TOD(99999999))=99999999. Standalone FRD's declared-width rules remain
separate. Native numerical equivalence is unverified.

All six relations compose with nested FRD/TOD, existing integer arithmetic,
bitwise operators, ABS/TRN/TRUNC, BOOL tags and Boolean AND/OR/XOR/NOT or
&&/||/^^/!. Use parentheses to make numeric and Boolean grouping explicit.
BOOL values are not numeric FRD/TOD arguments. Required numeric values and
intermediates must fit DINT; a later mask or relation does not conceal overflow.
REAL/LREAL/wide numeric inputs, floating/typed/larger literals, REAL-producing
functions and string mixtures remain outside this BCD comparison profile.
Ordinary comparisons without BCD operators retain their existing profiles.

The condition parser explicitly enables these operators for ladder CMP and
uses a separate cache key. [FAL/FSC BCD expressions](file-bcd.md) now opt into
these conversions; ST and direct condition parsers retain their function sets. This adds no instruction mnemonic, new language form,
native alias spelling, math-status flag or controller fault class.

Structural preflight checks types, scalar shapes, references and syntax without
consuming saved values or live dynamic indices. False rungs and ordinary
prescan skip comparison operands; downstream OTE coils clear. Reached conditions
consume both logical operands eagerly. A true OR branch, false AND branch or
zero mask does not hide an unknown source, invalid index or divide-by-zero.
Aliases, UDT members, indirect/function indices and constant sources remain
read-only. Existing AOI copied inputs, InOut arrays and local state share these
rules, including conditional downstream writes. Runtime errors and later
failures restore data, coils, task timing/progress and warm AOI bindings.
Completed prescan remains a separate lifecycle boundary.

Open **Bit lab** and select **BcdComparisons**. The section starts disabled with
CmpBcdDecimal=-1, CmpBcdIndex=99 and an unknown middle row. Set Decimal=42,
Index=1 and CmpBcdRows[1]=33; enable CmpBcdEnabled and Step. All six match coils
are true. Neighboring row guards remain 101 and 999. Select a CMP node to inspect
its raw condition and observe the rung and coil state.

Set Packed=34, Decimal=21 and Rows[1]=34, then Step. DecodeMatch, MaskMatch and
IndexedMatch become false; RoundTripMatch, PatternMatch and GateMatch remain
true. Gate=false clears GateMatch. Disable the section to clear all match coils.
Monitoring leaves the stopped simulation unchanged.

Enabling before initializing Decimal/Index/Rows[1] demonstrates separate range,
bounds and unknown-input faults. Decimal=100000000, Divisor=0 or LateDivisor=0
exercise additional rollback. Divisor=0 still faults when Gate=false because
logical operands are eager. Restore valid inputs before retrying; disable
before returning dormant values to invalid ranges.

The source basis is installed v35 Compare (14592), Compute (14597) and Data
Conversions (14451). The current published
[CMP reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compare-instructions/compare--cmp-.html)
uses newer BCD_TO/TO_BCD spellings; this increment targets installed v35 FRD/TOD.
Native numerical, sampling, status, fault, lifecycle and Studio acceptance remain
unverified. See [condition implementation](../source/logixlab/conditions.py),
[dispatch](../source/logixlab/extended.py),
[focused cases](../source/tests/test_cmp_bcd.py),
[BitLab.L5X](../source/samples/BitLab.L5X) and
[comparison semantics](integer-expressions.md#operand-selection).

[Bounded integer powers](ladder-integer-power.md) now compose with these
FRD/TOD expressions; exponents remain in 0..31 with checked DINT results.

[Integer SQR nodes](ladder-integer-roots.md) now retain narrow integer arithmetic
in eligible ladder expressions, including composition with these operations.

[Homogeneous wide BCD expressions](cpt-bcd.md#wide-integer-expressions) separately
qualify FRD/TOD in CPT/CMP/FAL/FSC for USINT, UINT, UDINT, LINT and ULINT, using
their selected 8/16/32/64-bit software conversion widths. Mixed numeric tag
widths, REAL/LREAL, ST/index expansion and native parity remain excluded.
