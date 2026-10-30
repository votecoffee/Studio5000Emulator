# Predefined data-type coverage

Baseline: **222 supplied Studio 5000 catalog entries**, audited against app
`26.1030.155819` on 2026-10-30. Every supplied entry appears below in its original
order. Asterisks are retained as annotations, not as type-identifier characters.
This is an implementation backlog, not a declaration that all types are
available on every controller/firmware or that any type has full native parity.

The [JSON inventory](predefined-data-types.json) contains the same names,
families, status codes, version-listing comparisons and explicit verification
notes. It is documentation data; adding a record does not enable that type in
the execution engine. The [full emulation checklist](emulation-coverage.md) and
[roadmap](roadmap.md) remain the implementation plan.

## Current implementation

| Dedicated model category | Entries | Meaning |
| --- | --- | --- |
| Numeric model, bounded | 5 | BOOL, SINT, INT, DINT, REAL storage and supported operations; incomplete conversions/status/native parity |
| Wide integer profile, bounded | 5 | LINT, USINT, UINT, UDINT, ULINT storage and supported homogeneous [ladder](integer-execution.md) and [ST](wide-st.md) operations; profile restrictions apply |
| Timer/counter model, partial | 2 | TIMER and COUNTER fields plus the implemented instruction subset |
| STRING model, partial | 1 | Explicit LEN/DATA behavior and selected string instructions; complete built-in wire behavior remains unfinished |
| CONTROL model, partial | 1 | Logical members plus [Shifts, numeric FIFO/LIFO and RES](control-operations.md), plus [DINT sequencers](sequencer-operations.md); native layout and remaining forms unfinished |
| FBD_TIMER model, partial | 1 | [ST TONR/TOFR/RTOR](st-timers.md), logical fields and deterministic elapsed time; FBD graphs and native parity remain unfinished |
| FBD_COUNTER model, partial | 1 | [ST CTUD](st-counter.md), sampled edges and logical up/down state; FBD graphs and native parity remain unfinished |
| FBD_ONESHOT model, partial | 1 | [ST OSRI/OSFI](st-oneshot.md), sampled rising/falling pulses and logical fields; FBD graphs and native parity remain unfinished |
| SCALE model, partial | 1 | [ST SCL](st-scaling.md), finite REAL scaling, limiting, alarms and status; FBD graphs and native parity remain unfinished |
| HL_LIMIT model, partial | 1 | [ST HLL](st-signals.md), both/one-sided limits, alarms and status |
| SELECTABLE_NEGATE model, partial | 1 | [ST SNEG](st-signals.md), finite REAL selectable negation |
| SELECTED_SUMMER model, partial | 1 | [ST SSUM](st-signals.md), eight weighted input pairs and bias |
| RATE_LIMITER model, partial | 1 | [ST RLIM](st-rate-limiter.md), ramps/bypass and Periodic/oversample timing; RTS/FBD/native parity remain unfinished |
| Moving statistics models, partial | 2 | [ST MAVE/MSTD](st-moving-statistics.md), finite REAL queues and uniform/weighted averages/population deviation |
| Capture models, partial | 2 | [ST MAXC/MINC](st-capture.md), retained finite REAL extrema and reset baselines |
| LPF software model, partial | 1 | [ST LPF](st-low-pass-filter.md), explicit bilinear sections; native numerical recurrence remains unverified |
| Boolean memory models, partial | 4 | [ST DFF/JKFF/RESD/SETD](st-digital-memory.md), sampled clocks, dominant latches, complements and history |
| Accumulation models, partial | 2 | [ST UPDN/INTG](st-accumulation.md), finite REAL totals, timed integration, holds, limits and history |
| Enhanced selection model, partial | 1 | [ST ESEL](st-process-signals.md), healthy/manual selection, control requests and diagnostics |
| Derivative model, partial | 1 | [ST DERV](st-process-signals.md), timed rate of change, bypass and history |
| Curve/delay models, partial | 2 | [ST FGEN/DEDT](st-curves-delay.md), piecewise curves, sample delay queues, resizing and health recovery |
| PI software model, partial | 1 | [ST PI](st-pi-regulation.md), linear/shaped gains, integral holds/limits, initialization and history |
| No dedicated model | 184 | No dedicated bounded named runtime model |

