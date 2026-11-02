# FBD roots, powers, logarithms and trigonometry

SQR, LN, LOG, XPY, DEG, RAD, SIN, COS, TAN, ASN, ACS and ATN execute as FBD Blocks
in the bounded v35 ControlLogix 5580 finite REAL profile. They reuse the two
[existing math records](fbd-arithmetic.md) and the ladder model's host-math
functions. These forms add no new predefined types or RLL/ST record-call overloads.

| Block | Record and inputs | Behavior |
| --- | --- | --- |
| SQR | FBD_MATH_ADVANCED.Source | Square root of the absolute value, including negative inputs |
| LN / LOG | FBD_MATH_ADVANCED.Source | Natural / base-10 logarithm; positive source required |
| XPY | FBD_MATH.SourceA, SourceB | SourceA to the power SourceB; negative bases require an integral exponent |
| RAD / DEG | FBD_MATH_ADVANCED.Source | Degrees to radians / radians to degrees |
| SIN / COS / TAN | FBD_MATH_ADVANCED.Source | Trigonometric operation with a radian input |
| ASN / ACS | FBD_MATH_ADVANCED.Source | Inverse sine/cosine, with input in [-1,1]; radian result |
| ATN | FBD_MATH_ADVANCED.Source | Inverse tangent; radian result |

Inputs and Dest are REAL; EnableIn/EnableOut are BOOL. Every required input must
be known and finite, including XPY's base when its exponent is zero. Inputs and
results round to float32 at each block; calculations use host math functions.
Downstream blocks consume that rounded value. No hidden math history is added.
The SQR absolute-value rule is shared with the ladder/expression models.

Prescan retains enables/Dest. Connected false EnableIn clears enables and retains
Dest without evaluating inputs; unwired enable executes. Skipped calls retain
results. Direct Dest writes survive disabled/skipped calls and are replaced on
the next enabled calculation. Run entry reapplies prescan without clearing math
results. Other block families keep their own lifecycle rules.

Invalid logarithm/inverse-trig/power domains, nonfinite inputs and REAL overflow
fail and roll back the complete simulation advance. Earlier block outputs,
later errors, time, trace and scheduling participate in that transaction. Native
NaN/infinity results, EnableOut-on-overflow behavior, minor faults, math flags,
underflow/subnormals, tangent poles/large-angle reduction and bit-exact numerical
or lifecycle parity remain unqualified. Host behavior is not native acceptance.
Integer/wide operands, LREAL, tagless Function forms and additional aliases are
not enabled by this v35 Block increment.

Choose **FBD advanced math lab** for `FBDAdvancedMathLab.L5X`: 37 roots, twelve
blocks, 33 nodes and 38 wires. Defaults produce Root 3, CommonLog 2 and Power 8.
AngleDegrees 30 passes through RAD to SIN/COS/TAN; Ratio .5 drives ASN/ACS, and
ASN feeds DEG to recover approximately 30 degrees. Slope 1 drives ATN. Change
RootInput to -25 for Root 5; try invalid LogInput or Ratio to observe rollback.
BlockEnable gates all blocks; ExecuteGraph skips the routine; FaultDivisor zero
demonstrates a later ladder fault. Restore valid inputs before retrying.

There are 58 supported graph blocks: 21 shared ST-call names, 30 common RLL
names and seven FBD-only forms. RLL remains 101 and ST calls 27. The 222-entry
type catalog remains at 52 dedicated bounded models and 170 without one. These
counts do not establish full instruction/type coverage or native runtime parity.

Schemas and execution tables were checked against installed v35 help 14478.htm,
14479.htm, 14480.htm, 14617.htm, 14663.htm, 14676.htm, 14748.htm, 14749.htm,
14750.htm, 14751.htm, 14752.htm and 14768.htm, with Rockwell's
[general-instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
as corroboration. Studio import/Verify, packed layouts and transfer/edit
qualification were not established by the synthetic lab.
