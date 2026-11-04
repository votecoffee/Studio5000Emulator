# Mixed numeric tag arithmetic with LREAL

App `26.1104.020009` extends the v35 ControlLogix 5580 ladder software profile
for ADD, SUB, MUL, DIV and MOD. Both sources must be scalar numeric tags, at least
one source must be LREAL, and the destination must be LREAL. The other source
can be SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL or LREAL. Both source
orders are supported. NEG/ABS retain their existing LREAL-source/result forms.

```text
ADD(DoubleInput,DintInput,DoubleResult);
SUB(RealInput,DoubleInput,DoubleResult);
MUL(SignedWide,DoubleInput,SelectedResults[Index]);
DIV(DoubleInput,UnsignedWide,DoubleResult);
MOD(DoubleInput,DintDivisor,DoubleRemainder);
```

Declared types select the profile independently of saved values. Every required
source is read and converted to finite host binary64 before the operation;
there is no intermediate REAL conversion. Signed integers retain their numeric
sign, unsigned integers retain their numeric value, and REAL tags contribute
their already stored float32 value. Conversion does not recover precision lost
when a value was stored as REAL. Integer values beyond binary64's exact range
may round before calculation, including LINT/ULINT values beyond 2^53.

For example, subtracting DINT 16777217 from LREAL 16777218 produces 1 rather
than the 2 that a prior REAL conversion of the integer would produce. Subtracting
REAL 1 from LREAL 1.0000000000000002 retains 2^-52. LINT 9007199254740993 converts
to binary64 9007199254740992, so subtracting LREAL 9007199254740992 yields zero.
ULINT's maximum converts to the binary64 value 2^64. These are software solver
rules, not a claim of native bit-for-bit precision or overflow/status behavior.

DIV uses the host floating quotient. MOD uses host fmod with the dividend's sign;
it does not form an intermediate quotient. Zero divisors and nonfinite results
fault and roll back the advance. Both operands remain required even if one is
zero or the operation could be algebraically simplified. Native signed-zero,
subnormal, rounding, fault-continuation, status and lifecycle parity remain
unverified. No controller execution-time prediction is made.

Structural preflight checks scalar shapes, declared types, references, static
bounds and destination permissions without consuming saved dynamic indices or
values. False rungs and prescan skip live operands and retain results. Complete
writes establish unknown selected outputs while preserving sibling values.
Aliases, UDT members, overlapping source/result tags and existing AOI bindings
share the memory rules. Unknown consumed values, invalid indices, overflow and
later failures restore prior values, task progress, timing and AOI local/external
arrays and bindings within the advance. Run-entry initialization remains a
separate preceding prescan boundary. Matching LREAL InOut/local arrays with a
copied DINT AOI input have independent warm-state rollback cases; copied LREAL
parameters and broader AOI forms remain separate.

The remaining boundaries are explicit:

- Immediates remain outside LREAL arithmetic; prepare typed source tags with MOV.
- A LREAL destination with only integer/REAL inputs does not select this profile.
- LREAL arithmetic with a non-LREAL result remains guarded.
- [Mixed direct comparisons/LIM](mixed-lreal-comparisons.md) additionally promote
  numeric tags when at least one input is LREAL. Advanced math remains separate.
- LREAL ST expressions, CPT/CMP, bitwise arithmetic, time/date and aggregate
  operands remain outside this extension. No new FBD or SFC forms are added.

Open **Integer lab** and Step with EnableMixedDouble false. MixedDoubleIndex=99
is dormant and MixedDoubleResults[1] is unknown. Set the index to 1, enable the
section and Step. With the default DoubleA=1.0000000000000002:

- MixedDoubleAdd is 16777218; MixedDoubleSubtract is 2^-52.
- MixedDoubleMultiply is 16777217.000000004; MixedDoubleDivide is
  0.5000000000000001; MixedDoubleRemainder retains DoubleA.
- MixedDoubleWide is zero after the signed 64-bit input rounds to binary64;
  MixedDoubleUnsigned demonstrates conversion of ULINT's maximum.
- The selected result preserves neighboring guards 101.125 and 999.5.

Set MixedDoubleDivisor=0 for a division failure after earlier arithmetic, or
MixedDoubleLateDivisor=0 for a later failure after all mixed operations. Restore
the divisors to 2 and 1 respectively before continuing. Disable the section
before returning its index to 99. Other Integer lab sections remain available.

The source basis is installed v35 arithmetic help, including ADD14623 and
MOD14620, plus Data Conversions14451, which ranks LREAL highest. The published
[Rockwell data-conversion reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/data-conversions.html)
provides related context. Requiring a LREAL input avoids extending the solver
to unqualified integer/REAL intermediate and destination-conversion rules.

See [implementation](../source/logixlab/scalar_math.py),
[focused cases](../source/tests/test_mixed_lreal_math.py) and
[IntegerLab.L5X](../source/samples/IntegerLab.L5X).
