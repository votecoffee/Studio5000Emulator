# Roadmap

Language order: **ladder → Structured Text → FBD → SFC**. Complete and qualify
ladder and ST before new FBD/SFC feature work. Existing partial language
implementations remain available; their presence does not complete these gates.

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
pending-duplicate semantics, external triggers/timeouts and CPU/status remain open.

Available system-value increment: [explicit Task/Controller GSV](gsv-configuration.md),
including microsecond rates/watchdogs, periodic priorities, flags, names and
controller settings. Runtime status/fault/timing and broader SSV remain open; [InhibitTask control](task-inhibition.md) is available for bounded Standard tasks.

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
