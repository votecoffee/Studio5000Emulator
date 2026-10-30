# Emulation coverage and remaining work

Audited 2026-10-30; FBD selector graphs added for app `26.1030.162944`. **Full Logix emulation is not
implemented.** The current engine executes bounded RLL/Structured Text and a
limited FBD selector graph.
Development now prioritizes execution, data and simulated devices; further
Studio 5000 compatibility expansion is deferred until those foundations mature.

This inventory separates parsing/storage, execution, protocol access and native
engineering acceptance. A visible tag, exported structure, empty discovery
catalog or successful SDK transfer does not establish instruction execution.
An implemented mnemonic does not establish every operand form or scan mode.

The initial compatibility target remains Standard Logix v35, currently with an
L85E identity profile. Instruction and type availability must be qualified by
controller family, firmware and language. Specialized process, Safety and newer
firmware features are separate profiles, not implicit L85E capabilities.

## Current status

| Area | Current implementation | Remaining |
| --- | --- | --- |
| Function blocks | [Single-sheet SEL/MUX graphs](function-blocks.md), typed IRef/ORef/wires, dependency execution, enables, diagnostics and rollback | Other blocks/functions, multiple sheets, feedback/connectors, AOIs, native ordering/layout/lifecycle/status/fault and transfer/edit parity |
| Ladder (RLL) | 101 built-in dispatch entries, branches, bounded calls, [FOR/BRK loops](ladder-loops.md), [paired MCR zones](master-control.md), traces and prescan | Additional instructions, operand forms, full scan/status/fault semantics |
| Event tasks | [Instruction-only EVENT dispatch](event-tasks.md), RLL/ST, immediate higher priorities, deferred lower/equal priorities, first scans, separate active/pending diagnostics and transaction-wide limits/rollback | Native time slicing and pending-duplicate semantics, external triggers/timeouts, AOI/harness/ST FOR forms and CPU/status/fault parity |
| System values | [Explicit Task/Controller GSV settings](gsv-configuration.md), typed scalar/string destinations, existing Controller audit values and [SSV task inhibition](task-inhibition.md) | Runtime timing/status/fault attributes, broader SSV classes/forms and native execution parity |
| String conversions | [LOWER/UPPER and STOR/RTOS](string-conversions.md) in RLL/ST, ASCII byte handling and decimal/float32 exchange | Native RTOS formatting, STOR exponent/no-digit edge parity, wider types, expression operands and native status/fault behavior |
| File arithmetic | [FAL ALL/numeric modes](file-arithmetic.md) and [idle-source INC](file-incremental.md), indexed transforms, scalar accumulation and sequential writes | Saved active INC/hidden state, mixed CONTROL consumers, AOIs, broader expressions/types and native cursor/overflow/status/partial-fault parity |
| File search | [FSC ALL/numeric modes](file-search.md) and [idle-source INC](file-incremental.md), comparisons, match/inhibit/resume and false-rung numeric continuation | Saved active INC/hidden state, mixed CONTROL consumers, AOIs, broader expressions/types and native cursor/status/fault parity |
| File sorting | [SRT in ladder/ST](array-sort.md), exact numeric ordering in one selected dimension and ST call transitions | Native internal POS cursor, partial states/faults, wider types and indirect/alias/AOI starting arrays |
| Array statistics | [AVE and sample STD](array-statistics.md), one selected dimension in 1D/2D/3D numeric arrays, REAL results and CONTROL transitions | Partial POS/resume, integer AVE results, broader references and native precision/fault/status behavior |
| Common REAL math | [Twelve ladder math forms](math-operations.md), REAL results and absolute-value square roots in ladder/CPT/ST | Integer destinations, wide/unsigned/LREAL sources, FBD and native precision/math-status/nonfinite behavior |
| BCD/byte-order conversions | [DINT FRD/TOD and INT/DINT SWPB](numeric-conversions.md), with ST SWPB calls | Other BCD types, mixed conversions, expression/FBD forms and native math/fault status |
| Bit diagnostics | [DINT RLL FBC/DDT](file-bit-compare.md), all/one-mismatch modes, bit-offset results, wrapped result lists and selective reference updates | AOI/indirect/alias array starts, broader profiles and native cursor/status/fault parity |
| Data transition | [DINT RLL DTR](data-transition.md), masked comparison, true/false reference updates, lexical prescan and existing AOI bindings | Other controller profiles and native operand/status/fault parity |
| Numeric COP/CPS | [Little-endian byte copies](numeric-copies.md) across nine numeric types, clipped lengths, preserved partial elements, row-major/member arrays, budget/rollback and ST loop write effects | Native aggregate/BOOL/string/LREAL layouts, cross-member/base-tag copying, synchronization and fault/partial-effect parity |
| Masked/bit-field moves | [MVM/BTD ladder forms](bit-transfer.md) for SINT/INT/DINT, mixed widths, preserved bits and bounded fields | Wide/unsigned types, MVMT/BTDT and native status/fault parity |
| Structured Text | Assignments, conditionals, [integer/REAL CASE](st-case-selection.md), bounded loops, [homogeneous wide expressions](wide-st.md), [decimal typed constants](st-integer-literals.md), supported calls and RLL/ST calls | Complete language/functions, mixed/wide FOR/CASE/index forms, full numeric promotion, time arithmetic and aggregates |
| Function Block Diagram (FBD) | Routine kind can be identified; execution is blocked | Graph import, execution ordering, state, instructions, monitoring and validation |
| Sequential Function Chart (SFC) | Routine kind can be identified; execution is blocked | Steps, transitions, actions, qualifiers, branches, timers, reset/pause/forcing and monitoring |
| BOOL/SINT/INT/DINT/REAL | Saved values, scalar/member/array access and supported operations | Complete conversions, math flags, overflow and native edge cases |
| LINT and unsigned integers | Storage/transfers plus homogeneous RLL and [ST](wide-st.md) arithmetic/comparisons/bitwise operations in the v35 5580 profile | Mixed types/conversions, additional ST forms, wide CPT/CMP/MEQ, native math/status and other targets |
| LREAL | No built-in scalar model | 64-bit floating storage, expressions, instructions, conversions and transfers |
| DT/LDT/TIME32/TIME/LTIME | No dedicated built-in models | Typed storage, literals, units/ranges, operations, formatting, clock interaction and firmware qualification |
| PROP_INT and ST PI software profile | [PI regulation](st-pi-regulation.md), linear/shaped gains, holds, output/integral limits, initialization, timing and transactional history | Native coefficients/thresholds/rounding/ordering, RTS, FBD graphs, packed layouts, other profiles and separate PID/PIDE families |
| FUNCTION_GENERATOR/DEADTIME | [ST FGEN/DEDT](st-curves-delay.md), piecewise curves, selected tables, sampled transport delay, resizing, health recovery and transactional arrays | Native startup/conditional diagnostics/precision/resize/recovery, RTS, FBD graphs, packed layouts and other profiles |
| SELECT_ENHANCED/DERIVATIVE | [ST ESEL/DERV](st-process-signals.md), healthy high/low/median/mean/manual selection, control requests, timed rate of change, bypass and rollback | Native startup/request/health/timing/rounding qualification, RTS, FBD graphs, packed layouts and other profiles |
| UP_DOWN_ACCUM/INTEGRATOR | [ST UPDN/INTG](st-accumulation.md), per-call totals, timed integration, initialization, directional holds, limits, alarms and transactional history | Native startup/rounding/precedence, RTS, FBD graphs, packed layouts and other controller profiles |
| FLIP_FLOP_D/FLIP_FLOP_JK/DOMINANT_RESET/DOMINANT_SET | [ST Boolean memory](st-digital-memory.md), clocked data/toggle state, Clear priority, dominance, complements and transactional history | FBD graphs, packed layouts, other profiles and native startup/Run/skip/postscan/output-write/status/fault parity |
| FILTER_LOW_PASS software model | [ST LPF](st-low-pass-filter.md), explicitly chosen bilinear orders 1/2/3, Periodic/elapsed/oversample timing, bounds/status and section rollback | Native discrete recurrence/coefficients/precision/transitions, RTS, FBD graphs, packed layouts, other profiles and full lifecycle/status/fault parity |
| MAXIMUM_CAPTURE/MINIMUM_CAPTURE | [ST MAXC/MINC](st-capture.md), finite REAL extrema, held reset baselines, per-record history, skip/Run/rollback behavior | FBD graphs, packed layouts, other profiles and native initialization/reset/skip/postscan/precision/status/fault parity |
| MOVING_AVERAGE/MOVING_STD_DEV | [ST MAVE/MSTD](st-moving-statistics.md), uniform/direct-weighted averages, population deviation, REAL queues, sampling/initialization, resize/status and transactional count | FBD graphs, packed layouts, native queue/resize/hold/lifecycle/precision/status/fault parity |
| RATE_LIMITER and ST RLIM | [Rate limiting](st-rate-limiter.md), separate rates, bypass, Periodic/elapsed and explicit oversample timing, status aliases and rollback | Module timestamp mode/RTS diagnostics, FBD graphs and native timing/precision/status/layout/fault parity |
| ST signal conditioning | [HLL/SNEG/SSUM](st-signals.md), logical HL_LIMIT/SELECTABLE_NEGATE/SELECTED_SUMMER, inclusive limit alarms, selector diagnostics and weighted sums | FBD graph forms and native precision/overflow/status/layout/fault parity |
| SCALE and ST SCL | [Analog scaling](st-scaling.md), finite REAL interpolation/extrapolation, limiting, raw alarms and status aliases | FBD graph forms and native precision/overflow/status/layout/fault parity |
| FBD_ONESHOT and ST edges | [OSRI/OSFI](st-oneshot.md), rising/falling pulses, startup suppression, skipped calls and transactional history | FBD graph forms, shared-kind records and native layout/lifecycle/fault parity |
| FBD_COUNTER and ST CTUD | [Up/down counting](st-counter.md), sampled edges, reset, signed wrap, first-call/Run priming and rollback | FBD graph forms and native lifecycle/reset/flags/layout/fault parity |
| FBD_TIMER and ST timers | [TONR/TOFR/RTOR](st-timers.md), logical fields/status aliases, deterministic milliseconds, reset/retention, skipped calls and rollback | FBD graph forms, native clocks/layout/status/fault parity and other controller profiles |
| TIMER/COUNTER | Modeled TON/TOF/RTO, CTU/CTD/RES and represented fields | Other timer/counter families, all status transitions, clock/resolution/fault/overflow parity |
| CONTROL | [Logical members, shifts, FIFO/LIFO and RES](control-operations.md); [matching string/UDT records](record-queues.md); [DINT sequencers](sequencer-operations.md); scalar member access | Native packed layouts/transfers, remaining consumers/forms and full scan/status/fault parity |
| MESSAGE and other predefined types | Some exported decorated fields may be retained as data-only structures | Dedicated schemas and the asynchronous/stateful behavior of their instructions |
| UDTs | Explicit nested structures, arrays, members, selected packed bits and bounded wire layouts | Complete native layout/type rules, aggregate assignments/copies and uncommon/hidden/overlaid forms |
| STRING and user strings | Built-in STRING and explicit DINT LEN/one-dimensional SINT DATA types; CONCAT/MID, [FIND/INSERT/DELETE](string-operations.md), [ASCII case and REAL conversions](string-conversions.md) | Remaining edge/type/conversion/status/encoding behavior and built-in STRING wire profile |
| AOIs | Bounded RLL/ST definitions, nested instances, scalar Input/Output, exact-type InOut, Prescan and EnableInFalse | Remaining parameter forms, Postscan/SFC, FBD definitions, full instance lifecycle and protected definitions |
| Tasks/controller | Mixed Standard Continuous/Periodic tasks, deterministic serial releases with coincident priority order, Program/Run and per-Program first scans | General CPU preemption/time slicing, other event triggers, watchdogs, full fault handlers, restart/retention |
| Motion | Empty source-checked motion discovery only | Axis/group/coordinate models and every motion instruction family |
| I/O modules | Limited local-controller metadata; ordinary tags can be driven externally | Module backplane/adapters, cyclic I/O, channel behavior, diagnostics, forces and failures |
| POINT I/O | No POINT I/O device model | Adapter, rack/slot/channel configuration, digital/analog/specialty modules and connection lifecycle |
| FANUC robots | HTTP/optional MQTT can connect an external tag simulator | FANUC device assemblies, handshakes, robot state/faults and optional robot-simulator integration |
| EDS/AOP | No EDS parser or device-model generator | EDS import/validation, assemblies/parameters/connections and separately authored behavioral models |
| Produced/consumed tags | No executing producer/consumer model | Connections, sampling, updates, timeouts, status and peer scheduling |
| Messaging | Local explicit CIP tag access is implemented separately | Executable MSG requests, queues, paths, replies, cancellation, timeouts and error state |
| Safety/redundancy | No Safety or redundancy execution | Separate logical profiles and validation; no functional-safety certification claim |
| Studio 5000 | Bounded SDK Online/transfers/routine replacement accepted for tested fixtures | General GUI behavior, direct uploaded-project saving, replacement and complete edit lifecycle; deferred |

