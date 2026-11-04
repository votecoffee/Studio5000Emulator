# Integer powers in ladder expressions

The bounded v35 ControlLogix 5580 model supports `**` in CPT/CMP and FAL/FSC
expressions with SINT, INT and DINT numeric operands. These are additional forms
of existing instructions; the instruction inventory count is unchanged.

```text
CPT(Result,Base**Exponent);
CMP(Base**Exponent=Expected)OTE(Matches);
FAL(Calc,?,?,ALL,Results[Calc.POS],Inputs[Calc.POS]**2);
FSC(Find,?,?,INC,Inputs[Find.POS]**2>=Threshold);
```

## Arithmetic

Integer exponents must be in **0..31**. Narrow signed inputs promote to DINT;
each power and subsequent arithmetic node must fit a signed DINT. Calculations
stay exact, including `46340**2 = 2147395600` and `(-2)**31 = -2147483648`.
`2**31` faults even if a later division would reduce it. A narrow destination
must also hold the final result. Zero exponent produces one, including `0**0`;
this is an explicit software-model rule awaiting native qualification.

Power precedes unary negation and multiplication. Equal-order operators retain
the existing left-to-right rule: `-2**2` is -4, `(-2)**2` is 4 and `2**3**2`
is 64. Parentheses select a different grouping. Integer division, remainder,
bitwise operators, ABS/TRN and existing FRD/TOD conversions can compose with
powers. CMP/FSC Boolean operands are eager: an invalid power in either side
still faults even when the other side already determines the logical result.

Existing REAL promotion is unchanged. For example, a REAL CPT destination
selects floating arithmetic, so `2**(-1)` produces 0.5. The bounded integer
exponent rule applies to the integer path. Existing ST powers use their separate
language evaluator. Wide/LREAL expressions, negative or larger integer
exponents, array-subscript powers and other controller profiles remain outside
this added profile.

## Execution and recovery

Structural preflight checks declared types, references and permissions without
consuming saved values or dynamic indices. Prescan/false calls skip live inputs;
complete CPT/FAL writes can establish unknown destinations. Reached arithmetic
requires both operands and validates the live exponent and intermediate ranges.
Aliases, supported UDT/array cells and existing AOI input/InOut/local bindings
share these rules.

FAL/FSC retain ALL, numeric distribution and observed-edge INC behavior,
including active numeric continuation with a false gate, held/done/inhibited
skips, search resume and RES progress clearing. A fault restores the whole
modeled advance, including earlier rows/writes, CONTROL values, hidden file
progress, warm AOI bindings and scheduler/timing state. A completed prescan is a
separate lifecycle event; previously committed advances remain committed.

## Control Lab

Open Control lab and step once with PowerEnabled false. PowerResults[0..3]
remain unknown. Set PowerEnabled true and step:

- PowerBase=-3 and PowerExponent=3 produce PowerResult=-27 and PowerMatches true.
- PowerResults becomes [9,4,4,9,901]; the outside guard remains 901.
- PowerFind stops at row 0 with FD/IN set. Clear PowerFind.IN and step to find
  row 3 with DN set.

Set PowerExponent to -1 or 32 to exercise range faults; restore 3 to retry.
PowerBase=50000 with exponent 2 exercises DINT overflow. PowerLateDivisor=0
faults after earlier power/file work; restore 1. To restart the file examples,
set PowerEnabled false, pulse PowerReset true for one step, then clear it and
restore valid inputs before enabling. Reset retains arrays and LEN=4.

See [sample](../source/samples/ControlLab.L5X),
[implementation](../source/logixlab/expressions.py) and
[focused tests](../source/tests/test_ladder_integer_power.py).

The installed v35 CPT reference (14597) supplies the operator/promotion/order
baseline. Rockwell's published [CPT reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/compute-math-instructions/compute--cpt-.html)
provides context. The bounded exponent domain, checked intermediate overflow,
zero-base convention, native numerical precision, math flags, fault records,
partial effects and controller/Studio lifecycle equivalence require separate
native qualification. Software checks do not establish that acceptance.
