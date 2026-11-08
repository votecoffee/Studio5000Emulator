# Controller fault handlers

## Recover a ladder MOV array fault

An ordinary v35 ControlLogix 5580 Program can assign a separate ladder
routine with Program `FaultRoutineName`. In whole-project execution,
an out-of-bounds integer subscript in a ladder MOV triggers the assigned
routine with Type 4 Code 20. The fault routine runs in that Program's
scope, so `GSV(Program,THIS,MajorFaultRecord,...)` reads the active
record. The flat and structured operands described below apply.

With an 11-word DINT buffer, these rungs capture and selectively clear
this fault. The packed Type and Code are in word 2.

```text
GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);
EQU(FaultWords[2],1310724)CLR(FaultWords[2])SSV(Program,THIS,MajorFaultRecord,FaultWords[0]);
```

A successful clear skips the faulting MOV and continues at the next
instruction with the incoming rung power. The handler's writes and the
clear commit with the scan. A missing clear or a later execution error
rolls back the scan and preserves the preceding successful clear.
The browser displays the last successful recovery and the trace marks
the skipped MOV.

The bounded profile runs the assigned ladder routine during whole-project
scans and keeps it out of prescan, normal routine calls and the isolated
harness. Other instruction faults, Program fault subroutines and native
fault history remain open.
[Rockwell Major, Minor, and I/O Faults manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)

## Recover COP and CPS array faults

During whole-project ladder execution, an out-of-bounds array operand in
COP or CPS triggers the same Type 4 Code 20 handler path. A successful
clear skips the copy and continues at the next instruction with the
incoming rung power. The destination keeps its prior values even when the
handler corrects the index. A subsequent scan uses the corrected index.

This applies to supported numeric byte copies and matching aggregate
copies. Valid starts still use the existing clipping rules. An invalid
length or another copy error outside the modeled array fault follows the
usual scan rollback. The browser names the skipped instruction.

[Rockwell fault recovery reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/controller-properties/major-fault-state.html)

## Recover a JSR argument fault

During whole-project ladder execution, an out-of-bounds array index
in a JSR input or return destination triggers Type 4 Code 20 during
argument selection. If a fault handler clears the record, the caller
continues at the next instruction with its incoming rung power. The
callee is skipped and the call performs no input or return transfers.
A later call uses the current indices.

An array fault after entering the subroutine belongs to the instruction
that raised it. For example, a recoverable MOV in the subroutine skips
that MOV and continues inside the subroutine. This profile covers ladder
JSR argument selection. ST calls retain their existing rollback behavior.

[Rockwell JSR fault recovery example](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/controller-properties/major-fault-state.html)

## Recover a ladder arithmetic array fault

During whole-project ladder execution, ADD, SUB, MUL, DIV, MOD, NEG,
ABS and CPT can raise Type 4 Code 20 for an out-of-bounds source or
destination array subscript. If either fault handler clears the record,
the instruction skips its destination write. The rung continues at the
next instruction with the incoming power. A subsequent scan uses the
current subscript.

The calculation and result conversion still use the existing arithmetic
rules. Zero divisors, arithmetic overflow and other errors outside
the modeled array fault follow the usual scan rollback.

[Rockwell array subscript reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html)

## Recover a ladder bitwise array fault

During whole-project ladder execution, an out-of-bounds array subscript
in AND, OR, XOR, NOT, MVM or BTD can raise Type 4 Code 20. If a fault
handler clears it, the instruction skips its destination write and the
rung resumes with the incoming power. This includes an indexed MVM mask
and a destination selected for a partial masked or bit-field write.

A later scan uses the current subscript and the existing instruction
rules for operand widths, masks and untouched bits. Unknown operand
values and other errors outside the modeled array fault follow the usual
scan rollback.

[Rockwell move and logical instructions](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/move-logical-instructions.html)
[Rockwell array subscript reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html)

## Recover FLL, CLR and SWPB array faults

During whole-project ladder execution, a reached out-of-bounds array
subscript in FLL, CLR or SWPB can raise Type 4 Code 20. If either fault
handler clears it, the instruction skips its writes and the rung
continues. The next visit resolves the current array addresses.

