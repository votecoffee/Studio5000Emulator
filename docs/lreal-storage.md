# Finite LREAL storage and moves

App `26.1104.003503` adds a bounded LREAL storage model. Decorated L5X values,
arrays, explicit UDT members, aliases and external scalar writes retain finite
IEEE 754 binary64 values. Unknown exported elements remain unknown. This adds
a dedicated bounded type model; it does not complete LREAL execution support.

## Ladder MOV and CLR

The v35 ControlLogix 5580 software profile accepts LREAL tags with existing
scalar MOV/CLR. MOV supports all 100 pairings of the eight integer types, REAL
and LREAL. CLR establishes positive floating zero without reading old data.

```text
MOV(DoubleInput,DoubleCopies[DoubleIndex]);
MOV(IntegerInput,DoubleFromInt);
MOV(DoubleInput,SinglePrecision);
MOV(DoubleInput,IntegerResult);
CLR(DoubleClear);
```

A declared LREAL source retains binary64 precision before destination
conversion. `1.0000000000000002` remains distinct from 1.0 in another LREAL,
but narrows to REAL 1.0. DINT 16777217 becomes LREAL 16777217.0; an already
stored REAL source containing that input has rounded to 16777216.0 and widening
does not recover lost precision. Integer-to-LREAL conversion rounds to the
nearest representable binary64 value. LREAL-to-integer conversions use nearest,
ties to even, with a required representable signed/unsigned result.

Large finite values, subnormals and signed zero are retained where representable.
NaN/Infinity and REAL/integer destination overflow are outside the supported
profile and fail. Whole advances roll back instead of fabricating native
overflow/status results. Existing MOV literals remain bounded DINT/REAL inputs;
use a declared LREAL source tag for binary64 precision and range.

Structural checks retain scalar types, write permissions and reference grammar
without saved dynamic indices. False rungs and prescan skip live values and
indices. Complete writes establish unknown selected cells; partial logical
updates preserve untouched members. Invalid reached indices, required unknown
sources and later faults restore values and scheduling together.

## External tag access

HTTP and the existing optional tag bridge can read/write represented scalar
values. Atomic EtherNet/IP reads and explicitly enabled writes use type 0xCB
and little-endian eight-byte doubles. Fragmented reads/writes retain the existing
region and known-backing-byte rules. A complete write can establish an unknown
element; an incomplete element needs known preserved bytes. Nonfinite multi-
element writes reject the entire write. Existing permissions and network-write
opt-in remain required. Integer Read Modify Write does not accept LREAL.

These tag services are separate from Studio upload/download/online-edit
acceptance. LREAL UDT members have logical storage, but whole-UDT wire templates,
packed layouts and transferred compiled definitions remain unqualified.

## Integer lab

Open **Integer lab** and Step. `EnableDouble=false` keeps `DoubleIndex=99`
dormant and output cells unknown. Set `DoubleIndex=1`, enable `EnableDouble`, then Step.
`DoubleCopies[1]` retains 1.0000000000000002; `DoubleRounded` is 1.0,
`DoubleFromInt` is 9007199254740991.0, `DoubleAsInteger` is 1 and `DoubleClear`
is positive zero. The two array guards remain 101.125 and 999.5.

Change `DoubleInput` to 3.5 to observe nearest-even integer 4. `DoubleDivisor=0`
demonstrates a late fault with complete rollback; restore 1 before continuing.
Disable the section before returning `DoubleIndex` to 99. See the authored
[IntegerLab.L5X](../source/samples/IntegerLab.L5X),
[storage conversions](../source/logixlab/numeric_storage.py) and
[focused tests](../source/tests/test_lreal_storage.py).

The source basis is installed v35 help14688 (MOV),14685 (CLR) and4816 (types).
Published [MOV](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/move-logical-instructions/move--move-.html)
and [CLR](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/move-logical-instructions/clear--clr-.html)
references provide related instruction context. [Matching-tag ladder arithmetic
and comparisons](lreal-math.md), plus [matching-tag advanced math](lreal-advanced.md),
additionally execute. [TRN](lreal-truncate.md) additionally handles REAL/LREAL sources and integer/REAL/LREAL
results. Mixed arithmetic/immediates, ST expressions/assignments, general AOI parameter forms, COP/CPS and FLL,
new literal syntax, aggregate wire layouts and native rounding/status/fault/
lifecycle equivalence remain unfinished. These unsupported instruction forms
stay guarded rather than falling through to the REAL implementation.
