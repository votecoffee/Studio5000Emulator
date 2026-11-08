# Sequencer source types

App `26.1104.112443` qualifies SINT, INT and DINT sources for SQL and SQI in
the v35 ControlLogix 5580 software profile. Tables remain DINT arrays and SQO
destinations remain writable DINT scalars. Masks keep their existing
SINT/INT/DINT declared-width, zero-filled patterns.

```text
SQL(Table[0],SignedByte,Control,?,?);
SQI(Table[0],16#FF,SignedByte,Control,?,?);
SQL(Table[0],16#FFFF_FFFF,Control,?,?);
SQI(Table[0],16#FFFF_FFFF,16#FFFF_FFFF,Control,?,?);
```

Sequencers now use their own operand rules instead of FIFO numeric-conversion
validation. This blocks REAL and other excluded payload types during preflight,
including on false rungs. It also blocks non-DINT SQO destinations. Those forms
could previously pass validation even though they were outside the documented
sequencer profile. FIFO conversion behavior is unchanged.

SQL retains signed narrow numeric values when loading a DINT row: SINT -1
loads DINT -1, and INT -32768 loads DINT -32768. SQI retains the model's existing
signed-source masked comparison. This extension does not introduce a new SQI
source-extension policy or establish native conversion parity. Short masks
still select only their declared bits; a SINT mask -1 selects eight bits.

Sources also accept signed DINT decimal literals and complete nonnegative
32-bit binary, octal and hexadecimal patterns. SQL stores 16#FFFF_FFFF as DINT
-1 and 16#8000_0000 as DINT minimum. SQI compares the same complete patterns
through its mask. Larger decimal/radix or typed literals, floating/BOOL/wide/
unsigned payloads, whole aggregates and non-DINT tables/results remain excluded.

Structural preflight validates types, shapes, references, permissions and
immediate bounds without reading saved values or dynamic indices. False and
invalid-CONTROL paths skip live payload references. SQI zero masks skip row and
compared-source values and references after the reached row is checked. SQL
full writes establish unknown selected rows. SQO full masks establish unknown
DINT results; partial masks require preserved destination bits.

The reached row may be startup row zero or a cyclic row from 1 through LEN.
Held SQL reloads, held SQO writes and SQI comparisons use that row. Aliases,
UDT members, indirect operands and supported AOI copied inputs, InOut bindings
and local tables follow the same selection rules. Required unknowns,
bad indices and later failures restore data, flags, task progress/timing and
warm AOI state/bindings. Sources and neighboring guards remain unchanged.

Open **Sequence lab** and Step once while NarrowEnabled is false. Set
NarrowIndex=1, enable NarrowEnabled and Step again. Both control positions
become 1. The byte and word tables load -1 and -32768, their match coils are
true, and outputs become 16#123400FF and 16#56788000. The pattern table stores
-1 and NarrowPatternMatch is true. Startup rows and out-of-window guards remain.

While held true, write NarrowByteSources[1]=-2 and NarrowWordSources[1]=-1.
The current rows and outputs update without advancing: 16#123400FE and
16#5678FFFF. Disable/Step/enable/Step to advance to row 2 and observe DN. A
subsequent edge wraps to row 1. The one-row pattern sequence wraps to itself.

NarrowIndex starts at 99 while disabled. Enabling before selecting a valid input
faults and rolls back. NarrowLateDivisor=0 demonstrates a failure after earlier
teaching/comparison/output writes; restore it to 1. Disable before returning
the source index to 99. Held outputs remain while match coils clear.

This adds no ST/FBD/SFC form, native CONTROL layout, fault records, status bits
or controller/Studio acceptance claim. Native source conversion, scan ordering,
invalid-state, partial-effect and lifecycle parity remain unverified.

Source basis: installed v35 SQI (14703), SQO (14704), SQL (14706) and Data
Conversions (14451). The published
[Rockwell SQI reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/sequencer-instructions/sequencer-input--sqi-.html)
also lists narrow sources and mask zero extension. Software tests do not prove
native controller equivalence.

See [implementation](../source/logixlab/sequencer_operations.py),
[focused cases](../source/tests/test_sequencer_sources.py),
[existing sequencer behavior](sequencer-operations.md) and
[SequenceLab.L5X](../source/samples/SequenceLab.L5X).
