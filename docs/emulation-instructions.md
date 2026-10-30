# Instruction execution inventory

Audited 2026-10-30; ST accumulation added for app `26.1030.144653`. The engine has **101 built-in
RLL dispatch entries**. Every entry has operand/type/scan limitations; none is a
claim of complete native controller equivalence. Project-defined AOIs are
separate. See the [full capability and remaining-work checklist](emulation-coverage.md).

[ST CASE](st-case-selection.md) supports narrow integer and REAL expression
profiles with immediate values, lists and ranges; wide forms remain unqualified.

This table covers the installed v35 instruction-set overview and A–Z indexes.
It includes language aliases and product-specific families, so it must not be
used to calculate a compatibility percentage. Firmware/controller/language
availability still needs qualification. SFC named elements are shown as a
separate language family, not RLL mnemonics.

- **RLL model** means a dispatch entry exists for supported forms.
- **Expression only** means the name can be used in the supported CPT/ST
  expression grammar; a standalone instruction/block is still unimplemented.
- **Remaining names** have no built-in execution implementation.
  [RLL FOR/BRK](ladder-loops.md) and ST FOR/EXIT have distinct execution profiles.

[ST-only TONR/TOFR/RTOR](st-timers.md) use logical FBD_TIMER records;
[ST CTUD](st-counter.md) uses FBD_COUNTER and [ST OSRI/OSFI](st-oneshot.md) use
FBD_ONESHOT. [ST SCL](st-scaling.md) uses SCALE; [ST HLL/SNEG/SSUM](st-signals.md)
add three signal-conditioning records. [ST RLIM](st-rate-limiter.md) uses
RATE_LIMITER. [ST MAVE/MSTD](st-moving-statistics.md) add MOVING_AVERAGE and
MOVING_STD_DEV. [ST MAXC/MINC](st-capture.md) add MAXIMUM_CAPTURE and
MINIMUM_CAPTURE. [ST LPF](st-low-pass-filter.md) adds a FILTER_LOW_PASS software
model. [ST Boolean memory](st-digital-memory.md) adds DFF/JKFF/RESD/SETD and
four logical records. [ST UPDN/INTG](st-accumulation.md) add two accumulation
records. These twenty-two additional calls are excluded from the RLL dispatch
count. Their FBD graph forms remain unimplemented.

## Instruction families

