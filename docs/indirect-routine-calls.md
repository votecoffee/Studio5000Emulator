# Indirect routine arguments

The v35 ControlLogix 5580 L81E–L85E profile supports runtime-selected caller
elements in JSR input arguments and return destinations. Existing ladder and
ST calls share the profile. See [implementation](../source/logixlab/calls.py)
and [checks](../source/tests/test_call_references.py).

```text
XIC(Enabled)JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);
```

The corresponding SBR input and RET source remain static references. Exact
parameter counts, declared types and array dimensions still match. Each
direction permits 40 parameters; JSR/FOR share the existing 25-level nesting
limit and execution budget. Main routines, recursion and AOI call restrictions
retain their existing checks.

## Selection and copied values

Structural JSR preflight checks reference grammar, declared shapes, permissions,
literal bounds and parameter compatibility without saved live caller indices.
False ladder rungs, skipped ST calls and prescan skip live caller addresses and
values. Prescan still visits reachable routines without parameter transfers.

Each executed call resolves its current input and return-destination addresses
before input copies or subroutine execution. All input values are then captured
before SBR writes any formal input. Return values go to those captured destination
elements even if SBR or the called logic changes an indexing tag. A later call
selects its addresses again.

This call-entry address policy is an explicit software model. Native address
sampling, task interruption and fault/partial-transfer parity remain unqualified.
It is not a native controller acceptance result.

New explicit indirect arguments select one complete element, including fully
selected multidimensional elements, numeric members and logical records. Dynamic
subarray/row arguments remain blocked; static whole arrays retain their existing
exact-dimension copy behavior. BOOL, numeric and matching logical-record values
use existing parameter types and copied storage. No numeric promotion, packed
ABI or private instruction-history transfer is inferred.

Known scalar inputs are required when copied. Logical records retain represented
unknown fields instead of inventing zeros. Full return writes can establish
unknown destinations. Stored copies own independent nested data. Aliases and
program-local references retain canonical storage and scope.

## Guards and rollback

Bit/system selections, constant destinations and mismatched signatures remain
blocked. SBR/RET operands retain static-index rules. FOR has a [separate selection
profile](ladder-loops.md#runtime-selected-operands). Overlap
is checked during preflight and again at actual call entry. Structural placeholder
addresses make preflight conservative: some potentially disjoint indirect forms
remain blocked. Multiple indirect results in separate arrays are supported.

During whole-project ladder execution, an out-of-bounds array index at
call entry can [skip the JSR after a fault clear](controller-handlers.md#recover-a-jsr-argument-fault).
Uncleared faults, consumed unknown values, actual overlapping return
destinations, missing required returns and later execution failures
restore earlier transfers, data, time, scheduling and call-stack state
within the modeled advance. Completed prescan is a separate boundary. Other controller
profiles retain their static-argument behavior.

## Call lab

Choose **Call lab** and step once. IndirectCall and IndirectPairCall start false;
CallInputIndex and CallOutputIndex start at 99. Selected inputs and results are
unknown without blocking disabled calls.

Set both indices to 1, IndexedCallInputs[1]=7 and RedirectReturn=true. Enable
IndirectCall and step. DoubleSelected receives 7 and writes 14 to
IndexedCallResults[1], although its logic changes CallOutputIndex to 2 before
RET. Result index 2 remains unknown on that first call. Disable IndirectCall
before another step to hold this example, or leave it true to select index 2
on the next call. Disable RedirectReturn to stop changing the indexing tag.

For logical records, disable IndirectCall, set both indices to 1 and
IndexedPairInputs[1].A=23, then enable IndirectPairCall. EchoSelectedPair copies
the selected record: result A is 23 and omitted B stays unknown. Disable the
gate before changing the source to observe independent result storage. Bad
live indices or unknown consumed scalar inputs fault transactionally; correct
them and retry. See [CallLab.L5X](../source/samples/CallLab.L5X).

Rockwell's [JSR/SBR/RET reference](https://www.rockwellautomation.com/en-fi/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/program-control-instructions/jump-to-subroutine--jsr---subroutine--sbr---and-re.html)
describes copied parameters, matching types/dimensions and nesting limits.
The bounded indirect-reference and rollback policies above remain separate
from native Studio/controller equivalence.
