# Roadmap

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
[DINT SQO/SQI/SQL](sequencer-operations.md) add cyclic output, comparison and
teaching. Aggregate transfers, mixed types, remaining file consumers and native
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
controller settings. Runtime status/fault/timing and SSV remain open.

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