| Family | RLL model, limited forms | Expression only; standalone remains | Remaining names |
| --- | --- | --- | --- |
| Alarm Instructions | — | — | `ALMA`, `ALMD`, `ASO` |
| Advanced Math Instructions | `LN`, `LOG`, `XPY` | — | — |
| Array (File)/Shift Instructions | `BSL`, `BSR`, `FFL`, `FFU`, `LFL`, `LFU` | — | — |
| Array File/Misc. Instructions | `AVE`, `COP`, `CPS`, `FAL`, `FLL`, `FSC`, `SIZE`, `SRT`, `STD` | — | — |
| ASCII Conversion Instructions | `DTOS`, `LOWER`, `RTOS`, `STOD`, `STOR`, `UPPER` | — | — |
| ASCII Serial Port Instructions | — | — | `ABL`, `ACB`, `ACL`, `AHL`, `ARD`, `ARL`, `AWA`, `AWT` |
| ASCII String | `CONCAT`, `DELETE`, `FIND`, `INSERT`, `MID` | — | — |
| Bit Instructions | `ONS`, `OSF`, `OSR`, `OTE`, `OTL`, `OTU`, `XIC`, `XIO` | — | — (ST-only OSRI/OSFI listed above) |
| Compare Instructions | `CMP`, `EQU`, `GEQ`, `GRT`, `LEQ`, `LES`, `LIM`, `MEQ`, `NEQ` | — | — |
| Compute/Math Instructions | `ABS`, `ADD`, `CPT`, `DIV`, `MOD`, `MUL`, `NEG`, `SQR`, `SUB` | `SQRT` | — |
| Drives Instructions | — | — | `HMIBC`, `PI`, `PMUL`, `SCRV`, `SOC` (ST-only INTG/UPDN listed above) |
| Drive Safety Instructions | — | — | `SBC`, `SDI`, `SFX`, `SLP`, `SLS`, `SOS`, `SS1`, `SS2` |
| Equipment Phase Instructions | — | — | `PATT`, `PCLF`, `PCMD`, `PDET`, `PFL`, `POVR`, `PPD`, `PRNP`, `PSC`, `PXRQ` |
| Equipment Sequence Instructions | — | — | `SASI`, `SATT`, `SCLF`, `SCMD`, `SDET`, `SOVR` |
| Filter Instructions | — | — | `DERV`, `HPF`, `LDL2`, `NTCH` (ST-only LPF software model listed above) |
| For Break Instructions | `BRK`, `FOR` | — | — |
| Input/Output Instructions | `GSV`, `SSV` | — | `IOT`, `MSG` |
| License Instructions | — | — | `LV` |
| Math Conversion Instructions | `DEG`, `FRD`, `RAD`, `TOD`, `TRN` | — | — |
| Metal Form Instructions | — | — | `AVC`, `CBCM`, `CBIM`, `CBSSM`, `CPM`, `CSM`, `EPMS`, `MMVC`, `MVC` |
| Motion Event Instructions | — | — | `MAOC`, `MAR`, `MAW`, `MDOC`, `MDR`, `MDW` |
| Motion Group Instructions | — | — | `MGS`, `MGSD`, `MGSP`, `MGSR` |
| Motion Move Instructions | — | — | `MAG`, `MAH`, `MAJ`, `MAM`, `MAPC`, `MAS`, `MATC`, `MCCP`, `MCD`, `MCSV`, `MDAC`, `MRP` |
| Motion State Instruction | — | — | `MAFR`, `MASD`, `MASR`, `MDF`, `MDO`, `MDS`, `MSF`, `MSO` |
| Move/Logical Instructions | `AND`, `BTD`, `CLR`, `MOV`, `MVM`, `NOT`, `OR`, `SWPB`, `XOR` | — | `BAND`, `BNOT`, `BOR`, `BTDT`, `BXOR`, `MVMT` (ST-only DFF/JKFF/RESD/SETD listed above) |
| Multi-Axis Coordinated Motion Instructions | — | — | `MCCD`, `MCCM`, `MCLM`, `MCPM`, `MCS`, `MCSD`, `MCSR`, `MCT`, `MCTO`, `MCTP`, `MCTPO`, `MDCC` |
| PlantPAx instructions | — | — | `PAH`, `PAI`, `PAID`, `PAIM`, `PAO`, `PBL`, `PCMDSRC`, `PD4SD`, `PDBC`, `PDI`, `PDO`, `PDOSE`, `PFO`, `PHLS`, `PINTLK`, `PLLS`, `PMTR`, `PNPOS`, `PPERM`, `PPID`, `PPTC`, `PRI`, `PRT`, `PTST`, `PVLV`, `PVLVMP`, `PVLVS`, `PVSD` |
| Process Control Instructions | — | — | `ALM`, `CC`, `D2SD`, `D3SD`, `DEDT`, `FGEN`, `IMC`, `LDLG`, `MMC`, `PIDE`, `POSP`, `RMPS`, `SRTP`, `TOT` |
| Program Control Instructions | `AFI`, `EVENT`, `JMP`, `JSR`, `LBL`, `MCR`, `NOP`, `RET`, `SBR`, `TND` | — | `EOT`, `JXR`, `SFP`, `SFR`, `UID`, `UIE` |
| Safety Instructions | — | — | `CROUT`, `DCA`, `DCAF`, `DCM`, `DCS`, `DCSRT`, `DCST`, `DCSTL`, `DCSTM`, `DIN`, `ENPEN`, `ESTOP`, `FPMS`, `FSBM`, `LC`, `RIN`, `ROUT`, `SMAT`, `THRS`, `THRSE`, `TSAM`, `TSSM` |
| Select/Limit Instructions | — | — | `ESEL`, `MUX`, `SEL` (ST-only HLL/SNEG/SSUM/RLIM listed above) |
| Sequencer Instructions | `SQI`, `SQL`, `SQO` | — | — |
| Sequential Function Chart (SFC) Instructions | — | — | `ACTION`, `STEP`, `STOP`, `TRANSITION` |
| Special Instructions | `DDT`, `DTR`, `FBC` | — | `PID` |
| Statistical Instructions | — | — | — (ST-only MAVE/MSTD/MAXC/MINC listed above) |
| Timer/Counter Instructions | `CTD`, `CTU`, `RES`, `RTO`, `TOF`, `TON` | — | — (ST-only variants listed above) |
| Trigonometric Instructions | `ACS`, `ASN`, `ATN`, `COS`, `SIN`, `TAN` | `ACOS`, `ASIN`, `ATAN` | — |
| Additional alphabetical entries | — | `TRUNC` | `BPT`, `PCE`, `TPT` |
| Additional motion registration and homing | — | — | `MAAT`, `MAHD`, `MRAT`, `MRHD` |

