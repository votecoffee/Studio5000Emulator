# Instruction execution inventory

Audited 2026-10-29; array statistics updated for app `26.1029.193708`. The engine has **86 built-in
RLL dispatch entries**. Every entry has operand/type/scan limitations; none is a
claim of complete native controller equivalence. Project-defined AOIs are
separate. See the [full capability and remaining-work checklist](emulation-coverage.md).

This table covers the installed v35 instruction-set overview and A–Z indexes.
It includes language aliases and product-specific families, so it must not be
used to calculate a compatibility percentage. Firmware/controller/language
availability still needs qualification. SFC named elements are shown as a
separate language family, not RLL mnemonics.

- **RLL model** means a dispatch entry exists for supported forms.
- **Expression only** means the name can be used in the supported CPT/ST
  expression grammar; a standalone instruction/block is still unimplemented.
- **Remaining names** have no built-in execution implementation. ST FOR/EXIT
  constructs do not implement the distinct RLL FOR/BRK instructions.

## Instruction families

| Family | RLL model, limited forms | Expression only; standalone remains | Remaining names |
| --- | --- | --- | --- |
| Alarm Instructions | — | — | `ALMA`, `ALMD`, `ASO` |
| Advanced Math Instructions | `LN`, `LOG`, `XPY` | — | — |
| Array (File)/Shift Instructions | `BSL`, `BSR`, `FFL`, `FFU`, `LFL`, `LFU` | — | — |
| Array File/Misc. Instructions | `AVE`, `COP`, `CPS`, `FLL`, `SIZE`, `STD` | — | `FAL`, `FSC` |
| ASCII Conversion Instructions | `DTOS`, `STOD` | — | `LOWER`, `RTOS`, `STOR`, `UPPER` |
| ASCII Serial Port Instructions | — | — | `ABL`, `ACB`, `ACL`, `AHL`, `ARD`, `ARL`, `AWA`, `AWT` |
| ASCII String | `CONCAT`, `DELETE`, `FIND`, `INSERT`, `MID` | — | — |
| Bit Instructions | `ONS`, `OSF`, `OSR`, `OTE`, `OTL`, `OTU`, `XIC`, `XIO` | — | `OSFI`, `OSRI` |
| Compare Instructions | `CMP`, `EQU`, `GEQ`, `GRT`, `LEQ`, `LES`, `LIM`, `MEQ`, `NEQ` | — | — |
| Compute/Math Instructions | `ABS`, `ADD`, `CPT`, `DIV`, `MOD`, `MUL`, `NEG`, `SQR`, `SUB` | `SQRT` | — |
| Drives Instructions | — | — | `HMIBC`, `INTG`, `PI`, `PMUL`, `SCRV`, `SOC`, `UPDN` |
| Drive Safety Instructions | — | — | `SBC`, `SDI`, `SFX`, `SLP`, `SLS`, `SOS`, `SS1`, `SS2` |
| Equipment Phase Instructions | — | — | `PATT`, `PCLF`, `PCMD`, `PDET`, `PFL`, `POVR`, `PPD`, `PRNP`, `PSC`, `PXRQ` |
| Equipment Sequence Instructions | — | — | `SASI`, `SATT`, `SCLF`, `SCMD`, `SDET`, `SOVR` |
| Filter Instructions | — | — | `DERV`, `HPF`, `LDL2`, `LPF`, `NTCH` |
| For Break Instructions | — | — | `BRK`, `FOR` |
| Input/Output Instructions | `GSV` | — | `IOT`, `MSG`, `SSV` |
| License Instructions | — | — | `LV` |
| Math Conversion Instructions | `DEG`, `FRD`, `RAD`, `TOD`, `TRN` | — | — |
| Metal Form Instructions | — | — | `AVC`, `CBCM`, `CBIM`, `CBSSM`, `CPM`, `CSM`, `EPMS`, `MMVC`, `MVC` |
| Motion Event Instructions | — | — | `MAOC`, `MAR`, `MAW`, `MDOC`, `MDR`, `MDW` |
| Motion Group Instructions | — | — | `MGS`, `MGSD`, `MGSP`, `MGSR` |
| Motion Move Instructions | — | — | `MAG`, `MAH`, `MAJ`, `MAM`, `MAPC`, `MAS`, `MATC`, `MCCP`, `MCD`, `MCSV`, `MDAC`, `MRP` |
| Motion State Instruction | — | — | `MAFR`, `MASD`, `MASR`, `MDF`, `MDO`, `MDS`, `MSF`, `MSO` |
| Move/Logical Instructions | `AND`, `BTD`, `CLR`, `MOV`, `MVM`, `NOT`, `OR`, `SWPB`, `XOR` | — | `BAND`, `BNOT`, `BOR`, `BTDT`, `BXOR`, `DFF`, `JKFF`, `MVMT`, `RESD`, `SETD` |
| Multi-Axis Coordinated Motion Instructions | — | — | `MCCD`, `MCCM`, `MCLM`, `MCPM`, `MCS`, `MCSD`, `MCSR`, `MCT`, `MCTO`, `MCTP`, `MCTPO`, `MDCC` |
| PlantPAx instructions | — | — | `PAH`, `PAI`, `PAID`, `PAIM`, `PAO`, `PBL`, `PCMDSRC`, `PD4SD`, `PDBC`, `PDI`, `PDO`, `PDOSE`, `PFO`, `PHLS`, `PINTLK`, `PLLS`, `PMTR`, `PNPOS`, `PPERM`, `PPID`, `PPTC`, `PRI`, `PRT`, `PTST`, `PVLV`, `PVLVMP`, `PVLVS`, `PVSD` |
| Process Control Instructions | — | — | `ALM`, `CC`, `D2SD`, `D3SD`, `DEDT`, `FGEN`, `IMC`, `LDLG`, `MMC`, `PIDE`, `POSP`, `RMPS`, `SCL`, `SRTP`, `TOT` |
| Program Control Instructions | `AFI`, `JMP`, `JSR`, `LBL`, `NOP`, `RET`, `SBR`, `TND` | — | `EOT`, `EVENT`, `JXR`, `MCR`, `SFP`, `SFR`, `UID`, `UIE` |
| Safety Instructions | — | — | `CROUT`, `DCA`, `DCAF`, `DCM`, `DCS`, `DCSRT`, `DCST`, `DCSTL`, `DCSTM`, `DIN`, `ENPEN`, `ESTOP`, `FPMS`, `FSBM`, `LC`, `RIN`, `ROUT`, `SMAT`, `THRS`, `THRSE`, `TSAM`, `TSSM` |
| Select/Limit Instructions | — | — | `ESEL`, `HLL`, `MUX`, `RLIM`, `SEL`, `SNEG`, `SSUM` |
| Sequencer Instructions | `SQI`, `SQL`, `SQO` | — | — |
| Sequential Function Chart (SFC) Instructions | — | — | `ACTION`, `STEP`, `STOP`, `TRANSITION` |
| Special Instructions | — | — | `DDT`, `DTR`, `FBC`, `PID` |
| Statistical Instructions | — | — | `MAVE`, `MAXC`, `MINC`, `MSTD` |
| Timer/Counter Instructions | `CTD`, `CTU`, `RES`, `RTO`, `TOF`, `TON` | — | `CTUD`, `RTOR`, `TOFR`, `TONR` |
| Trigonometric Instructions | `ACS`, `ASN`, `ATN`, `COS`, `SIN`, `TAN` | `ACOS`, `ASIN`, `ATAN` | — |
| Additional alphabetical entries | — | `TRUNC` | `BPT`, `PCE`, `SRT`, `TPT` |
| Additional motion registration and homing | — | — | `MAAT`, `MAHD`, `MRAT`, `MRHD` |

