# Incremental file operations

App `26.1029.222513` adds ladder FAL/FSC INC mode to the explicit v35
ControlLogix 5580 software profile. Existing operand and expression limits
remain in [FAL](file-arithmetic.md) and [FSC](file-search.md).

```text
XIC(StepTransform)FAL(TransformControl,?,?,INC,Output[TransformControl.POS],Input[TransformControl.POS]*Gain);
XIC(StepSearch)FSC(SearchControl,?,?,INC,Input[SearchControl.POS]>=Limit);
```

Use separate CONTROL records for the two operations. LEN/POS still use saved
members and neutral-text `?,?` pseudo-operands.

## Mode comparison

| Mode | First enabled call | Further held-true calls | False incomplete call |
| --- | --- | --- | --- |
| ALL | Remaining elements | Holds once done or inhibited | Clears EN |
| Numeric 1 | One element | Another element per call | Active work continues |
| INC | One element | Holds the current element | Clears EN and rearms an edge |

The table assumes no ER/IN inhibit.

INC begins at POS zero. Each later observed enable edge advances to the next
element. POS retains the last processed index. The last element sets DN; a
false completed call clears EN/DN/POS and internal progress. A skipped routine
call does not observe a false input and cannot rearm an edge. Rung output
continues to follow input power.

FSC sets FD/IN on a match. IN inhibits both true and false calls until cleared,
so clearing IN while EN is still true does not create a new enable edge. Clear
IN and scan a false input before the next true input. At a final match, clear
IN to allow false completed cleanup; FD retains its result. ER inhibits both
operations. Zero LEN completes without reading expression data.

## Initial state and lifecycle

This bounded profile requires an idle CONTROL in the source: POS zero and all
public flags false. Saved active/nonzero records are rejected, even on a false
rung. The exported public fields cannot reconstruct native hidden progress.
ALL/numeric modes retain their existing saved-state profiles.

The simulator keeps INC progress separately from public CONTROL flags, keyed
by the resolved CONTROL identity. Aliases share progress; selected array/member
controls have their own identities. RES clears progress and public flags/POS,
retaining LEN and array values. Run entry/prescan retain INC progress, as the
instructions have no prescan initialization. Routine replacement copies it
into the detached candidate without changing the active engine.

New iterations, completion/cleanup and RES share the whole advance's transaction.
An expression, budget or later task failure restores progress alongside values,
timers, first scans and scheduler state. A retry cannot silently skip an element.
Each processed element consumes the global instruction budget, and LEN remains
bounded to 4096. Required values must be known when consumed.

## Stats Lab

Choose **Stats lab**, set StepTransform and StepSearch true, and step twice.
Only StepValues[0] becomes 5; both CONTROL positions remain zero on the held-true
step. Set both flags false and step, then true and step: StepValues[1] becomes 9
and both positions become 1. Repeat for position 2; the search finds Values[2]=6
against SearchLimit=5 and sets FD/IN. Clear StepSearchControl.IN and scan the
false inputs before the next pulse. The fourth pulse fills StepValues[3]=17
and completes both operations. The fifth element remains the guard value 999.

Set the step flags false before using Reset. Reset clears the two controls and
their progress, preserving LEN and the arrays. See
[StatsLab.L5X](../source/samples/StatsLab.L5X) and
[shared INC implementation](../source/logixlab/file_incremental.py).

## Qualification limits

Native hidden-bit encoding, restoration from a saved active snapshot, copying
hidden progress through aggregate transfers, mixed consumers of one CONTROL,
final-cursor parity, native status/fault records and partial-write behavior
remain unqualified. AOI execution, ST/FBD instruction calls and additional
types/expressions remain unfinished. These are software-model checks; native
controller and Studio acceptance are separate.

The baseline is installed v35 help 14504/14515/14521/14523 and the INC/true/false
flowcharts. Rockwell's published
[FAL reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/array-file-misc-instructions/file-arithmetic_logic-fal.html)
and [FSC reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-search-and-compare-fsc.html)
provide context for modes and enable edges.
