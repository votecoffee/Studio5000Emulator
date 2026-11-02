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

MEQ retains SINT/INT zero extension to 32 bits and existing signed DINT/radix
patterns. Homogeneous LINT/USINT/UINT/UDINT/ULINT comparisons retain their exact
integer representation and bounded, representable DINT immediates. Mixed wide
types remain blocked. LIM includes both endpoints; reversed low/high limits
select the outside ranges. Equal limits select the single matching value.

This revision changes operand selection and validation, retaining the existing
numeric conversion rules. It does not qualify the complete mixed-type promotion
matrix or native status/fault/lifecycle behavior. Other controller profiles and
string comparisons keep their separate paths. No ST call or FBD form is added.
The API report exposes this bounded profile under `numeric_comparisons`.

Choose **Data lab** and enable `CompareEnable`. `MaskedMatch`, `InRange` and
`CompareEqual` show masked, range and ordinary equality tests. With the gate
false, set `CompareIndex` outside the array and step: the coils clear without
consuming the invalid index. Enabling the gate then reports a modeled fault;
correct the index to retry.

Reference basis: installed Studio 5000 v35 **Compare Instructions** (14591),
**Mask Equal To (MEQ)** (14602), and **Limit (LIM)** (14610). The published
[MEQ reference](https://www.rockwellautomation.com/en-nl/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compare-instructions/mask-equal-to--meq-.html)
also documents narrow zero extension and false-rung propagation. Software-model
and HTTP checks do not establish native controller equivalence.