The [instruction inventory](emulation-instructions.md) names the implemented and
remaining instruction families. The [execution model](execution-model.md)
describes current semantics. The [roadmap](roadmap.md) sets implementation order.

## Execution and controller foundation

- [ ] **E01 — Multiple tasks:** [Continuous/Periodic serial scheduling](task-scheduling.md)
  now honors modeled releases, coincident priorities, inhibition and Program order.
  Extend [instruction-only Event tasks](event-tasks.md) to remaining triggers/queues, CPU preemption/time slicing and
  deadline behavior. Full native scheduler parity remains unfinished.
- [ ] **E02 — Simulation time:** one deterministic clock shared by instructions,
  tasks, motion, device adapters and external simulation. Support pause, step,
  accelerated execution and reproducible event ordering without wall-clock drift.
- [ ] **E03 — Task timing/faults:** watchdogs, overlaps, missed events, queueing,
  time slices and task/Program scan counters. Host performance measurements must
  remain separate from modeled controller timing.
- [ ] **E04 — Lifecycle:** power-up, warm/cold restart, retentive memory,
  initialization, task start/stop, Program/Run transitions and first/last scans.
- [ ] **E05 — Faults/status:** native-style major/minor fault records, math status
  flags, handler dispatch, clear/retry behavior and effects before a fault.
  Current whole-scan rollback is a simulator policy, not controller fault parity.
