# Statistics operand selection

The v35 ControlLogix 5580 L81E–L85E ladder AVE/STD profile structurally checks
result references without consuming saved dynamic result indices. Declared
types, scalar shapes, permissions, literal bounds and source/CONTROL overlap
restrictions remain checked. See [implementation](../source/logixlab/array_statistics.py)
and [checks](../source/tests/test_statistics_operands.py).

```text
XIC(Calculate)AVE(Samples[SourceIndex],0,Means[ResultIndex],MeanState,?,?);
XIC(Calculate)STD(Samples[SourceIndex],0,Deviations[ResultIndex],DeviationState,?,?);
```

This extends [source-reference selection](statistics-references.md) to result
addresses. AVE retains SINT/INT/DINT/REAL results; STD retains REAL results.
No new types, calculation algorithms, instruction names or language forms are
added. Other controller profiles remain outside this statistics execution profile.

## Result selection and state

False calls and EN/DN/ER-inhibited calculations skip live result indices and
result values. A latched operation retains its previous result even if an
indirect result index changes to an invalid or unknown value. Existing false
transitions rearm the operation; the next fresh calculation uses its current
source and destination addresses.

A fresh calculation checks the actual selected source region and writable
result before reading samples. Full scalar writes establish unknown result
elements while preserving sibling elements. Known required samples, selected
dimension bounds, length/position rules, finite float32 arithmetic and existing
integer nearest-even/range conversion still apply.

Aliases, program-local results and supported AOI local/InOut references retain
canonical storage and frame scope. Destinations cannot overlap the selected
source array or their own CONTROL record. Constants cannot be destinations.

Actual CONTROL addresses remain required during prescan and runtime. AVE keeps
its existing ER-history read during prescan, and both instructions retain their
runtime flag and LEN/POS requirements. These changes do not make every false
CONTROL index or state field dormant. [CONTROL transitions](array-statistics.md#control-transitions)
retain their distinct AVE and STD behavior.

Unknown consumed samples, invalid addresses/regions, result range failures or
later faults restore result values, flags, time, scheduling and AOI bindings
within the modeled advance. Completed prescan is a separate lifecycle boundary.
Partial POS/resume, native precision/flags, packed layout, partial fault effects
and full controller parity remain unqualified.

## Stats lab

Choose **Stats lab** and step once. The called **StatisticsIndexed** routine
has three gated calculations, with source/result indices initially 99 and
selected samples and outputs unknown. Disabled examples leave these dormant.

Set StatisticsSourceIndex=1, StatisticsResultIndex=1 and
SelectedSamples[1..3]=2,4,6. Enable IndexedStatistics and step:

| Result | Value |
| --- | --- |
| IndexedMeans[1] | REAL 4.0 |
| IndexedDeviations[1] | REAL sample deviation 2.0 |
| IndexedIntegerMeans[1] | DINT 4 |

While enabled, change the source/result indices to 99 and step again. Completed
controls retain the results. Disable IndexedStatistics and step to rearm, then
restore the indices before enabling again. To select a different output, set
StatisticsResultIndex=2 and SelectedSamples[1]=8: the fresh result is mean 6.0,
deviation 2.0 and integer mean 6, with the previous result at index 1 retained.
Source guards SelectedSamples[0]=111 and SelectedSamples[4]=999 remain unchanged.

An unknown consumed sample or invalid live index faults transactionally; correct
the input and retry. Setting IndexedDeviationControl.LEN=1 after rearming also
demonstrates rollback of an earlier mean write when STD requires two samples.
Restore LEN=3 to recover. See [StatsLab.L5X](../source/samples/StatsLab.L5X).

Rockwell's [AVE reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-average-ave.html)
describes averaging selected array values and CONTROL state. Structural unknown
handling, lazy result selection and transactional boundaries here are explicit
software policies, not native Studio/controller acceptance. Newer documented
types do not expand this v35 profile.
