# Studio5000Emulator

An experimental offline Logix v35 emulator with a browser UI and local EtherNet/IP endpoint.

Execute supported ladder, Structured Text and FBD signal logic, inspect scan
traces and connect external device simulators. The app and executable use the
name **LogixLab**.

**Current app version: `26.1105.094954`.** Versions use `YY.MMDD.HHmmss`; the
browser title, page header, Windows tray and executable properties match.

**Development focus: full ladder support, then Structured Text, then FBD, then SFC.**
Complete and qualify ladder and ST before adding new FBD/SFC features. Full
emulation remains ahead of further Studio 5000 connectivity work.
The current model is partial: 106 built-in RLL instruction entries, a bounded ST
subset, supported AOIs/UDTs, explicit custom strings and a limited FBD signal
graph. General FBD, SFC, motion, cyclic module I/O and EDS-driven device models
remain unfinished.
See the [comprehensive capability checklist](docs/emulation-coverage.md),
[instruction inventory](docs/emulation-instructions.md),
[222-entry predefined type inventory](docs/predefined-data-types.md) and
[roadmap](docs/roadmap.md).

Existing native SDK connection, transfer and routine-edit profiles remain
experimental and preserved. Their acceptance does not establish full runtime
emulation or general Studio GUI compatibility. Detailed prior results are in
[native compatibility checkpoints](docs/native-compatibility-checkpoints.md)
and [connectivity history](docs/connectivity-history.md).
Development is maintained on `main`.

**Appliance startup recovery** now handles a timed-out VMware guest-address
query through the existing MAC-matched DHCP and pinned SSH fallback. Startup
keeps its bounded retry window and version checks; see
[appliance startup](docs/vmware-appliance.md).

**Ladder time and date tags** support exact ADD/SUB, moves, comparisons and a
raw LINT/LDT nanosecond bridge. In **Data Lab**, enable `TimeDateDemo` and step
to see signed duration arithmetic and a one-nanosecond timestamp difference.
[Time and date storage](docs/time-date-storage.md)

