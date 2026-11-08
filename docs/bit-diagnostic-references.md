# FBC/DDT references and AOIs

The bounded v35 ControlLogix 5580 ladder profile supports alias chains and
indirect DINT starts for FBC/DDT. RLL AOI bodies can use exact one-dimensional
InOut arrays and represented saved local arrays, with selected element starts.
[Bit offsets, modes, list wrapping and CONTROL transitions](file-bit-compare.md)
remain unchanged. ST/FBD forms and broader AOI shapes remain unqualified.

```text
FBC(Source[InputStart],Reference[ReferenceStart],Results[ResultStart],Compare,?,?,List,?,?);
```

## Storage roles

Disjoint logical array members and CONTROL records may share a base tag,
including a saved AOI instance. The two controls must resolve to distinct
storage, disjoint from data arrays. Results cannot share an array member with
source or reference; DDT source and writable reference also require distinct
array members. Different windows within the same array remain excluded for
these writable roles. FBC may read the same source/reference storage.

These checks follow canonical aliases/bindings. Structural overlap checks are
conservative; ambiguous dynamic parents may remain blocked. Actual source and
reference roles are checked again when a fresh comparison selects them, and
actual result overlap is checked before the first write. Read-only input arrays
are legal outside AOIs; existing InOut bindings require writable actuals even
for FBC read-only use. CONTROL.POS-dependent starts are rejected in every role.

## When addresses are sampled

Preflight checks data array structure, type and permissions without consuming
their dynamic starts. It checks live CONTROL addresses when available. A saved
out-of-bounds indirect CONTROL index can load after the declared writable
record and the other operands pass validation. Constant out-of-bounds CONTROL
subscripts are rejected during load.
[Prescan skips the unresolved selection](controller-handlers.md#skip-out-of-bounds-control-records-during-prescan)
and checks for distinct storage whenever both records are available.
False, held-EN, saved-done and invalid compare-state paths skip live data
array indices. Normal execution still selects both CONTROL records. A fresh
comparison selects the source and reference starts once and checks each
reached bit against the available words. Unvisited words are not read.
The limits remain 4096 compared bits and 4096 result entries.

The result start is selected lazily on the first mismatch, after validating
result LEN and POS and before DDT learning or result writes. An invalid
length or negative position sets compare ER without consuming the result
start. A valid selection stays fixed for that invocation, including list wraps.
The reached result slot must fit within the selected array or member. This prevents an index derived from learned reference
bits or result data from moving storage midway through the operation. With no
mismatch, live result indices/cursor values are not consumed. A later enable
edge selects new windows; retained compare/result positions apply relative to
those new starts. Authors must account for that when changing windows mid-search.

This address-sampling rule is an explicit simulator choice. Exact native
evaluation timing, partial effects, status and fault behavior remain unqualified.
A handler can
[clear a reached subscript, input or result-slot fault](controller-handlers.md#recover-bit-diagnostic-and-data-transition-array-faults)
during a whole-project scan. Unknown consumed indices or data, a full result
position without DN, limits, budget exhaustion and uncleared faults roll back the
entire modeled advance.

## AOI state

Separate and nested instances use canonical storage. Indirect InOut rebinding
and failed calls restore frame bindings, resolved caches and instance metadata
with local/external arrays, both controls, trace, time and task state. Missing
saved locals remain unknown; definition defaults do not establish their values.

Prescan and authored false calls apply the existing control rules. Partial
one-mismatch progress survives false calls; completed comparisons reset both
positions/done flags. An enabled EnableInFalse routine can false-call FBC/DDT;
without it, skipped bodies retain state. Required copied AOI inputs are still
consumed before either body path, so unknown copied indices can fault even
when the instruction itself would skip an array. These inputs are separate
from the instruction's lazy array-address sampling.

## Try the AOI bit diagnostics lab

Load **AOI bit diagnostics lab**. Enable CompareEnable and DetectEnable. Instance
A's FBC list wraps to `[32,39,31]` in CompareResultsA[1..3]. Instance B records
`[1,3,33]` in CompareResultsB[2..4]. References remain unchanged by FBC.

DDT learns one mismatch per edge: LearnedA[1] and DriverA.Scratch[1] first become
1, while instance B learns 2. Toggle DetectEnable false/true, stepping after
each change, to advance. High uncompared bits and guards remain intact. Disable
EnabledA to invoke only its authored false routine. FaultDivisor zero exercises
rollback of results, local/external learning and cursor updates together.

Reference basis: installed v35 help 14718/14722 and 3232, plus published
[FBC](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/file-bit-comparison--fbc-.html)
and [DDT](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/diagnostic-detect--ddt-.html)
guidance. Logical shared-member storage and per-call sampling do not establish
native packed layout, controller execution or Studio acceptance.