ASO is additionally confirmed in installed v35 instruction help for
ALARM_SET_CONTROL; it is not implemented. The
[predefined-type inventory](predefined-data-types.md) tracks its associated
schema/behavior backlog separately from instruction names.

## Remaining forms of existing instructions

| Existing family | Remaining semantic/operand work |
| --- | --- |
| Bit logic, comparisons, MOV/CLR and math | Homogeneous LINT/unsigned RLL operations now have a bounded [v35 5580 profile](integer-execution.md). Mixed types, remaining conversions, status/fault behavior and native scan parity remain unfinished. |
| SQR/XPY/LN/LOG/DEG/RAD/ACS/ASN/ATN/COS/SIN/TAN | [Finite REAL-result ladder forms](math-operations.md) for v35 5580, with SINT/INT/DINT/REAL sources. Integer destinations, wide/unsigned/LREAL sources, FBD and native precision/status/nonfinite behavior remain unfinished. |
| FRD/TOD/SWPB | [DINT BCD and INT/DINT byte-order forms](numeric-conversions.md) for v35 5580. SWPB also supports ST calls and INT-to-DINT sign extension. Other BCD types, mixed conversions, BCD expressions/FBD and native overflow/status behavior remain unfinished. |
| MVM/BTD | [SINT/INT/DINT ladder bit transfers](bit-transfer.md) support zero-fill, masks, overlap and bounded fields. Wide/unsigned operands, ST/FBD variants and native math/fault status remain unfinished. |
| BSL/BSR/FFL/FFU/LFL/LFU and CONTROL RES | [Bounded ladder shifts/numeric FIFO/LIFO](control-operations.md) and logical CONTROL state. Native layout/status parity, string/structure transfers, conversions and indirect/AOI array starts remain unfinished. |
| SQO/SQI/SQL | [DINT ladder sequencers](sequencer-operations.md) for v35 5580, with startup row zero and cyclic rows 1..LEN. Mixed source types, indirect/AOI table starts and native scan/fault parity remain unfinished. |
| AVE/STD | [Dimension-wise statistics](array-statistics.md) with SINT/INT/DINT/REAL arrays, REAL results and logical CONTROL. Partial POS/resume, integer AVE destinations, indirect/alias/AOI array starts and native precision/fault/status behavior remain unfinished. |
| COP/CPS | Raw byte reinterpretation, complete aggregate layouts, all legal source/destination forms and asynchronous/CPS synchronization behavior. Current copies require matching declared element types inside a modeled region. |
| FLL/SIZE | All legal types, narrowing/conversion rules and aggregate forms. Current FLL has bounded numeric destinations and DINT-zero structure fills. |
| CPT/CMP/MEQ | Complete expression/type/conversion matrix. MEQ currently covers SINT/INT/DINT; native arithmetic/status parity is unverified. |
| TON/TOF/RTO/CTU/CTD/RES | All state transitions, shared instances, skipped scans, timing/fault behavior and target-specific types. Current RLL timers/counters require neutral-text `?,?` operands. |
| JSR/SBR/RET/JMP/LBL/TND | Remaining legal parameter/reference and control-flow forms, task/language interactions and prescan behavior. Current calls use static references, exact counts/types/dimensions and bounded nesting. |
| CONCAT/MID/FIND/INSERT/DELETE/DTOS/STOD/TRN | [Common search/editing forms](string-operations.md) support RLL/ST and represented user strings. Empty-search/zero-delete and broader range/type/conversion/status/encoding behavior remain unfinished. |
| GSV | Currently only Controller AuditValue and ChangesToDetect, with an empty instance operand and LINT/two-DINT destination. All other objects/attributes remain unsupported; SSV has no execution model. |
| AOI calls | Parameter variants, lifecycle, Postscan, FBD/SFC integration, protected definitions and complete native semantics. See [AOI checklist](emulation-coverage.md#languages-calls-and-aois). |

The exact current dispatch table is `ARITIES` in
[model.py](../source/logixlab/model.py). Execution and operand checks live in
[runtime.py](../source/logixlab/runtime.py), [extended.py](../source/logixlab/extended.py),
[bit_transfer.py](../source/logixlab/bit_transfer.py),
[numeric_conversions.py](../source/logixlab/numeric_conversions.py),
[real_math.py](../source/logixlab/real_math.py),
[array_statistics.py](../source/logixlab/array_statistics.py),
[string_operations.py](../source/logixlab/string_operations.py),
[control_operations.py](../source/logixlab/control_operations.py),
[sequencer_operations.py](../source/logixlab/sequencer_operations.py),
[structured.py](../source/logixlab/structured.py),
[expressions.py](../source/logixlab/expressions.py) and
[st_expression.py](../source/logixlab/st_expression.py). Loading a project reports
its own supported forms and blockers; the mnemonic inventory alone cannot
declare an entire project executable.