Thus **38 entries have dedicated bounded models**; this is not 38 fully
emulated types and not a percentage-complete claim. UDTs, custom string types,
AOIs and module-generated types have separate inventories and are not added to
the supplied 222-entry count.

Some other names can occur in exported Decorated data. The importer may retain
represented fields as a `DecoratedDataOnly` structure. That does not establish
the predefined type's complete schema, hidden state, defaults, layout,
instruction behavior or transfer compatibility. Such entries remain **No
dedicated model** here; no default members or zero values are invented.

## Controller and version qualification

Rockwell's [published 37.01 catalog](https://www.rockwellautomation.com/en-no/docs/studio-5000-logix-designer/37-01/contents-ditamap/studio-5000-logix-designer/data-type-editor/pre-defined-data-types.html)
matches the supplied naming. Its asterisk restricts those entries to
CompactLogix 5380/5480, ControlLogix 5580 and Compact GuardLogix 5380/GuardLogix
5580 families. It is not a wildcard or a statement that the remaining names
work on all controllers. Per-type firmware, language and product-profile
availability still needs verification before implementation is enabled.

The installed v35 help catalog (`4816.htm`) lists 211 of the supplied entries:
203 exact labels and eight legacy spelling variants. Eleven supplied entries
are absent from that particular index. **Absence from an index is not proof
that the type is unsupported by all v35 controllers.** They stay in the backlog
with explicit version qualification, rather than being dropped or enabled.

| Not listed in the installed v35 index | Required follow-up |
| --- | --- |
| OPC_UA_SERVER | Verify firmware/server schema and lifecycle; controller-owned OPC UA is separate from an external monitoring bridge |
| P_DISCRETE_4STATE, P_DISCRETE_MIX_PROOF, P_DISCRETE_N_POSITION | Verify the relevant PlantPAx/controller profile, schema and instruction |
| REF_TO_AXIS_CIP_DRIVE, REF_TO_AXIS_CONSUMED, REF_TO_AXIS_GENERAL_DRIVE, REF_TO_AXIS_SERVO, REF_TO_AXIS_SERVO_DRIVE, REF_TO_AXIS_VIRTUAL, REF_TO_COORDINATE_SYSTEM | Verify introduction/version, reference identity and lifetime semantics; no pointer or axis behavior is inferred |

The local v35 index spells seven SEQ names with hyphens and spells S_CURVE as
S-CURVE. These are recorded as documentation spelling variants, not automatic
runtime aliases. `SAFELY_LIMITED POSITION` contains a space in the supplied and
published index label; v35 SLP instruction help uses `SAFELY_LIMITED_POSITION`.
Keep the original label and verify the actual schema before choosing an
identifier. `REF_TO_AXIS_GENERAL_DRIVE` is also preserved exactly; it is not
silently replaced with `REF_TO_AXIS_GENERIC_DRIVE`.

TIMER_T appears in the later 38.00 catalog but not this 222-entry baseline.
Track it as a later-version extension in D05, rather than silently changing
the supplied baseline. Other later additions follow the same policy.

## Complete per-type inventory

Family labels are implementation-planning groups, not vendor availability rules.
The next section defines the remaining schema/behavior work for each family.
Every dedicated model status still requires the qualifications above.

