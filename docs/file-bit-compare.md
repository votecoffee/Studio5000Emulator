# Ladder file bit diagnostics

App `26.1030.082637` adds FBC and DDT to the bounded v35 ControlLogix 5580
ladder profile. Both compare DINT arrays and record the relative bit offsets
of mismatches in a DINT result array. FBC retains its reference; DDT changes
each mismatching reference bit to match the source. Uncompared bits retain
their existing values, including the rest of a partial final word.

```text
XIC(CompareEnable)FBC(Source[0],Reference[0],Results[0],CompareControl,?,?,ResultControl,?,?);
```

The two Length/Position pairs read live CONTROL members. Each pair can use
[literal initializers](control-operations.md#literal-len-and-pos-on-import)
or preserve saved values with `?`. Compare
length and position count **bits**; result length and position count **DINT
entries**. Bit zero is the least-significant bit of the selected starting word.

## Modes, edges and result lists

CompareControl.IN=false compares the remaining range on one enable edge.
IN=true searches until one mismatch is recorded or the range ends. A held
true rung retains compare EN and performs no additional comparisons. False
execution clears EN/FD and rearms the next edge. A partial comparison retains
both positions; the next edge resumes after the last recorded bit.

Compare FD indicates a mismatch found by that execution. Compare POS points
to the next bit, reaching LEN with DN=true at completion. Rung-out follows
incoming power; FD carries the match result. No mismatch still completes
the comparison and leaves existing result entries intact.

Each mismatch appends at ResultControl.POS and advances it. Reaching result
capacity sets result DN. The **next mismatch** clears that DN and restarts
at result entry zero. Comparison continues, so a short result array can wrap
within an all-mode operation. It does not stop merely because the list fills.
Unused result entries are retained rather than cleared automatically.

Prescan and false execution clear compare EN/FD. If compare DN was set, they
also clear both DN bits and reset both positions. ER, IN and unrelated CONTROL
flags retain their values. Prescan never learns reference bits or writes result
entries. A disabled MCR body follows the same false path; unlike DTR, FBC/DDT
do not refresh reference data on that false scan.

## Supported storage and failure policy

The current profile accepts [alias/indirect starts and RLL AOI arrays](bit-diagnostic-references.md).
Selected member arrays, offsets, program-local arrays and multidimensional
regions flattened within the modeled boundary remain supported outside AOIs.
AOI starts select elements of one-dimensional DINT arrays. Disjoint array members
and distinct controls may share a base tag; writable roles cannot share an array
member, even with disjoint windows. Read-only FBC input tables are allowed
outside AOIs. ST/FBD and other controller profiles remain unavailable.

Each fresh comparison resolves the source and reference starts and checks the
bounds of each reached bit. One-mismatch mode can stop before reaching a later
overrun.
The result start is selected once on the first mismatch, before DDT learning
or result writes. Each reached result position must fit within the selected
array or member. An available slot can be written even if ResultControl.LEN
exceeds the available space. The software limits are 4096 compared bits and
4096 configured result entries. Every compared bit consumes
the existing instruction budget. There is no cross-tag memory traversal.

Required unknown source/reference words or control values fault. Unvisited
words and unwritten result entries need not be known. Writes can establish
unknown result slots. Compare LEN<=0 or POS<0 sets compare ER without data
writes; a fresh valid comparison clears ER. A position at/after the configured
end completes at LEN without reading an input word.

A handler can
[clear a reached array fault](controller-handlers.md#recover-bit-diagnostic-and-data-transition-array-faults)
after the emulator restores both CONTROL records and any result or reference
writes made in the faulting call. An input overrun also sets compare ER for
the handler. A fresh valid comparison clears ER and can retry after repair.
Resource limits and unsupported cursor states use scan rollback. A full
result cursor requires DN set. Native partial-write behavior remains unqualified.

Coverage reports expose `file_bit_compare`; normal rung traces retain the two
instructions' power conditions. The profile does not imply native timing,
packed CONTROL layout or complete controller equivalence.

## Try Bit Lab

Choose **Bit lab** and step once. CompareEnable and DetectEnable start false.
CompareSource has mismatches at bits 0, 5, 31, 32 and 39. Set CompareEnable=true
and step: FBC completes in all mode. Its three-entry MismatchBits list wraps
to `[32,39,31]`; the fourth element stays 999. CompareReference stays unchanged.

DetectControl.IN starts true. Set DetectEnable=true and step: DDT records bit
0 and updates only that LearnReference bit. Toggle DetectEnable false/true
with a step after each change to find 5, 31, 32 and 39. The result list wraps
the same way. The high unselected bit of LearnReference[1] and both array guard
words remain unchanged. False after completion resets the control positions.

FaultDivisor=0 produces a late fault after the diagnostics. Correct it to 1
before retrying; offsets and learned bits then commit once. See
[BitLab.L5X](../source/samples/BitLab.L5X),
[implementation](../source/logixlab/file_bit_compare.py) and
[checks](../source/tests/test_file_bit_compare.py).

The installed v35 help and Rockwell's
[FBC](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/file-bit-comparison--fbc-.html)
and [DDT](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/diagnostic-detect--ddt-.html)
references describe the mode and control transitions. Software checks remain
separate from native controller acceptance.
