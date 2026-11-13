# Instruction execution inventory

Audited 2026-11-04; BCD FAL/FSC expressions added for app `26.1104.123302`. Language priority is ladder, then ST, then FBD, then SFC;
new FBD/SFC features wait for ladder/ST coverage and qualification. The engine has **108 built-in
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

[ST/FBD TONR/TOFR/RTOR](st-timers.md) use logical FBD_TIMER records;
[ST CTUD](st-counter.md) uses FBD_COUNTER and [ST OSRI/OSFI](st-oneshot.md) use
FBD_ONESHOT. [ST SCL](st-scaling.md) uses SCALE; [ST HLL/SNEG/SSUM](st-signals.md)
add three signal-conditioning records. [ST RLIM](st-rate-limiter.md) uses
RATE_LIMITER. [ST MAVE/MSTD](st-moving-statistics.md) add MOVING_AVERAGE and
MOVING_STD_DEV. [ST MAXC/MINC](st-capture.md) add MAXIMUM_CAPTURE and
MINIMUM_CAPTURE. [ST LPF](st-low-pass-filter.md) adds a FILTER_LOW_PASS software
model. [ST Boolean memory](st-digital-memory.md) adds DFF/JKFF/RESD/SETD and
four logical records. [ST/FBD UPDN/INTG](st-accumulation.md) add two accumulation
records. [ST/FBD ESEL/DERV](st-process-signals.md) add enhanced selection and derivative
records. [ST FGEN/DEDT](st-curves-delay.md) add piecewise curves and sampled delay.
[ST PI](st-pi-regulation.md) adds a PROP_INT software regulator.
[ST/FBD BTDT/MVMT](target-bit-moves.md) add explicit-target DINT field/mask
operations with logical records. These twenty-nine additional calls are excluded from the RLL dispatch count.
SCL/HLL/SNEG/SSUM and [TONR/TOFR/RTOR/CTUD/OSRI/OSFI](fbd-stateful.md) also
execute in the limited [FBD graph](function-blocks.md), alongside FBD-only SEL/MUX.
Sixty-three graph blocks are supported: twenty-three shared ST-call names, thirty-four
common RLL names and six FBD-only forms. These forms
include [Boolean logic/memory](fbd-boolean.md), [RLIM/MAXC/MINC](fbd-rate-capture.md), [UPDN/INTG](fbd-accumulation.md) and [ESEL/DERV](fbd-process-signals.md).
[ADD/SUB/MUL/DIV/ABS/NEG](fbd-arithmetic.md) and
[SQR/LN/LOG/XPY/DEG/RAD/SIN/COS/TAN/ASN/ACS/ATN](fbd-advanced-math.md) use two
logical math records; [MOD](fbd-conversions.md) adds finite REAL remainder.
[TRN/TOD/FRD](fbd-conversions.md) add typed conversion Blocks over logical
FBD_TRUNCATE/FBD_CONVERT records, sharing the existing ladder BCD calculations.
[EQU/NEQ/GRT/GEQ/LES/LEQ/LIM](fbd-comparisons.md) add FBD_COMPARE/FBD_LIMIT
with finite REAL inputs and BOOL outputs. These Block forms add no one-record
RLL/ST call overloads. [AND/OR/XOR/NOT/MEQ/MVMT](fbd-bitwise.md) add DINT bitwise/masked Block forms
and four logical record models. MVMT now also executes as a supported ST call.
The four Boolean record types also have bounded logical models. Other ST calls
lack FBD forms.

Ladder [TRN](lreal-truncate.md) also accepts finite floating L/l source constants
with its existing integer, REAL and LREAL destination types.

## Instruction families

