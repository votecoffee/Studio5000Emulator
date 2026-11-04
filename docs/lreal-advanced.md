# Tagged LREAL roots, powers, logarithms and trigonometry

App `26.1104.011710` adds finite binary64 execution for twelve standalone ladder
forms in the v35 ControlLogix 5580 software profile:

| Family | Instructions |
| --- | --- |
| Root and power | SQR, XPY |
| Logarithms | LN, LOG |
| Angle conversion | DEG, RAD |
| Trigonometry | SIN, COS, TAN, ASN, ACS, ATN |

The original forms require matching scalar LREAL source and destination tags.
[Mixed XPY sources and constants](mixed-lreal-power.md) additionally qualify
powers with at least one LREAL input and a LREAL result.
[Numeric unary sources](lreal-unary-sources.md) additionally accept numeric tags
and signed DINT constants with a LREAL result. Selected array elements,
aliases and explicit UDT members retain their declared types. Matching AOI InOut
arrays and represented local arrays have focused cases. Other mixed types,
immediates and broader copied LREAL AOI parameters remain unqualified. Existing
[MOV conversions](lreal-storage.md) can prepare matching source tags.

```text
SQR(RootInput,Result);
XPY(Base,Exponent,PowerResult);
LN(LogInput,LogResult);
SIN(Radians,SineResult);
ASN(InverseInput,ArcResult);
```

## Numerical policy

Sources and results use finite host binary64 values, without a REAL/float32
intermediate. For example, LN(1.0000000000000002) retains approximately
2.2204460492503128e-16, and squaring that source yields 1.0000000000000004.
SQR accepts large finite values such as 1e308. Representable tiny/subnormal values
remain usable rather than first narrowing to zero.

SQR retains the existing absolute-value rule for a negative source. LN and LOG
require positive sources. SIN/COS/TAN consume radians; inverse functions return
radians. ASN/ACS require a source between -1 and 1, inclusive. A binary64 value
just outside that interval faults even if REAL conversion would have rounded it
back to an endpoint. DEG converts radians to degrees; RAD converts the opposite
direction. XPY uses the host real-valued power operation: negative bases with
integer exponents are accepted; fractional powers requiring complex results are
outside this profile. Host 0^0 yields 1; representable signed zero and underflow
results follow the host solver.

These rules reuse the existing host functions at binary64 precision. Native
instruction rounding, range reduction, subnormal handling, overflow results,
NaN/Infinity, math flags, fault continuation and bit-for-bit numerical equivalence
remain unverified. This does not predict controller execution time.

## Selection, faults and initialization

Structural preflight checks scalar types, reference grammar, fixed bounds and
write permissions without saved values or dynamic indices. False rungs and
prescan skip live operands and retain outputs. True calls consume every required
source, including both XPY sources even when the base is 1.

Complete writes establish unknown selected cells and preserve sibling elements.
Sources are read before their result is written, including aliases and overlapping
operands. Required unknowns, invalid indices, domain/overflow errors and later
faults roll back the advance, including earlier values, task progress, timing
histories and AOI local/external values and bindings. Run-entry initialization
retains its separate existing prescan boundary; running-scan rollback does not
undo a preceding Run-entry initialization.

## Math lab

Open **Math lab** and Step. `LrealMath=false` leaves `LrealIndex=99` dormant and
the selected result unknown. Set the index to 1, enable the section, then Step.
The independent `LrealAdvanced` routine demonstrates all twelve forms:

- LrealSqr is 3.0000000000000004 and the selected result has guards 101.125/999.5.
- LrealLn retains the small nonzero value above; LrealPower is 1.0000000000000004.
- LrealRad is the host binary64 value of pi; the other angle/trig results use
  the displayed LrealRadians, LrealDegrees and LrealInverse inputs.

Set LrealLogInput to zero, LrealInverse just above 1, or LrealLateDivisor to zero
to observe domain or late-fault rollback. Restore the corresponding defaults
before continuing. Disable the section before returning its index to 99.
Existing narrow math and ST examples remain independently available.

See [MathLab.L5X](../source/samples/MathLab.L5X),
[implementation](../source/logixlab/real_math.py) and
[focused cases](../source/tests/test_lreal_advanced.py).
The source basis is installed v35 help for all twelve forms, including SQR14617,
XPY14478, LN14479 and ASN14750. Later published
[square-root](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/square-root--sqrt-.html)
and [power](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/advanced-math-instructions/expt.html)
references use newer mnemonics. This increment retains v35 SQR/XPY; standalone
SQRT/EXPT aliases, LREAL ST/CPT/CMP expressions and general FBD LREAL execution
remain separate work.
