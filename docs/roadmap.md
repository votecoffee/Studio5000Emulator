# Roadmap

Language order: **ladder → Structured Text → FBD → SFC**. Complete and qualify
ladder and ST before new FBD/SFC feature work. Existing partial language
implementations remain available; their presence does not complete these gates.

Available in `26.1106.104547` [browser module simulation controls](gsv-configuration.md#simulated-module-connection)
set Running, Faulted or Clear input from Device I/O. The panel displays
the effective state alongside the input.

Available in `26.1106.103111` [aggregate Module LEDStatus](gsv-configuration.md#simulated-module-ledstatus)
summarizes effective simulated connection states and withholds ambiguous
results. Module Status Lab shows the change from none to some Running.

Available in `26.1106.101924` [simulated module connection inputs](gsv-configuration.md#simulated-module-connection)
let ladder and ST read Running, Faulted, FaultCode and FaultInfo from an
explicit test input. Module Status Lab demonstrates fault and recovery.

Available in `26.1106.100909` [Module EntryStatus Waiting](gsv-configuration.md#named-module-status)
reports an inhibited routed dependency while preserving a module's own
Inhibited state. Module Status Lab demonstrates a parent Mode change.

Available in `26.1106.095832` [remote ControlLogix backplane Path reads](gsv-configuration.md#remote-controllogix-backplane-path)
extend qualified Ethernet routes with a remote rack slot in ladder and ST.
Module Status Lab displays the configured path to a remote input module.

Available in `26.1106.094856` [Module Ethernet Path reads](gsv-configuration.md#module-ethernet-path)
derive IPv4 routes through a 5580 embedded Ethernet port or a local EN2T/EN2TR.
Module Status Lab displays the counted route to a configured POINT I/O adapter.

Available in `26.1106.093850` [Module backplane Path reads](gsv-configuration.md#module-backplane-path)
derive a counted port-and-slot route from explicit local chassis settings.
Module Status Lab shows the written bytes and unchanged adjacent cells.

Available in `26.1106.092923` [Module Mode writes](gsv-configuration.md#named-module-status)
let ladder and ST change the inhibit and major-fault mode bits with immediate
readback and rollback. Connection and device models remain future work.

Available in `26.1106.092040` [named Module status](gsv-configuration.md#named-module-status)
reads explicit Mode bits and inhibited EntryStatus in ladder and ST. Module
Status Lab exercises both reads before connection and device models are added.

Available in `26.1106.090742` [CST and WallClockTime offset reads](wall-clock-gsv.md#coordinated-system-time)
use the application-lifetime monotonic counter, with exact word pairs and
range-checked duration destinations. System Lab demonstrates both reads.

Available in `26.1106.085056` [WallClockTime calendar records](wall-clock-gsv.md#calendar-records)
write seven declared DINT fields from the first member operand. System Lab
shows the named values and preserves the trailing field.

Available in `26.1106.073147` [ladder alarms in AOIs](ladder-alarm.md#ladder-alarms-in-add-on-instructions)
allow ALMD and ALMA to use scalar alarm records passed by reference. AOI Alarm
Lab demonstrates qualification, acknowledgment and an authored false routine.

Available in `26.1106.063931` [ladder ALMA delay interruption](ladder-alarm.md#analog-level-alarms)
restarts an unfinished level delay after a false rung and shows the delay
preset on the faceplate. An already-qualified excursion retains its delay state.

Available in `26.1105.204656` [ladder ALMA timestamps](ladder-alarm.md#analog-alarm-timestamps)
record per-condition detection and shared state changes as exact UTC
microseconds. Alarm Lab shows the timestamps in the instruction inspector.

Available in `26.1105.203755` [ladder ALMA shelving](ladder-alarm.md#analog-alarm-shelving)
gives each level and rate-of-change condition its own shelf timer. Alarm Lab
shows which conditions are shelved while their alarm detection continues.

Available in `26.1105.202538` [ladder ALMA rate of change](ladder-alarm.md#rate-of-change)
adds sampled positive and negative alarm conditions, counts, acknowledgment
and configuration diagnostics. Alarm Lab shows the live rate on the faceplate.

Available in `26.1105.200737` [ladder ALMA level alarms](ladder-alarm.md#analog-level-alarms)
add four alarm levels, directional delay, deadband, acknowledgment and
configuration diagnostics. Ladder ALMD also accepts the five-operand
neutral-text export form.

Available in `26.1105.195653` [ladder ALMD diagnostics](ladder-alarm.md#diagnostics)
keep alarm evaluation active when severity is out of range. Status reports
configuration and input quality separately, and Alarm Lab shows both.

Available in `26.1105.194612` [ladder ALMD timestamps](ladder-alarm.md#timestamps)
use WallClockTime or ProgTime, retain the first detection time through a
minimum-duration delay, and expose exact LINT values in Alarm Lab.

Available in `26.1105.193517` [ladder alarm shelving](ladder-alarm.md#shelving)
adds operator shelf and reshelf commands, manual unshelving, and expiration on
the simulated clock. Alarm Lab demonstrates acknowledgment after expiration.

Available in `26.1105.192642` [ladder alarm suppression](ladder-alarm.md#suppression)
adds program and operator commands. Alarm Lab shows that a suppressed alarm
still activates and counts, and an active alarm requests acknowledgment when
unsuppressed.

Available in `26.1105.190432` [ladder digital alarms](ladder-alarm.md) add scalar
Alarm-format ALARM_DIGITAL storage and ALMD execution. Alarm Lab demonstrates
minimum duration, latch and acknowledgment/reset, and an active-low alarm.

Available in `26.1105.185210` [MID copy windows](string-operations.md#mid-copy-windows)
enforce source DATA bounds and read only the requested bytes in ladder and ST.
String Lab demonstrates a copy from a partially populated source.

Available in `26.1105.183658` [STOD decimal parsing](string-conversions.md#stod-decimal-input)
uses the whole-number part of the first decimal in ladder and ST. String Lab
shows STOD and STOR processing the same ASCII input.

Available in `26.1105.182758` [DTOS accepts REAL tags](string-conversions.md#dtos-with-real-input)
in ladder and ST. String Lab shows how the same input produces rounded integer
text with DTOS and fractional text with RTOS.

Available in `26.1105.181607` [ladder string comparison literals](string-operations.md#ladder-string-comparison-literals)
add quoted operands to the six standalone relations. String Lab demonstrates
case, prefix ordering, and coil rollback after an invalid index.

Available in `26.1105.175855` [ladder string MOV](string-operations.md#ladder-string-mov)
adds STRING and user-string copies from tags or quoted literals. String Lab
demonstrates capacity clipping, literal punctuation and rollback.

Available in `26.1105.174720` [binary64 ladder FSC](file-search.md#binary64-searches)
adds LREAL comparisons in ALL, numeric and INC modes. Stats Lab shows the
first match, resume after IN clears, and cursor rollback after a fault.

Available in `26.1105.172023` [binary64 ladder FAL](file-arithmetic.md#binary64-expressions)
adds LREAL and mixed numeric expressions in ALL, numeric and INC modes.
Stats Lab demonstrates partial-file rollback, REAL results and integer rounding.

Available in `26.1105.170122` [plain immediates with wide tags](typed-bitwise-operands.md#plain-immediates-with-wide-tags)
add 32-bit radix masks and signed DINT constants to mixed ladder AND, OR, XOR,
NOT and MEQ. Bit Lab demonstrates low-bit selection and exact ULINT results.

Available in `26.1105.165147` [mixed floating and integer bitwise forms](scalar-math.md#mixed-floating-and-integer-bitwise-operands)
add wide/unsigned integer tags and typed integer constants alongside REAL
and LREAL. Bit Lab demonstrates exact unsigned results and scan rollback.

Available in `26.1105.163752` [LREAL ladder bitwise operands](scalar-math.md#lreal-operands-in-ladder-bitwise-instructions)
round LREAL to signed LINT before AND, OR, XOR and NOT. Bit Lab
demonstrates exact results above 2^53 and LREAL destination rounding.

Available in `26.1105.162705` [REAL ladder bitwise operands](scalar-math.md#real-operands-in-ladder-bitwise-instructions)
round REAL to DINT before AND, OR, XOR and NOT, with optional REAL results.
Bit Lab shows rounding and scan rollback when the conversion overflows.

Available in `26.1105.161302` [controller-only Module status](gsv-configuration.md#controller-only-module-status)
adds LEDStatus and ForceStatus to ladder and ST. Both support an INT or
the low word of a known DINT.

Available in `26.1105.160158` [Controller source flags](gsv-configuration.md#controller-source-flags)
read producer RPI, redundancy enablement, test-edit retention and
firmware-update inhibition from explicit project settings in ladder and ST.

Available in `26.1105.155020` [ControllerDevice Status](gsv-configuration.md#controller-device-status)
reads the emulator's Remote Program, Remote Run and fault-entry status in
ladder and ST. The Logix EtherNet/IP endpoint uses the same word encoding.

Available in `26.1105.154033` [ControllerDevice GSV](gsv-configuration.md#controller-device-identity)
reads the v35 5580 catalog name, product and firmware codes, device type and
vendor in ladder and ST. System Lab demonstrates the counted SINT name.

Available in `26.1105.152847` [object identity GSV](gsv-configuration.md#object-identity-reads)
reads Program and Routine names and emulator Task slots in ladder and ST.
Routine THIS follows nested calls. System Lab demonstrates both languages.

Available in `26.1105.151815` [Program DisableFlag](program-disable.md#scope-and-readback)
uses the existing enabled runtime default when an ordinary Program omits
Disabled. Protocol byte 19 still requires explicit source data.

Available in `26.1105.150822` [activation of imported disabled Programs](program-disable.md#enabling-an-imported-disabled-program)
supports explicitly referenced scheduled targets. Prescan waits for the first
enabled invocation and rolls back with it. System Lab includes StandbyProgram.

Available in `26.1105.145204` [Program DisableFlag](program-disable.md)
controls eligible scheduled Programs in ladder and ST. Live readback, first
scan after re-enable and rollback are covered independently of Task releases.

Available in `26.1105.144033` [LastScanTime](scan-time-gsv.md#resetting-lastscantime) and
[Task StartTime](task-start-gsv.md#resetting-task-starttime) accept known-zero
SSV sources. The resets preserve the scan maxima and interval baseline.

Available in `26.1105.142703` [Task interval resets](task-start-gsv.md#resetting-task-intervals)
clear either interval independently with a known-zero TIME or word pair.
System Lab demonstrates ladder and ST readback and transactional rollback.

Available in `26.1105.141552` [scan maximum resets](scan-time-gsv.md#resetting-maxscantime)
clear a Program or Task maximum through ladder/ST SSV from a known zero.
The reset preserves the other measurements and commits with the full advance.

Available in `26.1105.134905` [runtime Event timeout settings](event-tasks.md#runtime-timeout-settings)
add Rate and EnableTimeOut SSV, immediate GSV readback and transactional
deadline changes. Event Lab includes runtime controls for its fallback task.

Available in `26.1105.110205` [configured Event timeouts](event-tasks.md#configured-timeouts)
schedule instruction-only fallback releases on the simulated clock, rearm after
completion and latch Status bit 1. Event lab includes a 35 ms example.

Available in `26.1105.104728` [Task Watchdog settings](gsv-configuration.md#changing-a-task-watchdog)
support exact DINT microseconds, Continuous/Periodic zero-write defaults and
live GSV readback. Task watchdog expiration and fault handlers remain open.

Available in `26.1105.103707` [Periodic and Event Task Priority](gsv-configuration.md#changing-a-task-priority)
accepts SSV INT writes with immediate GSV readback. Committed priorities govern
the next advance's release and Event order. System Lab shows SlowTask promotion.

Available in `26.1105.102326` [Periodic Task Rate](gsv-configuration.md#changing-a-periodic-task-rate)
supports whole-millisecond runtime changes through SSV and live GSV readback.
Changed periods start a new phase at the successful advance boundary.

Available in `26.1105.100847` [typed clock and timing GSV](time-date-storage.md#reading-timestamps-and-durations-with-gsv)
writes DT clock and Task start timestamps, TIME intervals and TIME32 scan
durations. System Lab shows the live UTC clock alongside committed measurements.

Available in `26.1105.094954` [exact time ADD and SUB](time-date-storage.md#exact-time-arithmetic)
handle durations, timestamp offsets and signed elapsed time. Data Lab
demonstrates a one-nanosecond timestamp difference.

Available in `26.1105.093801` [exact temporal operands](time-date-storage.md#exact-mixed-operands)
add same-family moves and comparisons and a raw LINT/LDT bridge. The ladder
inspector shows exact parsed time literal ticks.

Available in `26.1105.091610` [time and date storage](time-date-storage.md)
adds DT, LDT, TIME32, TIME and LTIME for matching ladder MOV and relations,
plus CLR. Data Lab shows nanosecond timestamp ordering.

Available in `26.1105.085827` [literal CONTROL initialization](control-operations.md#literal-len-and-pos-on-import)
seeds LEN/POS for sixteen ladder forms, including both FBC/DDT backing records.
Control lab demonstrates BSL and a shared FFL/FFU record.

Available in `26.1105.084258` [literal timer and counter initialization](ladder-timers.md#literal-presets-on-import)
seeds PRE/ACC for directly addressed records on Standard ladder import. Timer
lab demonstrates a retained timer seed and a signed counter seed.

Available in `26.1105.082615`: [wide integer SQR and XPY](math-operations.md#wide-integer-roots-and-powers).
Integer-only calls with a LINT or unsigned operand preserve exact input
values, check the result range and reject oversized powers before evaluation.
Integer lab includes ExactRootPower.

Available in `26.1105.081222`: [REAL math with LINT and unsigned results](real-destination-math.md#wide-and-unsigned-integer-results)
for nineteen ladder math forms. The float32 result rounds to the nearest integer
with ties to even and checked bounds. Integer lab includes RealIntegerOutputs.

Available in `26.1105.075557`: [LREAL inputs with REAL and integer results](lreal-math-literals.md#real-and-integer-results)
for nineteen standalone ladder math forms. Binary64 calculation precedes the
final destination conversion. Wide expression lab includes Binary64SourceResults.

Available in `26.1105.073842`: [typed FRD/TOD sources](numeric-conversions.md#typed-source-immediates)
and [LREAL TRN constants](lreal-truncate.md). FRD decodes the declared pattern,
TOD packs the exact integer value and TRN truncates at the selected source
precision. Conversion lab includes the gated TypedImmediateConversions routine.

Available in `26.1104.182610`: [typed bitwise operands](typed-bitwise-operands.md).
AND/OR/XOR/NOT/MEQ accept decimal L/U/UL sources under declared-width pattern
rules, mixing integer tags and legacy 32-bit immediates. Zero extension, integer
result truncation/reinterpretation, lazy operands and AOI rollback are covered.
Wide expression lab adds BitwiseOperandConstants. Other types/consumers, typed
radix and native status/fault/lifecycle parity remain separate.

Available in `26.1104.180138`: [typed integer operands](typed-integer-operands.md).
Seven integer-result arithmetic forms and seven integer comparisons accept
decimal L/U/UL constants under existing range-preserving rules. Source ranges
are checked structurally, calculation stays exact and constant-only forms work.
Wide expression lab adds IntegerOperandConstants. Narrowing, invented common
types, bitwise/MEQ/other consumers and native parity remain separate.

Available in `26.1104.174245`: [typed integers in REAL operations](real-integer-literals.md).
Decimal L/U/UL constants now work across nineteen REAL-result ladder math forms
and seven actual-REAL-tag comparisons. Declared integer ranges precede float32
conversion. LREAL inputs select [binary64](lreal-math-literals.md#real-and-integer-results).
Wide expression lab adds RealIntegerConstants.
Other result/consumer profiles, typed radix and native parity remain separate.

Available in `26.1104.172031`: [LREAL comparison constants](lreal-comparison-literals.md).
Six relations and LIM accept bounded DINT/finite REAL and decimal typed integer
or floating L/l constants when a declared LREAL tag or floating L/l literal
selects binary64. Constant-only calls, both/all operand positions, source precision,
inclusive/reversed limits, lazy selection and AOI rollback are covered. Wide
expression lab adds ComparisonConstants. Other profiles and native parity remain open.

Available in `26.1104.165922`: [LREAL standalone math constants](lreal-math-literals.md).
Nineteen arithmetic, power and unary forms accept bounded DINT/finite REAL and
decimal L/U/UL integer or floating L/l constants with a scalar LREAL result.
Declared source precision precedes binary64 calculation; selection, unknown
writes and AOI rollback retain their rules. Wide expression lab adds MathConstants.
Other result/consumer profiles, typed radix and native parity remain separate.

Available in `26.1104.164359`: [DINT radix MOV constants](radix-mov-literals.md).
Binary, octal and hexadecimal unsuffixed sources zero-fill to 32 bits and
interpret bit 31 as the signed DINT top bit before numeric conversion. The
ladder face and inspector show that source value; Wide expression lab adds
RadixMoves. Typed radix, other consumers and native parity remain separate.

Available in `26.1104.143546`: [floating constants in LREAL expressions](lreal-literals.md).
Unsuffixed decimals/scientific constants use finite REAL precision before
promotion; L/l-suffixed floating constants retain binary64 and can select the
LREAL profile without tags. Scoped parsing/caches keep generic, file, ST and
subscript consumers separate. Wide expression lab adds FloatingConstants.
Other typed forms and native numerical/status/fault/lifecycle parity remain open.

Available in `26.1104.141122`: [LREAL CPT result conversions](lreal-results.md).
LREAL expressions can store representable results in all ten numeric types.
Arithmetic stays binary64 until the final nearest-even integer or finite REAL
conversion; lazy selection, unknown full writes and AOI rollback retain their
rules. Wide expression lab adds Binary64Results. Native numerical/status/fault
behavior, broader literals and other consumers remain separate.

Available in `26.1104.134906`: [LREAL CPT/CMP expressions](lreal-expressions.md).
LREAL sources or CPT destinations select finite binary64 arithmetic, mixed
numeric tags, thirteen functions, six relations and eager Boolean composition.
Copied scalar AOI LREAL inputs/outputs retain source precision and exact output
types. Wide expression lab adds Binary64. Narrowing destinations, floating/typed
literals, other consumers and native numerical/status/fault parity remain separate.

Available in `26.1104.132555`: [integer SQR expressions](ladder-integer-roots.md).
SQR no longer forces eligible narrow CPT/CMP/FAL/FSC expressions to REAL. Each
integer root uses finite float32 input/result and nearest-even DINT conversion
before the next operator. Existing REAL/ST/alias and file/AOI behavior retains
its rules. Control lab contrasts both results. Wider forms and native numerical/
status/fault/lifecycle parity remain separate.

Available in `26.1104.130831`: [integer expression powers](ladder-integer-power.md).
CPT/CMP and FAL/FSC support SINT/INT/DINT bases and exponents with checked
DINT intermediates and exponents 0..31. Arithmetic/BCD composition, lazy
selection, file distribution and AOI rollback retain existing rules. Control
lab adds IntegerPower. Negative/larger exponents, wide forms and native
numerical/status/fault/lifecycle parity remain separate.

Available in `26.1104.123302`: [BCD FAL/FSC expressions](file-bcd.md).
Narrow FRD/TOD expressions now share the CPT/CMP conversion rules in file
transforms/searches. ALL/numeric/INC distribution, held/done/inhibit paths,
canonical progress, copied AOI bindings and atomic recovery retain their
existing contracts. Control lab adds BcdFiles examples. Broader types/languages,
saved active INC and native conversion/cursor/fault/lifecycle parity remain separate.

Available in `26.1104.120940`: [BCD CMP expressions](cmp-bcd.md).
FRD/TOD compose with integer arithmetic, six relations and Boolean conditions.
Scoped parsing/caches keep file/ST consumers separate. Lazy operands, required
arguments and warm AOI conditional writes retain atomic recovery. Bit lab adds
match-coil and fault-recovery examples. Wider/REAL/string mixtures and native
conversion/status/fault/lifecycle parity remain separate.

Available in `26.1104.114926`: [BCD CPT expressions](cpt-bcd.md).
FRD/TOD use narrow signed inputs and checked DINT intermediates, complete
eight-nibble decoding and bounded packed results. Nesting, arithmetic/bitwise
composition, aliases/UDTs/indirect destinations, lazy operands and copied AOI
inputs/InOut/local state retain rollback. Bit lab adds a gated conversion routine.
Other consumers/types, math flags and native parity remain separate.

Available in `26.1104.112443`: [sequencer source types](sequencer-sources.md).
SQL/SQI use dedicated SINT/INT/DINT scalar validation and complete 32-bit source
patterns. SQL preserves signed narrow values; SQI retains the existing signed
source comparison and declared-width masks. SQO requires DINT output, and REAL/
other excluded payloads are blocked before execution. Sequence lab adds narrow
teaching/comparison and held output examples. State/lazy/AOI rollback contracts
remain; native conversion/status/fault/lifecycle parity remains separate.

Available in `26.1104.105855`: [array-index functions](array-index-functions.md).
FRD/TOD/SQR extend existing v35 5580 references with checked DINT arguments and
results, eight-nibble BCD, bounded signed packing and float32/nearest-even roots.
Nesting, arithmetic, source/destination refs, existing ST/AOI bindings, lazy
selection and rollback are covered. Viewer snapshots resolve the same forms;
Bit lab adds a gated example. Generic BCD expressions, other functions/types/
profiles and native precision/status/fault/lifecycle parity remain separate.

Available in `26.1104.102844`: [array-index expressions](array-index-expressions.md).
The v35 5580 model adds integer division and AND/OR/XOR/NOT in subscripts,
checked DINT intermediates and exact single-tag indices for all eight integer
types. Structural/lazy selection, aliases, UDT members, existing ST and warm AOI
bindings retain rollback. Bit lab demonstrates division, masks and wide indices.
Subscript functions, wide arithmetic, broader profiles and native parity remain
separate.

Available in `26.1104.100623`: [REAL-result math](real-destination-math.md).
A REAL destination selects finite float32 inputs and result for seven arithmetic
forms, XPY and eleven unary forms. All nine integer/REAL tag types and bounded
integer/finite floating constants qualify. Integer lab demonstrates corrected
DINT input rounding, wide inputs, unary/power results and independent domain/
zero/overflow/late-fault recovery. LREAL narrowing and native numerical/status/
fault/lifecycle parity remain separate.

Available in `26.1104.094330`: [REAL comparison promotion](mixed-real-comparisons.md).
Six direct relations and LIM convert all operands to finite float32 when a REAL
tag is present and no LREAL input selects binary64. All nine numeric source
types, bounded integer/finite floating constants, inclusive/reversed limits and
source preservation are covered. Integer lab demonstrates corrected DINT
rounding, collapsed bounds, wide values, literal conversion and precedence.
Integer-only ordering stays exact. Broader expressions/profiles and native
precision/status/fault/lifecycle parity remain separate.

Available in `26.1104.092011`: [LREAL arithmetic result selection](lreal-destination-math.md).
The result selects finite binary64 for seven basic math instructions and XPY
across all numeric tag types and bounded signed DINT constants. Constant-only
calls and sources without LREAL now execute. Fractional division, precision and
wide promotion rounding are explicit; comparison selection is unchanged. Integer
lab adds guarded examples and faults. Floating/typed/larger literals, other
result conversions, expressions and native parity remain separate.

Available in `26.1104.085804`: [numeric unary inputs with LREAL results](lreal-unary-sources.md).
Eleven roots/logs/angle/trig forms accept all ten numeric tag types and bounded
signed DINT constants when the destination is LREAL. Binary64 conversion, stored
REAL precision, unknown full writes, lazy operands and advance/AOI rollback are
covered. Math lab adds precision, unsigned roots and separate domain/overflow/
late-fault examples. Other result types, floating/typed/larger literals, broader
expressions and native numerical/status/fault/lifecycle parity remain separate.

Available in `26.1104.083644`: [mixed numeric LREAL powers](mixed-lreal-power.md).
XPY accepts all numeric tag pairs containing LREAL and bounded signed DINT
constants in either source position, with a LREAL result. Finite binary64 math,
precision/promotion, lazy references, full unknown writes and advance/AOI rollback
retain their rules. Math lab adds mixed/constant powers and domain/overflow/late
faults. Other advanced forms, floating/typed/larger literals, expressions and
native numerical/status/fault/lifecycle parity remain separate.

Available in `26.1104.081351`: [integer constants with LREAL](lreal-constants.md).
ADD/SUB/MUL/DIV/MOD, six direct relations and LIM accept signed DINT-range
integer constants promoted exactly to binary64. An actual LREAL source is still
required; arithmetic results stay LREAL. Lazy references, unknown full writes,
source ordering and whole-advance/AOI rollback remain covered. Integer lab adds
a gated constant section. Floating/typed/larger literals, advanced math and
expressions, other controller profiles and native parity remain separate.

Available in `26.1104.021141`: [mixed-tag LREAL comparisons](mixed-lreal-comparisons.md).
Six direct relations and LIM promote numeric tag inputs to finite binary64 when
at least one input is LREAL. Both source orders, all limit positions, inclusive/
reversed limits, read-only operands and existing lazy/rollback rules are covered.
Integer lab adds gated precision, stored-REAL, large-integer rounding and fault
examples. Immediates, CMP/ST expressions, MEQ, broader profiles and native
numerical/status/fault/lifecycle equivalence remain separate.

Available in `26.1104.020009`: [mixed-tag LREAL arithmetic](mixed-lreal-math.md).
ADD/SUB/MUL/DIV/MOD accept all ten numeric source tag types when at least one
input and the result are LREAL. Inputs promote to finite binary64 before math.
Integer lab demonstrates DINT precision, stored REAL precision, signed/unsigned
64-bit rounding and atomic fault recovery. Immediate operands, LREAL results
without a LREAL input, narrowing results, mixed comparisons/advanced math, ST/
CPT/CMP and native precision/status/fault/lifecycle parity remain separate.

Available in `26.1104.014542`: [LREAL numeric byte copies](lreal-copy.md).
COP/CPS add finite eight-byte little-endian images, mixed numeric regions and
partial-byte preservation to the existing logical clipping/budget/rollback rules.
Byte copy lab adds selected outputs, precision round trips and invalid-image/
late-fault controls. Aggregate ABI, base-tag traversal, nonfinite payloads and
native synchronization/fault/lifecycle parity remain separate.

Available in `26.1104.013306`: [LREAL ladder truncation](lreal-truncate.md).
TRN consumes REAL or LREAL tags and writes representable signed/unsigned integer
or REAL/LREAL results. Binary64 sources retain their precision before truncation;
REAL sources and untyped immediates retain float32 behavior. Math lab adds a
gated example with selected outputs and signed/unsigned boundary inputs. Existing
SIZE types, ST/FBD forms and native numerical/status/fault/lifecycle qualification
remain separate.

Available in `26.1104.011710`: [tagged LREAL advanced math](lreal-advanced.md).
SQR/XPY/LN/LOG/DEG/RAD and six trigonometric forms use finite binary64
inputs/results with matching LREAL tags. Structural/lazy selection, complete
unknown writes, alias/member/AOI arrays and advance rollback remain. Math lab
adds a gated twelve-form example with precision/domain/late-fault controls.
Mixed types/immediates, ST/CPT/CMP, newer mnemonic aliases and native numerical/
status/fault/lifecycle parity remain separate.

Available in `26.1104.005430`: [tagged LREAL ladder math](lreal-math.md).
ADD/SUB/MUL/DIV/MOD/NEG/ABS and six direct relations/LIM retain finite binary64
values through matching LREAL tags. Structural/lazy references, unknown complete
writes, selected AOI arrays and whole-advance rollback remain. Integer lab adds
gated math, comparison and zero-divisor/late-fault examples. Mixed types and
immediates, ST/CPT/CMP, advanced math and native precision/status/lifecycle parity
remain separate.

Available in `26.1104.003503`: [finite LREAL storage](lreal-storage.md).
Scalar/array/member values retain binary64 precision. Ladder MOV/CLR converts
across ten numeric types; atomic tag reads/writes use eight-byte LREAL values.
Existing permission, unknown-data, fragment and rollback checks remain. Integer
lab adds a gated precision/conversion example. LREAL arithmetic, ST expressions,
aggregate wire/copy forms and native precision/status/lifecycle parity remain
separate.

Available in `26.1105.140355`: [TIME32 Task interval word pairs](task-start-gsv.md).
Ladder and ST can read the committed minimum or maximum interval into two
contiguous TIME32 elements. Both words are checked before writing. System lab
includes ladder minimum and ST maximum examples alongside existing TIME and
DINT forms.

Available in `26.1104.001622`: [Task start/interval GSV](task-start-gsv.md).
Named/THIS ladder and ST read committed StartTime and minimum/maximum intervals
for eligible Continuous/Periodic/instruction-only Event tasks. Independent
actual host starts share prior-advance visibility, complete 64-bit output
windows and whole-advance rollback. System lab adds guarded ladder/ST examples.
These measurements do not predict simulated task rates or native performance;
SSV/time types/Safety/native visibility and lifecycle parity remain separate.

Available in `26.1103.235756`: [Event OverlapCount GSV/SSV](event-overlap-count.md).
Named and THIS ladder/ST calls read the live active-request count and reset it
from an exact known-zero DINT. Counter reset and Status clearing are independent;
resets between requests preserve later increments. Absolute commit validates
counts and retains whole-advance rollback and detached lifecycle. Event lab
adds guarded count/reset and late-fault examples. Periodic/Safety/other Event,
native overflow/protocol/status/lifecycle qualification remain separate.

Available in `26.1103.233755`: [Event task scan-time GSV](event-task-timing.md).
Qualified instruction-only Events retain independent successful last/maximum
invocation durations, with prior-advance named/THIS/ST visibility. Program THIS
also selects ordinary Event contexts. Ignored, overlapping, coalesced and
canceled requests add no timing records; initially inhibited Events can be
enabled and measured. Whole-advance rollback and detached lifecycle are retained.
Event lab adds comparison/guard/inhibition/fault examples. Native timing/status
protocols, precision, scheduling and controller equivalence remain separate.

Available in `26.1103.231834`: [runtime Event inhibition](event-task-inhibition.md).
Named and THIS SSV InhibitTask control qualified Event requests and pending
dispatch; the active body completes. Ignored work is not replayed, accepted
status stays latched, and an initially inhibited Event can be enabled then
self-inhibit. Live GSV flags and explicit Event settings support ordinary
contexts. Event lab demonstrates named controls, THIS settings and late rollback.
Other Event sources/Safety/AOI/harness and native cancellation/lifecycle parity
remain separate.

Available in `26.1103.230102`: [logical Event task Status](event-task-status.md).
GSV/SSV read and replace accepted-request/active-overlap bits in ladder/ST,
including THIS inside qualified Event tasks. Live words are latched until
cleared; pending duplicates retain coalescing. Status, values and scheduling
commit only with a successful advance. Event lab adds guarded read-clear,
THIS/named/ST and rollback examples. External events and other bits,
AOI/harness/Safety and native protocol/status/lifecycle parity remain separate.

Available in `26.1103.224555`: [multi-task scan-time GSV](scan-time-gsv.md).
Eligible Standard Continuous/Periodic Tasks retain independent last/maximum
interpreter invocation durations and execution counts. Named and ordinary THIS
reads use the previous successful advance; runtime inhibition retains counters.
Failed advances discard all uncommitted timings; routine replacement preserves
detached timing state. System lab demonstrates ladder/ST/THIS equality and
selected output guards. The existing single-Task protocol profile is unchanged;
Event/Safety timing and native timing/status/visibility parity remain separate.

Available in `26.1103.222552`: [current-instance GSV](current-instance-gsv.md).
THIS resolves to the ordinary scheduled Program or its unique Standard
Continuous/Periodic owner Task for existing settings/timing reads. Reached
calls verify active Task context; called ladder/ST routines retain their owner.
Configuration destinations now use structural/lazy preflight and complete
conservative ST FOR effects. System lab adds current-context examples. AOI,
harness, Event, empty/numeric instances, setters and native parity remain separate.

Available in `26.1103.220551`: [basic record queues](basic-record-queues.md).
Matching TIMER/COUNTER/CONTROL records and explicit UDTs containing them now
use ladder FFL/FFU/LFL/LFU. Full logical snapshots retain unknown fields; unloads
clear typed data without transferring private instruction histories. Existing
edges, bounds, aliases, exact AOI bindings and transactional rollback remain.
Record lab adds a called snapshot example. Native packed layouts, hidden state,
other operational/AOI schemas and broader language/profile parity remain separate.

Available in `26.1103.214730`: [byte/word packed BCD](numeric-conversions.md#byte-and-word-packed-bcd).
Ladder FRD/TOD accept all eight signed/unsigned integer source/destination types.
FRD weights the declared 2/4/8/16 nibbles; TOD packs within the destination
decimal capacity, retaining signed bit patterns. Lazy references, unknown full
writes, typed AOIs and transactional range/fault rollback remain. Conversion lab
adds a called byte/word example. Native saturation/status/fault equivalence,
BCD expressions, ST availability and broader FBD forms remain separate.

Available in `26.1103.213202`: [clipped aggregate operations](clipped-aggregates.md).
Matching COP/CPS and zero FLL stop at the selected logical array/member or
scalar; copies also stop at the remaining source. Complete records, unknowns,
sequential overlap, captured operands and transactional work limits remain.
Existing ST calls protect every written record in FOR analysis, with conservative
effects for changing selections. Data lab adds a called ladder example. Packed
base-tag traversal, native synchronization and lifecycle parity remain separate.

Available in `26.1103.210811`: [scan-time GSV](scan-time-gsv.md).
Program and Task LastScanTime/MaxScanTime read the preceding committed
interpreter timing snapshot in whole microseconds. Programs retain existing
scheduled-source eligibility; whole-Task last/max metrics now include independent
Standard Continuous/Periodic Tasks. Structural/lazy outputs, typed AOIs, complete conservative ST FOR
effects and timing/value rollback are modeled. System lab adds gated Program
examples. Native timing/visibility, broader fields/profiles and setters remain
separate.

Available in `26.1103.204552`: [wall-clock GSV](wall-clock-gsv.md).
Ladder and existing ST GSV calls read host UTC microseconds and seven-field
calendars, sharing the existing CIP clock. LocalDateTime requires the explicit
source UTC-local policy. Structural/lazy destinations, unknown full writes,
AOI windows and complete conservative ST FOR effects retain rollback. System
lab adds a called ladder routine and gated ST reads. Clock setters, non-UTC/DST,
Broader attributes and native parity remain separate.

Available in `26.1103.203024`: [numeric FIFO/LIFO conversions](queue-conversions.md).
FFL/LFL convert payloads to the selected queue element type; FFU/LFU convert
unloaded values to their destination type. Narrow integer sign extension,
low-bit narrowing and representable float32/nearest-even results share the
existing numeric storage model. Control lab adds a called example. Structural
selection, edges, logical boundaries, independent AOI types and transactional
rollback remain; wide types and native overflow/status/lifecycle parity remain
separate.

Available in `26.1103.201221`: [clipped numeric FLL](clipped-fills.md).
Oversized numeric requests stop at the selected logical array/member or scalar.
Source/length capture, conversions, lazy operands and rollback remain. Data lab
adds array/scalar examples. Existing emulator ST FLL calls share clipping with
complete conservative FOR write effects; native ST availability is separate.
Wide types, packed cross-member copying and native partial-effect parity remain
unqualified; aggregate zero fills now use the logical clipping documented above.

Available in `26.1103.195250`: [wide integer file operations](integer-files.md).
FAL adds exact matching LINT/unsigned transforms; FSC uses the existing wide/mixed
CMP profile. ALL, numeric and idle-source INC retain their current CONTROL and
iteration rules, including existing AOI forms. Stats lab adds exact signed and
unsigned examples. LREAL, wider literals, full FAL promotion and native status/
cursor/overflow/lifecycle parity remain separate.

Available in `26.1103.193217`: [UID/UIE interrupt control](interrupt-control.md).
Nested task-local masks defer higher-priority EVENT work until the outer UIE,
including called routines and existing ST calls. Event lab adds a gated nested
example. False/prescan and whole-advance rollback are covered. Unmatched pairs
are guarded software forms; native CPU/Periodic preemption, watchdog/fault and
persistent-state behavior remain separate.

Available in `26.1103.191933`: [indirect FOR operands](ladder-loops.md#runtime-selected-operands).
Ladder loops structurally validate runtime-selected scalar operands without
saved indices. True loops retain their selected index element for one invocation
and reselect terminal/step operands when read. Loop lab adds a gated example.
Existing types, inclusive ranges, BRK, budgets and rollback remain; native
sampling, overflow/status/lifecycle and hardware parity remain separate.

Available in `26.1103.190050`: [indirect routine arguments](indirect-routine-calls.md).
JSR callers select complete scalar/logical-record elements through runtime
indices. Structural preflight skips saved caller indices; true calls capture
input/return addresses before input copies. Existing ST calls share validation.
Call lab adds numeric and UDT examples. Exact type/dimension/count rules,
static SBR/RET, conservative overlap guards and native parity remain separate.

Available in `26.1103.184412`: [statistics operand selection](statistics-operands.md).
AVE/STD structurally validate result references without saved dynamic indices.
False and EN/DN/ER-inhibited calls skip result selection; fresh calculations
resolve actual results and full writes establish unknown elements. Stats lab
adds three called examples. Existing CONTROL/prescan, float32 calculations,
rounding, bounds, latches and native parity remain separate.

Available in `26.1103.182714`: [sequencer operand selection](sequencer-operands.md).
SQI/SQO/SQL structurally validate masks and payloads without saved dynamic
indices. False/invalid-state calls skip those operands; zero masks skip live
compared-source/output references after table checks. Held SQO/SQL still consume
live data without advancing again. Sequence lab adds a called routine. Existing
CONTROL/prescan, bounds/ER policies, algorithms and native parity remain separate.

Available in `26.1103.181119`: [CONTROL operand selection](control-operands.md).
Shift and FIFO/LIFO payloads use structural preflight and are consumed only on
paths that need data. CONTROL RES skips false/prescan live indices, establishes
unknown POS/flags, retains LEN and clears resolved modeled incremental progress.
Control lab adds a called indirect-operand routine. Existing prescan, edge/data
algorithms, runtime CONTROL reads and native parity remain separate.

Available in `26.1103.175514`: [matching aggregate COP/CPS](aggregate-copies.md).
Basic records, strings and explicit nested UDTs use structural/lazy operand
selection, captured complete windows, unknown propagation, independent storage
and scalar-member work limits. Data lab adds three gated copies. Existing ST
calls share validation; packed layouts, native clipping/private histories,
synchronization and parity remain separate.

Available in `26.1103.172122`: [declared-schema aggregate zero FLL](aggregate-fill.md).
Basic records, strings and explicit nested UDTs receive typed zero values even
when saved fields are unknown. Structural/lazy selection, captured windows and
source/length aliases, guarded records and AOI rollback are modeled. Data lab
adds four gated fills. Nonzero/REAL/wider source patterns, operational/AOI records,
packed layouts, native clipping/history resets and parity remain separate.

Available in `26.1103.165339`: [ladder timer state selection](ladder-timers.md).
TON/TOF/RTO require known nonnegative DINT PRE/ACC and only consume EN/DN when
that path needs their history. Unknown retained DN is preserved while false
and rejected when used. Existing millisecond recurrence, canonical clock
identities, prescan and rollback remain; Timer lab adds a called ladder routine.
Native clock/status/lifecycle parity and other profiles remain separate.

Available in `26.1103.163323`: [ladder counter/reset state selection](ladder-counters.md).
CTU/CTD require known DINT PRE/ACC and required BOOL history instead of treating
unknown edges as false. False counter rungs establish their own edge flag;
TIMER/COUNTER RES establishes ACC/status while preserving PRE and skips live
indices when false. Counter lab adds two ladder routines. Counter prescan still
needs actual indices; timer clocks, CONTROL RES and native parity remain separate.

Available in `26.1103.161651`: [numeric COP/CPS operand selection](numeric-copies.md#operand-selection).
Structural preflight checks types, shapes, permissions and literal bounds without
saved lengths, dynamic indices or numeric values. Reached copies retain byte
clipping, overlap, unknown/full/partial-write rules and runtime limits. Byte copy
lab adds a called ladder round trip. Existing ST calls share validation; aggregate
layouts, synchronization and native parity remain separate.

Available in `26.1103.155205`: [ladder string operand selection](string-operations.md#operand-selection).
String calls, direct string relations and string-bearing CMP validate types,
shapes and permissions without consuming saved data or dynamic indices. False
rungs and prescan skip live inputs; reached calls require source LEN/active DATA,
retain runtime range/capacity checks and can populate unknown destinations.
String lab adds six gated indexed rungs. AOI bindings and whole-advance rollback
are modeled; algorithms, encoding, broader types and native parity remain separate.

Available in `26.1103.151913`: [mixed CPT/CMP integer arithmetic](ladder-wide-expressions.md#mixed-integer-arithmetic).
Exact basic operations, unary signs and ABS use a common actual source type that
covers all source ranges. Every arithmetic subtree must contain that type; CPT's
destination matches it. Structural/lazy selection, required unknowns, full writes
and runtime/AOI rollback are modeled. The ladder expression lab adds nine gated
examples. Other intermediates, numeric bitwise mixtures, ST and native parity
remain separate.

Available in `26.1103.114348`: [numeric CPT/CMP operand selection](integer-expressions.md#operand-selection).
Structural preflight retains declared types, shapes, grammar and permissions while
allowing unknown saved operands and dynamic indices until reached. False/prescan
skip values, full CPT writes establish unknown results, true CMP remains eager,
and runtime/AOI rollback is modeled. Ladder wide expression lab adds four indexed
calculation examples. Calculations, promotion and native parity remain separate.

Available in `26.1103.113157`: [mixed integer CMP conditions](ladder-wide-expressions.md#mixed-integer-cmp).
Direct integer comparisons combine with eager Boolean logic when the highest-ranked
numeric tag type covers every tag range in the whole expression. Structural wide
CMP preflight, exact/read-only values, lazy rungs, required unknowns, AOI bindings
and runtime rollback are modeled. Integer lab adds eight gated examples. Mixed
arithmetic/bitwise/functions, broader promotion and native parity remain separate.

Available in `26.1103.111942`: [bounded constants in mixed limits](numeric-comparisons.md#bounded-constants-in-mixed-limits).
LIM accepts signed-DINT integer constants in Low, Test or High alongside mixed
integer tags, without relaxing complete tag ranges or unsigned representability.
Exact/read-only values, lazy selection, required unknowns, AOI bindings and
runtime rollback are modeled. Integer lab adds eight gated examples. Larger,
typed and REAL constants, broader promotion and native parity remain separate.

Available in `26.1103.110037`: [mixed integer ordering and limits](numeric-comparisons.md#mixed-integer-ordering-and-limits),
for standalone EQU/NEQ/LES/LEQ/GRT/GEQ/LIM. The highest-ranked declared tag type
must cover all complete operand ranges; numeric values and 64-bit precision
remain exact. Read-only/constant/alias/AOI sources, lazy selection and atomic
rollback are modeled. Integer lab adds nine gated examples. Lossy signed/unsigned
conversion, wide mixed literals, REAL/LREAL and native parity remain separate.

Available in `26.1103.103340`: [bounded arithmetic constants](scalar-math.md#bounded-arithmetic-constants),
for widening ladder ADD/SUB/MUL/DIV/MOD forms. Constants are signed-DINT integers
representable in the destination; source tags retain full-range type checks.
Both operand positions, exact integer results, lazy selection, unknown writes,
AOI bindings and rollback are modeled. Integer lab adds eight gated examples;
larger/typed/REAL literals and broader promotion remain separate.

Available in `26.1103.101035`: [widening integer tag arithmetic](scalar-math.md#widening-integer-tag-arithmetic),
for standalone ladder ADD/SUB/MUL/DIV/MOD/NEG/ABS. Mixed tag types are accepted
when the destination covers every complete source type range. Integer-exact
results, false/prescan selection, unknown writes, AOI binding and rollback remain.
Integer lab adds eight gated examples; mixed literals, narrowing, signed-to-
unsigned/REAL promotion and native status/fault parity remain separate.

Available in `26.1103.095341`: [scoped monitoring and label navigation](logic-viewer.md#instruction-presentation),
with program-local shadowing, AOI InOut aggregate resolution, exact snapshot-only
value lookup and JMP-to-LBL links through the inspector, double-click or Ctrl+Enter.
The viewer remains read-only; runtime execution coverage is unchanged.

Available in `26.1103.093714`: [AOI and instruction faceplates](logic-viewer.md#instruction-presentation),
with definition/instance headers, named and visible AOI parameters, Input/Output/
InOut markers, EN/ENO status, definition-logic navigation, built-in titles and
operands, saved TIMER/COUNTER/CONTROL members, and measured full-row layouts.
This changes read-only presentation; instruction execution coverage is unchanged.

Available in `26.1103.084226`: [Studio-style logic documents](logic-viewer.md),
ladder contact/coil symbols, rails and explicit branch wiring, read-only node
selection and operand details, exact values, zoom/fit, ST highlighting/call
navigation and FBD pins. The ladder graph separates nodes/ports/edges, source
mapping, layout and monitoring. Offline node and wire authoring is planned.

Available in `26.1103.082411`: [32/64-bit BCD conversions](numeric-conversions.md#exact-64-bit-bcd),
DINT/UDINT/LINT/ULINT packed words, sixteen-digit wide capacity, exact signed/
unsigned patterns, representable results and existing aliases/AOI rollback.
Conversion Lab adds `WideConversions`. FRD/TOD 8/16-bit packed forms, saturation,
flags and native calculation/fault/lifecycle parity remain unfinished.

Available in `26.1103.081017`: [mixed integer-tag MEQ](numeric-comparisons.md#mixed-integer-tag-widths),
all eight signed/unsigned integer input types, zero-filled declared patterns,
read-only constants and exact 64-bit masks. Data Lab adds `MixedCompare`.
Wide immediate restrictions and arithmetic promotion remain separate; native
status/fault/lifecycle/layout parity remains unqualified.

Available in `26.1103.075330`: [mixed integer-tag bitwise forms](scalar-math.md#mixed-integer-tag-widths),
all eight signed/unsigned integer tag types for AND/OR/XOR/NOT, zero extension,
exact 64-bit values and typed destination bits. Bit Lab adds `MixedBitwise`.
Wide immediate forms retain homogeneous restrictions; arithmetic promotion,
floating-point bitwise and native status/fault/layout qualification remain open.

Available in `26.1103.073819`: [FRD/TOD/SWPB operand selection](numeric-conversions.md#operand-selection),
structural index preflight, false/prescan operand skips, actual true-call checks
and full writes to unknown results. Conversion Lab adds indexed round trips and
byte swapping. Type/calculation/range contracts and native status/fault/layout
boundaries remain unchanged.

Available in `26.1103.072635`: [MVM/BTD operand selection](bit-transfer.md#operand-selection),
v35 5580 structural preflight, false/prescan dynamic-index skips, full unknown
writes and existing partial-bit/address requirements. Bit Lab adds indexed
transfers. Runtime bit selection/clipping and older controller paths are unchanged;
remaining forms and native fault/status/layout qualification remain open.

Available in `26.1103.071432`: [standalone math operand selection](math-operations.md#operand-selection),
structural preflight for all twelve existing forms, false/prescan dynamic-index
skips, true reached-value checks and full unknown results. Math Lab adds indexed
root/power examples. Existing finite calculations, range rollback and native
precision/status/fault/lifecycle boundaries remain.

Available in `26.1103.070406`: [SINT/INT/DINT bitwise widths](scalar-math.md#sintintdint-bitwise-widths),
source zero extension for AND/OR/XOR/NOT, complement after promotion, signed
low-bit results, full unknown writes and Bit Lab examples. Mixed wide/unsigned/
REAL forms and native status/fault/lifecycle/layout qualification remain open.

Available in `26.1103.065425`: [finite ladder REAL MOD](scalar-math.md#finite-real-remainder),
SINT/INT/DINT/REAL source/result forms, float32 input/result conversion,
dividend-sign remainders, rounded integer results and transactional recovery.
Math Lab adds `RealModulo`; wide/unsigned/LREAL mixtures and native precision/
status/minor-fault behavior remain open.

Available in `26.1102.161542`: [scalar arithmetic/bitwise operand selection](scalar-math.md),
structural preflight, false/prescan skips and full unknown destination writes for
eleven existing operations. Math Lab adds a basic-operations section; complete
promotion/width/status/native fault qualification remains open.

Available in `26.1102.160128`: [numeric MOV/CLR](numeric-storage.md), all nine
signed/unsigned integer and REAL scalar combinations, typed zeros, structural
preflight and lazy/full unknown writes. Native status/REAL overflow and remaining
LREAL/time/date/string/aggregate forms remain open.

Available in `26.1102.154916`: [contacts/coils/one-shots](bit-logic.md), structural
BOOL preflight, complete unknown-value writes and state-dependent one-shot reads.
Bit Lab adds contact/latch/edge examples; packed backing preservation and native
layout/fault/postscan/lifecycle boundaries remain explicit.

Available in `26.1102.153859`: [lazy numeric comparisons](numeric-comparisons.md),
structural preflight for six relations plus MEQ/LIM, false/prescan index/value
skips, unknown-import recovery and existing exact wide/AOI forms. Native numeric
promotion, fault/status/lifecycle and broader profile qualification remain open.

Available in `26.1102.152534`: [SIZE/TRN forms](size-truncate.md), selected
array/string DATA dimensions without leaf reads, REAL SIZE results and signed/
unsigned TRN destinations. False/prescan reads remain lazy; unknown destinations
can be established. Direct string SIZE, LREAL and native overflow/status remain open.

Available in `26.1102.151103`: [numeric FLL](numeric-fill.md), integer low-bit
narrowing/sign extension, lazy source/length/index reads, full unknown-element
writes and typed AOI/local fills. Logical member bounds, representable REAL
conversion and aggregate/other-controller boundaries remain explicit.

Available in `26.1102.145714`: [BCD operand combinations](numeric-conversions.md),
SINT/INT TOD inputs, SINT/INT FRD results, exact integer round trips and range
rollback in Conversion Lab/AOIs. Packed values stay DINT; reverse width
combinations, wider types and native overflow/status behavior remain open.

Available in `26.1102.144504`: [integer AVE results](array-statistics.md),
SINT/INT/DINT rounding/range checks, canonical CONTROL-result exclusion and
Stats Lab examples. STD stays REAL-only. Existing dimension/reference/AOI/latch
contracts remain; native precision/status/fault/layout and partial POS stay open.

Available in `26.1102.143300`: [narrow integer ladder math results](math-operations.md),
covering all twelve existing math forms, float32-to-nearest-even conversion,
range rollback and Math Lab examples. Wider types, native precision/status/fault
behavior and full ladder/ST qualification remain open.

Available in `26.1102.114903`: [FBC/DDT references and AOIs](bit-diagnostic-references.md),
alias/indirect DINT windows, disjoint logical array/control members, lazy fixed
result windows and independent local/InOut learning with AOI Bit Lab. Native
address-sampling/status/fault/layout and broader AOI qualification remain open.

Available in `26.1102.113048`: [sorting references and AOIs](sort-references.md),
alias/indirect SRT windows, numeric InOut/saved local arrays, parent-array ST FOR
write protection and AOI Sort Lab. Native cursor/fault/layout and broader lifecycle
qualification remain open.

Available in `26.1102.112144`: [statistics references and AOIs](statistics-references.md),
alias/indirect AVE/STD windows, exact one/two/three-dimensional InOut and saved
local arrays, canonical binding rollback and AOI Statistics Lab. Partial POS,
integer AVE results and native lifecycle/precision/fault parity remain open.

Available in `26.1102.105414`: [sequencer references and AOIs](sequencer-references.md),
alias/indirect DINT tables, exact InOut/saved locals and disjoint instance outputs.
Caller alias suffixes now retain their program namespace. Native operand/fault
parity, broader AOI shapes and ST sequencer calls remain open.

Available in `26.1102.103932`: [one-way PID cascade](pid-cascade.md) and
[ladder AOI PID](aoi-pid.md), authored master/slave order, engineering SP scaling,
exact InOut/saved local records and independent instances with AOI PID lab.
Cascade feedback, native filtering and broader lifecycle/layout parity remain open.

Available in `26.1102.101552`: [PID manual PV tracking/inhold](pid-restart.md),
manual SP tracking, explicit readback initialization and automatic release.
Analog module handshakes/timing and exact native restart behavior remain open.

Available in `26.1102.095230`: [PID numeric operands/tieback](pid-operands.md),
SINT/INT/DINT/REAL PV/CV, explicit conversion/deadband behavior and MO hardware
manual. PID lab now has separate REAL/INT loops and Boolean mode aliases.

Available in `26.1102.093759`: [PID derivative/deadband](pid-dynamics.md),
unsmoothed PV/error rates, independent/dependent gains and output holds with or
without zero crossing. Native filtering, boundaries and lifecycle remain unqualified.

Available in `26.1102.092032`: [ladder PID P/PI](ladder-pid.md), explicit percent-error
regulation, independent/dependent gains, scaling, limits, software manual tracking
and alarms. Derivative/deadband/cascade and native solver/layout parity remain open.

Available in `26.1102.085455`: [AOI FAL/FSC](aoi-file-operations.md),
ALL/numeric/INC file transforms and searches, canonical progress, exact InOut
and represented local operands, with AOI File Lab. Native cursor/fault parity remains open.

Available in `26.1102.083150`: [ladder AOI queues and shifts](aoi-queues.md),
selected one-dimensional InOut/local arrays, scoped subscript resolution,
transactional binding rollback and AOI Queue Lab. Broader AOI/native parity remains open.

Available in `26.1102.081249`: [shift/FIFO/LIFO starting references](queue-references.md),
alias chains and bounded indirect starts with edge-sensitive index reads and
Queue Reference Lab. Separate file/sequencer and AOI starts remain unchanged.

Available in `26.1102.075653`: [ladder wide CPT/CMP/MEQ](ladder-wide-expressions.md),
homogeneous LINT/unsigned expressions, exact 64-bit comparisons and masks, with
Ladder Wide Expression Lab. Mixed conversions and native status/fault parity remain open.

Available in `26.1102.073226`: [ST/FBD BTDT/MVMT](target-bit-moves.md),
dynamic DINT bit fields and masks with explicit Target, shared records and Target
Bit Move Lab. Native flags/fault/source-excess/lifecycle/postscan parity unqualified.

Available in `26.1102.071333`: [FBD MOD/TRN/TOD/FRD](fbd-conversions.md),
finite REAL remainder, REAL-to-DINT truncation and shared DINT BCD conversion with
FBD Conversion Lab. Native saturation/minor-fault/overflow/flag parity unqualified.

Available in `26.1102.065922`: [FBD advanced math](fbd-advanced-math.md),
SQR/LN/LOG/XPY/DEG/RAD/SIN/COS/TAN/ASN/ACS/ATN over the existing REAL records, with
FBD Advanced Math Lab. Host functions/float32 boundaries; native precision/faults unqualified.

Available in `26.1031.094624`: [FBD bitwise/masked operations](fbd-bitwise.md),
AND/OR/XOR/NOT/MEQ/MVMT with signed DINT patterns, explicit-target merging and
FBD Bitwise Lab. Four logical records; native flags/lifecycle/layout unqualified.

Available in `26.1031.093331`: [FBD comparisons/limits](fbd-comparisons.md),
EQU/NEQ/GRT/GEQ/LES/LEQ/LIM with finite REAL inputs, BOOL results and FBD Comparison
Lab. Two logical records; native nonfinite/lifecycle/packed-layout parity unqualified.

Available in `26.1031.092055`: [FBD arithmetic](fbd-arithmetic.md), finite REAL
ADD/SUB/MUL/DIV/ABS/NEG, two logical math record models and FBD Arithmetic Lab.
Prescan retention; native flags/minor-fault/overflow handling remain unfinished.

Available in `26.1031.090828`: [FBD ESEL/DERV](fbd-process-signals.md), enhanced
healthy-input selection, Program/Operator requests and rate of change with FBD
Process Lab. Shared ST history and rollback; native transitions/parity unqualified.

Available in `26.1031.085701`: [FBD UPDN/INTG](fbd-accumulation.md), per-call
totals and timed integration with FBD Accumulation Lab. Shared ST history, enables,
holds, limits and diagnostic wires; native timing/lifecycle parity remains unqualified.

Available in `26.1031.084520`: [FBD RLIM/MAXC/MINC](fbd-rate-capture.md),
rate limiting and retained extrema with FBD Rate/Capture Lab. Shared ST algorithms,
enables/status wires and rollback; native timing/lifecycle parity remains unqualified.

Available in `26.1030.172212`: [Boolean FBD logic](fbd-boolean.md),
BAND/BOR/BNOT/BXOR plus DFF/JKFF/RESD/SETD, with FBD Boolean Lab. Logical records
and shared retained state; native layout/lifecycle parity remains unqualified.

Available in `26.1030.170127`: [stateful FBD blocks](fbd-stateful.md),
TONR/TOFR/RTOR, CTUD and OSRI/OSFI, with FBD Timer/Counter Lab. Shared clocks/edges,
connected enables and whole-advance rollback; native FBD timing remains unqualified.

Available in `26.1030.164452`: [FBD signal conditioning](function-blocks.md),
SCL/HLL/SNEG/SSUM, typed BOOL diagnostic wires and FBD Signal Lab. Existing ST
numerical models are shared; native FBD lifecycle/precision parity remains unqualified.

Available in `26.1030.162944`: [FBD selector graphs](function-blocks.md),
SEL/MUX logical records, typed acyclic wires and FBD Selector Lab. General FBD
execution and native ordering/lifecycle/status/fault parity remain unfinished.

Available in `26.1030.155819`: [numeric COP/CPS byte copies](numeric-copies.md),
mixed numeric images, clipped regions, partial elements and Byte Copy Lab. Native
aggregate layouts, cross-member copying and CPS synchronization remain unfinished.

Available in `26.1030.153352`: [ST PI software regulation](st-pi-regulation.md),
linear/shaped gains, holds, limits and Regulator Lab with a synthetic closed loop.
Native coefficients/thresholds/rounding/ordering remain unqualified.

Available in `26.1030.151533`: [ST curves and delay](st-curves-delay.md),
FGEN piecewise conversion and DEDT sampled delay with Curve and Delay Lab. Native
startup/precision/conditional diagnostics/resize/recovery remain unqualified.

Available in `26.1030.145913`: [ST process signals](st-process-signals.md),
ESEL selection/control requests and DERV rate of change with Process Lab. Native
startup/request/health/timing/rounding qualification remains unfinished.

Available in `26.1030.144653`: [ST accumulation](st-accumulation.md), UPDN and
INTG logical records, totals/integration/holds/diagnostics and Accumulator Lab.
Native startup, rounding and interacting-condition precedence remain unqualified.

Available in `26.1030.142312`: [ST Boolean memory](st-digital-memory.md),
DFF/JKFF/RESD/SETD logical records, edges/dominance/rollback and Digital Lab.

Available in `26.1030.140207`: [ST LPF software model](st-low-pass-filter.md),
bilinear orders 1/2/3, timed filtering/diagnostics and Filter Lab. Native discrete
recurrence and numerical parity remain open.

Available in `26.1030.134503`: [ST MAXC/MINC](st-capture.md), logical capture
records, retained extrema/reset baselines and Capture Lab.

Available in `26.1030.132924`: [ST MAVE/MSTD](st-moving-statistics.md), logical
moving-statistics records, REAL queues, sampling/resize/diagnostics and Moving Lab.

Available in `26.1030.105135`: [ladder FOR/BRK](ladder-loops.md), inclusive
indexed routine loops, nested early exits, Event isolation and Loop Lab.

Available in `26.1030.102258`: [ST RLIM](st-rate-limiter.md), logical RATE_LIMITER,
separate ramps, bypass, Periodic/elapsed and oversample timing, and Rate Lab.

Available in `26.1030.100100`: [ST HLL/SNEG/SSUM](st-signals.md), three logical
signal records, limits/diagnostics, selectable negation, weighted sums and Signal Lab.

Available in `26.1030.094109`: [ST SCL analog scaling](st-scaling.md), logical SCALE
records, finite REAL scaling, limiting/alarms/status recovery and Scale Lab.

Available in `26.1030.092825`: [ST OSRI/OSFI](st-oneshot.md), logical FBD_ONESHOT
records, rising/falling edge pulses, startup/skip/rollback behavior and Pulse Lab.

Available in `26.1030.090800`: [ST CTUD](st-counter.md), logical FBD_COUNTER
records, sampled-edge/reset/wrap behavior and Counter Lab.

Available in `26.1030.084708`: [ST TONR/TOFR/RTOR timers](st-timers.md), logical
FBD_TIMER records, elapsed-time/retention/reset/status behavior and Timer Lab.

Available in `26.1030.082637`: [FBC/DDT ladder bit diagnostics](file-bit-compare.md),
all/one-mismatch modes, result-list wrapping, reference learning and Bit Lab examples.

Available in `26.1030.081135`: [DINT ladder DTR](data-transition.md), including
prescan/false reference refresh, AOI bindings, MCR interaction and Bit Lab examples.

Available in `26.1030.074205`: [paired MCR zones](master-control.md), including
false scanning, local routine/AOI scope, validated jumps and Control Lab examples.

Available in `26.1030.070834`: [string and explicit UDT FIFO/LIFO](record-queues.md)
with whole-record copies, typed clearing, unknown-field preservation and Record Lab.

Available in `26.1030.001741`: [SSV runtime task inhibition](task-inhibition.md)
with live GSV feedback, release-boundary control, prescan correction and System Lab examples.

Available in `26.1030.000222`: [integer/REAL ST CASE](st-case-selection.md) with
finite float32 labels, lists/ranges, first-match execution and Text Lab examples.

## Current priority: emulation first

As of 2026-11-02, prioritize complete ladder, then ST, then FBD, then SFC.
Defer new FBD/SFC features until ladder and ST coverage and qualification pass.
Build the runtime toward complete, explicitly qualified Logix
emulation before expanding Studio 5000 connectivity. Keep accepted connection,
transfer and bounded edit profiles working. Do not use transfer acceptance as
a substitute for executable instruction or device behavior.

The [capability checklist](emulation-coverage.md) is the detailed remaining-work
inventory. The [instruction inventory](emulation-instructions.md) names current
RLL entries, expression-only forms and unimplemented instruction families.
All milestones below are planned capabilities, not current compatibility claims.

Track implementation in [full-emulation issue #1](https://github.com/votecoffee/Studio5000Emulator/issues/1).

## 1. Execution and data foundation

Prioritize basic, widely used features before specialized types or motion:
Continuous/Periodic execution, standard RLL/ST forms, bit/move/math operations,
timers/counters, strings, arrays, UDTs and ordinary AOIs. Next common gaps include
remaining shift/FIFO/LIFO/sequencer forms, string conversions, basic
math functions, practical fault/status behavior, then event tasks/MSG/virtual I/O.
LREAL/time expansion, advanced languages/process families, Safety and motion
follow these common execution paths.

Scope: E01–E08 and D01–D09 in the capability checklist. Use the
[222-entry predefined-type catalog](predefined-data-types.md) to track schemas,
behavior and version/controller qualification independently. Start with explicit
controller/firmware feature profiles and complete common execution semantics;
expand numeric forms and types without bypassing type checks.
Build deterministic multi-task/event scheduling and fault/status/lifecycle
semantics before relying on them in devices or motion. Expand common missing
data-manipulation, array/shift/sequencer, math and string instructions.

Available CONTROL increment: [BSL/BSR and numeric FIFO/LIFO](control-operations.md)
with logical CONTROL members, saved LEN/POS and reset.
[Matching string/UDT payloads](record-queues.md) extend the queue profile.
[DINT SQO/SQI/SQL](sequencer-operations.md) add cyclic output, comparison and
teaching. Sequencer aggregate transfers, mixed types, remaining file consumers and native
layout/status parity stay open.

Available string increment: [FIND/INSERT/DELETE in ladder and ST](string-operations.md)
with explicit user-string capacities, alias-safe source reads and rollback.
Remaining string edge cases, conversions and native status behavior stay open.

Available event increment: [instruction-only EVENT execution](event-tasks.md)
with immediate higher priorities, deferred lower/equal priorities, RLL/ST context,
separate active/pending diagnostics and rollback. Native time slicing and
pending-duplicate semantics, external triggers and CPU/status parity remain open.

Available system-value increment: [explicit Task/Controller GSV](gsv-configuration.md),
including microsecond rates/watchdogs, periodic priorities, flags, names and
controller settings. [InhibitTask](task-inhibition.md), [Periodic Rate](gsv-configuration.md#changing-a-periodic-task-rate) [Task Priority](gsv-configuration.md#changing-a-task-priority) and [Task Watchdog](gsv-configuration.md#changing-a-task-watchdog) provide bounded Standard task settings. Broader SSV and native status/fault/timing parity remain open.

Available conversion increment: [LOWER/UPPER and STOR/RTOS](string-conversions.md)
in ladder/ST with custom strings and AOI bindings. Native RTOS formatting, STOR
edge forms, wider types and math/status/fault behavior remain open.

Available arithmetic increment: [FAL ALL/numeric execution](file-arithmetic.md),
including indexed transforms, scalar accumulation and sequential writes.
[Idle-source INC](file-incremental.md) adds one iteration per enable edge.
Saved active INC, broader types/functions, AOIs and native cursor/status stay open.

Available search increment: [FSC ALL/numeric execution](file-search.md),
including match/inhibit/resume and numeric continuation on false rungs.
[Idle-source INC](file-incremental.md) adds one comparison per enable edge.
Saved active INC, broader expressions, AOIs and native cursor/status remain open.

Available sorting increment: [dimension-wise SRT in ladder/ST](array-sort.md),
including exact integer ordering and ST write effects. Native internal POS,
partial states/faults, remaining file consumers and broader references stay open.

Available statistics increment: [dimension-wise AVE/sample STD](array-statistics.md)
with REAL results and logical CONTROL transitions. Partial resume, integer AVE
results, remaining file consumers and native precision/fault/status stay open.

Available common math increment: [finite REAL-result ladder math](math-operations.md),
including roots, power, logs, angle conversions and trigonometry. Integer
destinations, wide/unsigned/LREAL inputs, FBD and native math/status parity stay open.

Available conversion increment: [DINT FRD/TOD and INT/DINT SWPB](numeric-conversions.md),
including ST SWPB and byte-order/sign-extension examples. Other BCD types, mixed
conversions, expression/FBD variants and native overflow/status behavior remain open.

Available common move increment: [MVM/BTD ladder execution](bit-transfer.md)
for SINT/INT/DINT, with mixed widths, masks and bounded fields. Native status
parity and distinct language variants remain open.

Available scheduler increment: [mixed Continuous/Periodic execution](task-scheduling.md)
with deterministic serial releases, per-Program first scans and transactional
rollback. [Instruction-only EVENT tasks](event-tasks.md) add a separate bounded
profile. General CPU preemption, other event sources and watchdog enforcement remain open.

Available expression increment: [narrow ST/CPT/CMP division](integer-expressions.md)
with exact quotients/remainders, explicit REAL promotion and FAL/FSC integration.
The complete conversion matrix and native status/fault behavior remain open.

Available numeric increment: [homogeneous wide-integer RLL execution](integer-execution.md)
for v35 ControlLogix 5580, with exact division and explicit type/profile limits.
[Homogeneous wide ST](wide-st.md) adds exact arithmetic and comparisons in
assignments/conditions with matching AOI and routine bindings. Mixed types,
broader expressions/loop forms, native flags and other targets remain open.
[Decimal L/U/UL ST literals](st-integer-literals.md) now represent full-width
constants directly; other literal formats and conversions remain unfinished.

Acceptance: focused fixtures for every type/operation/scan-mode boundary;
mixed-task ordering and fault-handler tests; unchanged saved values and clear
unsupported-feature reports. Native comparisons are identified separately.

## 2. Languages and AOIs

Scope: L01–L05 and A01–A03. First complete ladder families, operand/type forms,
scan modes, faults/status and AOI parameters/lifecycle; then complete ST
expressions, constructs and calls on the same typed memory and clock. Each gate
requires a published form-by-form coverage matrix and positive, negative,
conditional-scan and fault checks. Keep native equivalence claims evidence-bound.
After both gates pass, complete FBD graphs and stateful instructions; then SFC
steps/actions/transitions. New FBD/SFC features are deferred until those gates pass.

Acceptance: mixed-language calls, nested instances, Prescan/EnableInFalse/
Postscan, feedback and parallel-chart behavior; deterministic traces and
explicit fault cases. A parser-only implementation does not complete a language.

## 3. Device, I/O and communications simulation

Scope: I01–I10. Define a stable device model and simulation-step contract;
implement generic digital/analog I/O, produced/consumed tags, executable MSG
and cyclic EtherNet/IP. Add EDS-derived mappings with separately authored
behavior, POINT I/O models and FANUC assembly/handshake profiles. Extend the
existing HTTP/MQTT interface without putting external work in the scan path.

Acceptance: I/O data ownership, RPI/timeouts, Run/Program/fault modes, reconnects,
channel diagnostics and simulated device round trips. EDS parsing alone does
not complete device simulation; a FANUC I/O model does not execute robot programs.

## 4. Virtual motion and specialized execution

Scope: M01–M07, L05 and C04. Begin with virtual axes and deterministic trajectory
state, then single-axis moves, gearing/cams/events and coordinated motion.
Add drive/process/phase/sequence and specialty families through explicit target
profiles. Safety logic/network simulation needs a separate boundary and cannot
be presented as a certified safety controller.

Acceptance: positions/velocities/status/errors over time, interrupted and
overlapping commands, limits/homing/fault recovery, device coupling and trusted
reference comparisons where available. No physical-drive equivalence is implied.

## 5. Mixed-project qualification and usability

Scope: C01–C05 and V01–V03. Exercise realistic sanitized projects combining
tasks, languages, AOIs, UDTs/strings, messages, devices and motion. Add repeatable
snapshot/restart/replay, resource limits and useful module/axis/chart monitors.

The [graph editor foundation](logic-viewer.md#planned-node-and-wire-editor)
now provides read-only instruction nodes and power connections. Planned authoring
adds durable document identities, node insertion/connection and operand commands,
undo/redo, topology/type validation, graph-to-neutral-text round trips and explicit
save/export to new working copies. Coordinate/selection changes stay separate
from executable logic revisions. Native transfers and online authoring require
their own qualification.

Acceptance: a versioned controller/firmware capability matrix with traceable
passing/failing cases, repeatable long runs and preserved source/current values.
An overall percentage from mnemonic counts is not an acceptance criterion.

## 6. Return to Studio 5000 compatibility

After the runtime milestones, resume general uploads/downloads, direct uploaded
ACD saving, edited-project history, other-project replacement, broad GUI
monitoring and the complete pending/accept/test/untest/assemble/cancel lifecycle.
Existing bounded profiles and their known failures/unknowns stay preserved.

### Native Linx and Studio connection

The previous chronological roadmap is retained in
[native connectivity milestones](native-connectivity-milestones.md), with
[README checkpoints](native-compatibility-checkpoints.md) and
[connectivity history](connectivity-history.md). Those historical priority
statements do not override this emulation-first plan.

## VMware-independent host-only networking

Status: planned. Provide a managed private network and isolated execution backend
without requiring VMware Workstation. Prefer existing free, maintained components
before developing a network driver or TCP/IP stack.

Acceptance criteria:

- Each emulated PLC gets an independent IP and TCP/UDP port 44818 while host Linx
  continues running.
- Windows Studio/Linx can reach the PLC by IP; verify unicast discovery, then
  supported range/broadcast browsing and device location separately.
- Preserve the existing model, browser UI, Windows ACD conversion and tray
  lifecycle across networking backends.
- Support repeatable start, shutdown and cleanup without changing physical
  interface configuration or interrupting existing automation communications.
- Define and review any required administrator setup, routing or adapter changes.
- Record exact component versions, licenses and local configuration receipts;
  keep machine-specific addresses, keys and captures out of the public tree.

Candidate architectures include a Linux container backend under WSL2, a portable
QEMU appliance with a private virtual adapter, and Windows network-compartment
integration. A new adapter or VLAN alone does not supply an independent network
stack. Avoid recreating a general network-lab platform inside the emulator.

### Existing tools

Assessment date: 2026-10-17. Suitability judgments below are project design
assessments; no integration with these products has been implemented or tested.

| Tool | Cost/licensing evidence | Fit for this project |
| --- | --- | --- |
| GNS3 | Free download; open-source components use GPLv3 | Useful optional lab integration for multiple PLCs, clients and routed networks. More orchestration than a single PLC endpoint needs. |
| EVE-NG | Legacy Community Edition is free but listed as end-of-life; the current release is freemium for limited personal/non-commercial use, with paid full features | A possible external lab environment, but not the preferred dependency for a maintained, freely usable backend. |
| Containerlab | Free, open source under BSD-3-Clause | Preferred evaluation candidate among these three for repeatable container topologies and independent PLC instances. Windows uses a Linux backend, normally WSL2. |

Primary sources:

- [GNS3 downloads](https://gns3.com/) and [GNS3 GUI source/license](https://github.com/GNS3/gns3-gui).
- [GNS3 Windows/local-server guidance](https://docs.gns3.com/docs/getting-started/setup-wizard-local-server).
- [EVE-NG downloads and edition lifecycle](https://www.eve-ng.net/index.php/download/) and [published edition terms](https://www.eve-ng.net/index.php/documentation/eula/).
- [Containerlab source and BSD license](https://github.com/srl-labs/containerlab) and [Windows/WSL setup](https://containerlab.dev/windows/).

Start by evaluating a plain Linux container endpoint and host reachability.
Containerlab can add topology management when it provides useful capabilities;
it is not itself a Windows virtual-network driver. EVE-NG and GNS3 similarly do
not remove the need for an execution backend with its own network stack.

## External device simulation

Current committed snapshots and bounded queued writes provide HTTP and optional
separate-process MQTT integration. They are a foundation for device simulators,
not implemented POINT I/O, FANUC, servo or EDS behavior. See [Device I/O](device-io.md).
Device ownership, simulation-clock synchronization and optional OPC UA/DDS/
historian adapters belong to milestone 3.

## Execution coverage

Use the [complete remaining-work checklist](emulation-coverage.md) and
[instruction inventory](emulation-instructions.md) as the maintained baseline.
Add supported forms with focused tests, keep unknown/unsupported data explicit
and run broader integration checks at milestone gates.

Direct ladder CPT/CMP now accept matching decimal L/U/UL constants through the
full LINT/UDINT/ULINT ranges, including exact arithmetic, comparisons and bitwise
forms. See [integer constants](ladder-integer-literals.md). Mixed typed forms,
other consumers and native precision/status/fault/lifecycle parity remain open.

[Typed integer constants in LREAL CPT/CMP](lreal-integer-literals.md) now accept
decimal L/U/UL forms, checking declared integer range before conversion to
binary64. An LREAL tag/literal or destination must select this profile; integer
constants alone retain exact integer rules. Other consumers, typed radix forms
and native numerical/status/fault/lifecycle parity remain separate.

[Decimal L/U/UL constants in FAL/FSC](file-integer-literals.md) now cover
matching LINT/UDINT/ULINT expressions, with exact arithmetic/comparisons and
existing ALL/numeric/INC progress, lazy selection and whole-advance rollback.
Mixed typed forms, floating/radix/file-argument expansion and native parity
remain separate.

[Typed MOV constants](typed-mov-literals.md) now use decimal L/U/UL integer
sources or finite LREAL floating constants, checked before existing numeric
conversion. The viewer retains integer digits and declared literal types.
Other arguments/consumers, typed radix forms and native parity remain separate.

The observed appliance guest-address query timeout now falls through existing
MAC-matched DHCP and pinned SSH discovery. The bounded wait, endpoint/version
checks and separate shutdown-intent rules are retained. See
[appliance startup](vmware-appliance.md). This maintenance change does not expand
PLC instruction or native Studio/controller qualification.