- [ ] **E06 — System objects:** extend the [Task/Controller GSV profile](gsv-configuration.md)
  to remaining attributes; extend [bounded SSV task inhibition](task-inhibition.md) to further supported forms and Program/module/clock/axis
  objects, state changes and access rules. Implement actual event/interrupt
  behavior before enabling the remaining event forms and UID/UIE.
- [ ] **E07 — Memory semantics:** aliases, scopes, constants, bit overlays,
  indirect indexing, parameter binding and asynchronous I/O updates across all
  supported types; distinguish ordinary COP from synchronous CPS behavior.
- [ ] **E08 — Source coverage:** retain complete executable L5X context, reject
  missing/protected logic clearly and preserve saved/unknown values. Continue
  optional ACD conversion on private copies. Direct native ACD interpretation
  without the converter remains a separate importer project.

## Data types and memory

The [222-entry predefined type inventory](predefined-data-types.md) records every
supplied name, current dedicated model status, controller annotation and v35
index comparison. Its [JSON catalog](predefined-data-types.json) is a maintained
backlog, not a source of invented schemas or automatically enabled behavior.

- [ ] **D01 — Full numeric operations:** extend the implemented homogeneous
  [LINT/unsigned RLL profile](integer-execution.md) to mixed types, expressions,
  conversions and all qualified targets. Add LREAL storage and operations,
  complete signed/unsigned boundaries and promotion. [Homogeneous wide ST](wide-st.md)
  covers bounded assignments/conditions; remaining ST forms, wide CPT/CMP/MEQ
  and native status semantics remain unfinished.