ASO is additionally confirmed in installed v35 instruction help for
ALARM_SET_CONTROL; it is not implemented. The
[predefined-type inventory](predefined-data-types.md) tracks its associated
schema/behavior backlog separately from instruction names.

## Remaining forms of existing instructions

| Existing family | Remaining semantic/operand work |
| --- | --- |
| Bit logic, comparisons, MOV/CLR and math | Homogeneous LINT/unsigned operations have bounded [RLL](integer-execution.md) and [ST](wide-st.md) profiles, including [decimal ST L/U/UL literals](st-integer-literals.md). Mixed types, remaining conversions, status/fault behavior and native scan parity remain unfinished. |
| SQR/XPY/LN/LOG/DEG/RAD/ACS/ASN/ATN/COS/SIN/TAN | [Finite REAL-result ladder forms](math-operations.md) for v35 5580, with SINT/INT/DINT/REAL sources. Integer destinations, wide/unsigned/LREAL sources, FBD and native precision/status/nonfinite behavior remain unfinished. |
| FRD/TOD/SWPB | [DINT BCD and INT/DINT byte-order forms](numeric-conversions.md) for v35 5580. SWPB also supports ST calls and INT-to-DINT sign extension. Other BCD types, mixed conversions, BCD expressions/FBD and native overflow/status behavior remain unfinished. |
| MVM/BTD | [SINT/INT/DINT ladder bit transfers](bit-transfer.md) support zero-fill, masks, overlap and bounded fields. Wide/unsigned operands, ST/FBD variants and native math/fault status remain unfinished. |
| BSL/BSR/FFL/FFU/LFL/LFU and CONTROL RES | [Bounded ladder shifts and FIFO/LIFO](control-operations.md), logical CONTROL state and [matching string/explicit UDT records](record-queues.md). Native layout/status parity, mixed conversions, operational/AOI records and indirect/AOI array starts remain unfinished. |
| SQO/SQI/SQL | [DINT ladder sequencers](sequencer-operations.md) for v35 5580, with startup row zero and cyclic rows 1..LEN. Mixed source types, indirect/AOI table starts and native scan/fault parity remain unfinished. |
| FAL | [Bounded ALL/numeric ladder iteration](file-arithmetic.md) and [idle-source INC](file-incremental.md), indexed destinations, sequential writes and the CPT grammar. Saved active INC state, additional types/functions, AOIs and native cursor/overflow/status/partial-fault behavior remain unfinished. |
| FSC | [Bounded ALL/numeric ladder search](file-search.md) and [idle-source INC](file-incremental.md), comparison expressions and FD/IN. Saved active INC state, AOIs, additional expressions and native cursor/status/fault parity remain unfinished. |
| SRT | [Dimension-wise ladder/ST sorting](array-sort.md), with SINT/INT/DINT/REAL arrays and three-operand ST calls. The qualified whole-region profile retains POS zero; native internal cursor, partial-state/fault behavior, broader references and types remain unfinished. |
| AVE/STD | [Dimension-wise statistics](array-statistics.md) with SINT/INT/DINT/REAL arrays, REAL results and logical CONTROL. Partial POS/resume, integer AVE destinations, indirect/alias/AOI array starts and native precision/fault/status behavior remain unfinished. |
| COP/CPS | Raw byte reinterpretation, complete aggregate layouts, all legal source/destination forms and asynchronous/CPS synchronization behavior. Current copies require matching declared element types inside a modeled region. |
| FLL/SIZE | All legal types, narrowing/conversion rules and aggregate forms. Current FLL has bounded numeric destinations and DINT-zero structure fills. |
| CPT/CMP/MEQ | [Narrow integer division](integer-expressions.md) now works in CPT/CMP and FAL/FSC expressions with documented REAL promotion. Complete expression/type/conversion coverage remains unfinished. MEQ covers SINT/INT/DINT; native arithmetic/status parity is unverified. |
| UPDN/INTG (ST only) | [Logical accumulation records](st-accumulation.md), per-call totals, trapezoidal integration, initialization, holds, limits, alarms, timing and rollback. Native startup/rounding/precedence, RTS, FBD graphs and packed layouts remain unfinished. |
| DFF/JKFF/RESD/SETD (ST only) | [Logical Boolean memory](st-digital-memory.md), sampled clock/data/toggle behavior, Clear priority, latch dominance, complements and rollback. FBD graphs, layouts and native lifecycle/output-write/status/fault parity remain unfinished. |
| LPF (ST only, software solver) | [Logical FILTER_LOW_PASS](st-low-pass-filter.md), explicit bilinear orders 1/2/3, elapsed/Periodic/oversample timing, bounds/status and transactional sections. Native recurrence/coefficients/precision/transitions, RTS, FBD/layout/lifecycle/fault parity remain unfinished. |
| MAXC/MINC (ST only) | [Logical capture records](st-capture.md), retained finite REAL extrema, held reset baselines, skipped calls and rollback. FBD graphs, packed layouts and native lifecycle/precision/nonfinite/status/fault parity remain unfinished. |
| MAVE/MSTD (ST only) | [Logical moving-statistics records](st-moving-statistics.md), uniform/direct-weighted means, population deviation, active queue fill/resize, initialization, diagnostics and rollback. FBD graphs and native queue/layout/precision/lifecycle/status/fault parity remain unfinished. |
| RLIM (ST only) | [Logical RATE_LIMITER](st-rate-limiter.md), separate rates, bypass, Periodic/elapsed and oversample timing, status aliases and transactional history. Module timestamp mode, FBD graphs and native timing/precision/status/fault/layout parity remain unfinished. |
| HLL/SNEG/SSUM (ST only) | [Logical signal records](st-signals.md), both/one-sided limits, inclusive alarms, status aliases, selectable negation and eight weighted input pairs plus bias. FBD graphs and native precision/overflow/status/layout/fault parity remain unfinished. |
| SCL (ST only) | [Logical SCALE](st-scaling.md), finite REAL scaling, extrapolation/limiting, raw alarms, invalid-range status and rollback. FBD graphs and native precision/overflow/status/layout/fault parity remain unfinished. |
| OSRI/OSFI (ST only) | [Logical FBD_ONESHOT](st-oneshot.md), sampled rising/falling edges, startup suppression, skipped calls and transactional history. FBD graphs, mixed instruction kinds on one record and native layout/lifecycle/fault parity remain unfinished. |
| CTUD (ST only) | [Logical FBD_COUNTER](st-counter.md), sampled up/down edges, first-call/Run priming, reset, signed wrap and transactional history. FBD graphs and native reset/flag/layout/fault parity remain unfinished. |
| TONR/TOFR/RTOR (ST only) | [Logical FBD_TIMER and elapsed-time profile](st-timers.md), reset/retention, skipped calls, status aliases and rollback. FBD graphs, native clock/status/fault/layout parity and other profiles remain unfinished. |
| TON/TOF/RTO/CTU/CTD/RES | All state transitions, shared instances, skipped scans, timing/fault behavior and target-specific types. Current RLL timers/counters require neutral-text `?,?` operands. |
| FBC/DDT | [DINT ladder bit diagnostics](file-bit-compare.md), bit offsets, all/one-mismatch modes, result wrapping, selective DDT updates and prescan/false controls. Broader references/profiles and native cursor/status/fault parity remain unfinished. |
| DTR | [DINT ladder data transition](data-transition.md), complete prior-reference comparison, true/false writes and lexical prescan, including existing AOI bindings. Other profiles and native operand/status/fault parity remain unfinished. |
| MCR | [Paired ladder zones](master-control.md), false scanning, unconditional endings, routine/AOI isolation and trace markers. Open-ended/conditional/nested zones, cross-boundary jumps and native scan/fault/CPU parity remain unfinished. |
| FOR/BRK | [Ladder indexed routine loops](ladder-loops.md), signed inclusive bounds, early exits, nested calls and task-isolated frames. Native operand sampling/overflow/watchdog/postscan parity, recursion, AOI and SFC forms remain unfinished. |
| JSR/SBR/RET/JMP/LBL/TND | Remaining legal parameter/reference and control-flow forms, task/language interactions and prescan behavior. Current calls use static references, exact counts/types/dimensions and bounded nesting. |
| LOWER/UPPER/STOR/RTOS | [ASCII case and decimal/REAL conversion](string-conversions.md) in RLL/ST, explicit user strings, aliases, UDTs and existing AOI bindings. RTOS uses a documented software format; native formatting/status/fault parity and STOR exponent/no-digit edge behavior remain unfinished. |
| CONCAT/MID/FIND/INSERT/DELETE/DTOS/STOD/TRN | [Common search/editing forms](string-operations.md) support RLL/ST and represented user strings. Empty-search/zero-delete and broader range/type/conversion/status/encoding behavior remain unfinished. |
| EVENT | [Qualified instruction-only Event tasks](event-tasks.md) in RLL/ST: immediate higher priorities, deferred lower/equal priorities, pending-request coalescing, active-overlap suppression and shared limits/rollback. Native time slicing/pending-duplicate semantics, external triggers/timeouts, AOIs/harness/ST FOR forms and CPU/status parity remain unfinished. |
| GSV | Controller AuditValue/ChangesToDetect retain LINT/two-DINT reads. [Explicit Task/Controller settings](gsv-configuration.md) add exact INT/DINT/string destinations. Runtime timing/status, other objects/attributes, cross-type byte-copy forms and broader SSV remain unfinished. |
| SSV | [Task InhibitTask](task-inhibition.md) controls Standard Continuous/Periodic releases with an exact DINT source, live GSV/read-attribute feedback and rollback. Other classes/attributes, Event/Safety targets, AOIs and harness calls remain unfinished. |
| AOI calls | Parameter variants, lifecycle, Postscan, FBD/SFC integration, protected definitions and complete native semantics. See [AOI checklist](emulation-coverage.md#languages-calls-and-aois). |

The exact current dispatch table is `ARITIES` in
[model.py](../source/logixlab/model.py). Execution and operand checks live in
[runtime.py](../source/logixlab/runtime.py), [event_tasks.py](../source/logixlab/event_tasks.py), [gsv_configuration.py](../source/logixlab/gsv_configuration.py), [extended.py](../source/logixlab/extended.py),
[bit_transfer.py](../source/logixlab/bit_transfer.py),
[data_transition.py](../source/logixlab/data_transition.py),
[file_bit_compare.py](../source/logixlab/file_bit_compare.py),
[numeric_conversions.py](../source/logixlab/numeric_conversions.py),
[real_math.py](../source/logixlab/real_math.py),
[array_statistics.py](../source/logixlab/array_statistics.py),
[array_sort.py](../source/logixlab/array_sort.py),
[file_search.py](../source/logixlab/file_search.py),
[file_arithmetic.py](../source/logixlab/file_arithmetic.py),
[string_operations.py](../source/logixlab/string_operations.py),
[string_conversions.py](../source/logixlab/string_conversions.py),
[control_operations.py](../source/logixlab/control_operations.py),
[sequencer_operations.py](../source/logixlab/sequencer_operations.py),
[st_timers.py](../source/logixlab/st_timers.py),
[st_counter.py](../source/logixlab/st_counter.py),
[st_oneshot.py](../source/logixlab/st_oneshot.py),
[st_scale.py](../source/logixlab/st_scale.py),
[st_signal.py](../source/logixlab/st_signal.py),
[st_rate.py](../source/logixlab/st_rate.py),
[structured.py](../source/logixlab/structured.py),
[expressions.py](../source/logixlab/expressions.py) and
[st_expression.py](../source/logixlab/st_expression.py). Loading a project reports
its own supported forms and blockers; the mnemonic inventory alone cannot
declare an entire project executable.