| # | Supplied name | Family | Current model | Installed v35 index |
| --- | --- | --- | --- | --- |
| 1 | `ALARM` | Alarms | No dedicated model | Listed |
| 2 | `ALARM_ANALOG` | Alarms | No dedicated model | Listed |
| 3 | `ALARM_DIGITAL` | Alarms | No dedicated model | Listed |
| 4 | `ALARM_SET_CONTROL` | Alarms | No dedicated model | Listed |
| 5 | `AUX_VALVE_CONTROL` | Metal forming/valves | No dedicated model | Listed |
| 6 | `AXIS_CIP_DRIVE` | Motion/axis/reference | No dedicated model | Listed |
| 7 | `AXIS_CONSUMED` | Motion/axis/reference | No dedicated model | Listed |
| 8 | `AXIS_GENERIC` | Motion/axis/reference | No dedicated model | Listed |
| 9 | `AXIS_GENERIC_DRIVE` | Motion/axis/reference | No dedicated model | Listed |
| 10 | `AXIS_SERVO` | Motion/axis/reference | No dedicated model | Listed |
| 11 | `AXIS_SERVO_DRIVE` | Motion/axis/reference | No dedicated model | Listed |
| 12 | `AXIS_VIRTUAL` | Motion/axis/reference | No dedicated model | Listed |
| 13 | `BOOL` | Atomic numeric/BOOL | Numeric model (bounded) | Listed |
| 14 | `BUS_OBJ*` | PlantPAx/bus | No dedicated model | Listed |
| 15 | `CAM` | Motion/axis/reference | No dedicated model | Listed |
| 16 | `CAM_EXTENDED` | Motion/axis/reference | No dedicated model | Listed |
| 17 | `CAMSHAFT_MONITOR` | Metal forming/valves | No dedicated model | Listed |
| 18 | `CAM_PROFILE` | Motion/axis/reference | No dedicated model | Listed |
| 19 | `CAM_PROFILE_EXTENDED` | Motion/axis/reference | No dedicated model | Listed |
| 20 | `CB_CONTINUOUS_MODE` | Metal forming/valves | No dedicated model | Listed |
| 21 | `CB_CRANKSHAFT_POS_MONITOR` | Metal forming/valves | No dedicated model | Listed |
| 22 | `CB_INCH_MODE` | Metal forming/valves | No dedicated model | Listed |
| 23 | `CB_SINGLE_STROKE_MODE` | Metal forming/valves | No dedicated model | Listed |
| 24 | `CC` | Process/filter/drive | No dedicated model | Listed |
| 25 | `CONFIGURABLE_ROUT` | Safety | No dedicated model | Listed |
| 26 | `CONNECTION_STATUS` | Module/connection | No dedicated model | Listed |
| 27 | `CONTROL` | Array/control state | CONTROL model (partial) | Listed |
| 28 | `COORDINATE_SYSTEM` | Motion/axis/reference | No dedicated model | Listed |
| 29 | `COUNTER` | Timers/counters | Timer/counter model (partial) | Listed |
| 30 | `DATALOG_INSTRUCTION` | Data logging | No dedicated model | Listed |
| 31 | `DCAF_INPUT` | Safety | No dedicated model | Listed |
| 32 | `DCA_INPUT` | Safety | No dedicated model | Listed |
| 33 | `DCI_MONITOR` | Safety | No dedicated model | Listed |
| 34 | `DCI_START` | Safety | No dedicated model | Listed |
| 35 | `DCI_STOP` | Safety | No dedicated model | Listed |
| 36 | `DCI_STOP_TEST` | Safety | No dedicated model | Listed |
| 37 | `DCI_STOP_TEST_LOCK` | Safety | No dedicated model | Listed |
| 38 | `DCI_STOP_TEST_MUTE` | Safety | No dedicated model | Listed |
| 39 | `DEADTIME` | Process/filter/drive | Curve/delay model (partial) | Listed |
| 40 | `DERIVATIVE` | Process/filter/drive | Derivative model (partial) | Listed |
| 41 | `DINT` | Atomic numeric/BOOL | Numeric model (bounded) | Listed |
| 42 | `DISCRETE_2STATE` | Process/filter/drive | No dedicated model | Listed |
| 43 | `DISCRETE_3STATE` | Process/filter/drive | No dedicated model | Listed |
| 44 | `DIVERSE_INPUT` | Safety | No dedicated model | Listed |
| 45 | `DOMINANT_RESET` | FBD state/logic | Boolean memory model (partial) | Listed |
| 46 | `DOMINANT_SET` | FBD state/logic | Boolean memory model (partial) | Listed |
| 47 | `DT` | Time/date | No dedicated model | Listed |
| 48 | `DYNAMICS_DATA` | Motion/axis/reference | No dedicated model | Listed |
| 49 | `EIGHT_POS_MODE_SELECTOR` | Safety | No dedicated model | Listed |
| 50 | `EMERGENCY_STOP` | Safety | No dedicated model | Listed |
| 51 | `ENABLE_PENDANT` | Safety | No dedicated model | Listed |
| 52 | `ENERGY_BASE` | Energy | No dedicated model | Listed |
| 53 | `ENERGY_ELECTRICAL` | Energy | No dedicated model | Listed |
| 54 | `EXT_ROUTINE_CONTROL` | External routine | No dedicated model | Listed |
| 55 | `EXT_ROUTINE_PARAMETERS` | External routine | No dedicated model | Listed |
| 56 | `FBD_BIT_FIELD_DISTRIBUTE` | FBD state/logic | No dedicated model | Listed |
| 57 | `FBD_BOOLEAN_AND` | FBD state/logic | No dedicated model | Listed |
| 58 | `FBD_BOOLEAN_NOT` | FBD state/logic | No dedicated model | Listed |
| 59 | `FBD_BOOLEAN_OR` | FBD state/logic | No dedicated model | Listed |
| 60 | `FBD_BOOLEAN_XOR` | FBD state/logic | No dedicated model | Listed |
| 61 | `FBD_COMPARE` | FBD state/logic | No dedicated model | Listed |
| 62 | `FBD_CONVERT` | FBD state/logic | No dedicated model | Listed |
| 63 | `FBD_COUNTER` | FBD state/logic | FBD_COUNTER model (partial) | Listed |
| 64 | `FBD_LIMIT` | FBD state/logic | No dedicated model | Listed |
| 65 | `FBD_LOGICAL` | FBD state/logic | No dedicated model | Listed |
| 66 | `FBD_MASKED_MOVE` | FBD state/logic | No dedicated model | Listed |
| 67 | `FBD_MASK_EQUAL` | FBD state/logic | No dedicated model | Listed |
| 68 | `FBD_MATH` | FBD state/logic | No dedicated model | Listed |
| 69 | `FBD_MATH_ADVANCED` | FBD state/logic | No dedicated model | Listed |
| 70 | `FBD_ONESHOT` | FBD state/logic | FBD_ONESHOT model (partial) | Listed |
| 71 | `FBD_TIMER` | FBD state/logic | FBD_TIMER model (partial) | Listed |
| 72 | `FBD_TRUNCATE` | FBD state/logic | No dedicated model | Listed |
| 73 | `FILTER_HIGH_PASS` | Process/filter/drive | No dedicated model | Listed |
| 74 | `FILTER_LOW_PASS` | Process/filter/drive | LPF software model (partial) | Listed |
| 75 | `FILTER_NOTCH` | Process/filter/drive | No dedicated model | Listed |
| 76 | `FIVE_POS_MODE_SELECTOR` | Safety | No dedicated model | Listed |
| 77 | `FLIP_FLOP_D` | FBD state/logic | Boolean memory model (partial) | Listed |
| 78 | `FLIP_FLOP_JK` | FBD state/logic | Boolean memory model (partial) | Listed |
| 79 | `FUNCTION_GENERATOR` | Process/filter/drive | Curve/delay model (partial) | Listed |
| 80 | `HL_LIMIT` | Process/filter/drive | HL_LIMIT model (partial) | Listed |
| 81 | `HMIBC` | HMI button control | No dedicated model | Listed |
| 82 | `IMC` | Process/filter/drive | No dedicated model | Listed |
| 83 | `INT` | Atomic numeric/BOOL | Numeric model (bounded) | Listed |
| 84 | `INTEGRATOR` | Process/filter/drive | Accumulation model (partial) | Listed |
| 85 | `LDT` | Time/date | No dedicated model | Listed |
| 86 | `LEAD_LAG` | Process/filter/drive | No dedicated model | Listed |
| 87 | `LEAD_LAG_SEC_ORDER` | Process/filter/drive | No dedicated model | Listed |
| 88 | `LIGHT_CURTAIN` | Safety | No dedicated model | Listed |
| 89 | `LINT` | Atomic numeric/BOOL | Wide integer profile (bounded) | Listed |
| 90 | `LREAL` | Atomic numeric/BOOL | No dedicated model | Listed |
| 91 | `LTIME` | Time/date | No dedicated model | Listed |
| 92 | `MAIN_VALVE_CONTROL` | Metal forming/valves | No dedicated model | Listed |
| 93 | `MANUAL_VALVE_CONTROL` | Metal forming/valves | No dedicated model | Listed |
| 94 | `MAXIMUM_CAPTURE` | Process/filter/drive | Capture model (partial) | Listed |
| 95 | `MESSAGE` | Message/serial | No dedicated model | Listed |
| 96 | `MINIMUM_CAPTURE` | Process/filter/drive | Capture model (partial) | Listed |
| 97 | `MMC` | Process/filter/drive | No dedicated model | Listed |
| 98 | `MODULE` | Module/connection | No dedicated model | Listed |
| 99 | `MOTION_GROUP` | Motion/axis/reference | No dedicated model | Listed |
| 100 | `MOTION_INSTRUCTION` | Motion/axis/reference | No dedicated model | Listed |
| 101 | `MOVING_AVERAGE` | Process/filter/drive | Moving statistics model (partial) | Listed |
| 102 | `MOVING_STD_DEV` | Process/filter/drive | Moving statistics model (partial) | Listed |
| 103 | `MULTIPLEXER` | Process/filter/drive | No dedicated model | Listed |
| 104 | `MUTING_FOUR_SENSOR_BIDIR` | Safety | No dedicated model | Listed |
| 105 | `MUTING_TWO_SENSOR_ASYM` | Safety | No dedicated model | Listed |
| 106 | `MUTING_TWO_SENSOR_SYM` | Safety | No dedicated model | Listed |
| 107 | `ODOMETER` | Process/filter/drive | No dedicated model | Listed |
| 108 | `OPC_UA_SERVER` | Controller OPC UA | No dedicated model | Not listed |
| 109 | `OUTPUT_CAM` | Motion/axis/reference | No dedicated model | Listed |
| 110 | `OUTPUT_COMPENSATION` | Motion/axis/reference | No dedicated model | Listed |
| 111 | `PATH_DATA` | Motion/axis/reference | No dedicated model | Listed |
| 112 | `PHASE` | Phase/sequence | No dedicated model | Listed |
| 113 | `PHASE_INSTRUCTION` | Phase/sequence | No dedicated model | Listed |
| 114 | `PID` | Process/filter/drive | No dedicated model | Listed |
| 115 | `PIDE_AUTOTUNE` | Process/filter/drive | No dedicated model | Listed |
| 116 | `PID_ENHANCED` | Process/filter/drive | No dedicated model | Listed |
| 117 | `POSITION_DATA` | Motion/axis/reference | No dedicated model | Listed |
| 118 | `POSITION_PROP` | Process/filter/drive | No dedicated model | Listed |
| 119 | `PROP_INT` | Process/filter/drive | PI software model (partial) | Listed |
| 120 | `P_ANALOG_FANOUT*` | PlantPAx/bus | No dedicated model | Listed |
| 121 | `P_ANALOG_HART*` | PlantPAx/bus | No dedicated model | Listed |
| 122 | `P_ANALOG_INPUT*` | PlantPAx/bus | No dedicated model | Listed |
| 123 | `P_ANALOG_INPUT_DUAL*` | PlantPAx/bus | No dedicated model | Listed |
| 124 | `P_ANALOG_INPUT_MULTI*` | PlantPAx/bus | No dedicated model | Listed |
| 125 | `P_ANALOG_OUTPUT*` | PlantPAx/bus | No dedicated model | Listed |
| 126 | `P_BOOLEAN_LOGIC*` | PlantPAx/bus | No dedicated model | Listed |
| 127 | `P_COMMAND_SOURCE*` | PlantPAx/bus | No dedicated model | Listed |
| 128 | `P_DEADBAND*` | PlantPAx/bus | No dedicated model | Listed |
| 129 | `P_DISCRETE_4STATE` | PlantPAx/bus | No dedicated model | Not listed |
| 130 | `P_DISCRETE_INPUT*` | PlantPAx/bus | No dedicated model | Listed |
| 131 | `P_DISCRETE_MIX_PROOF` | PlantPAx/bus | No dedicated model | Not listed |
| 132 | `P_DISCRETE_N_POSITION` | PlantPAx/bus | No dedicated model | Not listed |
| 133 | `P_DISCRETE_OUTPUT*` | PlantPAx/bus | No dedicated model | Listed |
| 134 | `P_DOSING*` | PlantPAx/bus | No dedicated model | Listed |
| 135 | `P_HART_CODE_DESC_STATUS*` | PlantPAx/bus | No dedicated model | Listed |
| 136 | `P_HIGH_LOW_SELECT*` | PlantPAx/bus | No dedicated model | Listed |
| 137 | `P_INTERLOCK*` | PlantPAx/bus | No dedicated model | Listed |
| 138 | `P_INTERLOCK_BANK_STATUS*` | PlantPAx/bus | No dedicated model | Listed |
| 139 | `P_LEAD_LAG_STANDBY*` | PlantPAx/bus | No dedicated model | Listed |
| 140 | `P_LEAD_LAG_STANDBY_MOTOR*` | PlantPAx/bus | No dedicated model | Listed |
| 141 | `P_MOTOR_DISCRETE*` | PlantPAx/bus | No dedicated model | Listed |
| 142 | `P_PERMISSIVE*` | PlantPAx/bus | No dedicated model | Listed |
| 143 | `P_PID*` | PlantPAx/bus | No dedicated model | Listed |
| 144 | `P_PRESS_TEMP_COMPENSATED*` | PlantPAx/bus | No dedicated model | Listed |
| 145 | `P_RESTART_INHIBIT*` | PlantPAx/bus | No dedicated model | Listed |
| 146 | `P_RUN_TIME*` | PlantPAx/bus | No dedicated model | Listed |
| 147 | `P_STRAPPING_TABLE_ROW*` | PlantPAx/bus | No dedicated model | Listed |
| 148 | `P_TANK_STRAPPING_TABLE*` | PlantPAx/bus | No dedicated model | Listed |
| 149 | `P_VALVE_DISCRETE*` | PlantPAx/bus | No dedicated model | Listed |
| 150 | `P_VALVE_STATISTICS*` | PlantPAx/bus | No dedicated model | Listed |
| 151 | `P_VARIABLE_SPEED_DRIVE*` | PlantPAx/bus | No dedicated model | Listed |
| 152 | `PULSE_MULTIPLIER` | Process/filter/drive | No dedicated model | Listed |
| 153 | `RAC_CODE_DESCRIPTION*` | RAC interfaces | No dedicated model | Listed |
| 154 | `RAC_EVENT*` | RAC interfaces | No dedicated model | Listed |
| 155 | `RAC_ITF_DVC_PWRDISCRETE_CMD*` | RAC interfaces | No dedicated model | Listed |
| 156 | `RAC_ITF_DVC_PWRDISCRETE_SET*` | RAC interfaces | No dedicated model | Listed |
| 157 | `RAC_ITF_DVC_PWRDISCRETE_STS*` | RAC interfaces | No dedicated model | Listed |
| 158 | `RAC_ITF_DVC_PWRMOTION_CMD*` | RAC interfaces | No dedicated model | Listed |
| 159 | `RAC_ITF_DVC_PWRMOTION_INF*` | RAC interfaces | No dedicated model | Listed |
| 160 | `RAC_ITF_DVC_PWRMOTION_SET*` | RAC interfaces | No dedicated model | Listed |
| 161 | `RAC_ITF_DVC_PWRMOTION_STS*` | RAC interfaces | No dedicated model | Listed |
| 162 | `RAC_ITF_DVC_PWRVELOCITY_CMD*` | RAC interfaces | No dedicated model | Listed |
| 163 | `RAC_ITF_DVC_PWRVELOCITY_SET*` | RAC interfaces | No dedicated model | Listed |
| 164 | `RAC_ITF_DVC_PWRVELOCITY_STS*` | RAC interfaces | No dedicated model | Listed |
| 165 | `RAMP_SOAK` | Process/filter/drive | No dedicated model | Listed |
| 166 | `RATE_LIMITER` | Process/filter/drive | RATE_LIMITER model (partial) | Listed |
| 167 | `REAL` | Atomic numeric/BOOL | Numeric model (bounded) | Listed |
| 168 | `REDUNDANT_INPUT` | Safety | No dedicated model | Listed |
| 169 | `REDUNDANT_OUTPUT` | Safety | No dedicated model | Listed |
| 170 | `REF_TO_AXIS_CIP_DRIVE` | Motion/axis/reference | No dedicated model | Not listed |
| 171 | `REF_TO_AXIS_CONSUMED` | Motion/axis/reference | No dedicated model | Not listed |
| 172 | `REF_TO_AXIS_GENERAL_DRIVE` | Motion/axis/reference | No dedicated model | Not listed |
| 173 | `REF_TO_AXIS_SERVO` | Motion/axis/reference | No dedicated model | Not listed |
| 174 | `REF_TO_AXIS_SERVO_DRIVE` | Motion/axis/reference | No dedicated model | Not listed |
| 175 | `REF_TO_AXIS_VIRTUAL` | Motion/axis/reference | No dedicated model | Not listed |
| 176 | `REF_TO_COORDINATE_SYSTEM` | Motion/axis/reference | No dedicated model | Not listed |
| 177 | `SAFELY_LIMITED POSITION` | Safety | No dedicated model | Listed |
| 178 | `SAFELY_LIMITED_SPEED` | Safety | No dedicated model | Listed |
| 179 | `SAFETY_FEEDBACK_INTERFACE` | Safety | No dedicated model | Listed |
| 180 | `SAFETY_MAT` | Safety | No dedicated model | Listed |
| 181 | `SAFE_BRAKE_CONTROL` | Safety | No dedicated model | Listed |
| 182 | `SAFE_DIRECTION` | Safety | No dedicated model | Listed |
| 183 | `SAFE_OPERATING_STOP` | Safety | No dedicated model | Listed |
| 184 | `SAFE_STOP_1` | Safety | No dedicated model | Listed |
| 185 | `SAFE_STOP_2` | Safety | No dedicated model | Listed |
| 186 | `SCALE` | Process/filter/drive | SCALE model (partial) | Listed |
| 187 | `SEC_ORDER_CONTROLLER` | Process/filter/drive | No dedicated model | Listed |
| 188 | `SELECT` | Process/filter/drive | No dedicated model | Listed |
| 189 | `SELECTABLE_NEGATE` | Process/filter/drive | SELECTABLE_NEGATE model (partial) | Listed |
| 190 | `SELECTED_SUMMER` | Process/filter/drive | SELECTED_SUMMER model (partial) | Listed |
| 191 | `SELECT_ENHANCED` | Process/filter/drive | Enhanced selection model (partial) | Listed |
| 192 | `SEQUENCE` | Phase/sequence | No dedicated model | Listed |
| 193 | `SEQ_BOOL` | Phase/sequence | No dedicated model | Spelling variant |
| 194 | `SEQ_DINT` | Phase/sequence | No dedicated model | Spelling variant |
| 195 | `SEQ_INT` | Phase/sequence | No dedicated model | Listed |
| 196 | `SEQ_REAL` | Phase/sequence | No dedicated model | Spelling variant |
| 197 | `SEQ_SINT` | Phase/sequence | No dedicated model | Spelling variant |
| 198 | `SEQ_STEP` | Phase/sequence | No dedicated model | Spelling variant |
| 199 | `SEQ_STRING` | Phase/sequence | No dedicated model | Spelling variant |
| 200 | `SEQ_TRANSITION` | Phase/sequence | No dedicated model | Spelling variant |
| 201 | `SERIAL_PORT_CONTROL` | Message/serial | No dedicated model | Listed |
| 202 | `SFC_ACTION` | SFC state | No dedicated model | Listed |
| 203 | `SFC_STEP` | SFC state | No dedicated model | Listed |
| 204 | `SFC_STOP` | SFC state | No dedicated model | Listed |
| 205 | `SIGNED_ODOMETER` | Process/filter/drive | No dedicated model | Listed |
| 206 | `SINT` | Atomic numeric/BOOL | Numeric model (bounded) | Listed |
| 207 | `SPLIT_RANGE` | Process/filter/drive | No dedicated model | Listed |
| 208 | `STRING` | Strings | STRING model (partial) | Listed |
| 209 | `STRING_16` | Strings | No dedicated model | Listed |
| 210 | `STRING_32` | Strings | No dedicated model | Listed |
| 211 | `S_CURVE` | Process/filter/drive | No dedicated model | Spelling variant |
| 212 | `THRS_ENHANCED` | Safety | No dedicated model | Listed |
| 213 | `TIME` | Time/date | No dedicated model | Listed |
| 214 | `TIME32` | Time/date | No dedicated model | Listed |
| 215 | `TIMER` | Timers/counters | Timer/counter model (partial) | Listed |
| 216 | `TOTALIZER` | Process/filter/drive | No dedicated model | Listed |
| 217 | `TWO_HAND_RUN_STATION` | Safety | No dedicated model | Listed |
| 218 | `UDINT` | Atomic numeric/BOOL | Wide integer profile (bounded) | Listed |
| 219 | `UINT` | Atomic numeric/BOOL | Wide integer profile (bounded) | Listed |
| 220 | `ULINT` | Atomic numeric/BOOL | Wide integer profile (bounded) | Listed |
| 221 | `UP_DOWN_ACCUM` | Process/filter/drive | Accumulation model (partial) | Listed |
| 222 | `USINT` | Atomic numeric/BOOL | Wide integer profile (bounded) | Listed |

