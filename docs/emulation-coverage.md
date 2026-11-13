# Emulation coverage and remaining work

Audited 2026-11-12 for app `26.1112.231317`; includes matching mixed-integer constants and PID record transfers. **Full Logix emulation is not
implemented.** The current engine executes bounded RLL/Structured Text and a
limited FBD signal graph.
Development prioritizes **full ladder support, then ST, then FBD, then SFC**.
New FBD/SFC features wait for ladder and ST coverage and qualification gates.
Studio 5000 compatibility expansion follows the emulation foundations.

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
| FBD bitwise records | [AND/OR/XOR/NOT/MEQ/MVMT](fbd-bitwise.md), signed DINT patterns, masked BOOL comparison and explicit-target merging | Other record operations/forms/types and native flags/lifecycle/layout/transfer qualification; existing ST MVMT calls are listed separately below |
| FBD comparison records | [EQU/NEQ/GRT/GEQ/LES/LEQ/LIM](fbd-comparisons.md), finite REAL comparisons, inclusive/reversed limits, BOOL outputs and retained prescan values | Nonfinite behavior, other types/forms, packed layouts and native lifecycle/transfer parity |
| ST/FBD target bit moves | [BTDT/MVMT](target-bit-moves.md), DINT fields/masks, dynamic positions, explicit Target, enable/prescan and transactional calls | Other types/forms, native source-excess/flags/fault/lifecycle/postscan/layout/transfer qualification |
| FBD conversion records | [TRN/TOD/FRD](fbd-conversions.md), REAL-to-DINT truncation, DINT BCD roundtrips and shared ladder calculations | Other types/forms, implicit wire conversion, native saturation/overflow/flags/fault/lifecycle/layout/transfer qualification |
| FBD math records | [Basic arithmetic](fbd-arithmetic.md) plus [SQR/LN/LOG/XPY/DEG/RAD/trig](fbd-advanced-math.md), 19 finite REAL Block forms over two records, prescan retention and transactional failures | Other math/forms/types, native precision/flags, minor-fault/domain/nonfinite/overflow/layout/lifecycle parity |
| FBD Boolean records | [BAND/BOR/BNOT/BXOR](fbd-boolean.md), strict BOOL inputs, known-value requirements and four logical types | Tagless functions and native initialization/layout/lifecycle/fault parity |
| Function blocks | [Single-sheet signal graphs](function-blocks.md), Sixty-three blocks including target bit moves, conversions/remainder, advanced math, bitwise/masked operations, comparisons, limits, basic arithmetic, enhanced selection, derivatives, accumulation, integration, rate limiting, extrema, Boolean logic, latches and timers/counter/one-shots, typed references/wires, BOOL diagnostics, enables and rollback | Other blocks/functions, multiple sheets, feedback/connectors, AOIs, native ordering/layout/lifecycle/status/fault and transfer/edit parity |
| Ladder (RLL) | 108 built-in dispatch entries, branches, bounded calls, [FOR/BRK loops](ladder-loops.md), [paired MCR zones](master-control.md), traces and prescan | Additional instructions, operand forms, full scan/status/fault semantics |
| User interrupt control | [UID/UIE](interrupt-control.md), balanced task-local nesting in RLL/ST, queued EVENT requests, outer-UIE priority drain, called routines and transactional guards | Native unmatched/persistent-state behavior, CPU/Periodic preemption, latency, watchdog/fault/Safety/AOI/harness and other profiles remain separate |
| Event tasks | [Instruction-only EVENT dispatch](event-tasks.md), RLL/ST, [configured and runtime timeouts](event-tasks.md#runtime-timeout-settings), priority ordering, first scans, active/pending diagnostics and transactional rollback | Native time slicing and pending-duplicate semantics, external triggers, AOI/harness/ST FOR forms and CPU/status/fault parity |
| Program DisableFlag | [Runtime Program control](program-disable.md) in ladder/ST, named/THIS, SINT write, SINT/DINT readback, independent first scans, activation of imported disabled targets, enabled default for ordinary omissions, and rollback | Other Program kinds and native write/lifecycle parity |
| Event task inhibition | [Named/THIS InhibitTask](event-task-inhibition.md), live new/pending request checks, active-body completion, explicit Event configuration and atomic rollback | Other Event sources/Safety/AOI/harness control, native abort/resume/cancellation/status/lifecycle parity |
| Event overlap count | [Live GSV/SSV counter](event-overlap-count.md), named/THIS exact DINT reads and zero resets, independent Status, current instruction order and rollback | Periodic/Safety/other Event/AOI/harness profiles, native overflow/protocol/status/lifecycle parity |
| Event task status | [GSV/SSV Status](event-task-status.md), live accepted-request, configured timeout and active-overlap bits, named and Event THIS contexts, exact DINT replacements, lazy operands and rollback | Other status bits, external events, Continuous/Periodic/Safety status setters, AOI/harness contexts, native protocol/status/fault/lifecycle parity |
| Task start/interval GSV and SSV | [StartTime/MinimumInterval/MaximumInterval](task-start-gsv.md), named/THIS ladder/ST, prior committed host UTC starts/monotonic intervals, complete DINT pairs, StartTime DT/LINT and scalar TIME or paired TIME32 intervals, independent zero resets of StartTime and both interval extrema with rollback | Nonzero StartTime/interval setters, Safety/other Event/AOI/harness profiles, simulated-rate and native clock/visibility/lifecycle parity |
| Scan-time GSV and SSV | [Program/Task LastScanTime/MaxScanTime](scan-time-gsv.md), interpreter microseconds, DINT/TIME32 reads and independent known-zero LastScanTime/MaxScanTime resets, lazy full writes, typed AOI reads and ST FOR effects | [THIS](current-instance-gsv.md) supports ordinary scheduled contexts; whole-Task last/max metrics support eligible Continuous/Periodic and instruction-only Event tasks independently; AOI/harness THIS, other setters, fields and profiles, and native timing/visibility/status/lifecycle parity remain separate |
| Controller UTC setting | [SSV current value and calendars](wall-clock-set.md), scalar DT/LINT, two DINT source cells or seven DINT array/user-record calendar fields, transactional UTC adjustment, monotonic update interval, coherent GSV/CIP/MSG/alarm timestamps, application-lifetime state and explicit host-UTC reset | Other setters, non-UTC LocalDateTime, timezone/DST, built-in DATETIMESTRUCT layout, persistent hardware time, PTP and native fault/lifecycle parity |
| Wall-clock GSV | [CurrentValue/DateTime/qualified LocalDateTime](wall-clock-gsv.md), host UTC microseconds, DT/LINT/two-DINT counters, seven-DINT calendars in arrays or [declared records](wall-clock-gsv.md#calendar-records), lazy full writes, AOIs, complete ST FOR effects and [software CST/UTC offset](wall-clock-gsv.md#coordinated-system-time) | Other clock setters, built-in DATETIMESTRUCT layout, non-UTC/DST, CST status and chassis synchronization, native sampling/interruption/status/layout/lifecycle parity remain separate |
| System values | [Task/Controller GSV settings](gsv-configuration.md), [Controller source flags](gsv-configuration.md#controller-source-flags), [controller-only Module status](gsv-configuration.md#controller-only-module-status), [aggregate Module LEDStatus](gsv-configuration.md#simulated-module-ledstatus), [named Module Mode GSV/SSV and EntryStatus](gsv-configuration.md#named-module-status), [simulated module diagnostics](gsv-configuration.md#simulated-module-connection), [backplane Module Path](gsv-configuration.md#module-backplane-path), [IPv4 Module Path](gsv-configuration.md#module-ethernet-path), [remote chassis Module Path](gsv-configuration.md#remote-controllogix-backplane-path), [Program/Routine Name and Task Instance](gsv-configuration.md#object-identity-reads), [ControllerDevice identity and mode status](gsv-configuration.md#controller-device-identity), [ordinary Task THIS](current-instance-gsv.md), structural/lazy scalar/string destinations and complete conservative ST FOR effects, existing Controller audit values, [SSV task inhibition](task-inhibition.md), [Periodic Rate](gsv-configuration.md#changing-a-periodic-task-rate), [Event Rate/EnableTimeOut](event-tasks.md#runtime-timeout-settings), [Periodic/Event Priority](gsv-configuration.md#changing-a-task-priority) and [Watchdog settings](gsv-configuration.md#changing-a-task-watchdog) | Watchdog expiration, sub-millisecond periods, broader system attributes and native execution parity |
| String operand selection | [Structural/lazy string preflight](string-operations.md#operand-selection) for 11 calls, six string relations and string-bearing CMP, plus [literals in the six standalone relations](string-operations.md#ladder-string-comparison-literals); unknown full writes, [DELETE retained-window reads](string-operations.md#delete-retained-windows), [FIND suffix reads](string-operations.md#find-search-suffixes), preserved unused bytes, aliases/UDTs/AOIs and whole-advance rollback | New algorithms, broader types/encoding, other profiles and native status/fault/lifecycle parity |
| Digital alarms | [Ladder ALMD](ladder-alarm.md), scalar Alarm-format records, minimum duration, both polarities, latch/reset, acknowledgment, enable/disable, suppression, timed shelving, UTC or program timestamps, severity and input-quality diagnostics, ladder AOI InOut | ASO, ST/FBD, native layouts and alarm services |
| Analog alarms | [Ladder ALMA](ladder-alarm.md#analog-level-alarms), scalar Alarm-format records, four level thresholds, directional duration with false-rung restart, deadband, positive and negative rate of change, acknowledgment, suppression, per-condition timed shelving, UTC timestamps, enable/disable, diagnostics and ladder AOI InOut | ST/FBD and native alarm services |
| String conversions | [LOWER/UPPER and STOR/RTOS](string-conversions.md) in RLL/ST, ASCII byte handling and decimal/float32 exchange | Native RTOS formatting, STOR exponent/no-digit edge parity, wider types, expression operands and native status/fault behavior |
| Wide integer files | [Exact FAL/FSC](integer-files.md), matching LINT/unsigned FAL expressions and existing wide/mixed CMP searches across ALL/numeric/INC from idle or completed sources; qualified AOI bindings and rollback, and binary64 [FAL](file-arithmetic.md#binary64-expressions) and [FSC](file-search.md#binary64-searches) | Other promotions/functions and native precision/status/cursor/fault/lifecycle/layout parity remain separate |
| File arithmetic | [FAL ALL/numeric modes](file-arithmetic.md) and [INC from idle/completed sources](file-incremental.md), indexed transforms, scalar accumulation, sequential writes, [REAL calculation/result-store overflow and retry](file-arithmetic.md#real-overflow-and-retry) and [RLL AOI forms](aoi-file-operations.md) | Saved partial INC/hidden state, mixed CONTROL consumers, broader AOI lifecycle/schema and expressions/types and native cursor/overflow/status/partial-fault parity |
| File search | [FSC ALL/numeric modes](file-search.md) and [INC from idle/completed sources](file-incremental.md), comparisons, match/inhibit/resume, false-rung numeric continuation and [RLL AOI forms](aoi-file-operations.md) | Saved partial INC/hidden state, mixed CONTROL consumers, broader AOI lifecycle/schema and expressions/types and native cursor/status/fault parity |
| File sorting | [SRT in ladder/ST](array-sort.md), exact numeric ordering in one selected dimension, ST call transitions and [alias/indirect/AOI references](sort-references.md) | Native internal POS cursor, partial states/faults, wider types, broader lifecycle and conservative FOR effects |
| Array statistics | [AVE and sample STD](array-statistics.md), one selected dimension in 1D/2D/3D numeric arrays, REAL sample deviation with modeled [arithmetic](array-statistics.md#std-arithmetic-overflow) and [one-dimensional range](array-statistics.md#std-one-dimensional-range-overruns) error latches and narrow numeric averages with [AVE error latches](array-statistics.md#ave-error-latches), CONTROL transitions and [alias/indirect/AOI references](statistics-references.md) | Partial POS/resume, broader types/lifecycle and native precision/fault/status behavior |
| Common ladder math | [Twelve math forms](math-operations.md), structural dynamic-index preflight, false/prescan operand skips, full unknown-result writes, SINT/INT/DINT/REAL results and [REAL math with LINT/unsigned results](real-destination-math.md#wide-and-unsigned-integer-results), nearest-even conversion, range rollback, absolute-value square roots in ladder/CPT/ST, [binary64 calculation with REAL/integer results](lreal-math-literals.md#real-and-integer-results) and [exact wide integer SQR/XPY](math-operations.md#wide-integer-roots-and-powers) | Other mixed numeric forms, native precision/math-status/nonfinite/overflow behavior and broader controller profiles |
| BCD/byte-order conversions | [8/16/32/64-bit signed/unsigned packed BCD, all-eight-integer FRD/TOD pairs and INT/DINT SWPB](numeric-conversions.md), decimal and [radix L/U/UL conversion sources](numeric-conversions.md#typed-radix-bcd-sources), structural dynamic-index preflight, false/prescan skips, full unknown-result writes and existing ST SWPB calls | Other BCD expression consumers/types, broader FBD forms and native saturation/math/fault status |
| Bit diagnostics | [DINT RLL FBC/DDT](file-bit-compare.md), all/one-mismatch modes, bit-offset results, wrapped result lists, selective reference updates and [alias/indirect/AOI references](bit-diagnostic-references.md) | Broader AOI shapes/profiles and native sampling/cursor/status/fault parity |
| Data transition | [DINT RLL DTR](data-transition.md), masked comparison, true/false reference updates, lexical prescan and existing AOI bindings | Other controller profiles and native operand/status/fault parity |
| Scalar arithmetic/bitwise selection | [Eleven common operations](scalar-math.md), structural preflight, false/prescan skips, full unknown destination writes, all-eight-integer bitwise tag combinations with zero extension/result widths, widening integer-tag/constant arithmetic, finite REAL MOD, REAL calculation with LINT/unsigned results and existing AOI/wide rules | Remaining integer-only arithmetic promotion, mixed-wide/typed bitwise immediates, floating-point bitwise, native precision/status/fault/lifecycle/layout and broader profiles |
| MOV/CLR | [Scalar storage](numeric-storage.md), all ten numeric types, [time/date](time-date-storage.md) and [ladder string MOV](string-operations.md#ladder-string-mov) with tag/literal sources and capacity clipping | String CLR, non-string aggregate moves, broader conversions and native overflow/status/fault/lifecycle qualification |
| Contacts/coils/one-shots | [XIC/XIO/OTE/OTL/OTU/ONS/OSR/OSF](bit-logic.md), structural preflight, full BOOL establishment, lazy contacts/latches and state-dependent one-shot reads; existing prescan/AOI rollback | Packed writes require known backing integers; native BOOL layout/fault/postscan/lifecycle and broader profiles unfinished |
| Indirect FOR operands | [Runtime-selected loop elements](ladder-loops.md#runtime-selected-operands), structural/lazy preflight, retained index cell, live bound selection, aliases and advance rollback | Native sampling, overflow/status/lifecycle parity, wider types, AOI/ST FOR instruction forms and other profiles remain separate |
| Indirect routine arguments | [JSR caller elements](indirect-routine-calls.md), structural/lazy caller indices, call-entry input/return address capture, copied primitive/record values, [decimal/radix typed numeric constants](indirect-routine-calls.md#typed-numeric-constants), aliases and advance rollback; existing ST calls share the profile | ST SBR/RET keep static references; dynamic subarray arguments, conservative overlap forms, AOI calls and native sampling/fault/lifecycle/layout parity remain separate |
| Statistics operand selection | [AVE/STD result references](statistics-operands.md), structural/lazy indices, unknown full REAL/integer outputs, latched retention/rearm, aliases and AOI/runtime rollback | Actual CONTROL/prescan and existing flag/LEN/POS reads remain required; calculations, partial POS, broader forms/types and native precision/status/fault/lifecycle/layout parity remain separate |
| Sequencer operand selection | [SQI/SQO/SQL structural preflight](sequencer-operands.md), dormant masks/payloads, zero-mask skips after table checks, held live-data updates, unknown full outputs and AOI/runtime rollback | Actual CONTROL addresses and SQO/SQL prescan remain required; broader forms/types, native invalid-state/flags/fault/lifecycle/layout parity remain separate |
| Numeric queue conversions | [FFL/FFU/LFL/LFU](queue-conversions.md), all SINT/INT/DINT/REAL payload/array pairings, low-bit narrowing, sign extension, float32 rounding, lazy edges and AOI/advance rollback | Wide/unsigned/LREAL types, native overflow/status/fault/layout/lifecycle parity and other profiles remain separate |
| CONTROL operand selection | [Shift/queue payloads and CONTROL RES](control-operands.md), structural preflight, path-dependent live indices, unknown full resets, canonical incremental-progress clearing and AOI/runtime rollback | Actual shift/queue prescan/control-state reads remain required; algorithms, broader consumers/profiles and native layout/lifecycle/status/fault parity remain separate |
| Matching aggregate copies | [COP/CPS basic records/strings/UDTs with LREAL/time fields](aggregate-copies.md) and [PID records](aggregate-copies.md#pid-records), structural/lazy references, complete unknown copies, [clipped logical windows](clipped-aggregates.md), sequential overlap, independent storage and bounded actual scalar work; existing ST calls protect complete FOR effects | Mixed/other operational/AOI aggregate schemas, packed layouts, native base-tag clipping/cross-member copying, private histories and native synchronization/fault/lifecycle parity |
| Aggregate zero fills | [Declared-schema FLL](aggregate-fill.md) for basic timer/counter/control/string, [PID](aggregate-fill.md#pid-zero-fills) and nested UDT records including LREAL/time fields; typed unknown full writes, lazy operands, [clipped logical windows](clipped-aggregates.md), complete ST FOR effects, [all-ones integral/Boolean records](aggregate-fill.md#all-ones-record-fills) and AOI/advance rollback | Other nonzero/REAL/wider sources, all-ones PID and other operational/AOI aggregates, packed layouts, cross-member clipping, private histories and native fault/lifecycle parity |
| Numeric copy selection | [COP/CPS structural preflight](numeric-copies.md#operand-selection), dormant lengths/indices, existing byte transfers, unknown full writes and AOI/advance rollback | Aggregate/BOOL/string layouts, broader lengths/profiles, native synchronization/status/fault/partial effects |
| Numeric calculation selection | [CPT/CMP structural preflight](integer-expressions.md#operand-selection), lazy numeric values/indices, full unknown CPT writes, eager CMP operands, [bounded mixed integer arithmetic](ladder-wide-expressions.md#mixed-integer-arithmetic), [mixed integer FAL](integer-files.md#mixed-integer-fal), [matching typed constants](ladder-wide-expressions.md#matching-typed-constants) and [typed radix forms](ladder-wide-expressions.md#typed-radix-expressions) and transaction/AOI recovery | Other arithmetic intermediates, broader syntax/promotion, string/file/index consumers and native status/fault/lifecycle parity |
| Numeric ladder comparisons | [EQU/NEQ/LES/LEQ/GRT/GEQ/LIM/MEQ](numeric-comparisons.md), [REAL promotion](mixed-real-comparisons.md), structural preflight, false/prescan operand skips, mixed integer MEQ with read-only tags and bounded plain or typed immediates, [mixed integer CMP with Boolean composition](ladder-wide-expressions.md#mixed-integer-cmp) and AOI rollback | Mixed CMP arithmetic, complete numeric promotion matrix, broader profiles and native status/fault/lifecycle qualification |
| SIZE/TRN | [Array size and truncation](size-truncate.md), selected arrays/string DATA, metadata-only size reads, lazy references, REAL SIZE results and [REAL/LREAL TRN](lreal-truncate.md) with floating L/l constants and integer/REAL/LREAL destinations | Direct string SIZE, wider SIZE results, native numerical/status/fault/lifecycle and broader profiles; dynamic dimension tags remain a software extension |
| Clipped numeric fills | [FLL logical windows](clipped-fills.md), oversized requests clipped at numeric array/member or scalar boundaries, captured inputs, lazy references, AOI rollback and conservative ST FOR effects | Native packed cross-member/base-tag traversal, wide types, overflow/status/partial-effect/lifecycle parity and native ST availability remain separate |
| Typed bitwise operands | [AND/OR/XOR/NOT/MEQ](typed-bitwise-operands.md), decimal and [radix L/U/UL masks](typed-bitwise-operands.md#typed-radix-masks), declared-width zero extension, mixed integer tags/legacy patterns and complete result writes | BOOL, MEQ floating operands, unsigned inputs to floating results, MVM/BTD/other consumers and native status/fault/lifecycle parity remain separate |
| Typed integer operands | [Seven arithmetic forms and seven comparisons](typed-integer-operands.md), decimal and [typed radix L/U/UL constants](typed-integer-operands.md#typed-radix-integer-operands), range-preserving result/common types, exact division/remainder/order and atomic recovery | Narrowing, invented common types, floating typed-radix mixes/remaining consumers and native status/fault/lifecycle parity remain separate |
| Typed integers in REAL operations | [Nineteen math forms and seven comparisons](real-integer-literals.md), decimal L/U/UL constants, declared source ranges, float32 promotion, LREAL comparison priority and atomic recovery | Other consumer/controller profiles, typed radix and native numerical/status/fault/lifecycle parity remain separate |
| LREAL comparison constants | [Six relations and LIM](lreal-comparison-literals.md), LREAL tag/floating L/l selection, typed integer/REAL/LREAL thresholds, source precision and inclusive/reversed limits | Typed integer-only forms, typed radix, other consumers/controllers and native numerical/status/fault/lifecycle parity remain separate |
| LREAL standalone math constants | [Nineteen LREAL-result ladder forms](lreal-math-literals.md), bounded DINT/finite REAL and decimal L/U/UL integer or floating L/l constants, source precision, lazy operands and AOI recovery | Other result/consumer profiles, typed radix and native numerical/status/fault/lifecycle parity remain separate |
| Radix MOV constants | [Binary/octal/hexadecimal sources](radix-mov-literals.md), unsuffixed DINT and [attached L/U/UL patterns](radix-mov-literals.md#typed-radix-mov-sources), declared-width zero fill, ten numeric destination conversions and scoped ladder monitoring | Other consumers, explicit signed-radix extensions and native numerical/status/lifecycle parity remain separate |
| Numeric FLL | [Narrow numeric fills](numeric-fill.md), integer truncation/sign extension, representable REAL conversion, structural preflight, lazy reads and existing AOI bindings | Native clipping/base-tag traversal, REAL overflow bits/status, wider types and other profiles; aggregate zero fills keep their separate contract |
| Numeric COP/CPS | [Little-endian byte copies](numeric-copies.md) across ten numeric types including [LREAL](lreal-copy.md), clipped lengths, preserved partial elements, row-major/member arrays, budget/rollback and ST loop write effects | Native aggregate/BOOL/string layouts, cross-member/base-tag copying, synchronization and fault/partial-effect parity |
| Masked/bit-field moves | [MVM/BTD ladder forms](bit-transfer.md) for SINT/INT/DINT, structural dynamic-index preflight, false/prescan skips, full unknown writes, partial-bit preservation, mixed widths and bounded fields | Wide/unsigned types, remaining forms and native status/fault parity; separate ST/FBD target moves are listed above |
| Structured Text | Assignments, conditionals, [integer/REAL CASE](st-case-selection.md), bounded loops, [homogeneous wide expressions](wide-st.md), [decimal typed constants](st-integer-literals.md), supported calls and RLL/ST calls | Complete language/functions, mixed/wide FOR/CASE/index forms, full numeric promotion, time arithmetic and aggregates |
| Function Block Diagram (FBD) | [Bounded single-sheet signal graphs](function-blocks.md), 63 blocks, typed references/wires and monitoring | General graphs, multiple sheets, feedback/connectors, AOIs and native ordering/lifecycle/status/transfer parity |
| Sequential Function Chart (SFC) | Routine kind can be identified; execution is blocked | Steps, transitions, actions, qualifiers, branches, timers, reset/pause/forcing and monitoring |
| BOOL/SINT/INT/DINT/REAL | Saved values, scalar/member/array access and supported operations | Complete conversions, math flags, overflow and native edge cases |
| LINT and unsigned integers | Storage/transfers, homogeneous RLL/[ST](wide-st.md), [range-preserving ordering/LIM](numeric-comparisons.md#mixed-integer-ordering-and-limits), [widening RLL arithmetic](scalar-math.md#widening-integer-tag-arithmetic), [exact typed operands](typed-integer-operands.md), integer-tag bitwise operations and [ladder CPT/CMP/MEQ](ladder-wide-expressions.md) in the v35 5580 profile | Arithmetic narrowing/non-covering signedness mixes, typed radix, remaining operand/instruction/ST forms, native math/status/fault/lifecycle and other targets |
| LREAL | [Finite binary64 storage/MOV/CLR](lreal-storage.md), [standalone math constants](lreal-math-literals.md), [comparison constants](lreal-comparison-literals.md), [CPT/CMP expressions](lreal-expressions.md), qualified AOIs and atomic tag access | ST, native aggregate wire layouts, broader operational/AOI/controller profiles and native numerical/status/fault/lifecycle parity |
| DT/LDT/TIME32/TIME/LTIME | [Exact scalar storage, typed literals, same-family MOV and relations, CLR, raw LINT/DT and LINT/LDT bridges and exact ADD/SUB](time-date-storage.md) | [Typed clock and timing GSV](time-date-storage.md#reading-timestamps-and-durations-with-gsv) covers DT/TIME32/TIME; lossy conversions, broader clock attributes, ST expressions, native layouts and firmware qualification remain open |
| PID ladder software profile | [P/PI/PID regulator](ladder-pid.md), gains, scaling, limits, [integer operands and tieback manual](pid-operands.md), CTL aliases, alarms, [derivative/deadband](pid-dynamics.md) and [PVT/inhold inputs](pid-restart.md), [one-way cascade](pid-cascade.md) and [ladder AOIs](aoi-pid.md) and [matching PID record copies](aggregate-copies.md#pid-records) and [PID zero fills](aggregate-fill.md#pid-zero-fills) | Native smoothing coefficients/cascade feedback/module restart, remaining operands/languages and native solver/status/fault/layout parity |
| PROP_INT and ST PI software profile | [PI regulation](st-pi-regulation.md), linear/shaped gains, holds, output/integral limits, initialization, timing and transactional history | Native coefficients/thresholds/rounding/ordering, RTS, FBD graphs, packed layouts, other profiles, remaining [ladder PID](ladder-pid.md) features and separate PIDE family |
| FUNCTION_GENERATOR/DEADTIME | [ST FGEN/DEDT](st-curves-delay.md), piecewise curves, selected tables, sampled transport delay, resizing, health recovery and transactional arrays | Native startup/conditional diagnostics/precision/resize/recovery, RTS, FBD graphs, packed layouts and other profiles |
| SELECT_ENHANCED/DERIVATIVE | [ST/FBD ESEL/DERV](fbd-process-signals.md), healthy high/low/median/mean/manual selection, control requests, timed rate of change, bypass and rollback | Native startup/request/health/timing/rounding qualification, RTS, general FBD forms, packed layouts and other profiles |
| UP_DOWN_ACCUM/INTEGRATOR | [ST/FBD UPDN/INTG](fbd-accumulation.md), per-call totals, timed integration, initialization, directional holds, limits, alarms and transactional history | Native startup/rounding/precedence, RTS, general FBD forms, packed layouts and other controller profiles |
| FLIP_FLOP_D/FLIP_FLOP_JK/DOMINANT_RESET/DOMINANT_SET | [ST/FBD Boolean memory](fbd-boolean.md), clocked data/toggle state, Clear priority, dominance, complements and transactional history | General FBD forms, packed layouts, other profiles and native startup/Run/skip/postscan/output-write/status/fault parity |
| FILTER_LOW_PASS software model | [ST LPF](st-low-pass-filter.md), explicitly chosen bilinear orders 1/2/3, Periodic/elapsed/oversample timing, bounds/status and section rollback | Native discrete recurrence/coefficients/precision/transitions, RTS, FBD graphs, packed layouts, other profiles and full lifecycle/status/fault parity |
| MAXIMUM_CAPTURE/MINIMUM_CAPTURE | [ST/FBD MAXC/MINC](fbd-rate-capture.md), finite REAL extrema, held reset baselines, per-record history, skip/Run/rollback behavior | General FBD forms, packed layouts, other profiles and native initialization/reset/skip/postscan/precision/status/fault parity |
| MOVING_AVERAGE/MOVING_STD_DEV | [ST MAVE/MSTD](st-moving-statistics.md), uniform/direct-weighted averages, population deviation, REAL queues, sampling/initialization, resize/status and transactional count | FBD graphs, packed layouts, native queue/resize/hold/lifecycle/precision/status/fault parity |
| RATE_LIMITER and ST/FBD RLIM | [Rate limiting](st-rate-limiter.md), separate rates, bypass, Periodic/elapsed and explicit oversample timing, status aliases and rollback | Module timestamp mode/RTS diagnostics, general FBD forms and native timing/precision/status/layout/fault parity |
| ST/FBD signal conditioning | [HLL/SNEG/SSUM](st-signals.md), logical HL_LIMIT/SELECTABLE_NEGATE/SELECTED_SUMMER, inclusive limit alarms, selector diagnostics and weighted sums | General FBD and native precision/overflow/status/layout/fault parity |
| SCALE and ST/FBD SCL | [Analog scaling](st-scaling.md), finite REAL interpolation/extrapolation, limiting, raw alarms and status aliases | General FBD and native precision/overflow/status/layout/fault parity |
| FBD_ONESHOT and ST/FBD edges | [OSRI/OSFI](st-oneshot.md), rising/falling pulses, startup suppression, skipped calls and transactional history | General FBD graph forms, shared-kind records and native layout/lifecycle/fault parity |
| FBD_COUNTER and ST/FBD CTUD | [Up/down counting](st-counter.md), sampled edges, reset, signed wrap, first-call/Run priming and rollback | General FBD graph forms and native lifecycle/reset/flags/layout/fault parity |
| FBD_TIMER and ST/FBD timers | [TONR/TOFR/RTOR](st-timers.md), logical fields/status aliases, deterministic milliseconds, reset/retention, skipped calls and rollback | General FBD graph forms, native clocks/layout/status/fault parity and other controller profiles |
| TIMER/COUNTER | [TON/TOF/RTO](ladder-timers.md) with known consumed PRE/ACC and EN/DN history, retained unread flags, canonical clock rollback; [CTU/CTD/RES](ladder-counters.md), known consumed counter values/history, signed wrap, unknown full resets, scoped records, runtime/AOI rollback and [literal import initialization](ladder-timers.md#literal-presets-on-import) | Other timer/counter families, all status transitions, clock/resolution/fault/overflow parity |
| CONTROL | [Logical members, shifts, FIFO/LIFO and RES](control-operations.md); [alias/indirect shift/queue starts](queue-references.md); [one-dimensional AOI queues/shifts](aoi-queues.md); [matching strings/UDTs with LREAL and time/date fields](record-queues.md) and [basic record payloads](basic-record-queues.md), plus [PID snapshots](record-queues.md#pid-payloads); [DINT sequencers](sequencer-operations.md) with [alias/indirect and AOI tables](sequencer-references.md); [literal import initialization](control-operations.md#literal-len-and-pos-on-import); scalar member access | Native packed layouts/transfers, remaining consumers/forms and full scan/status/fault parity |
| LREAL execution | [Finite storage/MOV/CLR](lreal-storage.md) plus [tagged ladder arithmetic/comparisons](lreal-math.md) and [advanced math](lreal-advanced.md), [TRN](lreal-truncate.md), [numeric byte copies](lreal-copy.md), [mixed-tag arithmetic](mixed-lreal-math.md), [mixed comparisons/LIM](mixed-lreal-comparisons.md), [integer constants](lreal-constants.md), [mixed powers](mixed-lreal-power.md), [numeric unary sources](lreal-unary-sources.md), [result-selected math](lreal-destination-math.md), scalar/array/UDT values, atomic tag access and rollback | Other mixed arithmetic/immediates, ST, other CPT/CMP forms, aggregate wire layouts, broader AOI forms and native rounding/status/lifecycle parity |
| MESSAGE | [Ladder MSG](ladder-message.md) models connected and unconnected Data Table transfers of matching numeric values, strings and explicit UDTs, bounded Generic Identity, Wall Clock Time, Time Sync, Port Object, TCP/IP Interface and Ethernet Link reads, writable self routes and ladder GSV/SSV path buffers and timing settings | External routing, other commands, wire layout and native status/timing parity |
| Other predefined types | Some exported decorated fields may be retained as data-only structures | Dedicated schemas and their stateful instructions |
| UDTs | Explicit nested structures, arrays, members, selected packed bits and bounded wire layouts | Complete native layout/type rules, aggregate assignments/copies and uncommon/hidden/overlaid forms |
| STRING and user strings | Built-in STRING and explicit DINT LEN/one-dimensional SINT DATA types; CONCAT/MID, [FIND/INSERT/DELETE](string-operations.md), [ASCII case and REAL conversions](string-conversions.md) | Remaining edge/type/conversion/status/encoding behavior and built-in STRING wire profile |
| AOIs | Bounded RLL/ST definitions, nested instances, scalar Input/Output, [decimal/radix typed numeric input constants](aoi-constants.md), exact-type InOut, Prescan and EnableInFalse | Remaining parameter forms, Postscan/SFC, FBD definitions, full instance lifecycle and protected definitions |
| Tasks/controller | Mixed Standard Continuous/Periodic tasks, deterministic serial releases with coincident priority order, Program/Run and per-Program first scans | General CPU preemption/time slicing, other event triggers, watchdogs, full fault handlers, restart/retention |
| Motion | Empty source-checked motion discovery only | Axis/group/coordinate models and every motion instruction family |
| I/O modules | Local-controller metadata, named local and qualified routed Mode reads and writes, Inhibited/Waiting EntryStatus, simulated Running/Faulted and fault diagnostics, aggregate LEDStatus, configured backplane and Ethernet routes, externally driven ordinary tags | Module backplane/adapters, cyclic I/O, channel behavior, diagnostics, forces and failures |
| POINT I/O | No POINT I/O device model | Adapter, rack/slot/channel configuration, digital/analog/specialty modules and connection lifecycle |
| FANUC robots | HTTP/optional MQTT can connect an external tag simulator | FANUC device assemblies, handshakes, robot state/faults and optional robot-simulator integration |
| EDS/AOP | No EDS parser or device-model generator | EDS import/validation, assemblies/parameters/connections and separately authored behavioral models |
| Produced/consumed tags | No executing producer/consumer model | Connections, sampling, updates, timeouts, status and peer scheduling |
| Messaging | [Virtual MSG reads and writes](ladder-message.md) with bounded queuing, cancellation, simulated timeouts and CIP Generic Identity, Wall Clock Time, Time Sync, Port Object, TCP/IP Interface and Ethernet Link reads | Network paths, additional services, device replies, and connections |
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
  conversions and all qualified targets. Complete the bounded LREAL model and
  complete signed/unsigned boundaries and promotion. [Homogeneous wide ST](wide-st.md)
  covers bounded assignments/conditions; [ladder wide CPT/CMP/MEQ](ladder-wide-expressions.md)
  are also bounded; remaining ST forms and mixed conversions
  and native status semantics remain unfinished.
- [ ] **D02 — Numeric edge behavior:** overflow/truncation, carry and math flags,
  divide-by-zero, rounding, REAL/LREAL NaN/infinity/subnormal handling and
  conversions. The current engine rejects nonfinite REAL/LREAL values.
- [ ] **D03 — Time types:** extend [DT, LDT, TIME32, TIME and LTIME storage](time-date-storage.md);
  typed literals, display radix, units, epoch/zone rules, comparisons, arithmetic,
  conversions and transfer encoding. The installed help lists these names, but
  runtime availability still needs verification against each controller/firmware
  profile. Do not treat them as untyped LINT aliases.
- [ ] **D04 — Predefined structures:** complete the named
  [predefined-type inventory](predefined-data-types.md), including dedicated
  complete CONTROL beyond its [logical shift/FIFO/LIFO profile](control-operations.md),
  and extend [MESSAGE](ladder-message.md), remaining [PID](ladder-pid.md)/PID_ENHANCED behavior, alarm/filter/drive/phase/sequence records, motion
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

[LREAL CPT/CMP expressions](lreal-expressions.md) now support finite binary64
calculations with mixed numeric tags and copied scalar AOI LREAL parameters.
Other consumers, narrowing/literal forms and native equivalence remain open.

[Integer SQR expressions](ladder-integer-roots.md) now round individual roots
before further narrow integer CPT/CMP/FAL/FSC arithmetic. Complete promotion and
native numerical/status/fault/lifecycle parity remain open.

[Integer expression powers](ladder-integer-power.md) now cover bounded narrow
CPT/CMP and FAL/FSC forms. Negative/larger exponents, wide arithmetic and native
numerical/status/fault/lifecycle parity remain open.

## Languages, calls and AOIs

- [ ] **L01 — RLL:** implement the remaining mnemonics and remaining forms of
  existing ones. Verify rung-in/out, false scan, prescan, duplicate/shared
  operands, branches, jumps, skipped calls and status side effects per family.
- [ ] **L02 — ST:** complete target-version statements/operators/functions,
  the complete division/promotion matrix, remaining wide/time expressions, aggregate operations and
  instruction availability. Preserve language-specific operand ordering and
  evaluation rules; current expressions evaluate operands eagerly.
- [ ] **L03 — FBD execution:** [Single-sheet signal graphs](function-blocks.md)
  now execute sixty-three blocks over typed acyclic wires with enable/status/rollback. Complete multiple
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
- [ ] **I08 — MSG:** extend [unconnected THIS transfers](ladder-message.md)
  to networked CIP generic/read/write services and supported legacy mappings,
  connection reuse, routing, replies, retries, timeouts and bounded external communications.
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
added by project AOIs are counted separately from the 108 built-in RLL entries.
Update both this matrix and the instruction inventory when capabilities change.

[REAL-result math](real-destination-math.md) additionally selects float32
inputs and result for arithmetic, XPY and eleven unary forms, across all nine
integer/REAL source types and bounded integer/finite floating constants.
LREAL result rules and other destination/consumer profiles remain separate.

[Array-index expressions](array-index-expressions.md) add division and integer
bitwise operators with DINT intermediates, plus exact single-tag indices for
all eight integer types. Existing consumer-specific reference rules remain.

[Array-index functions](array-index-functions.md) additionally qualify FRD, TOD
and SQR within existing references using checked DINT arguments/results. Viewer
snapshots share the forms; generic BCD expressions and native parity remain separate.

[Sequencer source types](sequencer-sources.md) qualify narrow SQL/SQI payloads,
complete source patterns and dedicated guards; SQO output remains DINT.

[BCD CPT expressions](cpt-bcd.md) qualify FRD/TOD with narrow integer
arguments/results, composition, lazy selection and AOI rollback. Other consumers,
REAL/wide mixtures and native numerical/status/fault/lifecycle parity remain separate.

[BCD CMP expressions](cmp-bcd.md) qualify FRD/TOD in narrow integer
comparisons and eager Boolean composition, with lazy rung selection and AOI
rollback. Wider/REAL/string mixtures, other consumers and native parity remain separate.

[BCD FAL/FSC expressions](file-bcd.md) add narrow FRD/TOD conversions to
existing ALL/numeric/INC transforms and searches, including lazy progress paths,
AOI arrays and rollback. Wider/REAL mixtures, ST and native parity remain separate.

[LREAL CPT results](lreal-results.md) now convert the final binary64 value to
all eight integer types or finite REAL/LREAL with checked ranges. Other forms
and native equivalence retain separate limits.

[LREAL floating constants](lreal-literals.md) now support unsuffixed REAL and
explicit floating L/l suffixes in direct ladder CPT/CMP. Other consumers and
native precision/status/fault/lifecycle qualification remain separate.

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