- [ ] **D02 — Numeric edge behavior:** overflow/truncation, carry and math flags,
  divide-by-zero, rounding, REAL/LREAL NaN/infinity/subnormal handling and
  conversions. The current engine rejects nonfinite REAL values.
- [ ] **D03 — Time types:** explicit DT, LDT, TIME32, TIME and LTIME representation;
  typed literals, display radix, units, epoch/zone rules, comparisons, arithmetic,
  conversions and transfer encoding. The installed help lists these names, but
  runtime availability still needs verification against each controller/firmware
  profile. Do not treat them as untyped LINT aliases.
- [ ] **D04 — Predefined structures:** complete the named
  [predefined-type inventory](predefined-data-types.md), including dedicated
  complete CONTROL beyond its [logical shift/FIFO/LIFO profile](control-operations.md),
  and implement MESSAGE, PID/PID_ENHANCED, alarm/filter/drive/phase/sequence records, motion
  control/axis/group/coordinate/cam records and module-defined I/O types.
  Decorated-data retention alone does not supply control behavior.
- [ ] **D05 — Timers/counters:** alternate instruction structures and reset
  variants, every enable/done/overflow/underflow transition, shared instances,
  skipped execution and timing resolution. Qualify newer forms such as TIMER_T
  separately rather than assuming v35 support.
