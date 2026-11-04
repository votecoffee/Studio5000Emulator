# Array-index functions

App `26.1104.105855` extends the v35 ControlLogix 5580 software profile with
FRD, TOD and SQR inside existing array references. Arguments are narrow integer
expressions: SINT, INT and DINT tags promote to checked DINT intermediates.
Function results are DINT. Constants, nesting, arithmetic and existing bitwise
operators can compose these functions.

```text
MOV(Input[FRD(PackedIndex)],Selected);
MOV(Input[TOD(DecimalIndex)],Selected);
MOV(Input[SQR(Position)],Selected);
MOV(Input[FRD(TOD(Position))],Output[SQR(Position*Position)]);
```

FRD interprets the argument as a 32-bit pattern and weights all eight nibbles,
including A-F, using the existing BCD solver. FRD(16#21) is 21 and FRD(16#1A)
is 20. Arguments are promoted to DINT before conversion, so FRD(-1) is
166666665 even if a narrow signed tag supplied -1. This index profile is
separate from standalone FRD's declared source-width rules.

TOD accepts 0..99999999, packs eight BCD digits and preserves the signed DINT
result pattern. TOD(21) is decimal 33 (16#21). TOD(99999999) is -1717986919;
it can be masked or decoded by an enclosing expression. A negative final index
still fails array bounds. Invalid TOD ranges stop and roll back the advance.

SQR uses the existing absolute-value square-root solver with finite float32
input and result, then nearest-even DINT conversion. SQR(3) is 2 in this 5580
software profile; SQR(-16) is 4. Stored integers retain their exact values,
while the function can lose input precision through its float32 conversion.
SQR(16777217) is 4096. Native numerical, status and lifecycle parity remain
unverified.

Structural preflight checks references, grammar and declared types without
consuming saved indices. False ladder rungs, prescan and skipped ST branches
can retain unknown arguments or invalid runtime ranges. Reached expressions
consume every required argument: masks do not hide unknowns or division by
zero. Full writes establish selected unknown destinations and preserve neighbors.

Existing aliases, UDT members, nested and multidimensional references, supported
ST assignments and AOI local/InOut bindings share the resolver. Consumer-specific
overlap, permission, static-start and opt-in CONTROL.POS restrictions remain.
Unknowns, ranges, DINT intermediate overflow, array bounds and later failures
restore earlier writes, task progress/timing and warm AOI state/bindings.

The logic viewer resolves the same forms from its existing snapshots, including
checked BCD patterns and root rounding. It adds no PLC reads, writes or polling.
Invalid, unknown or excluded forms remain unavailable; no arbitrary code is
evaluated.

Standalone FRD/TOD in ST remain excluded; [integer CPT](cpt-bcd.md) and
[integer CMP](cmp-bcd.md) now have separate profiles. Other functions
such as ABS, TRN and SQRT, MOD/power, floating/BOOL operands, wide arithmetic
arguments and broader controller profiles remain separate. A single wide integer
tag still works as an index through the existing simple-tag profile. This adds
no instruction mnemonic, language, FBD or SFC form, native fault records or
native controller/Studio acceptance claim.

Open **Bit lab**, set IndexFuncDecimal to 17, enable IndexFuncEnabled and Step.
Results 1 through 6 become 221, 223, 202, 217, 207 and 223; IndexFuncCheck is
true. Neighboring result guards remain 101 and 999. The section starts disabled
with Decimal=-1, demonstrating that false paths skip invalid runtime ranges.

Set Decimal=-1 or 100000000 for TOD range rollback, Root=2147483647 or Packed=-1
for selected-array bounds rollback, or LateDivisor=0 for a failure after earlier
writes. Restore Decimal=17, Root=3, Packed=33 and LateDivisor=1. External writes
affect the next Step; disable before returning inputs to invalid dormant values.
Stored results remain and the section's check coil clears.

Source basis: installed v35 **Index Through Arrays** (14431), **SQR** (14617),
and the existing bounded BCD conversion profile. The published
[Rockwell index reference](https://www.rockwellautomation.com/en-ie/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html)
also lists these functions. The installed v35 scope and software tests do not
establish native numerical or lifecycle equivalence.

See [implementation](../source/logixlab/expressions.py),
[snapshot resolution](../source/web/logic-values.js),
[focused cases](../source/tests/test_array_index_functions.py) and
[BitLab.L5X](../source/samples/BitLab.L5X).

[BCD CPT expressions](cpt-bcd.md) now have a separate v35 5580 narrow-integer
profile. CPT parser opt-in keeps other expression consumers and wider/REAL forms
separate; array-index functions retain their existing conversion rules.
