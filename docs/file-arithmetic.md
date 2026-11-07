# File arithmetic and logic

The explicit v35 ControlLogix 5580 ladder profile supports:

```text
FAL(Control,?,?,ALL,Dest[Control.POS],Source[Control.POS]*Gain+Bias);
FAL(Control,?,?,2,Dest[Control.POS],Source[Control.POS]);
FAL(Control,?,?,ALL,Sum,Sum+Source[Control.POS]);
```

Scans use live CONTROL.LEN/POS, which can receive
[literal initializers](control-operations.md#literal-len-and-pos-on-import).
ALL processes the remaining positions in one call. A positive
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
parity remains unverified. A handler can
[clear a reached array subscript fault](controller-handlers.md#recover-file-arithmetic-and-search-array-faults)
in a whole-project scan after the emulator restores the CONTROL and every
destination from the current call. A reached negative LEN or POS can be
[cleared as Type 4 Code 21](controller-handlers.md#recover-a-negative-file-cursor).
Unrecovered faults, other cursor errors and arithmetic errors roll back
the advance. Native fault records, ER overflow classification and native
partial effects remain unqualified.

## Expressions and destinations

FAL reuses the bounded CPT grammar and SINT/INT/DINT/REAL scalar types. Integer
arithmetic uses DINT intermediate values; REAL expressions use float32 rounding.
Integer division now follows the [narrow expression profile](integer-expressions.md).
[Matching LINT/unsigned expressions](integer-files.md) now use a separate exact
integer profile. Narrow [power and BCD expression forms](integer-expressions.md)
have separate bounds. [Binary64 expressions](#binary64-expressions) extend the
numeric profile below. Native conversion and status behavior remain open.

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

[INC mode](file-incremental.md) now supports one iteration per enable edge for
idle-source controls, with separate transactional progress and RES integration.
Saved active INC controls and ST/FBD FAL calls remain blocked.
[RLL AOI execution](aoi-file-operations.md) now supports exact InOut and
represented local operands with the same bounded expressions and modes.
No private native edge state or target-specific fault behavior is fabricated.

## Binary64 expressions

App `26.1105.172023` adds LREAL to ladder FAL in ALL, positive numeric
and idle-source INC modes. An LREAL destination, LREAL source tag or floating
L/l literal selects the [binary64 evaluator](lreal-expressions.md) for every
numeric node. REAL tags and unsuffixed floating literals keep their float32
precision before promotion. Typed L/U/UL integer constants are range-checked
before conversion, and large integers can round during binary64 conversion.

Each completed iteration converts its result once to the destination type.
All eight integer types, REAL and LREAL are supported. Integer results round
to nearest with ties to even and must fit the destination. Finite binary64
arithmetic, mixed numeric operands and the existing functions use the same
limits as CPT. Numeric bitwise operators and FRD/TOD remain outside the LREAL
profile. Existing integer-only and REAL FAL calculations retain their rules.

Each iteration resolves its live operands at CONTROL.POS. Later iterations
can see earlier writes to overlapping arrays. False or held calls that do no
work skip the expression, while an active numeric call still continues on a
false rung. Required unknowns, invalid references, range errors and later
faults roll back that advance, including written cells, CONTROL progress and
existing AOI bindings. Prior successful scans stay committed.

In **Stats lab**, enable `Binary64Transform` to write the first three
`Binary64Mapped` cells to 2^-52, 1.5 and 2.5. Set `Binary64Divisors[1]` to 0
before enabling to fault on the second element and restore the first write.
Restore the divisor to 1 and retry. Enable `Binary64Batch` for one REAL result
per scan (1.5, 3.0, 4.0), including continuation after a false rung. Pulse
`Binary64Step` three times with false scans between edges for DINT results
1, 2 and 4. The three guard cells stay at 901, 902 and 903.

See [binary64 FSC](file-search.md#binary64-searches) for searches using the
same numeric precision. Native fault, cursor and Studio import behavior
remain unqualified for these file expressions.

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

[BCD file expressions](file-bcd.md) now qualify FRD/TOD in narrow FAL/FSC
operands for existing ALL/numeric/INC modes. Conversion and progress/rollback
rules are explicit; wider types, ST and native parity remain separate.