- [ ] **D06 — UDTs:** exact member/dimension/access rules, nested structures,
  arrays of structures, packed BOOLs, hidden hosts/overlays, alignment/padding,
  import/export fidelity and layout-dependent copying. Current wire templates
  are bounded software layouts, not universal compiled controller layouts.
- [ ] **D07 — Strings:** complete STRING and custom string operations, LEN/DATA
  validity, maximum-capacity strings, arrays/nesting, ASCII conversions/search/
  editing and raw backing-byte preservation. Qualify STRING_16/STRING_32 and
  other encodings per firmware; they have no complete current runtime model.
- [ ] **D08 — Arrays/aggregates:** all supported element types and dimensions,
  whole-value assignment, type-compatible and byte-reinterpreting copies,
  overlapping regions, bounds, packed BOOL arrays and partial writes. Keep
  declared logical size separate from transport padding and byte offsets.
- [ ] **D09 — Scale limits:** qualify project/tag/array/UDT sizes and report
  deliberate simulator limits. Current examples include up to three dimensions
  and 100,000 imported array elements, with narrower 32,768-byte wire layouts.
  These are implementation limits, not claimed controller capacities.

## Languages, calls and AOIs

- [ ] **L01 — RLL:** implement the remaining mnemonics and remaining forms of
  existing ones. Verify rung-in/out, false scan, prescan, duplicate/shared
  operands, branches, jumps, skipped calls and status side effects per family.
- [ ] **L02 — ST:** complete target-version statements/operators/functions,
  the complete division/promotion matrix, remaining wide/time expressions, aggregate operations and
  instruction availability. Preserve language-specific operand ordering and
  evaluation rules; current expressions evaluate operands eagerly.
- [ ] **L03 — FBD execution:** [Single-sheet SEL/MUX graphs](function-blocks.md)
  now execute typed acyclic wires with enable/status/rollback. Complete multiple
  sheets, connectors, feedback, native execution order, retained state, sample
  periods, other FBD instructions/functions/AOIs and native transfer/edit support.
- [ ] **L04 — SFC execution:** active steps and transitions, selection/parallel
  branches, action execution/qualifiers, step timers, stored actions, stop/reset,
  restart/pause, first/last scans, Postscan, forces and cross-language calls.
  Add visual state monitoring after semantic tests exist.
- [ ] **A01 — AOI parameters:** additional compatible Input/Output aggregates,
  arrays/strings, alias and constant parameters/locals, nullable InOut, supported
  optional parameters and cross-call aliasing rules.
- [ ] **A02 — AOI lifecycle:** complete enable/disable transitions, Prescan,
  EnableInFalse and Postscan, nested instances and per-instance retained locals
  in every supported language. Hidden saved locals currently stay unknown until
  established by execution; definition defaults are not substituted.
