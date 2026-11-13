# BCD operators in CPT

App `26.1104.114926` adds FRD and TOD operators to integer ladder CPT
expressions in Standard v35 ControlLogix 5580 projects (`1756-L81E` through
`1756-L85E`). Source and result tags are scalar SINT, INT or DINT. Intermediates
are checked DINT values; larger or typed literals and other numeric types remain
outside this profile.

```text
CPT(Decoded,FRD(Packed));
CPT(Packed,TOD(Decimal));
CPT(RoundTrip,FRD(TOD(Decimal)));
CPT(Results[Index],FRD(Packed)/Divisor MOD 100);
```

FRD decodes all eight nibbles of the promoted 32-bit argument, including A-F
with their weighted values. FRD(16#1A) is 20; FRD(-1) is 166666665, even when
the source tag is SINT or INT. This expression rule promotes the signed numeric
value first; standalone FRD retains its separate declared-width behavior.

TOD accepts 0..99999999 and returns the signed interpretation of the complete
packed DINT pattern. TOD(99999999) is -1717986919;
FRD(TOD(99999999)) is 99999999. A negative or larger source faults when reached.
These are explicit software conversion rules; native numerical equivalence
has not been demonstrated.

The existing integer operators compose with FRD/TOD: arithmetic, exact division
truncated toward zero, dividend-sign MOD, bitwise operators, unary signs,
ABS/TRN/TRUNC and parentheses. Every intermediate must fit DINT; later operators
do not conceal earlier overflow. SINT/INT results must fit their declared range;
CPT does not truncate a BCD result to fit. TOD(99) cannot be stored in SINT,
while TOD(79) stores 121. REAL-producing functions, floating operands or
literals and REAL/LREAL/wide destinations remain excluded from BCD CPT calls.
Existing expressions without FRD/TOD retain their previous profiles.

CPT enables these operators through a scoped parser option.
[BCD CMP expressions](cmp-bcd.md) now have a separate comparison profile.
[FAL/FSC BCD expressions](file-bcd.md) now opt into the same conversions.
Generic expressions and ST retain their existing function sets. Array-index
FRD/TOD/SQR remain a separate profile. No new instruction mnemonic, FBD/SFC form,
native expression spelling, math-status bit or controller fault class is added.

Structural preflight checks references, scalar types, syntax and destination
permissions without consuming saved values or live dynamic indices. False
rungs and ordinary prescan skip runtime arguments, including unknowns, invalid
TOD values and zero divisors. Reached calls consume required inputs eagerly;
a zero multiplier or mask does not hide an unknown argument. Full writes can
establish unknown selected results. Aliases, UDT members, nested function
subscripts and existing AOI copied inputs/InOut/local tables use the same
resolver. Required input errors, invalid indices, arithmetic/range errors and
later failures restore scan data, scheduler/timing and warm AOI bindings.
Completed prescan remains a separate lifecycle boundary.

Open **Bit lab** and select **CptConversions**. The section starts disabled,
with CptBcdDecimal=-1 and CptBcdIndex=99. Set Decimal=42 and Index=1, enable
CptBcdEnabled and Step. Exact=12345678, RoundTrip=42, NarrowResult=166666665,
Pattern=-1717986919, Mix=78, Results[1]=43 and Truncated=8. Result guards remain
101 and 999. Select a CPT node to inspect its expression and current destination.

Set Packed=34 and Decimal=21, then Step: Exact=22, RoundTrip=21, Mix=55 and
Results[1]=22. Decimal=-1 or 100000000, Index=99, Divisor=0 and LateDivisor=0
demonstrate separate faults and rollback. Restore valid inputs before retrying;
disable before returning dormant values to invalid ranges. Monitoring does not
advance the stopped simulation.

The source basis is installed v35 Compute (14597), Data Conversions (14451)
and the existing qualified BCD conversion model. The current published
[CPT reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/compute--cpt-.html)
uses newer BCD_TO/TO_BCD spellings; this increment targets the installed v35
FRD/TOD syntax. Native calculation, sampling, status, fault, lifecycle and Studio
acceptance remain unverified.

See [expression parser](../source/logixlab/expressions.py),
[CPT dispatch](../source/logixlab/extended.py),
[focused cases](../source/tests/test_cpt_bcd.py),
[BitLab.L5X](../source/samples/BitLab.L5X) and
[standalone conversions](numeric-conversions.md).

[Bounded integer powers](ladder-integer-power.md) now compose with these
FRD/TOD expressions; exponents remain in 0..31 with checked DINT results.

[Integer SQR nodes](ladder-integer-roots.md) now retain narrow integer arithmetic
in eligible ladder expressions, including composition with these operations.

## Wide integer expressions

The separate homogeneous v35 5580 profile now accepts FRD/TOD in ladder CPT,
CMP, FAL and FSC with USINT, UINT, UDINT, LINT or ULINT numeric operands.
Numeric tags and results must have one matching declared type. BOOL condition
tags remain allowed. Compatible constants retain the existing signed-DINT or
matching L/U/UL literal rules. Mixed numeric tag widths stay excluded for BCD.

The selected type supplies every intermediate width: 8, 16, 32 or 64 bits.
FRD weights all nibbles, including A-F, in that width. TOD accepts nonnegative
values up to 99, 9999, 99999999 or 9999999999999999, respectively. Packed
patterns use the result type's signed interpretation. For example, LINT
TOD(9999999999999999L) is -7378697629483820647; decoding it gives the exact
original decimal value. FRD(-1L) is 16666666666666665. These reuse the existing
standalone conversion software model; native expression widths, status and
precision remain unverified. Narrow SINT/INT/DINT still use DINT intermediates.

Nested FRD/TOD, ABS, supported integer arithmetic/bitwise operators and eager
Boolean comparisons compose under the existing per-intermediate range checks.
Unknown operands, invalid indices, conversion ranges and later faults roll back
the modeled advance. Structural preflight and false/prescan lazy reads remain.
REAL/LREAL combinations, other math functions, ST and index syntax are unchanged.

In **Wide expression lab**, set WideBcdIndex=1 and WideBcdEnabled=true. Packed
becomes -7378697629483820647, Roundtrip=9999999999999999, AllNibbles=
16666666666666665 and BytePacked=153. Match is true and Selected[1] contains
the packed LINT, with guards 101/999. The gate starts false with index99 dormant.
Input=10000000000000000 or LateDivisor=0 exercises rollback; restore the input
to 9999999999999999 or divisor to 1 before retrying.

The report publishes `wide_ladder_expressions.bcd`. The source basis is installed
v35 CPT/CMP/FAL/FSC operator tables (14597/14592/14504/14515) and FRD/TOD
operand references (14675/14674). See [focused checks](../source/tests/test_wide_bcd_expressions.py).
