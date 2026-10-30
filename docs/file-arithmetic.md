# File arithmetic and logic

The explicit v35 ControlLogix 5580 ladder profile supports:

```text
FAL(Control,?,?,ALL,Dest[Control.POS],Source[Control.POS]*Gain+Bias);
FAL(Control,?,?,2,Dest[Control.POS],Source[Control.POS]);
FAL(Control,?,?,ALL,Sum,Sum+Source[Control.POS]);
```

LEN/POS use saved CONTROL members. Neutral-text pseudo-operands do not replace
them on each scan. ALL processes the remaining positions in one call. A positive
DINT immediate selects the number of iterations per scan in numeric mode. LEN
is bounded to 4096 and each iteration also consumes the global instruction budget.
See [implementation](../source/logixlab/file_arithmetic.py).

## Scan state

Prescan has no initialization. The bounded software profile starts at saved POS
when EN is clear and resumes after the last computed position when EN is set.
DN latches when the last position is computed. Held true with DN set retains
the destination. A false call after completion clears EN/DN/POS. ER inhibits
both execution and false-rung cleanup; RES can clear it. IN/FD/EU/EM/UL are not
used or changed by FAL.

After starting, numeric mode continues its per-scan iterations even when rung
input is false. Completion with false input clears EN immediately and retains
DN/POS until the next false call. An incomplete false ALL call clears EN without
computing. Rung output always follows incoming power, independently of DN.
Zero LEN and an initial POS equal to LEN complete without evaluating data.

The software profile retains the last computed POS on completion. Installed
v35 prose and flowcharts present the final cursor differently; native final-POS
parity remains unverified. Negative/excessive LEN/POS and invalid reads/writes
fail explicitly, with whole-advance rollback. Native fault records, ER overflow
classification and partial writes are not implemented by this profile.

## Expressions and destinations

FAL reuses the bounded CPT grammar and SINT/INT/DINT/REAL scalar types. Integer
arithmetic uses DINT intermediate values; REAL expressions use float32 rounding.
Integer-only division/power, BCD expression functions, wider/unsigned/LREAL and
the full native conversion/status matrix remain unfinished. The existing
arithmetic, bitwise operators and supported math functions are available.

Destination references resolve for each current POS, including numeric UDT
members and multidimensional arrays. Scalar destinations can accumulate or be
overwritten by successive iterations. Reads and writes occur in sequence:
overlapping source/destination arrays can propagate a value through later
positions. There is no operation-wide source snapshot.

Type validation uses structural subscripts and restores the memory mode even
when validation fails. Actual data reads are deferred until execution. An
unknown destination can be overwritten; an unknown required source fails.
Constants remain read-only. Control/destination aliases are supported; a
destination overlapping its own CONTROL record is rejected on each iteration.
Array accesses remain within the selected member/dimension.

INC mode, execution inside AOIs, and ST/FBD FAL calls are explicitly blocked.
No private native edge state or target-specific fault behavior is fabricated.

## Stats Lab

Select Stats lab, set Transform and BatchTransform on, and step once.
MappedValues becomes [5,9,13,17,999]. BatchValues becomes [5,9,0,0,999]: numeric
mode has processed two positions. Set BatchTransform off and step again; the
active operation still finishes as [5,9,13,17,999]. Its next false scan clears
DN/POS. Transform stays done until it is set off and scanned.

Both examples use Values*Gain+Bias with Gain=2 and Bias=1. The fifth element is
outside LEN=4 and remains unchanged. Reset clears control state and retains
lengths and array data. See [StatsLab.L5X](../source/samples/StatsLab.L5X).

The baseline is installed v35 help 14504 and its true/false/ALL/numeric/INC
flowcharts. Rockwell's published [FAL reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/array-file-misc-instructions/file-arithmetic_logic-fal.html)
provides context. Software tests do not establish native controller or Studio
acceptance.
