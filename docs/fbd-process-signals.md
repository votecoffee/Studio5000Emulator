# FBD enhanced selection and derivatives

ESEL and DERV execute as FBD Blocks in the bounded v35 ControlLogix 5580 software
graph. They share the [existing ST models](st-process-signals.md), including
Program/Operator arbitration and derivative input/output/clock history. There
are 46 graph blocks: 21 shared ST-call names, 18 common RLL names
and seven FBD-only forms. RLL remains
101 and ST calls 27.

| Block | Logical record | Main outputs besides EnableOut |
| --- | --- | --- |
| ESEL | SELECT_ENHANCED | Out, SelectedIn, ProgOper, Override, Status and BOOL status aliases |
| DERV | DERIVATIVE | Out, DeltaT, Status and BOOL status aliases |

ESEL selects manually or chooses the highest, lowest, median or mean of healthy
inputs within the InsUsed prefix. Unknown health is an error. Faulted and unused
values are not read. High/low ties choose the first input; even medians choose
the first original input matching either middle value in this software profile.
Mean sets SelectedIn to zero. Manual selection uses the active Program/Operator
selector independently of count and health, while count diagnostics still apply.
Selector zero, invalid mode/count or all used inputs faulted holds the represented
Out and SelectedIn. This held output can feed downstream DERV.

The first reached call starts in Operator control. Program requests lock control:
ProgOperReq wins over ProgProgReq. Otherwise the Operator request to leave current
control applies. Override requests use manual selection. Operator requests clear
after use; ProgValueReset clears Program requests after their current values apply.
Wires copy source values before every reached block, so a true wired request is
reapplied each time. Clearing a record request does not clear its source tag.
Two continuously true Operator request wires can therefore switch control on
successive calls under the existing software arbitration policy.

DERV calculates Gain times the change of In divided by DeltaT after startup.
The first reached non-bypassed call samples input and produces zero. ByPass
passes In. Gain may be negative and is required only for an actual positive-time
derivative calculation. Every enabled reached call samples In, including bypass
and zero/invalid timing intervals. Resuming valid timing uses that latest reached
sample. These transition choices retain the existing ST qualification limits.

Mode 0 uses the Periodic task interval or elapsed simulated time in other supported
contexts. Mode 1 uses OversampleDT per call. Zero holds the hidden output without
a timing diagnostic; negative/oversized intervals report Status.0/.31 with DeltaT
zero. Invalid modes report Status.0/.27; module timestamp mode 2 remains unsupported.
BOOL status outputs can drive downstream enables or ORefs. RTS aliases are
addressable without implementing module timestamps or RTS diagnostics.

Connected false EnableIn clears enables and skips algorithms, preserving outputs,
diagnostics, requests and history. Wires still copy inputs. Unwired EnableIn is
true. Skipped graphs retain state; elapsed Continuous timing includes the skipped/
disabled gap. Required unknown values stay errors rather than becoming false/zero.

ST/FBD calls share resolved-record histories. Direct DERV Out writes do not replace
its hidden held output; ESEL's invalid-selection hold uses represented Out.
Prescan clears enables; Run clears histories. Whole-advance rollback includes
request clearing, arbitration, selection, derivative samples/clocks and scheduling.
Supported detached RLL caller replacement preserves that state.

Choose **FBD process lab** for `FBDProcessLab.L5X`: 42 roots, two blocks, 38 drawing
nodes and 38 wires. Inputs 10/20/30 initially high-select 30; DERV starts at zero.
Changing Input3 to 40 with Gain 1 and SampleTime 0.25 yields Derivative 40. The
controls expose health, selection/control requests, override, bypass and timing.
BlockEnable gates both; ExecuteGraph skips their routine. FaultDivisor zero
demonstrates a late fault; restore it to 1 to retry with current inputs.

The [single-sheet graph restrictions](function-blocks.md) still apply. Logical
schemas, language forms and pins were checked against installed v35 help 14821.htm
and 19659.htm. Native initialization, simultaneous requests, health/override/reset/
median ordering, timing transitions, precision, packed layouts and full status/
fault/lifecycle parity remain unqualified. Native Studio import/Verify, transfer
and online-edit acceptance have not been established by this synthetic fixture.