**Literal ladder CONTROL settings** initialize LEN/POS when importing supported
shifts, queues, sequencers, statistics and file operations. **Control lab**
demonstrates a bit shift and FIFO with values supplied by the rung.
[CONTROL initialization](docs/control-operations.md#literal-len-and-pos-on-import)

**Literal ladder timer and counter presets** seed PRE/ACC when loading an L5X
project. In **Timer lab**, enable `LiteralPresets` to exercise the saved
starting values. See [literal presets on import](docs/ladder-timers.md#literal-presets-on-import).

**Wide integer SQR and XPY** preserve exact input values through calculation.
In **Integer lab**, enable `ExactRootPowerEnabled` and step. See
[wide integer roots and powers](docs/math-operations.md#wide-integer-roots-and-powers).

**REAL inputs** can write LINT and unsigned integer results in nineteen ladder
math forms. In **Integer lab**, enable `RealIntegerEnabled` and step. See
[REAL math with integer results](docs/real-destination-math.md#wide-and-unsigned-integer-results).

**LREAL inputs** select binary64 calculation in nineteen ladder math forms
with REAL or integer results. In **Wide expression lab**, enable
`Binary64ResultEnabled` and step. See [REAL and integer results](docs/lreal-math-literals.md#real-and-integer-results).

**Typed conversion constants** work in FRD, TOD and TRN. In **Conversion lab**,
enable `ImmediateConversions` and step to see a 16-digit BCD round trip and
compare REAL and LREAL truncation. See [BCD conversions](docs/numeric-conversions.md#typed-source-immediates)
and [LREAL truncation](docs/lreal-truncate.md).

**Typed bit patterns** now work in AND, OR, XOR, NOT and MEQ. Decimal L/U/UL
constants retain their declared widths when combined with integer tags and
legacy patterns; see [typed bitwise operands](docs/typed-bitwise-operands.md).

**Typed integer arithmetic and comparisons** now accept decimal L/U/UL constants
under the existing range-preserving integer rules, with exact division and
ordering beyond floating precision. See [integer operands](docs/typed-integer-operands.md).

**Typed integers in REAL ladder operations** now work across nineteen math forms
and seven comparisons, using declared integer ranges and existing float32
conversion. See [REAL integer constants](docs/real-integer-literals.md).

**LREAL comparison constants** now work across six relations and LIM. An LREAL
tag or floating L/l constant selects binary64, with declared source precision
and inclusive/reversed limits; see [comparison constants](docs/lreal-comparison-literals.md).

**LREAL ladder math constants** now work across nineteen arithmetic, power,
root, logarithm, angle and trigonometric instructions. Decimal typed integers
and floating L/l constants preserve their source precision; see
[LREAL math constants](docs/lreal-math-literals.md).

**Radix MOV constants** now interpret binary, octal and hexadecimal values as
32-bit DINT patterns, including signed top bits, zero-filled short constants and
exact source values in the ladder viewer. See [radix moves](docs/radix-mov-literals.md).

**Typed MOV constants** now support decimal L/U/UL integers and finite LREAL
floating constants, with declared source precision and existing numeric conversion.
The viewer preserves typed constants and exact integer digits; see
[typed MOV constants](docs/typed-mov-literals.md).

**Wide integer constants in file expressions** now work in FAL transforms and
FSC searches with matching LINT/UDINT/ULINT operands, exact values and existing
ALL/numeric/INC progress. See [file integer constants](docs/file-integer-literals.md).

**Typed integer constants in LREAL expressions** now use checked L/U/UL values
with binary64 calculation and final numeric conversion. Wide expression lab
contrasts rounded floating results with exact integer results; see
[typed constants and LREAL](docs/lreal-integer-literals.md).

**Wide integer constants** now work in matching-type ladder CPT/CMP: decimal
L/U/UL suffixes retain full integer precision and checked ranges. Wide expression
lab adds exact constants, comparisons and recovery examples; see
[ladder integer constants](docs/ladder-integer-literals.md).

**LREAL expressions** now execute in ladder CPT/CMP with finite binary64
arithmetic, mixed numeric tags, [checked integer/REAL results](docs/lreal-results.md)
and copied AOI parameters. [Floating constants](docs/lreal-literals.md) now support
REAL defaults and explicit LREAL suffixes in CPT/CMP. Wide expression lab
adds precision and fault-recovery examples; see [LREAL expressions](docs/lreal-expressions.md).

**Integer square-root expressions** now retain narrow integer arithmetic.
Control lab contrasts integer and REAL results; see [integer roots](docs/ladder-integer-roots.md).

**Integer powers** now execute in bounded narrow CPT/CMP and FAL/FSC
expressions. Control lab includes a gated example with file search and atomic
fault recovery; see [integer expression powers](docs/ladder-integer-power.md).

The [logic viewer](docs/logic-viewer.md) includes AOI definition/instance headers,
named visible parameters, input/output roles and status indicators. Built-in
instructions have descriptive titles and named operands. Program-local tags
and AOI InOut values retain their scope, and JMP instructions link to their labels. It uses Studio-style ladder symbols, rails
and branch wiring, ST syntax coloring and FBD pin connections. Select a node
for operand details; zoom and fit the document. Ladder topology has explicit
instruction/junction nodes, typed ports and edges for a future node and wire
editor. The current monitor remains read-only.

[Scan-time GSV reads](docs/scan-time-gsv.md) expose Program and Task
LastScanTime/MaxScanTime in DINT and TIME32. A zero-source SSV clears either
measurement. **System lab** demonstrates reads and resets in ladder and ST.

[Object identity GSV](docs/gsv-configuration.md#object-identity-reads) reads
Program and Routine names plus Task registry slots in ladder and ST.
**System lab** shows how Routine THIS follows a called routine.

[Controller source flags](docs/gsv-configuration.md#controller-source-flags)
read the project settings for producer RPI, redundancy, test-edit retention,
and firmware-update inhibition in ladder and ST.

[Controller-only Module status](docs/gsv-configuration.md#controller-only-module-status)
adds LEDStatus and ForceStatus reads in ladder and ST. DINT destinations keep
their upper word. [Named Module status](docs/gsv-configuration.md#named-module-status)
reads the Mode word and reports Inhibited or Waiting for qualified modules.
Waiting means a modeled parent or ancestor is inhibited or faulted. Ladder
and ST can set Mode with SSV and read it back in the same scan. The **Module status lab**
demonstrates these states and reads local and Ethernet routes, including
[a slot in a remote chassis](docs/gsv-configuration.md#remote-controllogix-backplane-path).
Use the [simulated connection input](docs/gsv-configuration.md#simulated-module-connection)
to exercise Running, Faulted, FaultCode and FaultInfo in ladder and ST.
The Device I/O tab sets the simulated input and displays the effective state.
[Simulated loss of a required Running module](docs/gsv-configuration.md#required-module-loss-during-run)
trips a latched I/O major fault during whole-project Run, including when a
[simulated upstream fault interrupts a required connection](docs/gsv-configuration.md#required-module-loss-through-an-upstream-fault).
Restore the affected connections and use **Clear I/O major fault** to return to
Program with current tag values. A [required connection blocked by a simulated fault at Run entry](docs/gsv-configuration.md#required-module-fault-at-run-entry)
trips before prescan. A [ladder controller fault handler](docs/controller-handlers.md#simulated-io-fault-capture)
can capture and clear the active simulated I/O fault using DINT words or a
[structured fault record](docs/controller-handlers.md#read-and-clear-a-structured-fault-record).
Its main routine can [call ladder diagnostic subroutines](docs/controller-handlers.md#call-ladder-diagnostic-subroutines)
and commit their tag writes and fault clearing together.
A separate [ladder Program fault routine](docs/controller-handlers.md#recover-a-ladder-mov-array-fault)
can clear out-of-bounds MOV, [COP/CPS](docs/controller-handlers.md#recover-cop-and-cps-array-faults),
[JSR](docs/controller-handlers.md#recover-a-jsr-argument-fault),
[arithmetic](docs/controller-handlers.md#recover-a-ladder-arithmetic-array-fault),
[bitwise](docs/controller-handlers.md#recover-a-ladder-bitwise-array-fault),
[FLL, CLR and SWPB](docs/controller-handlers.md#recover-fll-clr-and-swpb-array-faults),
[contact, coil, ONS and comparison](docs/controller-handlers.md#recover-contact-coil-ons-and-comparison-array-faults),
[OSR and OSF](docs/controller-handlers.md#recover-osr-and-osf-array-faults),
[timer, counter and reset](docs/controller-handlers.md#recover-timer-counter-and-reset-array-faults),
[shift and queue](docs/controller-handlers.md#recover-shift-and-queue-array-faults),
[sequencer](docs/controller-handlers.md#recover-sequencer-array-faults),
[file arithmetic and search](docs/controller-handlers.md#recover-file-arithmetic-and-search-array-faults),
[bit diagnostics and data transition](docs/controller-handlers.md#recover-bit-diagnostic-and-data-transition-array-faults),
[sorting and statistics](docs/controller-handlers.md#recover-sort-and-statistics-array-faults),
[BCD, size and truncation](docs/controller-handlers.md#recover-bcd-size-and-truncation-array-faults),
[standalone math](docs/controller-handlers.md#recover-standalone-math-array-faults),
[string operations and conversions](docs/controller-handlers.md#recover-string-operation-and-conversion-array-faults),
[system values](docs/controller-handlers.md#recover-gsv-and-ssv-array-faults),
[PID and alarms](docs/controller-handlers.md#recover-pid-and-alarm-array-faults)
and [FOR](docs/controller-handlers.md#recover-for-array-faults)
operands to continue at the next instruction. The Controller Fault Handler can
[recover an uncleared array fault](docs/controller-handlers.md#escalate-an-uncleared-program-fault).
The [ladder monitor marks the skipped instruction](docs/logic-viewer.md#fault-recovery-in-the-ladder-monitor)
and shows the cleared fault code in its details.
[Aggregate LEDStatus](docs/gsv-configuration.md#simulated-module-ledstatus)
summarizes a complete simulated module inventory.

[Controller device GSV](docs/gsv-configuration.md#controller-device-identity)
reads the loaded 5580 model's catalog name, product code, packed firmware
revision, device type and vendor. [Controller device status](docs/gsv-configuration.md#controller-device-status)
uses the same mode word as the emulator's EtherNet/IP endpoint.
**System lab** demonstrates ladder and ST.

[Wall-clock GSV reads](docs/wall-clock-gsv.md) expose UTC microseconds and
calendar fields to ladder and existing ST calls through the same host clock
as the CIP endpoint. In **System lab**, enable ReadClock to fill a calendar
record with [named DINT fields](docs/wall-clock-gsv.md#calendar-records)
and read [software CST and its UTC offset](docs/wall-clock-gsv.md#coordinated-system-time).
ReadTypedTimes shows a DT timestamp, its exact LDT conversion and typed Task
measurements.

[BCD file expressions](docs/file-bcd.md) add FRD/TOD transforms and searches
in ALL, numeric and INC modes. **Control lab** includes a BcdFiles routine.

[BCD CMP expressions](docs/cmp-bcd.md) add integer conversions inside ladder
comparisons and Boolean conditions. **Bit lab** demonstrates live match coils.

[BCD CPT expressions](docs/cpt-bcd.md) add integer FRD/TOD operators, nesting
and arithmetic. **Bit lab** demonstrates conversions and rollback recovery.

[Sequencer source types](docs/sequencer-sources.md) qualify SINT/INT/DINT
SQL/SQI sources and complete 32-bit patterns, with sequencer-specific guards.
**Sequence lab** demonstrates signed teaching, masks and held updates.

[Array-index functions](docs/array-index-functions.md) add FRD, TOD and SQR
with checked DINT arguments/results and matching snapshot values. **Bit lab**
includes nested conversions, rounded roots and fault recovery.

[Array-index expressions](docs/array-index-expressions.md) add exact division
and bitwise operators, plus single wide integer tag indices. **Bit lab** includes
a gated example with lazy operands and atomic recovery.

[REAL-result math](docs/real-destination-math.md) adds float32 input conversion
for basic arithmetic, power and eleven unary forms across integer/REAL sources.
**Integer lab** demonstrates precision, wide values and recovery.

[REAL comparison promotion](docs/mixed-real-comparisons.md) adds numeric tag
mixtures for six ladder relations and LIM, including float32 rounding before
comparison. **Integer lab** shows precision, collapsed limits and precedence.

[LREAL arithmetic results](docs/lreal-destination-math.md) select binary64 for
ADD/SUB/MUL/DIV/MOD/NEG/ABS and XPY across numeric tags and bounded integer
constants, including calls without a LREAL source. **Integer lab** has examples.

[Numeric unary inputs with LREAL results](docs/lreal-unary-sources.md) extends
eleven ladder math forms to all numeric tag types and signed DINT-range
constants. **Math lab** demonstrates roots, angles, logs, trig and fault recovery.

[Mixed LREAL powers](docs/mixed-lreal-power.md) adds XPY with numeric tag pairs
and signed DINT-range constants, with a LREAL result.
**Math lab** includes precision, wide-integer rounding and fault examples.

[Integer constants with LREAL](docs/lreal-constants.md) adds signed DINT-range
constants to five binary ladder operations, six relations and LIM. **Integer lab**
includes both source orders, limits, precision and fault recovery.

[Mixed comparisons with LREAL](docs/mixed-lreal-comparisons.md) adds six direct
ladder relations and inclusive/reversed LIM across numeric tag types.
**Integer lab** demonstrates precision, promotion rounding and fault recovery.

[Mixed numeric arithmetic with LREAL](docs/mixed-lreal-math.md) adds five binary
ladder operations with numeric tag sources and a LREAL result. **Integer lab** includes conversion, precision and fault examples.

[LREAL byte copies](docs/lreal-copy.md) adds COP/CPS binary64 images, integer
round trips and partial writes. **Byte copy lab** includes precision, selected
outputs and invalid-image/late-fault examples.

[LREAL truncation](docs/lreal-truncate.md) preserves binary64 sources for ladder
TRN, with signed/unsigned integer and REAL/LREAL results. **Math lab** includes
precision, selected-output and late-fault examples.

[LREAL roots, powers, logarithms and trigonometry](docs/lreal-advanced.md) adds
twelve matching-tag ladder forms without a REAL intermediate. **Math lab**
includes precision, selected outputs and domain/late-fault examples.

[LREAL ladder arithmetic and comparisons](docs/lreal-math.md) adds seven math
operations, six relations and LIM for matching LREAL tags. **Integer lab**
includes precision, selected-output and fault-recovery examples.

[Finite LREAL storage](docs/lreal-storage.md) adds binary64 ladder MOV/CLR,
numeric conversions and atomic tag reads/writes. **Integer lab** demonstrates
precision retention, REAL narrowing and guarded selected outputs.

[Task start and interval GSV](docs/task-start-gsv.md) adds named/THIS ladder and
ST reads of StartTime, MinimumInterval and MaximumInterval, including DT
starts, TIME intervals and paired TIME32 interval destinations. Ladder and ST
can also reset either interval or the reported Task start timestamp from a
known-zero source. **System lab** includes word windows, resets and rollback.

[Event overlap counts](docs/event-overlap-count.md) adds live ladder/ST reads
and zero resets, including THIS and separate status/counter behavior. **Event
lab** includes guarded count and reset controls.

[Event task timing](docs/event-task-timing.md) adds last/maximum interpreter
durations and Program/Task THIS reads for instruction-only Events. **Event lab**
compares named ladder, ST and THIS snapshots with inhibition and rollback.

[Configured Event timeouts](docs/event-tasks.md#configured-timeouts) let an
instruction-triggered Event task run when no trigger arrives. **Event lab**
shows a 35 ms timeout, its latched Status bit and deadline changes after EVENT.
Use [runtime timeout settings](docs/event-tasks.md#runtime-timeout-settings)
to change the period or disable the fallback from ladder or Structured Text.

[Event task inhibition](docs/event-task-inhibition.md) adds live named/THIS
controls, queued-request checks and Event configuration reads. **Event lab**
includes controls for inhibit, enable and self-inhibition.

[Event task status](docs/event-task-status.md) adds ladder/ST trigger and active
overlap reads and clears, including THIS inside instruction-only Event tasks.
**Event lab** demonstrates latched bits and transactional read-clear behavior.

[Current-instance GSV](docs/current-instance-gsv.md) lets ordinary scheduled
ladder/ST routines use THIS for supported Program timing and Task settings.
[Multi-task scan timing](docs/scan-time-gsv.md) adds independent last/maximum
Task duration reads; inhibited tasks retain their last completed measurements.
**System lab** demonstrates reads from its background and periodic contexts.

[Basic record queues](docs/basic-record-queues.md) copy matching TIMER, COUNTER
and CONTROL records, including nested UDT members. **Record lab** demonstrates
detached snapshots and typed clearing in FIFO/LIFO storage.

[Numeric queue conversions](docs/queue-conversions.md) let ladder FIFO/LIFO
load and unload different SINT/INT/DINT/REAL types with typed conversion,
edge retention and transactional rollback. **Control lab** includes a called
example for both queues and stacks.

[Clipped numeric fills](docs/clipped-fills.md) let FLL stop oversized requests
at the selected logical array boundary while preserving source capture and
transactional rollback.

[Wide integer file operations](docs/integer-files.md) add exact LINT and
unsigned FAL transforms and wide FSC comparisons, including values beyond
floating-point integer precision.

[UID/UIE interrupt control](docs/interrupt-control.md) lets nested critical
sections defer higher-priority EVENT work until their outer UIE.

[Indirect FOR operands](docs/ladder-loops.md#runtime-selected-operands) let ladder
loops select index and bound elements at runtime with explicit sampling and
transactional rollback. The [ladder monitor shows the held index and last bound reads](docs/logic-viewer.md#for-loop-operand-values).

[Indirect routine arguments](docs/indirect-routine-calls.md) let JSR callers
select input and return elements at runtime with copied values and captured
call-entry addresses. Two JSR return operands can select distinct elements
of the same array. Ladder SBR and RET select the callee's indexed elements
when their transfer runs. The [ladder monitor shows captured call operands](docs/logic-viewer.md#call-operand-values)
when a transfer has executed.

[Statistics operand selection](docs/statistics-operands.md) defers dormant
AVE/STD result indices and establishes unknown REAL/integer result elements.

[Sequencer operand selection](docs/sequencer-operands.md) defers dormant mask
and payload indices while preserving held output/teach updates and table checks.

[CONTROL operand selection](docs/control-operands.md) defers shift and FIFO/LIFO
payload indices until needed and lets false CONTROL resets skip live addresses.

[Clipped record operations](docs/clipped-aggregates.md) stop COP/CPS and zero
FLL at the selected logical region. **Data lab** demonstrates source-limited
copies with preserved neighboring records.

[Matching aggregate copies](docs/aggregate-copies.md) give COP/CPS structural
validation, lazy live operands, complete unknown-value copies and bounded work
for basic records, strings and nested UDTs.

[Aggregate zero fills](docs/aggregate-fill.md) initialize unknown TIMER, COUNTER,
CONTROL, strings and explicit UDTs with declared member types. **Data lab** adds
guarded record, timer, counter and string fill examples.

[Ladder timers](docs/ladder-timers.md) check the saved values and history each
TON/TOF/RTO path consumes. **Timer lab** adds ladder delay, retention and pause
examples with clock-history rollback.

[Ladder counters and resets](docs/ladder-counters.md) require known PRE/ACC and
edge history when consumed. **Counter lab** adds ladder counting and resets
that initialize unknown timer/counter fields while preserving PRE.

[Numeric COP/CPS selection](docs/numeric-copies.md#operand-selection) defers saved
lengths and indices until reached. **Byte copy lab** includes an indexed ladder
byte round trip with unknown inputs and outputs, alongside its ST examples.

[Ladder wide expressions](docs/ladder-wide-expressions.md) add exact homogeneous and bounded mixed
LINT/unsigned CPT and CMP forms for v35 5580. Ladder MEQ additionally mixes
all eight integer tag types with zero extension and exact 64-bit masks. **Ladder wide expression lab**
demonstrates values beyond floating-point precision, high-bit masks and fault recovery.

[Event tasks](docs/event-tasks.md) add EVENT calls in ladder/ST for qualified
instruction-only tasks. **Event lab** demonstrates immediate higher-priority
dispatch, deferred lower/equal-priority work, first scans and request diagnostics.

[System-value reads](docs/gsv-configuration.md) add explicit Task/Controller
configuration through GSV in ladder and ST. **System lab** shows task rates and
watchdogs in microseconds, typed priorities, names and controller settings.

[Ladder digital alarms](docs/ladder-alarm.md) import scalar `ALARM_DIGITAL`
records and run ALMD minimum duration, latching, acknowledgment, reset,
enable/disable, [suppression](docs/ladder-alarm.md#suppression),
[timed shelving](docs/ladder-alarm.md#shelving) and
[UTC event timestamps](docs/ladder-alarm.md#timestamps). Choose **Alarm lab**
to step through both polarities and inspect timestamps and
[alarm diagnostics](docs/ladder-alarm.md#diagnostics).
The same example runs [ladder ALMA level alarms](docs/ladder-alarm.md#analog-level-alarms)
with low-low, low, high and high-high limits, directional delay and deadband.
An unfinished level delay restarts after a false rung.
The faceplate shows the live [rate of change](docs/ladder-alarm.md#rate-of-change)
and separate rising and falling conditions. Operators can
[shelve individual ALMA conditions](docs/ladder-alarm.md#analog-alarm-shelving)
for a set duration. The ALMA instruction inspector shows exact
[UTC event timestamps](docs/ladder-alarm.md#analog-alarm-timestamps).
**AOI Alarm lab** runs both instructions through
[InOut alarm record bindings](docs/ladder-alarm.md#ladder-alarms-in-add-on-instructions).

[String conversions](docs/string-conversions.md) add LOWER/UPPER and STOR/RTOS
in ladder and Structured Text, including user strings and existing AOI bindings.
**String lab** demonstrates case conversion, decimal/REAL exchange,
[DTOS with REAL tags](docs/string-conversions.md#dtos-with-real-input),
[STOD decimal parsing](docs/string-conversions.md#stod-decimal-input),
[MID copy windows](docs/string-operations.md#mid-copy-windows) and
[lazy indexed string operands](docs/string-operations.md#operand-selection).
[Ladder string MOV](docs/string-operations.md#ladder-string-mov) copies tags or
single-quoted literals and clips the result to the destination capacity.
The [six ladder string relations](docs/string-operations.md#ladder-string-comparison-literals)
also accept literals on either side. Enabled instructions can populate unknown string destinations while retaining
unused bytes; false rungs skip dynamic indices and saved operand values.

[File arithmetic](docs/file-arithmetic.md) adds FAL ALL/numeric/INC modes for
indexed array transforms, scalar accumulation and arithmetic/bitwise expressions.
**Stats lab** demonstrates full-array, scan-distributed and
[incremental transforms](docs/file-incremental.md), including
[binary64 FAL with LREAL](docs/file-arithmetic.md#binary64-expressions) and
checked REAL and integer results.

[File search](docs/file-search.md) adds FSC ALL/numeric/INC modes, match/inhibit
state and resumable searches using the existing comparison grammar. **Stats lab**
shows ALL/numeric searches and one comparison per enable edge in INC mode,
including [binary64 searches with LREAL](docs/file-search.md#binary64-searches).

[File sorting](docs/array-sort.md) adds SRT in ladder and Structured Text, with
exact integer ordering and selected array dimensions. **Stats lab** demonstrates
ladder enable edges and ST sorting on each executed call. [Sorting references
and AOIs](docs/sort-references.md) add alias/indirect starts, one/two/three-dimensional
InOut/local arrays and conservative ST FOR write protection. Choose **AOI sort lab**
to compare independent instances and selected axes.

[Statistics references and AOIs](docs/statistics-references.md) extend AVE/STD to
alias/indirect arrays and independent one-, two- and three-dimensional InOut/local
AOI data. Choose **AOI statistics lab** to compare latched means, deviations and
selected axes.

[Array statistics](docs/array-statistics.md) add ladder AVE and sample STD with
REAL sample deviation and SINT/INT/DINT/REAL averages, including nearest-even
integer conversion and range rollback. **Stats lab** demonstrates averages,
deviation, row/column selection and CONTROL rearming.

[Integer expressions](docs/integer-expressions.md) add exact narrow division in
ST/CPT/CMP and FAL/FSC consumers. **Math lab** compares truncation, remainder,
REAL promotion and cross-language results.

[Common ladder math](docs/math-operations.md) now accepts SINT/INT/DINT/REAL
results, with ties-to-even integer rounding and transactional range checks.
**Math lab** demonstrates integer roots and halfway results. The profile includes
ladder SQR, XPY, logs, angle
conversions and trigonometry. **Math lab** compares ladder, CPT and ST values,
including the v35 absolute-value rule for negative square-root inputs. The twelve
standalone ladder math instructions validate dynamic indices structurally and
skip their values while false or in prescan. Set `MathIndex` to 1 and enable
`IndexedMath` to try selected root/power writes into unknown result arrays.

[REAL ladder bitwise operands](docs/scalar-math.md#real-operands-in-ladder-bitwise-instructions)
round to DINT before AND, OR, XOR and NOT, with optional REAL results.
Enable RealBitwise in **Bit lab** to see the conversions. The
[LREAL forms](docs/scalar-math.md#lreal-operands-in-ladder-bitwise-instructions)
use signed LINT and demonstrate exact integer results above 2^53.
[Mixed floating and integer forms](docs/scalar-math.md#mixed-floating-and-integer-bitwise-operands)
include unsigned results and typed integer immediates.

[Basic scalar arithmetic and bitwise operations](docs/scalar-math.md) validate
unknown values structurally, skip false-rung operands and establish full numeric
destinations. Integer-tag `AND`/`OR`/`XOR`/`NOT` mix all eight signed/unsigned
integer types using declared widths, zero extension and destination low bits.
Enable `MixedBitwise` in **Bit lab** for exact 64-bit and signed/unsigned examples.
`BitwiseWidths` shows narrow cases. `WideMaskEnabled` demonstrates
[plain 32-bit masks with wide tags](docs/typed-bitwise-operands.md#plain-immediates-with-wide-tags),
including MEQ. Enable
`BasicMath` in **Math lab** for eleven common operations.
[Widening integer arithmetic](docs/scalar-math.md#widening-integer-tag-arithmetic)
allows mixed integer tags when the destination covers every source type range.
Enable `MixedArithmetic` in **Integer lab** for exact LINT/DINT and unsigned
examples across ADD/SUB/MUL/DIV/MOD/NEG/ABS. Enable `ArithmeticConstants`
for mixed tag/constant examples: signed DINT literals must fit the destination,
while the destination covers every source tag type's full range.
Ladder `MOD` also supports finite REAL sources mixed with SINT/INT/DINT and
representable narrow integer results. Enable `RealModulo` for fractional
remainders and rounded results; zero divisors retain the model's rollback policy.

[Numeric move and clear](docs/numeric-storage.md) support signed/unsigned integer
and REAL scalar MOV conversions, typed CLR zeros and full writes to unknown
destinations. Enable `MoveNumeric` in **Data lab** to try the examples.

[Ladder contacts and coils](docs/bit-logic.md) allow unknown BOOL values during
validation, establish complete coil values and read one-shot history only when
needed. **Bit lab** adds contact, latch and rising/falling pulse examples.

[Numeric ladder comparisons](docs/numeric-comparisons.md) validate unknown values
without consuming them on false rungs, including MEQ and LIM dynamic indices.
Enable `CompareEnable` in **Data lab** to try mask, range and equality tests.
Enable `MixedCompare` for signed/unsigned MEQ examples, including adjacent
64-bit values. All three operands are read-only; wide immediate restrictions remain.
[Mixed integer ordering and limits](docs/numeric-comparisons.md#mixed-integer-ordering-and-limits)
use the highest-ranked source tag type when it covers every input range. Enable
`MixedRelations` in **Integer lab** for six comparisons and three LIM examples.
[Bounded constants in mixed limits](docs/numeric-comparisons.md#bounded-constants-in-mixed-limits)
can occupy any LIM operand position. Enable `RelationConstants` for eight examples.
[Mixed integer CMP conditions](docs/ladder-wide-expressions.md#mixed-integer-cmp)
combine exact comparisons with Boolean logic. Enable `MixedConditions` for eight examples.
[Numeric CPT/CMP selection](docs/integer-expressions.md#operand-selection) keeps saved
unknowns and dynamic indices dormant on false rungs. **Ladder wide expression lab**
adds an `ExecuteIndexed` section for full writes, faults and recovery.
[Mixed expression arithmetic](docs/ladder-wide-expressions.md#mixed-integer-arithmetic)
adds CPT/CMP calculations with explicit intermediate checks. Enable
`MixedExpressionMath` in that lab for nine examples.

[Array size and truncation](docs/size-truncate.md) add selected array/string DATA
size reads, lazy unknown-value handling and signed/unsigned TRN results. In
**Data lab**, enable `InspectData` to see these forms.

[Numeric file fills](docs/numeric-fill.md) add integer narrowing/sign extension,
structural validation and lazy operand reads for FLL. In **Data lab**, enable
FillNumeric to compare guarded byte, word, signed and rounded REAL fills.

[Numeric conversions](docs/numeric-conversions.md) support 8/16/32/64-bit packed BCD.
All eight integer types work as ladder FRD/TOD sources and destinations.
**Conversion lab** adds gated byte/word round trips with signed packed bits.
TOD accepts all eight integer source types into DINT/UDINT/LINT/ULINT; FRD decodes
those packed types into representable signed/unsigned integer results. Enable
`WideConversions` in **Conversion lab** for exact 16-digit signed/unsigned round
trips and weighted hexadecimal nibbles. The profile also includes
INT/DINT SWPB byte ordering in ladder, with SWPB also available in ST. Choose
**Conversion lab** to inspect packed BCD, byte orders and sign extension.
The ladder forms validate dynamic indices structurally and skip live operands
while false or in prescan. Set `ConversionIndex` to 0 and enable
`IndexedConversions` for selected BCD round-trip and byte-swap results.

[CONTROL, bit shifts and FIFO](docs/control-operations.md) add BSL/BSR, numeric
FFL/FFU, LFL/LFU and CONTROL reset with explicit edge and bounds rules;
[matching string/UDT payloads](docs/record-queues.md) extend the queue forms.
[Alias and indirect array starts](docs/queue-references.md) now work in these
ladder shift/queue forms for v35 5580. **Queue reference lab** demonstrates
changing windows, aliases, edge suppression and rollback.
[AOI queue execution](docs/aoi-queues.md) adds selected one-dimensional InOut
and saved local arrays, scoped indices and disjoint instance storage. Choose
**AOI queue lab** to compare two independent queue/stack/shift instances.
[AOI FAL/FSC execution](docs/aoi-file-operations.md) adds bounded ALL, numeric
and INC transforms/searches with per-CONTROL progress. **AOI file lab** shows
two independent scaled arrays, local scratch data and match inhibition.
Choose **Control lab** to inspect shifts and queues. **Sequence lab** demonstrates
a stack plus [DINT SQO/SQI/SQL](docs/sequencer-operations.md) for masked pattern
outputs, feedback comparison and teaching a table. [Sequencer references and AOIs](docs/sequencer-references.md)
add alias/indirect starts, caller-scope indices and independent InOut/local tables.
Choose **AOI sequencer lab** to exercise masked outputs, teaching and feedback
through two instances.

[String search and editing](docs/string-operations.md) add FIND, INSERT and
DELETE in ladder and ST, including explicit user strings and in-place edits.
Choose **String lab** for a combined ladder/ST example.

[Masked moves and bit fields](docs/bit-transfer.md) add ladder MVM/BTD for
SINT/INT/DINT values, including mixed widths and scalar/member/array operands.
Choose **Bit lab** to try packing and extracting data. In the v35 5580 profile,
false/prescan skip saved dynamic indices; enabled transfers keep address and
preserved-bit checks. Set `TransferIndex` to 0 and enable `IndexedTransfers`
for selected full writes into unknown result arrays.
[Data transition](docs/data-transition.md) adds DINT DTR change detection,
including reference updates during prescan and false scans.
[FBC/DDT references and AOIs](docs/bit-diagnostic-references.md) add alias/indirect
starts, disjoint shared members and stable per-call result windows. Choose
**AOI bit diagnostics lab** to compare independent result lists and local/external
learning.

[File bit diagnostics](docs/file-bit-compare.md) add FBC/DDT array comparisons,
all/one-mismatch modes, result-list wrapping and selective reference learning.

[Continuous/periodic scheduling](docs/task-scheduling.md) now runs mixed
Standard tasks at deterministic simulated release times. Choose **Task lab**
in the header to try the 10/25 ms example and inspect per-task counts in
Coverage. [Instruction-only EVENT tasks](docs/event-tasks.md) have a separate
bounded profile. General CPU preemption, other event sources and Safety remain unfinished.

[Wide integer ladder execution](docs/integer-execution.md) and
[wide Structured Text](docs/wide-st.md) support homogeneous LINT/unsigned
arithmetic, comparisons and bitwise operations for the v35 ControlLogix 5580
model. **Integer lab** compares RLL/ST results and demonstrates exact
[L/U/UL integer literals](docs/st-integer-literals.md). Complete mixed-type arithmetic,
additional expression forms and native math flags remain unfinished.

[Numeric CASE selection](docs/st-case-selection.md) supports integer and REAL
expressions with immediate lists/ranges and first-match execution. **Text lab**
demonstrates float32 comparisons, overlapping ranges and late-fault rollback.

[Periodic task rate changes](docs/gsv-configuration.md#changing-a-periodic-task-rate)
use SSV with immediate GSV readback and a new release phase after the advance
commits. In **System lab**, enable ApplyFastRate to change FastTask from
10 ms to 20 ms.

[Task priority changes](docs/gsv-configuration.md#changing-a-task-priority)
use SSV and GSV for qualified Periodic and Event tasks. In **System lab**,
enable ApplySlowPriority to change SlowTask from priority 5 to 1. The next
advance uses the new order for coincident releases.

[Task watchdog settings](docs/gsv-configuration.md#changing-a-task-watchdog)
support SSV writes in exact microseconds and immediate GSV readback. In
**System lab**, enable ApplyWatchdog to change BackgroundTask's setting.
A command of zero selects the Continuous default of 5 seconds.

[Runtime task inhibition](docs/task-inhibition.md) adds SSV Task InhibitTask in
ladder and ST, live GSV readback, and rollback with task progress. **System lab**
provides independent controls for its Fast and Slow tasks.

[Program DisableFlag](docs/program-disable.md) pauses individual scheduled
Programs in ladder and ST while their Tasks continue releasing. **System lab**
demonstrates both controls, activation of a Program imported disabled, and
first-scan behavior. Ordinary Programs with an omitted Disabled field start
enabled in the emulator.

[String and UDT queues](docs/record-queues.md) extend FIFO/LIFO to complete
matching records, including custom strings, arrays and exact 64-bit fields.
Choose **Record lab** to try part tracking, a stack and a text FIFO.

[Paired MCR zones](docs/master-control.md) add controlled false scanning in
ladder and supported RLL AOIs. **Control lab** shows output clearing, retained
values, timer/counter behavior and whole-advance rollback.

[Structured Text timers](docs/st-timers.md) add TONR, TOFR and RTOR with logical
FBD_TIMER records, reset/retention, status bits and simulated elapsed time.
Choose **Timer lab** to compare on/off delays, pause/resume and fault rollback.

[Structured Text up/down counting](docs/st-counter.md) adds CTUD with logical
FBD_COUNTER records, sampled edges, reset, signed wraparound and rollback.
Choose **Counter lab** to try the count inputs and outputs.

[Structured Text edge one-shots](docs/st-oneshot.md) add OSRI/OSFI with logical
FBD_ONESHOT records, startup suppression, reached-call pulses and rollback.
Choose **Pulse lab** to try rising/falling edges and skipped calls.

[Structured Text analog scaling](docs/st-scaling.md) adds SCL with logical SCALE
records, range alarms, output limiting, status aliases and rollback.
Choose **Scale lab** to try raw/engineering ranges and invalid-range recovery.

[Structured Text signal conditioning](docs/st-signals.md) adds HLL limits, SNEG
selectable negation and SSUM weighted sums with three logical record types.
Choose **Signal lab** to combine limits, negation, selected gains and bias.

[Structured Text rate limiting](docs/st-rate-limiter.md) adds RLIM with a logical
RATE_LIMITER record, separate ramp rates, bypass and period/oversample timing.
Choose **Rate lab** to try ramps, timing diagnostics and clock rollback.

[Ladder FOR/BRK](docs/ladder-loops.md) adds indexed subroutine loops, nested
early exits, shared limits and transactional rollback. Choose **Loop lab** to try
ascending/descending ranges and conditional breaks.

[Structured Text moving statistics](docs/st-moving-statistics.md) adds MAVE
uniform/weighted averages and MSTD population deviation with logical records and
visible REAL sample queues. Choose **Moving statistics lab** to try sampling,
window changes, initialization and fault recovery.

[Structured Text maximum/minimum capture](docs/st-capture.md) adds MAXC/MINC
with retained extrema, reset baselines and transactional history. Choose
**Capture lab** to try extrema, held resets, skipped calls and fault recovery.

[Structured Text LPF software filtering](docs/st-low-pass-filter.md) adds three
filter orders with periodic/oversample timing, diagnostics and rollback. Its
bilinear recurrence is a documented software approximation; native numerical
parity remains unverified. Choose **Filter lab** to try step responses.

[Structured Text Boolean memory](docs/st-digital-memory.md) adds DFF/JKFF clocked
state and reset-/set-dominant latches with complements and transactional history.
Choose **Digital lab** to try clock edges, Clear, dominance and skipped calls.

[Structured Text accumulation](docs/st-accumulation.md) adds UPDN totals and
INTG timed integration with hold, initialization, limits, alarms and rollback.
Choose **Accumulator lab** to try both instructions. [FBD accumulation](docs/fbd-accumulation.md)
adds the same models to graphs, with an **FBD accumulation lab** for totals,
integration, initialization, holds and BOOL diagnostics.

[Structured Text process signals](docs/st-process-signals.md) adds ESEL healthy-input
selection and DERV rate of change. Choose **Process lab** to try selection modes,
Program/Operator requests, bypass, timing and fault recovery. [FBD process signals](docs/fbd-process-signals.md)
add the same ESEL/DERV models to graphs, with an **FBD process lab**.

[Structured Text curves and delay](docs/st-curves-delay.md) adds FGEN piecewise
conversion and DEDT transport delay. Choose **Curve and delay lab** to try table
switching, buffer timing/resizing, health recovery and transactional faults.

[Structured Text PI regulation](docs/st-pi-regulation.md) adds a bounded software
regulator with gain shaping, holds and output limits. Choose **Regulator lab**
for a closed-loop step response or externally supplied process feedback.

[Ladder PID](docs/ladder-pid.md) adds bounded P/PI/PID calculations, scaling,
limits, alarms and software manual tracking. [Derivative and deadband](docs/pid-dynamics.md)
include unsmoothed PV/error rates and zero-crossing output holds.
[Numeric operands and tieback](docs/pid-operands.md) add integer PV/CV and hardware
manual mode. Choose **PID lab** for independent REAL/INT loops and Boolean mode
controls. [PV tracking and inhold](docs/pid-restart.md) add manual SP tracking and
explicit output-readback initialization. [One-way PID cascade](docs/pid-cascade.md)
and [ladder AOI PID](docs/aoi-pid.md) add master/slave scaling and independent
InOut/local records; module behavior, smoothing and cascade feedback
remain unfinished.

[Numeric COP/CPS byte copies](docs/numeric-copies.md) add mixed integer/REAL bit
images, clipped lengths and preserved partial destination elements. Choose
**Byte copy lab** to inspect a packed packet and REAL/DINT roundtrips.

[FBD bitwise operations](docs/fbd-bitwise.md) adds DINT AND/OR/XOR/NOT, masked
comparison MEQ and explicit-target MVMT. Choose **FBD bitwise lab** for bit
patterns, masked merging and BOOL-driven selector/timer behavior.

[FBD comparisons](docs/fbd-comparisons.md) adds EQU/NEQ/GRT/GEQ/LES/LEQ/LIM
with finite REAL inputs, BOOL results and an **FBD comparison lab** connecting
conditions to a selector and timer.

[ST/FBD target bit moves](docs/target-bit-moves.md) adds BTDT field transfer
and ST MVMT calls. Choose **Target bit move lab** to compare both languages
with dynamic bit positions, masks and explicit target values.

[FBD conversions](docs/fbd-conversions.md) adds MOD remainder, TRN truncation and
TOD/FRD BCD conversion with typed REAL/DINT wires. Choose **FBD conversion lab**
for remainder-to-integer and packed BCD roundtrip examples.

[FBD advanced math](docs/fbd-advanced-math.md) adds roots, powers, logarithms,
angle conversion and trigonometry over the existing REAL records. Choose
**FBD advanced math lab** for connected angle conversions and domain recovery.

[FBD arithmetic](docs/fbd-arithmetic.md) adds finite REAL ADD/SUB/MUL/DIV/ABS/NEG
with typed logical records, retained prescan values and an **FBD arithmetic lab**.
Native minor-fault/overflow and math-flag behavior remain unfinished.

[FBD selector graphs](docs/function-blocks.md) add SEL/MUX, typed wires and
manual/automatic selection. Choose **FBD selector lab** to switch signal sources
and inspect the executing graph.

[FBD signal conditioning](docs/function-blocks.md) adds SCL, HLL, SNEG and SSUM
with connected enables and BOOL diagnostic outputs. Choose **FBD signal lab**
for a scale/limit/negate/sum chain.

[Stateful FBD blocks](docs/fbd-stateful.md) add TONR/TOFR/RTOR, CTUD and
OSRI/OSFI with shared clocks/edge histories and transactional rollback. Choose
**FBD timer/counter lab** to exercise pulses, counting and timer behavior.

[FBD rate limiting and extrema](docs/fbd-rate-capture.md) adds RLIM, MAXC and MINC
with shared ST history, BOOL diagnostics and the **FBD rate/capture lab**.

[FBD Boolean logic](docs/fbd-boolean.md) adds BAND/BOR/BNOT/BXOR plus
DFF/JKFF/RESD/SETD. Choose **FBD Boolean lab** for truth tables, sampled clocks
and dominant latches.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Current Support](#current-support)
- [External Device Simulation](#external-device-simulation)
- [Development](#development)
- [Roadmap](#roadmap)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

Studio5000Emulator is being built toward a custom Logix emulator, starting with
explicitly supported instructions and data types. It combines deterministic
local scans, a logic monitor, tag editing, coverage reports and protocol tracing.
Unsupported features are reported before execution where possible.

L5X execution uses Python's standard library. ACD import is optional and converts
a private copy through separately installed native tooling. The execution engine
runs independently after import and does not depend on FactoryTalk Logix Echo.

## Install

### Dependencies

- Windows and Python 3.13 for the tested source workflow.
- Optional ACD import: compatible Studio 5000/Logix Designer SDK tooling and an
  `l5xgit` converter. Configure it in **Import settings**, with
  `LOGIXLAB_CONVERTER`, or by placing `l5xgit` on `PATH`.
- Optional executable build: PyInstaller.
- Optional independent protocol probes: `pycomm3`.

```powershell
git clone --branch main https://github.com/votecoffee/Studio5000Emulator.git
cd Studio5000Emulator
.\INSTALL-AND-RUN.cmd
```

On Windows, double-click **INSTALL-AND-RUN.cmd** in the project root, or run it
as above. It finds Python 3.13 (installing it for the current user through
Windows Package Manager if needed), creates an ignored `.venv`, installs
PyInstaller there, builds the current source and opens LogixLab. Missing
dependencies require internet access. If `winget` is unavailable, install
Python 3.13 with pip and the Python launcher first.

Use `INSTALL-AND-RUN.cmd -InstallOnly` to prepare the executable without
launching a session. After setup, `START.cmd` opens the existing build;
rerun `INSTALL-AND-RUN.cmd` after updating the source to rebuild it.
ACD conversion and the optional VMware appliance need their separate setup.

No additional Python packages are needed to run L5X projects or bundled demos.
To run directly from source, use `py -3.13 -X utf8 source/launch.py`.
See [development guidance](docs/development.md) for optional tooling, including
an offline CIP capture inspector with bounded signed-envelope decoding for
connection research. Its format-4 reports preserve nested object paths and
requested attribute IDs while keeping symbols, values and raw bytes private by
default. These analysis features do not establish native Studio Go Online.
An optional [native SDK acceptance probe](docs/development.md#native-sdk-acceptance-probe)
records connection, tag-read, upload, download-preparation and online-edit attempts against the running emulator
using private ACD copies and reports.
The Linux appliance also exposes a documented subset of
[Ethernet diagnostic counters](docs/ethernet-counters.md) from its virtual NIC
driver, with unavailable diagnostic fields identified in the API.
Read-only [native inventory discovery](docs/native-inventory.md) now covers
source-checked empty I/O, alarm and Add-On Instruction catalogs.
[Data Logging and native policy diagnostics](docs/native-session-policy.md)
include acknowledgements that retain an existing source Timeline UID.
[Nested I/O Connection discovery](docs/io-connection-discovery.md) preserves
parent scope, and [native coordination](docs/programming-coordination.md)
provides an exclusive session lease and a source-backed Local link-address read.

[Source-equivalent download](docs/download-image.md#source-equivalent-installation)
validates the prepared object graph, typed values, settings and routine source
before replacing the loaded demo's interpreter state. Native compiled code stays
opaque. General replacement with another project remains unsupported.

[Remote Run/Program control](docs/controller-mode.md) starts and stops actual
scans, and local controls report the same state through the native endpoint.
[Run-entry initialization](docs/run-entry.md) rearms `S:FS` and performs bounded
prescan once per transition. Historical transfer checkpoints and their limits
are kept in the [connectivity history](docs/connectivity-history.md).

## Usage

Choose a bundled demo from **Examples** or open a complete L5X export. Check
**Coverage**, then use
**Step scan** or **Run**. Edit inputs in **Tag Watch** and inspect the logic trace.
**Program** stops continuous scans and preserves the current values. The same
state is used by native Remote Run/Program requests. Scanning runs in the app
and continues with the webpage closed.
Entering Run performs modeled prescan, which can reset non-retentive values and
execute enabled AOI Prescan routines. Repeated Run requests do not repeat it.
For supported Studio edits, select **Connectivity → Allow supported Studio edits**
before connecting. This profile replaces an existing standard RLL routine in
**Program** mode. Changes stay in memory; reload the original project to restore
its logic. Native SDK import is tested; the Studio GUI edit workflow is unverified.
The browser title and header show the running app's full timestamp version;
the header also shows the PLC endpoint IP. On Windows,
its tray icon offers
**Open app** and **Quit LogixLab**; hover over it to see the version and session
address. The icon may appear under the taskbar's hidden-icons arrow.

Use **End session** or **Quit LogixLab** to stop the app and its protocol endpoint.
Closing a browser tab leaves the app running; reopen it from the tray. `--no-tray`
disables the icon for headless runs.

Original project files are preserved. Settings and imported copies normally live
under `%LOCALAPPDATA%\LogixLab`; `--data-dir` selects another private directory.

For a separate PLC IP while Linx retains the host's port 44818, use the optional
[VMware host-only appliance](docs/vmware-appliance.md). After preparation,
`START-VM.cmd` starts it with a localhost browser tunnel and Windows tray controls.
On Windows, its SSH tunnel and helper commands run without console windows.
The appliance answers ICMP ping on its guest IP for IP-scanner discovery. See
[ping and IP scanners](docs/vmware-appliance.md#ping-and-ip-scanners) for the
network to scan. The executable, tray, browser tab and webpage use the PLC
simulator icon bundled with the app.

### CLI

Start a demo with checkout-local session storage:

```powershell
py -3.13 -X utf8 source/launch.py --sample TextLab --data-dir .local/session
```

Generate an offline coverage report:

```powershell
py -3.13 -X utf8 source/launch.py --report source/samples/TextLab.L5X
```

Start the Network Lab's read-only EtherNet/IP endpoint:

```powershell
py -3.13 -X utf8 source/launch.py --sample NetworkLab --eip-port 44818 --eip-profile logix-v35-l85e --data-dir .local/network-session
```

The HTTP UI binds to `127.0.0.1`. The protocol endpoint defaults to that address;
**Bind IP** or `--eip-bind` selects another IPv4 address belonging to this PC.
See [Linx coexistence](docs/connectivity.md#linx-coexistence-and-addresses) if
another application owns port 44818. Protocol access starts disabled unless
requested. Tag writes require **Allow tag writes** or
`--eip-writes`. Use the **Connectivity** tab to start/stop the endpoint and export
its trace. See [connectivity documentation](docs/connectivity.md) for the supported
services, identity profiles and remaining Studio handshake work.
Unsupported attribute reads now show their object, field IDs and read counts in
Connectivity, with the full bounded summary in the exported trace.
For saved upload exchanges, [Change Log sequence inspection](docs/native-change-log.md#inspect-a-saved-sequence)
checks cursor links, repeated queries and rejections offline. It keeps opaque
records separate from demonstrated history or native upload acceptance.
Linux endpoints can restart on the same IP and port after closing connected
clients; a conflicting active listener still prevents startup.

### Build an executable

```powershell
py -3.13 -m pip install pyinstaller
powershell -NoProfile -File source/build.ps1
.\dist\LogixLab.exe
```

The build places the executable under `dist/`. `START.cmd` launches that build.
Source-authored L5X demos are bundled; generated ACD files are kept local.

## Current Support

| Area | Available behavior |
| --- | --- |
| Projects | v35 L5X import; optional native ACD-to-L5X conversion on a copy |
| Execution | Supported RLL/ST forms, routine calls, AOIs and deterministic Continuous/Periodic releases and qualified immediate/deferred EVENT dispatch |
| Inspection | Coverage checks, tag watch, traces, snapshots and routine harnesses |
| EtherNet/IP | Unicast and Linux broadcast discovery, sessions, Class 3 messaging and atomic tag services |
| Connected reply sizes | Standard/Large Forward Open replies use their negotiated size up to 4,000 bytes, including sequence and signed-message overhead |
| Atomic transfers | Reads/writes, fragmented transfers and integer OR/AND mask updates |
| Structured transfers | Aligned numeric UDTs, explicit user LEN/DATA strings, packed Boolean flags and fragmented reads/writes |
| Native compatibility | Experimental anonymous metadata/tag reads and bounded Run/Program control; fresh keys, checked single/batch MACs and counters; peer authentication unverified |
| Offline protocol analysis | `0x36`/`0x37` singles, `0x38` batches, observed `0x39` transfers and `0x3A` read chunks with bounded detached assembly; decoded captures never execute |
| ACD correlation | Source-bound Change Log identifiers and TagInfo symbol IDs; controller/program instance paths use imported IDs; native SDK passes project identity comparison for the tested demo |
| Upload discovery | Existing-project SDK upload verified for bounded fixtures; a value snapshot retains Online correlation using a matching saved baseline. An Offline Program rebuild saves/reopens without that baseline and requires a download before Online. Direct general uploaded-project saving and arbitrary projects remain unfinished |
| Download preparation | Three source-checked batches, task/controller/setup metadata, Map and Change Log headers, and bounded installation with exact scalar, numeric-array, supported structure and structure-array values; general project replacement remains unsupported |
| Routine metadata | Original scoped Type/instance values, opaque source metadata, live header references and guarded ordinary RLL edit/pause/unsigned state; compiled logic and native signature verification remain unavailable |
| AOI metadata | Original definition and scoped Routine IDs, clean model state, explicit revision/vendor headers and available Routine descriptions; compiled definitions and native AOI edits remain unavailable |
| Native status | Source-checked empty I/O force/LED and SFC force status; module connections, SFC forcing and force writes remain unsupported |
| PLC message mapping | Source-checked empty PCCC mapping descriptors; configured mappings and PCCC commands remain unsupported |
| Time Sync | Source-backed PTP enable/priorities, read-only local UTC time and explicit unsynchronized/empty-port state; PTP networking remains unsupported |
| Catalog refresh | Controller class revision/inventory and source-bound comparison tokens |
| Identity revisions | Read-only virtual hardware revision and profile firmware build, alongside source-based major/minor revision |
| Controller configuration | Source-backed legacy SecurityCode, name/description and read-only pass-through configuration; limited Metadata Definition discovery; security enforcement and pass-through routing remain unsupported |
| Change detection | Explicit source mask plus a simulator-owned Audit Value; SDK mode/import updates and upload field reads verified on `.144`; State Detection signatures remain unsupported |
| Get System Value | Ladder/ST audit values and [Task/Controller settings](docs/gsv-configuration.md). Prior `.145` native acceptance applies to audit reads. Qualified Standard tasks support [inhibition](docs/task-inhibition.md), [Periodic rate changes](docs/gsv-configuration.md#changing-a-periodic-task-rate) [task priority changes](docs/gsv-configuration.md#changing-a-task-priority) and [watchdog settings](docs/gsv-configuration.md#changing-a-task-watchdog). |
| Software device metadata | Read-only location/locale and empty trusted-slot/operator state, explicitly identified as emulator defaults |
| File Manager | Read-only class discovery; reports zero emulated storage devices |
| Network metadata | Read-only CIP port/node addresses, IPv4 status/configuration, verified Linux DHCP/DNS flags and actual adapter MAC |
| Device locator | Network-triggered blinking webpage banner with timed expiry and cancellation |
| Studio online | Native SDK Go Online, bidirectional Run/Program control, Go Offline, installed scalar BOOL/SINT/INT/DINT/LINT/REAL reads and bounded source-equivalent transfers verified for demo and expanded fixtures; Studio GUI acceptance and general tag/rung monitoring remain unverified |
| Supported routine edits | Opt-in Program-mode Standard RLL replacement; consecutive SDK imports, replacement across routines and reconnection using the same updated project verified; edited L5X working-copy export |

Coverage depends on the actual project and execution scope. Preemptive/event scheduling,
motion, physical I/O, CIP Safety, FBD/SFC and broad native runtime parity remain
outside the current model. Unknown data and unsupported forms are not silently
replaced with assumed behavior.

Read the [execution model](docs/execution-model.md) before interpreting scan
results, and the [protocol contract](docs/connectivity.md) before using clients.

### External Device Simulation

The **Device I/O** tab enables queued external input writes. External monitors
read consistent cached snapshots without taking the scan lock. A separate MQTT
bridge distributes tag values and accepts atomic input batches from robot,
servo and other device simulators. Writes apply between scans, with scoped
tokens, expiry, duplicate detection and queued/applied/rejected acknowledgements.

See [setup, MQTT topics and the HTTP API](docs/device-io.md). The MQTT dependency
is optional; the app runtime remains standard-library-only. OPC UA/DDS adapters
and a SQL historian are future extensions of the same interface.

## Development

The code, public L5X fixtures, tests and browser assets are under `source/`.
Shared technical documentation is under `docs/`. Build output goes to `dist/`.
See the [community project assessment](docs/community-projects.md) for reusable
components, licensing and conversion-validation results.

Run the behavioral suite from the repository root:

```powershell
Set-Location source
py -3.13 -X utf8 -m unittest discover -s tests -v
```

With Node.js installed for development, run the dependency-free viewer checks
from the project root:

```powershell
node --test source/tests/web/logic-view.test.cjs source/tests/web/logic-values.test.cjs
```

See the [viewer architecture and planned graph editor](docs/logic-viewer.md).

Store machine-specific notes, private PLC files, settings, captures and test
receipts in ignored `.local/` storage. Generated builds and local reports are
excluded from Git. See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and repository
conventions.

## Roadmap

1. Complete and qualify ladder instruction families, operand/type forms, task and
   scan lifecycle, faults/status, arrays/strings/UDTs and ordinary AOIs. Common forms come first.
2. Complete Structured Text on the same runtime, including expressions, control
   flow, calls, AOI lifecycle and equivalent type/fault behavior.
3. After both language gates pass, expand FBD; complete its gate before SFC.
   Preserve the existing bounded graph support while this work is deferred.
4. Build generic cyclic I/O and device models, including EDS mappings, POINT I/O
   and FANUC handshakes; then virtual drive/motion execution.
5. Qualify mixed-feature projects with explicit conformance evidence.
6. Resume broader Studio uploads/downloads and the complete online-edit lifecycle.

Follow the [full-emulation tracker](https://github.com/votecoffee/Studio5000Emulator/issues/1).

The [full remaining-work inventory](docs/emulation-coverage.md) includes current
limitations and specialized controller profiles. The [milestones](docs/roadmap.md)
define acceptance gates. Preserve existing connectivity and external HTTP/MQTT
interfaces while executing this plan.

## Maintainers

[@votecoffee](https://github.com/votecoffee)

## Contributing

Questions, bug reports and pull requests are welcome through
[GitHub Issues](https://github.com/votecoffee/Studio5000Emulator/issues) and
[pull requests](https://github.com/votecoffee/Studio5000Emulator/pulls).
Please read [CONTRIBUTING.md](CONTRIBUTING.md), use minimal synthetic fixtures,
and include relevant verification with changes.

## License

[MIT](LICENSE) © 2026 votecoffee.