## Remaining family work

For an unimplemented type, define and validate its complete schema first:
member names/types/dimensions, visible/hidden state, storage/packing/alignment,
initialization and retention, writable/read-only/configuration fields and
controller/firmware applicability. Then implement its consumers, scan modes,
time/state transitions, error/reset behavior, serialization and conformance cases.
Field storage alone does not complete an asynchronous or stateful type.

| Family | Work items | Remaining implementation |
| --- | --- | --- |
| Atomic numeric/BOOL | D01/D02 | Complete type operations, conversions, flags and target profiles. |
| Time/date | D03 | Implement exact typed storage, literals, units, operations, clock interaction and transfers. |
| Timers/counters | D05 | Complete dedicated fields, instruction states, time behavior and native fault/status parity. |
| Strings | D07 | Complete capacities/encoding, backing storage, instructions and wire models. |
| Array/control state | D04/L01 | Expand remaining shift/FIFO/LIFO/sequencer forms, aggregate transfers, conversions and file consumers; qualify native layout/status parity. |
| Alarms | D04/L05 | Define alarm/set state, operations, periodic evaluation, event lifecycle and consumers. |
| Motion/axis/reference | D04/M01-M07 | Define axes, references, groups, trajectories/cams and instruction state on the simulation clock. |
| Metal forming/valves | D04/M07 | Define configuration/state and linked metal-form/valve instruction models. |
| Safety | C04 | Define layouts and separate logical Safety instruction/lifecycle profiles; no certification claim. |
| FBD state/logic | D04/L03 | Define block state and implement FBD execution order, pins, enable/reset and scan behavior. |
| Process/filter/drive | D04/L05/M05 | Define configuration/state, timing, numeric algorithms, limits and consumer instruction semantics. |
| PlantPAx/bus | D04/L05 | Define public/private storage, ownership/mode/alarm state, instruction behavior and target applicability. |
| RAC interfaces | D04/I01/I05 | Define interface structures, commands/acknowledgements/status and explicit device behavior. |
| Module/connection | D04/I01-I04 | Implement module identity/topology, I/O connection state, faults, diagnostics and cyclic behavior. |
| Message/serial | D04/I08 | Define asynchronous control state, configuration, queues, paths, replies, timeouts and cancellation. |
| Phase/sequence | D04/L05 | Define phase/sequence records, step/transition state, ownership, commands and lifecycle. |
| SFC state | D04/L04 | Define active steps/actions/stops, qualifiers, timers and chart execution lifecycle. |
| Energy | D04/C04 | Define configuration/measurement/status and consumers; empty discovery is not execution. |
| Data logging | D04/C03 | Define trigger/status, record buffering, timestamps, retention and file/storage behavior. |
| HMI button control | D04/L05 | Define button/control state and linked HMIBC execution/handshakes. |
| External routine | E08/D04 | Define ABI/parameters/lifecycle and an explicit supported code backend; descriptors do not execute code. |
| Controller OPC UA | D04/I10 | Qualify firmware, then define controller-server configuration/status and runtime; separate from an external bridge. |

