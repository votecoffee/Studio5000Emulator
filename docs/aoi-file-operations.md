# Ladder AOI file operations

App `26.1102.085455` adds `FAL` and `FSC` inside supported RLL AOIs for the
Standard v35 ControlLogix 5580 profile. ALL, positive immediate numeric and
INC from idle or [completed source controls](file-incremental.md#initial-state-and-lifecycle) uses the same bounded algorithms and expressions as
ordinary ladder routines.

```text
XIC(Transform)FAL(Calc,?,?,INC,Output[Calc.POS],Input[Calc.POS]*Gain+Bias);
XIC(Search)FSC(Find,?,?,INC,Input[Find.POS]>=Threshold);
```

## Operands and progress

Use separate writable CONTROL records for each operation. Saved LEN/POS fields
drive execution; neutral-text `?,?` operands do not initialize them per scan.
FAL supports narrow numeric, [matching wide integer](integer-files.md) and
[binary64](file-arithmetic.md#binary64-expressions) expressions, with the same
destination rules as an ordinary FAL call. FSC uses the bounded CMP profiles,
including [binary64 comparisons](file-search.md#binary64-searches), with eager
operand checks.

AOI operands can be exact-type/dimension InOut bindings or represented saved
locals. Array expressions resolve indices in the AOI frame, including
`Calc.POS`, nested AOIs and selected InOut banks. Covered forms include
one-dimensional local arrays and exact-shaped multidimensional InOut arrays.
Array/member bounds, constant protection, destination/CONTROL overlap checks,
the 4096-element limit and global instruction budget remain active.

INC progress belongs to resolved CONTROL storage. Two instances with separate
controls remain independent. Aliases of one CONTROL share progress. Rebinding
an InOut parameter to another CONTROL selects that record's progress; it does
not relocate prior state. Local controls continue to belong to their instance.

The existing source restriction remains: INC requires saved POS zero and all
public CONTROL flags false. An active, nonzero or unknown saved record cannot
reconstruct hidden native progress. Definition DefaultData does not establish
omitted local state. ALL and numeric modes retain their earlier saved-state rules.

## Modes and AOI lifecycle

| Mode | Enabled execution | False execution while incomplete |
| --- | --- | --- |
| ALL | Remaining iterations/comparisons in one call | Clears EN when allowed by flags |
| Numeric | Up to the configured count per call | Active work continues |
| INC | One element per observed enable edge | Clears EN and rearms an edge when not inhibited |

The table assumes the existing ER/IN/DN rules allow execution. A skipped AOI
without EnableInFalse suspends its body and retains latches/progress. An authored
EnableInFalse routine can call these instructions with false power: active
numeric work can continue, while partial INC work rearms. False power therefore
does not universally cancel a file operation.

FSC sets FD/IN on a match. IN inhibits both true and false calls until cleared.
For INC, clearing IN while EN is still true does not create a new edge: observe
a false call before the next true call. Final completion sets DN; the existing
false-completion cleanup and FD retention rules remain. Examine FD/IN/POS to act
on a match; FSC rung output follows input power.

Prescan does not initialize file state. Run reentry preserves simulated INC
progress. RES clears that record's flags/POS and progress, retaining LEN and
array values. Required unknown values are consumed only by reached expressions;
guard elements outside the configured indices remain untouched.

Expression, bounds, budget or later task failures roll back the whole advance:
earlier iterations and instances, parameters, external/local arrays, CONTROL
fields, hidden progress, bindings, time, trace and scheduling. Earlier successful
advances remain committed. Correcting an input permits retry of the pending edge.
This transactional policy is separate from native partial effects and fault records.

## AOI File Lab

Choose **AOI file lab** or load [AOIFileLab.L5X](../source/samples/AOIFileLab.L5X).
The synthetic fixture has 24 roots, two instances, four main rungs and nine
AOI Logic/EnableInFalse rungs. All routines are ladder; the bundled mode is INC.

Set Transform and Search true, then step. Holding true does not advance INC.
Set both false and step before the next true step. Four transform pulses produce:

| Value | Driver A | Driver B |
| --- | --- | --- |
| Output elements 0..3 | 5, 9, 13, 17 | 2, 8, 14, 20 |
| Local Scratch elements 0..3 | 3, 5, 7, 9 | 0, 2, 4, 6 |
| Total from Scratch | 24 | 12 |
| First search result | index 2, value 6 >= 5 | no match against threshold 8 |

Clear FindA.IN and observe a false Search call before resuming INC to index 3.
EnabledA/B gate whole AOIs; their explicit false routines invoke false file calls.
Pulse Reset with Transform/Search false to clear controls and progress. Arrays
remain; Total is recomputed from Scratch. FaultDivisor zero demonstrates rollback
after file work, and one permits retry. Input[4], Output[4] and each Scratch[4]
are guards outside the default LEN of four.

## Remaining qualification

Focused model and HTTP checks cover all modes, independent/nested instances,
dynamic bank rebinding and rollback, multidimensional InOut rows, scalar types,
match inhibition, RES, Run entry, omitted locals, Event/Periodic/routine execution
and late faults. They do not establish native Studio instruction acceptance.

Saved active INC snapshots, mixed consumers of one CONTROL, additional expression
types/functions/conversions, broader AOI schema/lifecycle contracts and native
cursor/status/fault/partial-effect/layout parity remain unfinished. This increment
adds no ST, FBD or SFC instruction forms; language priority remains ladder, ST,
FBD, then SFC.

Installed v35 FAL/FSC and mode help was reviewed. Rockwell's
[FAL reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-arithmetic_logic-fal.html)
and [General Instructions manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
provide context. Later references do not extend this bounded v35 profile.
