# Array statistics references and AOIs

The bounded v35 ControlLogix 5580 ladder AVE/STD profile accepts alias chains
and indirect fully subscripted SINT/INT/DINT/REAL arrays. RLL AOIs can use exact
one-, two- or three-dimensional InOut arrays and represented saved local arrays,
with writable SINT/INT/DINT/REAL AVE results and REAL STD results in disjoint
sibling members. Results cannot overwrite the operation's own CONTROL record. [Calculation and
CONTROL transitions](array-statistics.md) remain unchanged.

```text
AVE(Samples[StartIndex],0,Mean,MeanState,?,?);
STD(Samples[StartIndex],0,Deviation,DeviationState,?,?);
AVE(Grid[0,Column],0,ColumnMean,ColumnState,?,?);
```

## Source selection and latches

Preflight checks shape, source/destination types, permissions, dimension and
index expression structure without consuming dynamic source indices. A fresh
true operation with EN/DN/ER clear and POS zero consumes the current indices
and completes LEN samples along the selected dimension. Other indices stay
fixed; arrays are not flattened across rows. Alias suffixes retain the caller
namespace, while AliasFor-authored indices retain the declaration namespace.

False instructions and true instructions inhibited by EN, DN or ER skip live
source indices and values. Thus changing a start index while completed does
not recalculate the result; rearm before selecting another window. A
[reached array subscript fault](controller-handlers.md#recover-sort-and-statistics-array-faults)
can be cleared by a handler in a whole-project ladder scan. Unknown source
values fault when consumed. Limits and lengths are
checked before live source reads; the maximum remains 4096 samples, and the
complete region must fit the selected dimension/member. No adjacent member
or row is included to satisfy an oversized request.

CONTROL.POS-dependent starting subscripts are rejected, including alias,
nested-expression and AOI references. The instruction owns its offset; authors
must avoid adding it again. This is an explicit bounded reference guard, shared
with sequencers. Destination/source overlap is checked again using the actual
fresh source selection, including dynamic parents and aliased results.

## AOI state and qualification

Each InOut binding and saved local resolves to canonical storage. Separate
instances, nested AOIs and indirect InOut rebinding retain their own values
and CONTROL records. Failed advances restore external/local results, controls,
frames, binding caches, instance metadata, trace, time and task state together.
Constant source arrays are legal outside AOIs; existing InOut binding rules
require writable actuals even for read-only instruction uses.

Prescan retains POS and saved data while applying the existing AVE/STD flag
rules. A completed operation followed by Run therefore needs explicit CONTROL
reset/reinitialization before this complete-operation profile can run again.
An authored EnableInFalse routine may false-call AVE/STD to rearm completed
records. Without it, skipped bodies retain latches. Required copied AOI inputs
are still consumed before either body path; unknown copied inputs can fault
even if the statistics operation itself would skip a source index. Missing
saved locals remain unknown; definition defaults do not fill them.

The separate [SRT reference profile](sort-references.md) now qualifies aliases,
indirect starts and AOI arrays with its own transition and FOR-effect rules.

Partial POS/resume, wider source/result types, additional
languages and broader AOI/native lifecycle, precision, status, faults and packed
layouts remain unfinished. These are software-model checks, not native import
or controller qualification.

## Try the AOI statistics lab

Load **AOI statistics lab** and set Calculate true. DriverA's Mean/Deviation
are 4/2; its ColumnMean/RowMean/PlaneMean are 7/10/7. DriverB's Mean/Deviation
are 20/10 and its three axis means are 19/14/20. The saved local means are 4/6,
with local sample deviations 2/2. SampleView aliases SamplesA.

Leave Calculate true and change IndexA to 2: results stay latched. Set Calculate
false and step, then true and step: DriverA's Mean and LocalMean become 6.
Disable EnabledA to run its authored false routine without rearming instance B.
FaultDivisor zero exercises whole-advance rollback. Guard values outside each
selected sample region remain intact.

Reference basis: installed v35 help 14507, 14501/14536, 14492 and 3232.
Published [AVE guidance](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/array-file-misc-instructions/file-average-ave.html)
also describes selecting a dimension and keeping CONTROL.POS out of the
starting subscript; newer-release type availability is not imported into this
bounded v35 profile.

Indirect result selection is documented in [Statistics operands](statistics-operands.md).
The source-start rules above remain; false or EN/DN/ER-inhibited calls now also
skip live result indices. Actual CONTROL/prescan and state reads remain.