Safety structures need a separate logical simulation profile; their names do
not imply a certified controller or CIP Safety implementation. Axis/reference
types need identity/lifetime and deterministic motion state, not fabricated
addresses. MESSAGE, ALARM_SET_CONTROL and SFC/FBD records need their
consumer instruction/chart state machines as well as fields. PlantPAx/RAC
records may include private fields that cannot be reconstructed from a partial
export. Unknown members and layouts must stay explicit.

## Evidence and maintenance

The source of the 222 names is the supplied catalog baseline, cross-checked
against the published 37.01 index. The installed v35 index and SLP help were
read locally; their files are not redistributed. Source hashes and comparison
receipts stay private. Published catalogs do not supply an execution/schema
implementation merely by listing a name.

Implementation status is based on [model.py](../source/logixlab/model.py),
[runtime.py](../source/logixlab/runtime.py),
[integer_math.py](../source/logixlab/integer_math.py),
[control_operations.py](../source/logixlab/control_operations.py),
[templates.py](../source/logixlab/templates.py) and the current dedicated type
and transfer tests. Custom UDT/string behavior is documented in the
[execution model](execution-model.md).

Update both the JSON inventory and this table when a type gains verified
storage or behavior. Keep the supplied name/number stable, preserve source
spellings and annotations, and record type/profile qualifications. Full
instruction, language, device and native transfer acceptance remains separate.