- [ ] **A03 — AOI integration:** FBD definitions, legal routine-call forms,
  revisions/signatures/source protection, online definition/instance changes and
  native layout validation. A signature is not evidence that hidden code can
  execute; protected source needs an explicitly supported execution source.
- [ ] **L05 — Phase/sequence/process:** equipment phase and sequence state
  machines, ownership/request rules, PID/PIDE loops, filters, statistics,
  alarms/events and process-controller instruction profiles.

## Motion and drive emulation

- [ ] **M01 — Virtual axes:** axis state machine, servo on/off, shutdown/reset,
  faults, actual/commanded position and velocity, units, scaling, feedback,
  limits, homing and deterministic update periods.
- [ ] **M02 — Single-axis profiles:** MAM/MAJ/MAS/MAH, acceleration/deceleration/
  jerk, blending/merge, command acceptance/completion, aborts and instruction
  control status/errors. Add numeric trajectory reference cases.
- [ ] **M03 — Coupling/events:** gearing, electronic cams, position redefinition,
  registration, watches, output cams and event timing.
- [ ] **M04 — Groups/coordinated motion:** group state, coordinate systems,
  linear/circular/path moves, transformations, kinematics and coordinated stops.
- [ ] **M05 — Drive models:** generic drive speed/torque/state behavior, faults
  and realistic scan/cyclic-I/O handshakes; specialized drive instructions.
- [ ] **M06 — Device integration:** virtual axis/drive behavior first; external
  physics/servo/robot engines through a stable timestamped interface. Emulating
  an instruction is distinct from reproducing a particular drive's physics.
- [ ] **M07 — Specialized/Safety motion:** metal-forming and drive Safety
  instructions require separate profiles and validation. No current motion
  discovery response implies any of these behaviors.

## Modules, EDS and robot interfaces

- [ ] **I01 — Device architecture:** reusable adapter/module/device models,
  identity/keying, rack/slot topology, configuration and input/output assemblies,
  ownership, data validity and synchronized simulation updates.
- [ ] **I02 — Cyclic EtherNet/IP I/O:** actual Class 1 producer/consumer
  connections, RPI, sequence/run-idle headers, unicast/multicast, watchdogs,
  reconnects, exclusive/listen-only ownership and invalid/stale input policies.
  Current Class 3 explicit messaging is a separate implementation.
- [ ] **I03 — Generic I/O:** digital input/output, analog ranges/scaling,
  filtering, hold-last/fault/Program modes, channel quality, open-wire/overrange
  diagnostics, force tables and connection/module faults.
- [ ] **I04 — POINT I/O:** 1734 adapter/rack/slot behavior, configurable module
  profiles, digital/analog channels, specialty/high-speed modules, keying,
  configuration assemblies and module/channel fault propagation.
- [ ] **I05 — FANUC:** configurable Ethernet/IP assembly sizes and byte/bit
  mapping, UOP and ordinary I/O/group signals, start/ready/busy/complete/reset
  handshakes, acknowledgement/timeout/fault cases and optional robot simulator
  coupling. A FANUC communication profile does not execute KAREL/TP programs or
  model robot mechanics by itself; those need a separate backend if required.
- [ ] **I06 — EDS parser:** versioned device identity, parameters, data types,
  assemblies, connections, defaults, units and validation. Generate reviewable
  candidate mappings and report unsupported/vendor-specific sections.
- [ ] **I07 — Behavior beyond EDS:** attach explicit device behavior to those
  mappings; validate any AOP/module-generated types separately. An EDS describes
  interfaces and configuration, not the device's complete operating algorithm.
  EDS import must not claim automatic full device emulation.
- [ ] **I08 — MSG:** executable CIP generic/read/write services and supported
  legacy mappings, asynchronous EN/DN/ER state, queues, connection reuse,
  routing, retries/timeouts/cancel and bounded external communications.
- [ ] **I09 — Produced/consumed tags:** type/connection compatibility, rates,
  local peer simulation, connection status, timeout and restart behavior.
- [ ] **I10 — External adapters:** retain current HTTP/MQTT snapshots and queued
  writes; add device ownership/mapping, synchronized stepping and optional
  OPC UA/DDS/historian adapters without blocking the PLC scan.

