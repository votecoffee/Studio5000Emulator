# FBD accumulation and integration

UPDN and INTG execute as FBD Blocks in the bounded v35 ControlLogix 5580 software
graph. They share the [ST accumulation models](st-accumulation.md) and resolved
record histories. The graph inventory is now 25 blocks: 19 names shared with ST
and six FBD-only forms. RLL remains 101 and ST calls 27.

| Block | Logical record | Inputs besides EnableIn | Outputs besides EnableOut |
| --- | --- | --- | --- |
| UPDN | UP_DOWN_ACCUM | InPlus, InMinus, Initialize, InitialValue, Hold | Out |
| INTG | INTEGRATOR | In, Initialize, InitialValue, IGain, HighLimit, LowLimit, HoldHigh, HoldLow, TimingMode, OversampleDT, RTSTime, RTSTimeStamp | Out, HighAlarm, LowAlarm, DeltaT, Status and BOOL status aliases |

UPDN adds InPlus and subtracts InMinus once per enabled reached call. Its hidden
total starts at zero. Initialize takes priority over Hold and assigns InitialValue
on every initialization call. Otherwise Hold retains the total without consuming
the plus/minus inputs. Both inputs can be negative. Multiple calls at one timestamp
each accumulate once.

INTG uses the existing trapezoidal software recurrence, with finite REAL output
and input history. The first ordinary reached call establishes zero history and
output. Initialize assigns InitialValue and captures In; subsequent calls use
that baseline. Directional holds suppress increases/decreases while sampling input
on valid positive intervals. Output clamps to limits without a hidden excess.
Alarms use inclusive comparisons. Initialize may exceed limits in this profile.
Native startup and interacting-condition precedence remain unqualified.

Mode 0 uses the configured Periodic interval or elapsed simulated time between
enabled reached calls in Continuous/Event/harness execution. Mode 1 uses the
supplied OversampleDT for every call. Zero holds the integral and input sample
without a timing diagnostic. Negative or oversized intervals report Status.0/.31
with DeltaT zero. Invalid modes report Status.0/.27; module timestamp mode 2 is
unsupported and faults when reached enabled. No RTS timestamps are simulated.

Negative IGain is written as zero with diagnostic bits and holds the prior output.
Invalid limits set both alarms, report Status.0/.2 and select LowLimit unless
Initialize applies. InstructFault, IGainInv, HighLowLimsInv, TimingModeInv and
DeltaTInv are BOOL source pins. RTS aliases are addressable without implementing
RTS behavior. Required unknowns remain errors; exported omissions do not inherit
declaration defaults. INTG always requires In, including initialization and holds.

Connected false EnableIn clears both enables and skips the algorithm. Outputs,
alarms, diagnostics and histories retain; initialization is skipped too. Unwired
EnableIn is true. A skipped graph retains state. Continuous resume includes the
elapsed gap; Periodic and oversample calls each use one configured interval.
These software timing policies do not establish native disable/resume equivalence.

ST/FBD calls share histories. Repeated Continuous calls add no time at the same
timestamp; Periodic and oversample calls can integrate repeatedly. UPDN always
counts reached calls. Direct Out writes do not replace hidden totals or integrals.
Prescan clears enables; Run clears histories. Whole-advance rollback includes
wires, gain corrections, totals, integrals, samples, clocks and scheduling.
Supported detached RLL caller replacement preserves this state.

Choose **FBD accumulation lab** for `FBDTotalLab.L5X`: 33 roots, two blocks,
29 drawing nodes and 28 wires. Plus 2 and Minus 0.5 add 1.5 per call to Total.
Rate 4, Gain 1 and SampleTime 0.25 integrate in 250 ms intervals; Integral starts
at 0, then becomes 0.5 and 1.5. High/LowLimit default to 5/-5. Separate initialize,
seed and hold controls exercise each algorithm. BlockEnable gates both blocks;
ExecuteGraph skips the routine. FaultDivisor zero demonstrates a late fault;
restore it to 1 to retry without consuming another total update or integral sample.

The [single-sheet graph rules](function-blocks.md) still apply. Operand schemas,
language forms and pins were checked against installed v35 help 14773.htm and
14789.htm. Native lifecycle, intermediate precision, initialization/limit/hold
ordering, packed layouts, nonfinite/status/fault parity, Studio import/Verify and
transfer/edit behavior remain unqualified. The lab is a synthetic software fixture.
