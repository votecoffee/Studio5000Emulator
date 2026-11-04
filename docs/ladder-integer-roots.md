# Integer square roots in ladder expressions

In the bounded v35 ControlLogix 5580 profile, SQR no longer promotes a narrow
CPT/CMP or FAL/FSC expression to REAL by itself. SINT, INT and DINT inputs use
checked DINT arithmetic; each integer SQR node returns a DINT before the next
operator executes. This corrects expressions whose result depends on the point
at which rounding occurs.

```text
CPT(Result,SQR(Source)+SQR(Source));
CMP(SQR(Source)=2)OTE(Matches);
FAL(Calc,?,?,ALL,Results[Calc.POS],SQR(Inputs[Calc.POS]) AND 16#FF);
FSC(Find,?,?,INC,SQR(Inputs[Find.POS])>=Threshold);
```

## Calculation and promotion

For an integer SQR node, the argument first uses existing checked DINT
arithmetic. The root solver consumes a finite float32 value, takes its absolute
value, computes the root, rounds the root to float32 and converts that result to
DINT using nearest-even rounding. The implementation reuses the existing
array-index SQR conversion. Negative arguments are valid: SQR(-3) is 2. The
DINT minimum produces 46341; 16777217 converts to float32 before its root and
produces 4096. Native precision and rounding equivalence remain unverified.

| Integer expression | Result |
| --- | --- |
| SQR(3)+SQR(3) | 4 |
| SQR(3)/3 | 0 |
| SQR(3)**2 | 4 |
| SQR(3) AND 1 | 0 |
| FRD(TOD(SQR(3)+10)) | 12 |

Each argument/intermediate must fit DINT, including before a root could reduce
its magnitude. SQR(50000**2) faults on the power; SQR(2147483647+1) faults on the
addition. A narrow final destination must hold its result. Existing powers,
integer division/remainder, bitwise operations and FRD/TOD compose with SQR.
CMP/FSC still evaluate both logical operands eagerly.

Existing REAL promotion remains: a REAL operand or floating literal, a
REAL-producing function, or a REAL CPT/FAL destination selects floating
arithmetic for the expression. A REAL destination for SQR(3)+SQR(3) receives
approximately 3.46410155, while an integer destination receives 4. A floating
literal in a comparison also selects REAL: SQR(3)=2 is true in this integer
profile, while SQR(3)=2.0 is false.

ST, the legacy SQRT expression alias and older controller paths retain their
existing behavior and separate qualification limits. This addition does not
qualify new mnemonic aliases, wide/LREAL expressions, other controller profiles,
math flags or native fault/partial-effect/lifecycle behavior.

## Execution and recovery

Structural preflight checks types, references, grammar and permissions without
requiring saved operands or dynamic indices. False/prescan calls skip live
inputs. Complete writes can establish unknown destinations; reached arguments
must be known and in range. Aliases, selected UDT/array cells and existing AOI
copied inputs, InOut arrays and local state use the same conversions.

FAL/FSC retain their ALL/numeric/INC distribution, active numeric false
continuation, held/done/inhibited skips, search resume and RES progress rules.
A failed advance restores earlier scalar/array writes, CONTROL values, hidden
file progress, warm AOI bindings and scheduler/timing state. Completed prescan
and prior successful advances remain separate committed events.

## Control Lab

Open Control lab and step once with RootEnabled false. RootResults[0..3]
remain unknown. Enable RootEnabled and step:

- RootInput=3 gives RootResult=4, RootRealResult approximately 3.46410155 and
  RootMatches true against RootExpected=4.
- RootResults becomes [1,2,2,3,902]; the outside guard remains 902.
- RootFind stops at row 1 with FD/IN. Clear RootFind.IN and step to find row 2;
  clear it again and step to row 3 with DN.

RootRangeFault enables an overflowing argument addition; clear it to recover.
RootLateDivisor=0 faults after earlier root/file work; restore 1. Changing
RootInput to 7 while the late fault is active demonstrates retention of the
previous result; a successful retry then gives RootResult=6 and RootMatches
false until RootExpected is updated. To reset files, disable RootEnabled,
pulse RootReset true for one step, then clear it; data and LEN=4 are retained.

See [sample](../source/samples/ControlLab.L5X),
[implementation](../source/logixlab/expressions.py) and
[focused tests](../source/tests/test_ladder_integer_roots.py).
The installed v35 CPT (14597), CMP (14592) and SQR/SQRT (14617) help supplies the
promotion/operator baseline. Rockwell's published [CMP reference](https://www.rockwellautomation.com/en-ua/docs/factorytalk-design-studio/current/contents-ditamap/instructions/instruction-set/compare-instructions/compare--cmp-.html)
provides context; the installed v35 spellings govern this profile. Software
checks do not establish native controller or Studio acceptance.