| Family | RLL model, limited forms | Expression only; standalone remains | Remaining names |
| --- | --- | --- | --- |
| Alarm Instructions | [`ALMD`](ladder-alarm.md), [`ALMA` levels and rate of change](ladder-alarm.md#analog-level-alarms) | — | `ASO` |
| Advanced Math Instructions | `LN`, `LOG`, `XPY` | — | — |
| Array (File)/Shift Instructions | `BSL`, `BSR`, `FFL`, `FFU`, `LFL`, `LFU` | — | — |
| Array File/Misc. Instructions | `AVE`, `COP`, `CPS`, `FAL`, `FLL`, `FSC`, `SIZE`, `SRT`, `STD` | — | — |
| ASCII Conversion Instructions | `DTOS`, `LOWER`, `RTOS`, `STOD`, `STOR`, `UPPER` | — | — |
| ASCII Serial Port Instructions | — | — | `ABL`, `ACB`, `ACL`, `AHL`, `ARD`, `ARL`, `AWA`, `AWT` |
| ASCII String | `CONCAT`, `DELETE`, `FIND`, `INSERT`, `MID` | — | — |
| Bit Instructions | `ONS`, `OSF`, `OSR`, `OTE`, `OTL`, `OTU`, `XIC`, `XIO` | — | — (ST/FBD OSRI/OSFI listed above) |
| Compare Instructions | `CMP`, `EQU`, `GEQ`, `GRT`, `LEQ`, `LES`, `LIM`, `MEQ`, `NEQ` | — | — |
| Compute/Math Instructions | `ABS`, `ADD`, `CPT`, `DIV`, `MOD`, `MUL`, `NEG`, `SQR`, `SUB` | `SQRT` | — |
| Drives Instructions | — | — | `HMIBC`, `PMUL`, `SCRV`, `SOC` (ST-only PI and ST/FBD INTG/UPDN listed above) |
| Drive Safety Instructions | — | — | `SBC`, `SDI`, `SFX`, `SLP`, `SLS`, `SOS`, `SS1`, `SS2` |
| Equipment Phase Instructions | — | — | `PATT`, `PCLF`, `PCMD`, `PDET`, `PFL`, `POVR`, `PPD`, `PRNP`, `PSC`, `PXRQ` |
| Equipment Sequence Instructions | — | — | `SASI`, `SATT`, `SCLF`, `SCMD`, `SDET`, `SOVR` |
| Filter Instructions | — | — | `HPF`, `LDL2`, `NTCH` (ST/FBD DERV and ST-only LPF software model listed above) |
| For Break Instructions | `BRK`, `FOR` | — | — |
| Input/Output Instructions | `GSV`, `SSV`, [`IOT`](device-io.md#immediate-output-captures), [`MSG`](ladder-message.md) | — | — |
| License Instructions | — | — | `LV` |
| Math Conversion Instructions | `DEG`, `FRD`, `RAD`, `TOD`, `TRN` | — | — |
| Metal Form Instructions | — | — | `AVC`, `CBCM`, `CBIM`, `CBSSM`, `CPM`, `CSM`, `EPMS`, `MMVC`, `MVC` |
| Motion Event Instructions | — | — | `MAOC`, `MAR`, `MAW`, `MDOC`, `MDR`, `MDW` |
| Motion Group Instructions | — | — | `MGS`, `MGSD`, `MGSP`, `MGSR` |
| Motion Move Instructions | — | — | `MAG`, `MAH`, `MAJ`, `MAM`, `MAPC`, `MAS`, `MATC`, `MCCP`, `MCD`, `MCSV`, `MDAC`, `MRP` |
| Motion State Instruction | — | — | `MAFR`, `MASD`, `MASR`, `MDF`, `MDO`, `MDS`, `MSF`, `MSO` |
| Move/Logical Instructions | `AND`, `BTD`, `CLR`, `MOV`, `MVM`, `NOT`, `OR`, `SWPB`, `XOR` | — | — (ST/FBD BTDT/MVMT, FBD Boolean blocks and ST/FBD DFF/JKFF/RESD/SETD listed above) |
| Multi-Axis Coordinated Motion Instructions | — | — | `MCCD`, `MCCM`, `MCLM`, `MCPM`, `MCS`, `MCSD`, `MCSR`, `MCT`, `MCTO`, `MCTP`, `MCTPO`, `MDCC` |
| PlantPAx instructions | — | — | `PAH`, `PAI`, `PAID`, `PAIM`, `PAO`, `PBL`, `PCMDSRC`, `PD4SD`, `PDBC`, `PDI`, `PDO`, `PDOSE`, `PFO`, `PHLS`, `PINTLK`, `PLLS`, `PMTR`, `PNPOS`, `PPERM`, `PPID`, `PPTC`, `PRI`, `PRT`, `PTST`, `PVLV`, `PVLVMP`, `PVLVS`, `PVSD` |
| Process Control Instructions | — | — | `ALM`, `CC`, `D2SD`, `D3SD`, `IMC`, `LDLG`, `MMC`, `PIDE`, `POSP`, `RMPS`, `SRTP`, `TOT` |
| Program Control Instructions | `AFI`, `EVENT`, `JMP`, `JSR`, `LBL`, `MCR`, `NOP`, `RET`, `SBR`, `TND`, `UID`, `UIE` | — | `EOT`, `JXR`, `SFP`, `SFR` |
| Safety Instructions | — | — | `CROUT`, `DCA`, `DCAF`, `DCM`, `DCS`, `DCSRT`, `DCST`, `DCSTL`, `DCSTM`, `DIN`, `ENPEN`, `ESTOP`, `FPMS`, `FSBM`, `LC`, `RIN`, `ROUT`, `SMAT`, `THRS`, `THRSE`, `TSAM`, `TSSM` |
| Select/Limit Instructions | — | — | — (FBD-only SEL/MUX, ST/FBD HLL/SNEG/SSUM and ST/FBD ESEL/RLIM listed above) |
| Sequencer Instructions | `SQI`, `SQL`, `SQO` | — | — |
| Sequential Function Chart (SFC) Instructions | — | — | `ACTION`, `STEP`, `STOP`, `TRANSITION` |
| Special Instructions | `DDT`, `DTR`, `FBC`, `PID` | — | — |
| Statistical Instructions | — | — | — (ST-only MAVE/MSTD and ST/FBD MAXC/MINC listed above) |
| Timer/Counter Instructions | `CTD`, `CTU`, `RES`, `RTO`, `TOF`, `TON` | — | — (ST/FBD variants listed above) |
| Trigonometric Instructions | `ACS`, `ASN`, `ATN`, `COS`, `SIN`, `TAN` | `ACOS`, `ASIN`, `ATAN` | — |
| Additional alphabetical entries | — | `TRUNC` | `BPT`, `PCE`, `TPT` |
| Additional motion registration and homing | — | — | `MAAT`, `MAHD`, `MRAT`, `MRHD` |

ASO is additionally confirmed in installed v35 instruction help for
ALARM_SET_CONTROL; it is not implemented. The
[predefined-type inventory](predefined-data-types.md) tracks its associated
schema/behavior backlog separately from instruction names.

[WallClockTime GSV](wall-clock-gsv.md) adds UTC CurrentValue/DateTime and explicit
UTC-local LocalDateTime reads to existing RLL/ST calls. Exact DT/LINT/two-DINT
counters, seven-DINT calendar arrays or declared records, lazy references and whole-advance rollback
are modeled; no clock setters, time-zone/DST changes or native parity is implied.

[Scan-time GSV](scan-time-gsv.md) adds Program/Task LastScanTime and MaxScanTime
reads to existing RLL/ST calls with scalar DINT or TIME32 destinations. Values are committed interpreter measurements;
whole-Task reads now support independently measured Continuous/Periodic and
[qualified Event tasks](event-task-timing.md). They do not predict
controller performance or establish native per-execution visibility.
[Current-instance THIS](current-instance-gsv.md) selects ordinary scheduled
Program/Task contexts without expanding the existing timing/attribute profile.

[Finite LREAL storage](lreal-storage.md) adds binary64 MOV/CLR conversions and
atomic tag access; [homogeneous tagged ladder math](lreal-math.md) additionally executes. ST expressions and
aggregate byte-copy layouts remain unqualified.

[LREAL advanced ladder math](lreal-advanced.md) adds matching-tag roots, powers,
logarithms, angle conversion and trigonometry; ST/CPT/CMP remain unqualified.

[Mixed-tag LREAL arithmetic](mixed-lreal-math.md) adds five binary operations
with all ten numeric source tag types and a LREAL result.
[Mixed-tag comparisons/LIM](mixed-lreal-comparisons.md) additionally promote
numeric tag inputs when at least one is LREAL. [Signed DINT-range constants](lreal-constants.md)
add binary arithmetic, direct relations and limits; floating/typed/larger literals
and other advanced math remain separate. [Mixed XPY powers](mixed-lreal-power.md)
qualify numeric tag pairs and signed DINT constants with a LREAL result.
[Unary LREAL results](lreal-unary-sources.md) additionally accept all numeric tag
sources and signed DINT constants across eleven roots/logs/angle/trig forms.
[LREAL arithmetic results](lreal-destination-math.md) now select binary64 for
seven basic operations and XPY without requiring an actual LREAL source.
[REAL comparison promotion](mixed-real-comparisons.md) additionally covers
all nine numeric source types, constants and converted-limit behavior.

[Typed AOI input constants](aoi-constants.md) add exact decimal LINT, UDINT,
ULINT and finite LREAL values to required scalar Inputs as of `26.1112.213355`.
Copied input/prescan/false-mode behavior is retained; Output and InOut operands
still require writable tags. **AOI constants lab** demonstrates all four types.

## Remaining forms of existing instructions

| Existing family | Remaining semantic/operand work |
| --- | --- |
| Bit logic, comparisons, MOV/CLR and math | Homogeneous LINT/unsigned operations have bounded [RLL](integer-execution.md) and [ST](wide-st.md) profiles, including [decimal ST L/U/UL literals](st-integer-literals.md). Mixed types, remaining conversions, status/fault behavior and native scan parity remain unfinished. |
| SQR/XPY/LN/LOG/DEG/RAD/ACS/ASN/ATN/COS/SIN/TAN | [Finite ladder forms](math-operations.md) for v35 5580, with SINT/INT/DINT/REAL sources and results, nearest-even integer conversion and range rollback. Structural preflight skips saved dynamic indices; false/prescan skip operands, true math checks reached indices/values, and full writes establish unknown results. Matching-tag [LREAL forms](lreal-advanced.md) additionally execute. Other wide/unsigned results and operand forms, plus native precision/status/nonfinite/overflow behavior, remain unfinished; FBD uses separate REAL-record forms. |
| FRD/TOD/SWPB | [8/16/32/64-bit signed/unsigned BCD with all-eight-integer FRD/TOD pairs](numeric-conversions.md), plus INT/DINT byte-order forms, for v35 5580. FRD/TOD accept decimal L/U/UL sources. SWPB also supports ST calls and INT-to-DINT sign extension. Structural preflight skips saved dynamic indices; false/prescan skip live operands, true calls check actual indices/values, and full writes establish unknown results. TOD uses 2/4/8/16 decimal digits by destination width; FRD weights the declared nibbles including A-F. Standalone BCD expressions, broader FBD forms and native saturation/overflow/status behavior remain unfinished. |
| MVM/BTD | [SINT/INT/DINT ladder bit transfers](bit-transfer.md) support zero-fill, masks, overlap and bounded fields. v35 5580 structural preflight skips saved dynamic indices while false/prescan; enabled calls retain address, mask and preserved-bit requirements. Full writes establish unknown results. Wide/unsigned operands and native math/fault status remain unfinished; ST/FBD target moves have separate support above. |
| BSL/BSR/FFL/FFU/LFL/LFU and CONTROL RES | [Bounded ladder shifts and FIFO/LIFO](control-operations.md), logical CONTROL state, [literal LEN/POS initialization for sixteen ladder forms](control-operations.md#literal-len-and-pos-on-import) and [matching strings/explicit UDTs with LREAL and time/date fields](record-queues.md) and [TIMER/COUNTER/CONTROL payloads](basic-record-queues.md). [Aliases and bounded indirect starts](queue-references.md) are supported for these shift/queue forms. [One-dimensional AOI InOut/local arrays](aoi-queues.md) now work in RLL. [Numeric FIFO/LIFO conversions](queue-conversions.md) support narrow numeric payloads of different types in the v35 5580 profile, including independently typed AOI operands. Native layout/status/overflow parity, wide types, operational/AOI records and broader AOI shapes/lifecycle remain unfinished. |
| SQO/SQI/SQL | [DINT ladder sequencers](sequencer-operations.md) for v35 5580, with startup row zero and cyclic rows 1..LEN. [Alias/indirect starts and RLL AOI tables](sequencer-references.md) now execute. [Narrow source types and complete source patterns](sequencer-sources.md) now execute. Wider types, broader AOI shapes and native scan/fault parity remain unfinished. |
| Wide FAL/FSC | [Integer file operations](integer-files.md) add exact matching LINT/unsigned FAL transforms and shared wide/mixed CMP searches, preserving ALL/numeric/INC from idle or completed sources and existing AOI bindings. [Binary64 FAL](file-arithmetic.md#binary64-expressions) supports LREAL and mixed numeric operands. [Binary64 FSC](file-search.md#binary64-searches) supports LREAL comparisons. Other promotion/function forms and native status/cursor/fault/lifecycle/layout parity remain separate. |
| FAL | [Bounded ALL/numeric ladder iteration](file-arithmetic.md) and [INC from idle/completed source controls](file-incremental.md), indexed destinations, sequential writes and the CPT grammar. [RLL AOI forms](aoi-file-operations.md) use exact InOut/local operands and canonical progress. [REAL calculation and finite binary64 result-store overflow](file-arithmetic.md#real-overflow-and-retry) latches ER and retains a transactional retry position. Saved partial INC state, additional types/functions, broader AOI lifecycle/schema and native cursor/overflow/status/partial-fault behavior remain unfinished. |
| FSC | [Bounded ALL/numeric ladder search](file-search.md) and [INC from idle/completed source controls](file-incremental.md), comparison expressions and FD/IN. [RLL AOI forms](aoi-file-operations.md) now support frame-scoped searches and per-CONTROL progress. Saved partial INC state, broader AOI lifecycle/schema, additional expressions and native cursor/status/fault parity remain unfinished. |
| SRT | [Dimension-wise ladder/ST sorting](array-sort.md), with SINT/INT/DINT/REAL arrays and three-operand ST calls. The qualified whole-region profile retains POS zero; [alias/indirect and AOI references](sort-references.md) now execute with conservative ST FOR effects. Native internal cursor, partial-state/fault behavior, broader lifecycle and types remain unfinished. |
| AVE/STD | [Dimension-wise statistics](array-statistics.md) with SINT/INT/DINT/REAL arrays and AVE results, REAL STD results and logical CONTROL. [Alias/indirect starts and RLL AOI arrays](statistics-references.md) now execute. [AVE error latches](array-statistics.md#ave-error-latches), [STD arithmetic overflow](array-statistics.md#std-arithmetic-overflow) and [one-dimensional range overruns](array-statistics.md#std-one-dimensional-range-overruns) preserve results; AVE retains errors on false rungs until reset. Partial POS/resume, broader AOI lifecycle and native precision/fault/status behavior remain unfinished. |
| COP/CPS | [Numeric byte regions](numeric-copies.md) support SINT/INT/DINT/LINT, unsigned integers and finite REAL/[LREAL](lreal-copy.md) in RLL/ST: destination-sized requests, clipped numeric-region bounds, partial destination preservation and forward overlap. [Structural/lazy selection](numeric-copies.md#operand-selection) defers saved lengths/indices/values; runtime transfer limits and unknown/full/partial-write rules remain. Aggregate/BOOL/string layouts, cross-member/base-tag forms, native synchronization and fault/partial-effect parity remain unfinished. |
| Scalar arithmetic/bitwise selection | [ADD/SUB/MUL/DIV/MOD/NEG/ABS/AND/OR/XOR/NOT](scalar-math.md) use structural preflight and lazy source reads. Integer-tag bitwise operations mix all eight signed/unsigned integer types, zero-extend source patterns, complement after promotion and keep typed destination low bits. [Plain and typed immediates](typed-bitwise-operands.md) mix with all eight integer tag types. [REAL bitwise operands](scalar-math.md#real-operands-in-ladder-bitwise-instructions) round to DINT and support REAL destinations. [LREAL operands](scalar-math.md#lreal-operands-in-ladder-bitwise-instructions) round to signed LINT. [Mixed floating forms](scalar-math.md#mixed-floating-and-integer-bitwise-operands) support all integer destinations and typed integer sources. MOD adds finite REAL sources mixed with SINT/INT/DINT, float32 input/result conversion, dividend-sign remainder and rounded narrow results. Other calculation/width/range rules remain bounded; complete promotion/native precision/status forms are unfinished. |
| Clipped numeric FLL | [Clipped fill windows](clipped-fills.md) stop oversized requests at the selected numeric array/member or scalar boundary. Captured operands, conversions, lazy reads and rollback remain; existing emulator ST calls protect complete FOR write effects. Native packed cross-member traversal, native ST availability, wide types and lifecycle/status/partial-fault parity remain separate. |
| Time/date ADD/SUB, MOV, CLR, EQU/NEQ/LES/LEQ/GRT/GEQ | [Exact v35 5580 time/date storage](time-date-storage.md) supports typed literals, exact ADD/SUB, same-family MOV and relations, CLR and a LINT/LDT MOV bridge. DT, TIME32 and TIME also accept [selected GSV reads](time-date-storage.md#reading-timestamps-and-durations-with-gsv). Lossy conversion and native layout remain open. |
| MOV/CLR | [Scalar storage](numeric-storage.md) supports ten numeric types with integer pattern conversion, representable floating rounding and full unknown writes. [String MOV](string-operations.md#ladder-string-mov) handles tag/literal sources and clips to destination capacity. String CLR, non-string aggregates and native overflow/status remain unfinished. |
| TON/TOF/RTO | [Typed ladder timers](ladder-timers.md) require known nonnegative PRE/ACC and only read saved EN/DN on paths that consume them. Unknown RTO DN can remain while false. Existing millisecond recurrence, canonical clocks, prescan, aliases/UDTs/AOIs and value/history rollback remain. Native precision, skipped-execution/status/fault/lifecycle parity and broader profiles remain separate. |
| CTU/CTD and TIMER/COUNTER RES | [Typed ladder counters/resets](ladder-counters.md) check consumed DINT PRE/ACC and BOOL edge history; false counter rungs establish their own edge, signed wrap latches preserve DN until the opposite wrap or reset, unknown full resets preserve PRE, and aliases/UDTs/AOIs participate in rollback. Counter prescan needs actual indices. Timer clocks, CONTROL RES, native flags/faults/lifecycle/layout and broader profiles remain separate. |
| Contacts/coils/one-shots | [Bit logic](bit-logic.md) validates types/shape without saved BOOL values. Complete BOOL writes establish unknowns; contacts/latches and one-shots consume values only when needed. Packed integers, native layout/fault/postscan/lifecycle and broader profile qualification remain bounded. |
| Numeric comparisons | [EQU/NEQ/LES/LEQ/GRT/GEQ/LIM/MEQ](numeric-comparisons.md) validate types/shape without saved values and skip live indices/values while false. True calls consume all operands. MEQ mixes all eight integer types and bounded plain or typed immediates with read-only inputs. [String comparison literals](string-operations.md#ladder-string-comparison-literals) work in either operand of the six standalone relations. Arithmetic promotion and native parity remain incomplete. |
| FOR operand selection | [Indirect loop operands](ladder-loops.md#runtime-selected-operands) add structural/lazy scalar selection, a retained index cell and live terminal/step references. Existing narrow types, BRK, inclusive ranges, budgets and rollback remain. Native sampling/status/lifecycle and broader forms remain separate. |
| JSR/SBR/RET operand selection | [Indirect routine arguments](indirect-routine-calls.md) add v35 5580 runtime-selected caller elements and [ladder callee transfers](indirect-routine-calls.md#indexed-ladder-sbr-and-ret). JSR captures caller addresses at entry and permits distinct live result cells in one array. SBR and RET resolve their live elements at transfer time. [Typed numeric constants](indirect-routine-calls.md#typed-numeric-constants) add exact L/U/UL and LREAL inputs/returns. ST SBR/RET keep static references. Dynamic subarrays, AOI calls and native sampling/fault parity remain separate. |
| Statistics selection | [AVE/STD operands](statistics-operands.md) structurally validate result references, skip their live indices when false or inhibited by EN/DN/ER and establish unknown result elements on fresh calculations. Types, overlap guards, CONTROL/prescan reads, float32 math, rounding, bounds/latches and native parity retain separate requirements. |
| Sequencer selection | [SQI/SQO/SQL operands](sequencer-operands.md) structurally validate masks/payloads, skip their live indices on false/invalid-state paths and skip compared-source/output references for zero masks after table checks. Held SQO/SQL still use current data; CONTROL addresses, prescan, bounds/error policies, algorithms and native parity retain separate requirements. |
| CONTROL selection | [Shift/queue payloads and CONTROL RES](control-operands.md) validate declared types/permissions without live payload indices; false/held/data-free paths defer those reads. CONTROL RES establishes unknown POS/flags with LEN retained and resolved modeled incremental progress cleared; false/prescan skips its address. Prescan still needs actual shift/queue control records and queue LEN/POS. Existing algorithms, broader consumers and native parity remain separate. |
| Aggregate COP/CPS | [Matching logical record copies](aggregate-copies.md) validate structure without saved lengths or indices, skip live operands on false/prescan, propagate unknowns, preserve complete strings and sequential overlap, [clip logical windows](clipped-aggregates.md), protect complete ST FOR effects and bound actual work with rollback. Basic records/strings/nested UDTs, including LREAL/time/date fields, and existing ST calls are covered; packed layouts, operational/AOI aggregates, native clipping/private histories/synchronization and parity remain separate. |
| FLL/SIZE | [Numeric FLL](numeric-fill.md) qualifies v35 5580 integer narrowing/sign extension, representable REAL conversion and lazy references. Native clipping/cross-member layouts, REAL overflow/status, wider FLL types and aggregate fill qualification remain unfinished; [SIZE](size-truncate.md) now handles selected/member arrays and REAL results, with direct string forms still excluded; [Aggregate zero fills](aggregate-fill.md) add typed schema-based TIMER/COUNTER/CONTROL/string/UDT writes, including LREAL/time/date members, unknown destinations, lazy operands, logical clipping, complete ST FOR effects and bounded actual scalar work; [all-ones integral record patterns](aggregate-fill.md#all-ones-record-fills) also execute; other nonzero patterns, operational records and native ABI/history/reset parity remain unfinished. |
| CPT/CMP/MEQ | [Narrow integer division](integer-expressions.md) now works in CPT/CMP and FAL/FSC expressions with documented REAL promotion. [Homogeneous LINT/unsigned ladder forms](ladder-wide-expressions.md) add exact CPT/CMP; MEQ also mixes all eight integer types with bounded immediates. [Mixed integer CMP](ladder-wide-expressions.md#mixed-integer-cmp) adds direct relations and eager Boolean composition when every tag range fits the highest-ranked actual type. [Numeric CPT/CMP selection](integer-expressions.md#operand-selection) adds structural preflight and lazy saved values/indices without expanding calculations. [Mixed CPT/CMP arithmetic](ladder-wide-expressions.md#mixed-integer-arithmetic) adds exact operations when every arithmetic subtree contains a source of the common type and the CPT result matches that type. Other intermediates/conversions, wider immediates, functions/power, file/index consumers and native arithmetic/status parity remain unfinished. |
| PID (ladder software profile) | [Logical PID](ladder-pid.md), independent/dependent P/PI/PID, scaling, limits, [integer operands and hardware manual](pid-operands.md), alarms, [derivative/deadband](pid-dynamics.md) and [manual PVT/inhold](pid-restart.md), [one-way cascade](pid-cascade.md) and [ladder AOI PID](aoi-pid.md). Native smoothing coefficients/cascade feedback/module restart, further operands/languages and native coefficients/status/fault/layout parity remain unfinished. |
| PI (ST only, software profile) | [Logical PROP_INT regulation](st-pi-regulation.md), linear/shaped gains, trapezoidal integral, holds, limits, initialization, timing and rollback. Native coefficients/thresholds/rounding/ordering, RTS, FBD graphs and packed layouts remain unfinished; the separate [ladder PID](ladder-pid.md) has bounded P/PI/PID behavior and PIDE remains unimplemented. |
| FGEN/DEDT (ST only) | [Logical curves and delay](st-curves-delay.md), selected piecewise tables, endpoint clamps, sample queues, resizing, health/timing/status and rollback. Native startup/conditional diagnostics/precision/resize/recovery, RTS, FBD graphs and packed layouts remain unfinished. |
| ESEL/DERV (ST/FBD) | [Logical process signals](st-process-signals.md), healthy high/low/median/mean/manual selection, Program/Operator requests, timed rate of change, bypass and rollback. Native startup/request/health/timing/rounding qualification, RTS, general FBD forms and packed layouts remain unfinished. |
| UPDN/INTG (ST/FBD) | [Logical accumulation records](st-accumulation.md), per-call totals, trapezoidal integration, initialization, holds, limits, alarms, timing and rollback. Native startup/rounding/precedence, RTS, general FBD forms and packed layouts remain unfinished. |
| DFF/JKFF/RESD/SETD (ST/FBD) | [Logical Boolean memory](st-digital-memory.md), sampled clock/data/toggle behavior, Clear priority, latch dominance, complements and rollback. General FBD, layouts and native lifecycle/output-write/status/fault parity remain unfinished. |
| LPF (ST only, software solver) | [Logical FILTER_LOW_PASS](st-low-pass-filter.md), explicit bilinear orders 1/2/3, elapsed/Periodic/oversample timing, bounds/status and transactional sections. Native recurrence/coefficients/precision/transitions, RTS, FBD/layout/lifecycle/fault parity remain unfinished. |
| MAXC/MINC (ST/FBD) | [Logical capture records](st-capture.md), retained finite REAL extrema, held reset baselines, skipped calls and rollback. General FBD forms, packed layouts and native lifecycle/precision/nonfinite/status/fault parity remain unfinished. |
| MAVE/MSTD (ST only) | [Logical moving-statistics records](st-moving-statistics.md), uniform/direct-weighted means, population deviation, active queue fill/resize, initialization, diagnostics and rollback. FBD graphs and native queue/layout/precision/lifecycle/status/fault parity remain unfinished. |
| RLIM (ST/FBD) | [Logical RATE_LIMITER](st-rate-limiter.md), separate rates, bypass, Periodic/elapsed and oversample timing, status aliases and transactional history. Module timestamp mode, general FBD forms and native timing/precision/status/fault/layout parity remain unfinished. |
| HLL/SNEG/SSUM (ST/FBD) | [Logical signal records](st-signals.md), both/one-sided limits, inclusive alarms, status aliases, selectable negation and eight weighted input pairs plus bias. General FBD and native precision/overflow/status/layout/fault parity remain unfinished. |
| SCL (ST/FBD) | [Logical SCALE](st-scaling.md), finite REAL scaling, extrapolation/limiting, raw alarms, invalid-range status and rollback. General FBD and native precision/overflow/status/layout/fault parity remain unfinished. |
| OSRI/OSFI (ST/FBD) | [Logical FBD_ONESHOT](st-oneshot.md), sampled rising/falling edges, startup suppression, skipped calls and transactional history. General FBD, mixed instruction kinds on one record and native layout/lifecycle/fault parity remain unfinished. |
| CTUD (ST/FBD) | [Logical FBD_COUNTER](st-counter.md), sampled up/down edges, first-call/Run priming, reset, signed wrap and transactional history. General FBD and native reset/flag/layout/fault parity remain unfinished. |
| TONR/TOFR/RTOR (ST/FBD) | [Logical FBD_TIMER and elapsed-time profile](st-timers.md), reset/retention, skipped calls, status aliases and rollback. General FBD, native clock/status/fault/layout parity and other profiles remain unfinished. |
| TON/TOF/RTO/CTU/CTD/RES | All state transitions, shared instances, skipped scans, timing/fault behavior and target-specific types. Standard RLL import supports [literal PRE/ACC initialization](ladder-timers.md#literal-presets-on-import) for direct static records. Broader initialization and native precedence remain open. |
| FBC/DDT | [DINT ladder bit diagnostics](file-bit-compare.md), bit offsets, all/one-mismatch modes, result wrapping, selective DDT updates and prescan/false controls. [Alias/indirect and RLL AOI references](bit-diagnostic-references.md) now execute with canonical roles and lazy fixed result windows. Broader AOI shapes/profiles and native sampling/cursor/status/fault parity remain unfinished. |
| DTR | [DINT ladder data transition](data-transition.md), complete prior-reference comparison, true/false writes and lexical prescan, including existing AOI bindings. Other profiles and native operand/status/fault parity remain unfinished. |
| MCR | [Paired ladder zones](master-control.md), false scanning, unconditional endings, routine/AOI isolation and trace markers. Open-ended/conditional/nested zones, cross-boundary jumps and native scan/fault/CPU parity remain unfinished. |
| FOR/BRK | [Ladder indexed routine loops](ladder-loops.md), signed inclusive bounds, early exits, nested calls and task-isolated frames. Native operand sampling/overflow/watchdog/postscan parity, recursion, AOI and SFC forms remain unfinished. |
| JSR/SBR/RET/JMP/LBL/TND | Remaining legal parameter/reference and control-flow forms, task/language interactions and prescan behavior. Current calls support bounded v35 5580 indirect JSR and ladder SBR/RET elements, exact counts/types/dimensions and bounded nesting. |
| LOWER/UPPER/STOR/RTOS | [ASCII case and decimal/REAL conversion](string-conversions.md) in RLL/ST, explicit user strings, aliases, UDTs and existing AOI bindings. RTOS uses a documented software format; native formatting/status/fault parity and STOR exponent/no-digit edge behavior remain unfinished. |
| CONCAT/MID/FIND/INSERT/DELETE/DTOS/STOD/TRN | [TRN](size-truncate.md) adds lazy REAL reads; [tagged LREAL TRN](lreal-truncate.md) preserves binary64 sources and supports representable signed/unsigned integer and REAL/LREAL destinations. [Common search/editing forms](string-operations.md) support RLL/ST and represented user strings. [DELETE retained windows](string-operations.md#delete-retained-windows) permit unknown removed bytes while requiring every retained byte. [Operand selection](string-operations.md#operand-selection) adds structural preflight, lazy dynamic references and unknown full writes for string calls/relations/CMP in v35 5580. Empty-search/zero-delete and broader range/type/conversion/status/encoding behavior remain unfinished. |
| UID/UIE | [Balanced task-local interrupt control](interrupt-control.md) defers higher-priority EVENT requests until the outermost UIE in RLL/ST, across routine calls and with advance rollback. Unmatched-pair/persistent-state behavior, CPU/Periodic preemption, native latency/watchdog/fault/Safety, AOI/harness/ST FOR and other profiles remain separate. |
| EVENT | [Qualified instruction-only Event tasks](event-tasks.md) in RLL/ST: immediate higher priorities, deferred lower/equal priorities, pending-request coalescing, active-overlap suppression, [configured timeouts](event-tasks.md#configured-timeouts) and shared limits/rollback. Native time slicing/pending-duplicate semantics, external triggers, AOIs/harness/ST FOR forms and CPU/status parity remain unfinished. |
| GSV | Controller AuditValue/ChangesToDetect retain LINT/two-DINT reads. [Explicit Task/Controller settings](gsv-configuration.md) add exact INT/DINT/string destinations. [ControllerDevice identity](gsv-configuration.md#controller-device-identity) adds a counted SINT window and INT fields. [Program/Task timing](scan-time-gsv.md) and [logical Event Status](event-task-status.md) and [OverlapCount](event-overlap-count.md) add bounded runtime reads. [Task starts and intervals](task-start-gsv.md) add committed DT and TIME destinations and 64-bit word windows. Other objects/attributes, native status, cross-type byte-copy forms and broader SSV remain unfinished. |
| SSV | [Program DisableFlag](program-disable.md) enables or disables qualified scheduled Programs with a SINT source and live GSV readback. [Task InhibitTask](task-inhibition.md) controls Standard Continuous/Periodic and qualified Event releases with an exact DINT source, live GSV/read-attribute feedback and rollback. [Task Rate](gsv-configuration.md#changing-a-periodic-task-rate) stages a Periodic task rate with live GSV readback. [Event Rate and EnableTimeOut](event-tasks.md#runtime-timeout-settings) stage timeout settings. [Task Priority](gsv-configuration.md#changing-a-task-priority) updates Periodic/Event arbitration at the next advance. [Task Watchdog](gsv-configuration.md#changing-a-task-watchdog) supports DINT settings and qualified zero-write defaults. [Scan time resets](scan-time-gsv.md#resetting-lastscantime) clear either Program/Task scan-time measurement. [Task timing resets](task-start-gsv.md#resetting-task-intervals) clear the start timestamp or either interval independently. [Event Task Status](event-task-status.md) supports named/THIS logical bit replacement, and [OverlapCount](event-overlap-count.md) supports an independent zero reset. [Runtime Event inhibition](event-task-inhibition.md) adds named/THIS control and live pending-request checks. Other classes/attributes, Safety, AOIs and harness calls remain unfinished. |
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

[LREAL CPT/CMP expressions](lreal-expressions.md) now add mixed numeric-tag
binary64 calculations and comparisons, plus copied scalar AOI LREAL parameters.
Other expression consumers and native equivalence retain separate limits.

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