## Other controller features and acceptance

- [ ] **C01 — Forcing and diagnostics:** modeled I/O/tag/SFC forces, controller
  and module indicators, fault/status records and readable provenance for values
  from logic, devices, forces or external clients.
- [ ] **C02 — Time/network services:** WALLCLOCKTIME/CST, synchronization states,
  time-zone/clock changes and PTP/CIP Sync behavior as separate validated models;
  current unsynchronized metadata does not implement PTP networking.
- [ ] **C03 — Persistence:** save/reopen full simulator state, deterministic
  restart, project replacement, migration and crash recovery while preserving
  source values and separating runtime snapshots from engineering files.
- [ ] **C04 — Specialty profiles:** Safety task/instruction logic, CIP Safety,
  redundancy, alarms/events, equipment sequencing, energy and license-related
  behavior. Controller/product-specific availability needs explicit qualification.
  Any Safety simulation remains a software test model, not a certified system.
- [ ] **C05 — Engineering/runtime protection:** source-protected code handling,
  permissions, access enforcement and diagnostic clarity for unsupported
  operations. Native security/certificate parity remains a separate project.
- [ ] **V01 — Reference validation:** sanitized fixtures for each instruction,
  type, scan mode and language; numeric/state/timing boundary tests; comparison
  to trusted native results where available. Model tests alone do not establish
  native parity, and unavailable reference evidence remains identified.
- [ ] **V02 — Practical projects:** mixed-language multi-task projects containing
  nested AOIs/UDTs, strings, messages, virtual I/O/robots and motion; long runs,
  repeatable replay, cancellation and bounded memory/resource checks.
- [ ] **V03 — User visibility:** current capability matrix and per-project
  blockers, complete traces, watch/force/device/axis views, import diagnostics
  and version consistency across source/UI/executable/appliance deliveries.

## Studio compatibility work retained for later

Existing accepted profiles and their evidence remain preserved. Further work is
deferred, rather than being counted toward full execution coverage:

- General Studio GUI path selection/Online monitoring and rung/tag displays.
- Direct save/reopen of fully reconstructed uploaded ACDs without SDK faults.
- Upload of a live-edited project, including the still-unknown Change Log record
  format; retain existing rejections and unknown outcomes until resolved.
- Arbitrary other-project download/replacement, module/motion/AOI/other-language
  transfers and persistent correlation through resets/restarts.
- Complete native online edit lifecycle: pending/accept/test/untest/assemble/
  cancel, multiple edits/clients and tag/type/AOI changes beyond the bounded
  Program-mode Standard RLL replacement profile.
- General native aggregate/member monitoring/writes and large-value transport.
  A 640/644-byte array snapshot upload passes, but the SDK's whole-array Online
  read over its observed 500-byte connection still fails normally.
- Authentication/security, virtual chassis/backplane integration and broader
  controller identity profiles. Read-only metadata is not complete device parity.

## Audit basis and maintenance

Implementation evidence: [RLL/model](../source/logixlab/model.py),
[runtime](../source/logixlab/runtime.py), [integer execution](../source/logixlab/integer_math.py), [extended instructions](../source/logixlab/extended.py),
[ST](../source/logixlab/structured.py), [ST expressions](../source/logixlab/st_expression.py),
[AOIs](../source/logixlab/addons.py), [wire templates](../source/logixlab/templates.py),
[motion catalogs](../source/logixlab/motion_catalog.py),
[message catalogs](../source/logixlab/message_catalog.py) and
[device interface](../source/logixlab/device_io.py). The existing runtime,
Structured Text, AOI, call, numeric-layout, string, task and protocol tests provide
separate model-level checks.

Instruction names were checked against the installed Studio v35 instruction-set
and A–Z indexes; vendor help files and private projects are not redistributed.
The reference list includes language aliases, SFC elements and product-specific
families; it is not a denominator for a percentage-complete claim. Instructions
added by project AOIs are counted separately from the 101 built-in RLL entries.
Update both this matrix and the instruction inventory when capabilities change.