FLL resolves the length and destination window before writing numeric
elements or aggregate records. A zero-length fill still checks the
destination and skips the source. A valid oversized length within the
emulator's limits still clips at the modeled logical array boundary.
Invalid lengths and errors outside the modeled array fault use scan
rollback.

[Rockwell FLL reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-fill-fll.html)
[Rockwell CLR reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/move-logical-instructions/clear--clr-.html)
[Rockwell SWPB reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/move-logical-instructions/swap-byte--swpb-.html)

## Recover contact, coil, ONS and comparison array faults

During whole-project ladder scans, a reached out-of-bounds array
subscript in XIC, XIO, OTE, OTL, OTU, ONS, EQU, NEQ, LES, LEQ, GRT, GEQ,
LIM, MEQ or CMP can raise Type 4 Code 20. If either handler clears it,
the emulator skips the instruction and passes its incoming rung power
to the next instruction. A faulting coil or ONS leaves the targeted bit
unchanged, including when the bit is part of an integer. The next visit
evaluates the instruction with the current array indices.

XIC, XIO, OTL, OTU and the comparisons skip their array operands when
incoming power is false. OTE and ONS still select their destination
when false. For example, if the handler repairs an invalid OTE subscript
on a false rung, the next visit can clear the selected bit.

[Rockwell array subscript reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html)
[Rockwell OTE reference](https://www.rockwellautomation.com/en-pr/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/bit-instructions1/output-energize--ote-11.html)
[Rockwell major fault recovery reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/controller-properties/major-fault-state.html)

## Recover OSR and OSF array faults

During a whole-project ladder scan, an out-of-bounds storage or pulse
output subscript in OSR or OSF can raise Type 4 Code 20. If the pulse
output address faults after the storage write, the emulator restores
the original storage value before calling either handler. This also
restores unknown scalar storage and preserves adjacent bits in a packed
integer. The pulse output keeps its previous value.

When a handler clears the fault, the next instruction sees the incoming
rung power. A later valid execution can still emit the pending edge pulse
if the rung input differs from the retained storage in the required
direction. Valid executions still select the output after the storage
write. During prescan, an out-of-bounds destination uses the rule below.

[Rockwell OSR reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/bit-instructions1/one-shot-rising--osr-1.html)
[Rockwell OSF reference](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/bit-instructions1/one-shot-falling--osf-1.html)

### Skip coil and one-shot array faults during prescan

The v35 ControlLogix 5580 ladder profile skips OTE, ONS, OSR or OSF
when a prescan write encounters an out-of-bounds array selection.
Prescan continues with the next instruction without invoking a Program
or Controller fault handler. For OSR and OSF, the pulse destination
is evaluated after the storage write. If that destination is out of bounds,
the emulator restores the original storage, including unknown scalar
values and adjacent bits in packed integers.

Unknown indices, unknown packed backing values and errors caught by
structural validation still block initialization. If normal execution
reaches the same bad index, the existing Type 4 Code 20 path applies.
Native partial-write behavior remains unverified.

[Rockwell prescan fault reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)

## Recover timer, counter and reset array faults

During whole-project ladder scans, an out-of-bounds record subscript
in TON, TOF, RTO, CTU, CTD or RES can raise Type 4 Code 20. If a fault
handler clears it, the emulator skips the instruction and continues
with incoming rung power. This applies on either rung state for timers
and counters. A false RES skips the live subscript.

The skipped instruction leaves record fields, timer timestamps,
counter edge bits and CONTROL incremental progress intact. A later
valid timer call uses the existing elapsed time since its last execution.
A later valid count checks the retained edge bit. RES applies to TIMER,
COUNTER and CONTROL. A valid CONTROL reset uses the same resolved address
to clear the record and its incremental file progress, even if clearing
POS changes the expression that selected it.

Unknown fields use scan rollback. Elapsed-time overflow in the modeled
v35 5580 [TIMER profile](ladder-timers.md#existing-clock-policy) saturates
the accumulator and completes the interval.

### Skip timer and counter array faults during prescan

In the v35 ControlLogix 5580 ladder profile, prescan skips TON, TOF, RTO,
CTU or CTD when resolving the record raises an out-of-bounds array fault.
No record is written for that instruction, and prescan continues with the
next instruction without invoking a Program or Controller fault routine.
The loaded index keeps its value. Unknown indices and errors rejected
during structural validation still block initialization.

Normal execution evaluates the actual index again and can raise Type 4
Code 20 as described above. Native controller behavior remains
unverified.

[Rockwell prescan fault reference](https://www.rockwellautomation.com/en-fi/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/access-remote-i-o/clearing-a-major-fault-during-prescan.html)

### Recover negative timing values

In the v35 ControlLogix 5580 model, a negative DINT PRE or ACC raises
Type 4 Code 34 when the rung is true for TON/RTO or false for TOF.
The fault is raised before the timer changes its record or last execution
time. The Program or Controller handler can read the record, repair the
tag and clear the fault. In a flat DINT record, word 2 holds
`2228228` (`16#0022_0004`).

A clear skips the current timer call and preserves incoming rung power.
The next valid call uses the elapsed time since its last successful
execution. An uncleared fault rolls back the scan. The other rung states
still require known nonnegative PRE/ACC under the existing software
validation rules. Native timing, fault and controller behavior remain
unverified.

[Rockwell general instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
[Rockwell timer and counter instruction reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/timer-and-counter-instructions.html)
[Rockwell RES reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/timer-and-counter-instructions/reset--res-.html)

## Recover shift and queue array faults

A reached out-of-bounds subscript in BSL, BSR, FFL, FFU, LFL or LFU
can raise Type 4 Code 20 in a whole-project ladder scan. The emulator
restores the CONTROL record and any queue elements moved by an unload
before calling the fault handler. If the handler clears the fault, the
next instruction sees the incoming rung power. A later valid call can
still use the retained EN or EU edge state.

This covers the selected CONTROL address, a reached array start, a
load or shift source, and an unload destination, including the write
on an empty unload. Valid unloads still resolve their destination
after moving the queue. False, held and full-load paths retain their
existing rules for when to read an address.

For v35 ControlLogix 5580 BSL and BSR, a positive LEN that exceeds the bits
remaining at a valid standalone DINT array start also raises Type 4 Code 20.
The emulator preserves the array and the prior CONTROL state, then sets ER
before entering the handler. A cleared fault leaves the edge available for
the next scan.

FFU and LFU also raise Type 4 Code 20 when a reached unload edge has a LEN
that extends past a standalone array, including the empty-queue path. The
queue, destination and prior CONTROL state are retained. LFU sets ER for the
handler. Member overruns, load window limits, emulator work limits and
unknown consumed values use scan rollback.

[Rockwell general instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
[Rockwell FFU reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/array--file--shift-instructions/fifo-unload--ffu-.html)
[Rockwell LFU reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/array--file--shift-instructions/lifo-unload--lfu-.html)

## Recover sequencer array faults

A reached out-of-bounds subscript in SQI, SQO or SQL can raise Type 4
Code 20 in a whole-project ladder scan. This includes subscripts that
select the CONTROL record, table start, mask, source or destination.
Before either fault handler runs, the emulator restores the CONTROL
fields, including POS, EN, DN and ER. A skipped instruction leaves the
table and destination untouched.

If the handler clears the record, the next instruction receives the
incoming rung power. A later valid call uses the retained edge state
and position. For example, a held SQO can write the same row to a
repaired destination without advancing again. A zero mask still checks
the table window and skips the live compared source or destination.

A valid start with a configured table window that is too short retains
the existing behavior. SQI and SQO set ER, and SQL rolls back the scan.
Unknown consumed values, prescan and other errors remain separate.

[Rockwell general instructions reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
[Rockwell SQO reference](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/sequencer-instructions/sequencer-output--sqo-.html)

## Skip out-of-bounds CONTROL records during prescan

In the v35 ControlLogix 5580 ladder profile, prescan skips an out-of-bounds
CONTROL selection in BSL, BSR, FFL, FFU, LFL, LFU, SQL, SQO, AVE, STD,
FBC or DDT. The instruction leaves its records intact, and prescan
continues without running a Program or Controller fault handler.
FBC and DDT can load with a saved out-of-bounds indirect CONTROL index.
Load validation still checks writable CONTROL structure and known storage
roles. Prescan resolves both actual records and checks that they are distinct
before updating either one.

Unknown indices and missing control fields still fail when required.
Normal scans still resolve the live index and use the existing
Type 4 Code 20 path. Native controller behavior remains unverified.

[Rockwell prescan fault reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/controller-properties/major-fault-state.html)

## Recover file arithmetic and search array faults

A reached out-of-bounds array subscript in FAL or FSC can raise Type 4
Code 20 in a whole-project ladder scan. This covers ALL, numeric and
INC modes. Before either fault handler runs, the emulator restores the
CONTROL record and any FAL destination values written during that call.
Completed work from earlier calls remains available.

When a handler clears the fault, the next instruction receives the
incoming rung power. An active numeric call can still run on a false
rung. A failed INC iteration leaves its position, pending edge and
private progress as they were before the call. The next valid call
can retry that element.

### Recover a negative file cursor

When a FAL or FSC call reaches iteration with negative CONTROL.LEN or
CONTROL.POS, the emulator raises Type 4 Code 21 before processing any
element. The Program fault routine can capture and selectively clear
that record, or the Controller Fault Handler can clear it when the
Program routine leaves it uncleared. For the flat DINT record,
`FaultWords[2]` contains `1376260` (`16#0015_0004`).

A clear skips the faulting call, preserves incoming rung power and
allows the next scan to use any cursor correction written by the
handler. A missing clear rolls back the scan. Unknown fields, a
nonnegative POS beyond LEN and arithmetic overflow use the existing
scan rollback path. Native Studio and controller behavior remain
unverified.

[Rockwell FAL reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-arithmetic_logic-fal.html)
[Rockwell FSC reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/array-file-misc-instructions/file-search-and-compare-fsc.html)

## Recover bit diagnostic and data transition array faults

A reached out-of-bounds subscript in FBC, DDT or DTR can raise Type 4
Code 20 during a whole-project ladder scan. FBC and DDT restore the compare
and result CONTROL records before the fault handler runs. They resolve the
result array on the first mismatch, before writing any mismatch offsets
or changing reference bits. If a handler clears a fault on a later enable
edge, offsets and reference bits committed on earlier edges remain available.

DTR skips its reference write if an indexed source, mask or reference
faults. Recovery applies when a true scan compares the reference and when
a false scan refreshes it. In each instruction, a cleared fault passes
the incoming rung power to the next instruction. Other faults, including
a configured window that runs beyond a valid starting element, use the
existing scan rollback.

During prescan, DTR skips an out-of-bounds source, mask or reference
selection before writing anything. Prescan continues without invoking a user
fault handler. False and true runtime scans still use the recovery above.

[Rockwell FBC reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/file-bit-comparison--fbc-.html)
[Rockwell DDT reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/special-instructions/diagnostic-detect--ddt-.html)
[Rockwell DTR reference](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/special-instructions/data-transition--dtr-.html)

## Recover sort and statistics array faults

A reached out-of-bounds subscript in SRT, AVE or STD can raise Type 4
Code 20 during a whole-project ladder scan. This includes an indexed
CONTROL record, the start of the selected array dimension and the
result address for AVE or STD. Address selection happens before data
or CONTROL writes, so a handler sees the values from before the call.

When a handler clears the record, the next instruction receives the
incoming rung power. A later valid call can still sort the selected
window or calculate its result on the retained edge. False or
inhibited calls continue to skip live array and result operands
according to the instruction. The CONTROL address is still required.

A valid start with a window that extends beyond its selected dimension
or an unknown consumed value uses scan rollback.
The recovery path applies to ladder execution.

### Recover negative sort and deviation cursors

A reached negative CONTROL.LEN or CONTROL.POS in ladder SRT or STD
raises Type 4 Code 21 before sorting or writing the deviation. The
Program or Controller handler can clear the record and continue the
rung with its incoming power.

SRT sets CONTROL.ER before the handler runs. If the fault is cleared,
the ER bit stays set until logic clears it. Fix LEN/POS and clear ER
before the sort can run again. STD leaves its CONTROL and result
unchanged before the handler runs. The next eligible scan can use a
corrected cursor.

An uncleared fault rolls back the scan, including any SRT ER write.
Other invalid cursors, including unsupported positive positions and
AVE cursor errors, use scan rollback. This recovery covers whole-project
ladder. Native Studio and controller behavior remain unverified.

[Rockwell STD reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-standard-deviation-std.html)
[Rockwell SRT reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/array-file-misc-instructions/file-sort-srt.html)
[Rockwell array and file instructions reference](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions.html)

## Recover BCD, size and truncation array faults

A reached out-of-bounds subscript in FRD, TOD, SIZE or TRN can raise
Type 4 Code 20 during a whole-project ladder scan. This includes indexed
sources and destinations, as well as an indexed dimension tag in the
emulator SIZE extension. If a handler clears the fault, the instruction
skips its result write and the next instruction receives incoming rung
power. A later valid call uses the current operand values and indices.

False rungs skip live operands. Reached unknown values, invalid BCD
ranges, and SIZE dimensions outside the selected array rank use scan
rollback. This recovery applies to ladder calls.

[Rockwell array subscript reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html)

## Recover standalone math array faults

A reached out-of-bounds subscript in SQR, XPY, LN, LOG, DEG, RAD, SIN,
COS, TAN, ASN, ACS or ATN can raise Type 4 Code 20 during a whole-project
ladder scan. Recovery covers indexed sources, either XPY operand and
indexed destinations across the float32, binary64 and exact integer
profiles. When a handler clears the fault, the instruction skips its
result write and the next instruction receives the incoming rung power.

A later valid scan evaluates the current operands. False rungs skip live
operands. Unknown consumed values, invalid math domains, nonfinite
results and overflow use scan rollback.

[Rockwell array subscript reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/index-through-arrays.html)

## Recover string operation and conversion array faults

A reached out-of-bounds subscript in CONCAT, MID, DTOS, STOD, FIND, INSERT,
DELETE, LOWER, UPPER, STOR or RTOS can raise Type 4 Code 20 during a
whole-project ladder scan. Recovery covers indexed sources, positions,
quantities and destinations. When a handler clears the fault, the instruction
skips its string or numeric result write and passes incoming rung power to the
next instruction. A skipped string result keeps its LEN and every DATA byte.

A later valid scan evaluates the current operands. False rungs skip live
operands. Unknown consumed values, invalid string positions and quantities,
invalid numeric text and destination capacity errors still use scan rollback.
Structured Text calls use their existing rollback behavior.

[Rockwell ASCII string instructions](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/ascii-string-instructions.html)

## Recover GSV and SSV array faults

During a whole-project ladder scan, an out-of-bounds subscript in a GSV
destination or an SSV source can raise Type 4 Code 20. If a fault handler
clears the record, GSV skips the complete destination write and SSV leaves
the system setting untouched. The next instruction receives the incoming
rung power. A later enabled scan resolves the operand again.

False rungs skip live indices. A valid starting subscript with too few
contiguous elements, invalid settings, and unavailable values still use
scan rollback. Structured Text retains its existing rollback behavior.

[Rockwell GSV and SSV reference](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/get-system-value--gsv--and-set-system-value--ssv-.html)

## Recover PID and alarm array faults

A cleared Type 4 Code 20 in PID, ALMD or ALMA skips the instruction in a
whole-project ladder scan. PID retains its record, control output and last
solver sample. ALMD and ALMA retain the alarm record, pending operator
commands, and timing or edge history. The rest of the rung receives the
incoming rung power. On a later scan, the instruction uses the current
operands with its last committed history.

PID prescan and false rungs select only the PID record to clear .EN.
Prescan skips an out-of-bounds record without invoking a user fault handler.
A reached false or true runtime call still uses the recovery above.
ALMD still processes command operands on a false rung. ALMA skips live input and
command operands there. Invalid gains, invalid alarm configuration that
raises a model error, and other failures keep the existing scan rollback
behavior.

[Rockwell PID execution table](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/special-instructions/proportional-integral-derivative--pid-.html#execution)

## Recover FOR array faults

A reached out-of-bounds subscript in a ladder FOR index, initial value,
terminal value or step can raise Type 4 Code 20. If the fault handler clears
it, FOR ends the invocation and the next instruction receives the incoming
rung power. An entry fault preserves the original index, including when
the first terminal or step lookup fails after index initialization.

Once the body has run, a fault in a later terminal or step lookup preserves
completed routine writes and prior index increments. A failed step lookup
does not increment the index. The handler sees the index and body writes
at the point of failure. A later scan starts a new invocation.

Array faults inside the called routine follow that routine's instruction
rules. Unknown values, DINT overflow, and budget exhaustion still roll
back the scan. See [FOR sampling and lifecycle](ladder-loops.md#runtime-selected-operands).

## Escalate an uncleared Program fault

For a modeled array fault, the assigned Controller Fault Handler runs
when the Program fault routine finishes without clearing the record or
when the source confirms that the Program has no assigned fault routine.
The controller handler and its ladder subroutines can use `THIS` or
the handler Program's name to access the active simulated record. It
retains the original Type 4 Code 20 and timestamp. The origin Program
and routine are recorded in the browser's recovery data.

The controller handler uses its own subroutine stack and runs with
`S:FS` false. Both stages share the faulting scan's instruction budget.
If the controller handler clears the record, execution resumes after the
failed instruction and the scan commits both handlers' diagnostic writes.
A handler execution error or an uncleared fault rolls back the scan.
The browser names the routine that cleared the fault.

[Rockwell controller fault handler configuration](https://www.rockwellautomation.com/en-no/docs/studio-5000-logix-designer/37-00/contents-ditamap/studio-5000-logix-designer/controller-properties/configure-a-controller-fault-handler-program.html)

## Simulated I/O fault capture

A complete v35 ControlLogix 5580 export can assign one enabled, unscheduled
Standard Program through Controller `MajorFaultProgram`. Its ladder main
routine executes once when a simulated Type 3 Code 16 or Code 23 fault
latches. The routine runs outside normal task scheduling and prescan. Its
tag writes and trace are recorded at the current scan and simulated time.
The next prescan or scan replaces the trace. If the routine fails, its
writes and partial trace roll back. The original
I/O major fault remains latched, and its `handler` record reports the
routine, status and any error.

The handler profile accepts contacts, coils, compares, MOV, CLR, ADD, SUB,
MUL, DIV, AFI, NOP and the listed GSV reads. The handler can read named Module
EntryStatus, FaultCode and FaultInfo. To capture the active fault record,
declare a writable DINT array and use its first element.

```text
GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);
```

The read writes 11 DINT words. Words 0 and 1 hold the low and high halves
of the emulator UTC timestamp in microseconds. Word 2 holds Type in its
low half and Code in its high half. The eight fault-specific Info words
are unknown. The browser and HTTP fault record retain the injected module
code and information independently. The read is available inside the
executing handler. Additional I/O fault types and native handler references
remain open.
The existing recovery control can clear a fault after the simulated
connection is restored.
[Rockwell Major, Minor, and I/O Faults manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)
[Rockwell Program object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)

## Call ladder diagnostic subroutines

The handler main can use JSR to call ladder routines in its own Program.
Calls use the normal JSR/SBR/RET rules for typed parameter copies, with a
25-call limit and an instruction budget shared by the handler. Recursive
calls, calls to the main routine and unsupported instructions in called
routines block project execution during validation.

Called routines can read or clear the active MajorFaultRecord just like the
main. Their tag writes, including input and return copies, and a pending
fault clear commit together when the main finishes. An error anywhere in
the call chain discards those writes and its trace. Handler routines stay
outside normal task scheduling, prescan and the isolated routine harness.

[Rockwell JSR, SBR and RET reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)

## Read and clear a structured fault record

A user-defined record can declare either a scalar LINT timestamp or two
scalar DINT words in low/high order. Declare scalar INT Type and Code
next, then a one-dimensional DINT[8] Info array. The member names may
vary. Use the record's first timestamp member as the GSV destination or
SSV source. The selected record can be a scalar tag or an element of
an array. The simulator validates the entire declared layout, including
visible members and array extent, before writing any fields.

For a record whose first member is `Timestamp`, these rungs capture
the fault and clear only Type 3 Code 16.

```text
GSV(Program,THIS,MajorFaultRecord,FaultRecord.Timestamp);
EQU(FaultRecord.Type,3)EQU(FaultRecord.Code,16)CLR(FaultRecord.Type)CLR(FaultRecord.Code)SSV(Program,THIS,MajorFaultRecord,FaultRecord.Timestamp);
```

The split timestamp form uses its low word as the operand. Info words
remain unknown in either layout. Both INT fields must contain known zeros
to request a clear. The existing handler commit and rollback rules apply.
[Rockwell fault-record structure and operand guidance](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)
[Rockwell LINT timestamp layout](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)

## Clear an active fault in ladder logic

In the same controller handler, use SSV with THIS or the current handler
Program. For an 11-word DINT source, the packed Type and Code word must be
known zero. For example, after reading the active fault, this rung clears
only Type 3 Code 16.

```text
EQU(FaultWords[2],1048579)CLR(FaultWords[2])SSV(Program,THIS,MajorFaultRecord,FaultWords[0]);
```

The clear commits only after the handler completes. A later failure rolls
back the pending clear and handler writes. A reached SSV with an unknown
or nonzero Type/Code word fails the handler. A GSV in the handler after a
valid SSV sees zero Type and Code. The remaining record words stay read-only.

A cleared 3/16 continues Run at the next scan without another prescan. A
cleared 3/23 lets the current Run request proceed through prescan. The
simulated connection still reports the applied fault, so another
Program-to-Run request can raise a new 3/23. The browser and
`controller.last_cleared_module_fault` report the latest programmatic clear
for the current simulation, with the original type, code and diagnostics.
[Rockwell programmatic fault clearing example](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)

## Null native Controller handler references

Version `.111` adds reference-backed reads for absent Controller Power Loss
(attribute 1) and Fault Routine (attribute 6) handlers in native compatibility
mode. A successful v35 reference upload establishes four-byte values for both
fields, including an all-zero null. Nonzero physical references are not copied
or interpreted by the emulator.

## Source and scope

A null is available only when the complete controller export proves that the
corresponding handler is absent. Configured names, UID-only declarations,
context exports, missing source sections and ambiguous case/namespace variants
keep that field unavailable. Ordinary endpoint attributes remain unchanged.
Single reads and ordered lists share the same four-byte value; duplicate list
entries preserve their widths and positions. Setters remain denied.

Connectivity describes `handler_reference_encoding: null_uint32_only`, a
four-byte width and `configured_handler_references: false`. The native reference profile only serves proven null references.

## Aggregate profile

The Controller instance `Get Attributes All` read supports one observed
16-byte profile when both handlers are proven absent:

| Field | Bytes | Model source |
| --- | --- | --- |
| Communications time slice | 2 | Existing source value or declared compatibility default |
| Fault Routine reference | 4 | Proven absent handler |
| Power Loss reference | 4 | Proven absent handler |
| Run Mode Inhibit | 2 | Current programming lease state |
| Connection ID | 2 | Existing anonymous model slot value |
| Opaque zero trailer | 2 | Observed profile constant; meaning remains unresolved |

The trailer does not establish another controller attribute or runtime state.
The aggregate requires an instance path without an attribute and an empty
request body. Incomplete source or a configured handler returns an error.
Changing the owning lease's inhibit state changes the aggregate's inhibit
field; clearing the lease clears it. These reads do not change tags or scans.

The independent inventory reader retains the aggregate bytes and identifies
only an exact successful four-byte zero as `NULL_UINT32`. Other handler replies
stay unresolved. It does not convert opaque references into native addresses.

## Validation boundary

The reference upload includes successful handler and aggregate responses.
Nonzero configured native references remain unavailable. Synthetic source checks, independent signed TCP reads and inventory
tests cover null widths, duplicate lists, withheld configured/context data,
malformed scope/payload, live inhibit readback and unchanged tag/scan state.

The isolated SDK upload receives successful null-handler list reads. A second
case receives the 16-byte aggregate successfully, without the earlier fallback
list. Both still report `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`.
Successful object replies do not establish successful SDK collection or identify
its remaining cause. Native Offline, endpoint cleanup and source/model
preservation pass without a reported fatal fault. A separate native Go Online/
Go Offline case passes.

Full upload/download, configured handler references, native tag addresses and
Test/Untest/Assemble remain unfinished. The previous Template metadata fault
hypothesis is not retried. Private captures, projects and native references are
not distributed with the repository.
