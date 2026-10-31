# Roadmap

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

As of 2026-10-29, build the runtime toward complete, explicitly qualified Logix
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

Scope: L01–L05 and A01–A03. Complete common RLL/ST forms and AOI parameters and
lifecycle. Implement FBD graph execution and SFC step/action/transition execution
on the same typed memory and clock, including their stateful instruction sets.

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
