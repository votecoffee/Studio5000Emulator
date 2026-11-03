# Numeric ladder comparisons

The v35 ControlLogix 5580 software profile validates EQU, NEQ, LES, LEQ, GRT,
GEQ, LIM and MEQ structurally. Saved numeric values may remain unknown at import.
Declared types, scalar shape, static references and existing immediate/profile
restrictions are still checked, even on false rungs.

False rungs and ordinary prescan skip operand values and live indices. Downstream
OTE instructions still clear their coils when rung power is false. True calls
consume every comparison operand; reached unknowns or invalid indices fail the
advance. A zero MEQ mask does not infer a result from unknown operands. Earlier
writes, coils, task/time state and existing AOI bindings roll back on failure.

## Mixed integer tag widths

App `26.1103.081017` allows all tag-only combinations of SINT, INT, DINT, LINT,
USINT, UINT, UDINT and ULINT in ladder MEQ for the v35 ControlLogix 5580 profile.
Source, Mask and Compare are read-only inputs: constant tags, aliases, selected
array/UDT members and existing AOI Input/InOut/local bindings are accepted.
Each declared pattern is zero-extended before comparing `(Source & Mask)` with
`(Compare & Mask)`. Negative DINT values retain 32 bits when combined with a
64-bit operand; negative LINT values retain 64 bits. No floating-point conversion
is used, so adjacent 64-bit values remain distinguishable.

For example, SINT -1 under a ULINT mask of 65536 matches LINT 0, because the
byte pattern contains only eight set bits. DINT -1 under LINT -1 matches ULINT
4294967295, rather than the full 64-bit all-ones pattern.

Immediate rules remain separate. Narrow forms retain signed DINT decimal and
32-bit radix patterns. If any LINT/unsigned tag and an immediate are present,
all tag operands must retain one matching type, and every immediate must be a
signed DINT integer representable in that type. Mixed wide/immediate forms,
negative unsigned immediates, typed/wider immediates and REAL/LREAL operands
remain unsupported. Store large constants in typed tags.

LIM includes both endpoints; reversed low/high limits select the outside ranges.
Equal limits select the single matching value.

Arithmetic comparisons keep their existing numeric conversion rules. Complete
arithmetic promotion and native status/fault/lifecycle behavior remain unqualified.
Other controller profiles and
string comparisons keep their separate paths. No ST call or FBD form is added.
The API report exposes this bounded profile under `numeric_comparisons`.

Choose **Data lab** and enable `CompareEnable`. `MaskedMatch`, `InRange` and
`CompareEqual` show masked, range and ordinary equality tests. With the gate
false, set `CompareIndex` outside the array and step: the coils clear without
consuming the invalid index. Enabling the gate then reports a modeled fault;
correct the index to retry.

Enable `MixedCompare` for three additional examples. Initially `MixedMaskMatch`
is true and `MixedExactMatch`/`MixedWidthMatch` are false. Set `MixedExpectedExact`
to 9007199254740993 and `MixedExpected` to 4294967295: the exact and width tests
become true and the first test becomes false. Disabling the gate clears all three
coils. Wide tag values are exchanged as decimal strings to retain precision.

Reference basis: installed Studio 5000 v35 **Compare Instructions** (14591),
**Mask Equal To (MEQ)** (14602), and **Limit (LIM)** (14610). The published
[MEQ reference](https://www.rockwellautomation.com/en-nl/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compare-instructions/mask-equal-to--meq-.html)
also documents narrow zero extension and false-rung propagation. Software-model
and HTTP checks do not establish native controller equivalence.
