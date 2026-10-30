# Structured Text enhanced selection and derivative

`ESEL(State)` and `DERV(State)` run in the bounded v35 ControlLogix 5580 L81E–L85E
software profile. Choose **Process lab** or launch with `--sample ProcessLab` to
feed six synthetic sensor values through selection and rate-of-change blocks.

Logical schemas and equations were checked against installed Studio v35 help and
Rockwell's [process control and drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
These are software models with unqualified native lifecycle, precision and
interacting-condition behavior. FBD graphs, packed layouts and other controller
profiles remain unfinished. SEL and MUX remain unsupported; v35 help lists SEL
as FBD-only, so this increment does not add an ST SEL extension.

## ESEL and SELECT_ENHANCED

The logical record has 29 members:

| Type | Members |
| --- | --- |
| REAL | In1 through In6, Out |
| DINT | InsUsed, SelectorMode, ProgSelector, OperSelector, SelectedIn, Status |
| BOOL | EnableIn, In1Fault through In6Fault, ProgProgReq, ProgOperReq, ProgOverrideReq, OperProgReq, OperOperReq, ProgValueReset, EnableOut, ProgOper, Override |

Defaults are zero/false except EnableIn=true and InsUsed=1. InsUsed selects the
first 1–6 inputs for automatic selection. Faulted inputs in that prefix are
excluded. Unused input values and faulted input values need not be known.
Required health flags must be known BOOL values; unknown never means healthy.

| SelectorMode | Operation | SelectedIn |
| --- | --- | --- |
| 0 | Manual selection from active Program/Operator selector | Selected input index |
| 1 | Highest healthy input | First matching input index |
| 2 | Lowest healthy input | First matching input index |
| 3 | Median healthy input | First original input matching a middle value |
| 4 | Mean of healthy inputs | 0 |

Median always returns an available input value. With an even number of healthy
inputs, this profile chooses the first original input whose value is either
middle sorted value. Duplicate high/low values also select the first index.
Native tie behavior still needs comparison.

The first reached call starts in Operator control, then applies requests:

1. ProgOperReq wins and selects Operator control.
2. Otherwise ProgProgReq selects Program control.
3. Without either Program lock, the Operator request to leave the current
   control is honored. Simultaneous Operator requests therefore switch away
   from the current control once.

Operator requests are cleared after a reached call. ProgValueReset clears
ProgProgReq, ProgOperReq and ProgOverrideReq after their current values have
been used. ProgOper is an output backed by hidden per-record control history;
writing that visible output does not change retained ownership.

Manual selection uses ProgSelector in Program control or OperSelector in
Operator control. Values 1–6 select the corresponding input; zero holds Out and
SelectedIn. ProgOverrideReq acts as a level-sensitive request for manual
selection. In this software profile, manual/override selection ignores input
health and InsUsed, while invalid InsUsed still sets its diagnostic. All-used
bad health is evaluated only in automatic modes. Invalid SelectorMode prevents
selection even while Override is true. These combinations and request/reset
ordering remain native qualification work.

Diagnostics are recomputed each call. Status aliases share the DINT word:
InstructFault=.0, InsFaulted=.1, InsUsedInv=.2, SelectorModeInv=.3,
ProgSelectorInv=.4 and OperSelectorInv=.5. Invalid selectors are diagnosed even
when inactive; they block selection only when used. Invalid automatic count or
mode, all-used-inputs-faulted, and manual selector zero preserve visible Out and
SelectedIn. Successful selection clears prior diagnostic bits that no longer
apply. Control requests are still processed when selection holds.

## DERV and DERIVATIVE

The 12-member record contains BOOL EnableIn, ByPass and EnableOut; REAL In,
Gain, OversampleDT, Out and DeltaT; DINT TimingMode, RTSTime, RTSTimeStamp and
Status. Defaults are zero/false except EnableIn=true, Gain=1 and RTSTime=1.

For a positive interval, after startup and with ByPass clear:

`Out = Gain * (In - previous In) / DeltaT`

Gain may be negative. ByPass passes In directly. This software profile's first
reached call samples In and produces zero unless bypassed, avoiding an initial
rate spike. Every reached call samples In, including bypass and zero/invalid
intervals; leaving those states uses the most recently reached input. These
startup/transition choices need native comparison.

TimingMode 0 uses the configured Periodic task period or elapsed whole simulated
milliseconds in other supported contexts. Mode 1 uses OversampleDT on every
call, including repeated calls at one timestamp. Zero holds the hidden output.
Intervals outside 0 through float32(4194.303) set DeltaT=0 and Status.0/.31.
Modes outside 0..2 set DeltaT=0 and Status.0/.27. ByPass still passes In with
these diagnostics. Mode 2 faults as unsupported; RTS/module timestamps remain
unfinished. Unused RTS/oversample fields can remain unknown. Gain is read only
when a positive-interval derivative calculation is reached after startup.

Status aliases: InstructFault=.0, TimingModeInv=.27, RTSMissed=.28,
RTSTimeInv=.29, RTSTimeStampInv=.30 and DeltaTInv=.31. Only the modeled
diagnostics above are generated.

## Lifecycle and transactions

Both ST calls force the enable pair true. Prescan clears it. Skipped calls
retain values, requests and history. Run entry clears hidden histories;
startup applies on the next reached call. Direct DERV Out writes do not replace
its hidden held output. Scalars, nested/array/indirect records, local tags,
aliases and supported AOI bindings use resolved per-record identities.

Public REAL values and DERV history use float32, with host-double arithmetic
intermediates. Nonfinite inputs/results and overflow fault transactionally.
The whole advance rolls back values, consumed requests, ownership, derivative
history, time and scheduler counters together. Supported detached routine
replacement preserves histories. Native Studio transfer and online-edit
acceptance remain separate from these execution checks.
