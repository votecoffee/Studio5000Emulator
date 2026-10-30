# Structured Text signal conditioning

App `26.1030.100100` adds HLL, SNEG and SSUM for the bounded v35 ControlLogix
5580 profile. These are three ST-only calls using logical HL_LIMIT,
SELECTABLE_NEGATE and SELECTED_SUMMER records. The RLL dispatch count stays 99.
FBD graph execution remains unfinished.

```text
Limiter.In := RawValue;
HLL(Limiter);
Negator.In := RawValue;
SNEG(Negator);
Summer.In1 := Limiter.Out;
Summer.Select1 := TRUE;
Summer.In2 := Negator.Out;
Summer.Select2 := UseNegated;
SSUM(Summer);
Result := Summer.Out;
```

## Limits, negation and sums

HLL uses SelectLimit=0 for both limits, 1 for high only and 2 for low only.
Active limits clamp Out; HighAlarm/LowAlarm include equality at their respective
endpoints. An inactive alarm is false and its limit is not read. This differs
from the strict raw-range alarms in [SCL](st-scaling.md).

An invalid SelectLimit uses both limits without changing the setting and sets
Status.0/.2. Equal or reversed bounds in both-limit mode use LowLimit as Out
and set Status.0/.1. Combined diagnostics produce Status=7. The model compares
In against both active bounds for alarms, including invalid ranges; native
invalid-range alarm/status parity needs separate qualification. Correcting the
settings recalculates outputs and clears diagnostics. These conditions do not
cause a modeled scan fault.

SNEG selects -In when NegateEnable=true, otherwise In. The logical default for
NegateEnable is true. The finite float32 model preserves the selected zero sign.

SSUM selects up to eight input/gain pairs. It sums selected InN*GainN in index
order, then adds Bias. No selected inputs returns Bias. Gains default to 1.0;
selectors default to false. All selectors and Bias must be known. Unselected
input/gain values are not read, so omitted values in an unused pair can remain
unknown. Selecting that pair then requires known finite values.

## Records and execution

HL_LIMIT has BOOL EnableIn, EnableOut, HighAlarm and LowAlarm; REAL In,
HighLimit, LowLimit and Out; DINT SelectLimit and Status. InstructFault,
LimitsInv and SelectLimitInv share Status bits 0, 1 and 2.

SELECTABLE_NEGATE has BOOL EnableIn, NegateEnable and EnableOut, plus REAL In
and Out. SELECTED_SUMMER has BOOL EnableIn, EnableOut and Select1..Select8;
REAL In1..In8, Gain1..Gain8, Bias and Out. These records define logical values,
not native packed layouts. Missing exported values remain unknown. The v35
summer table's SELECTABLE_SUMMER heading differs from its operand/catalog name;
this implementation uses SELECTED_SUMMER and does not invent a spelling alias.

Reached ST calls execute regardless of stored EnableIn, set the enable pair
and update outputs. Skipped calls retain values. Repeated calls read current
inputs even at the same timestamp. Prescan clears only EnableIn/EnableOut; Run
entry does not reset represented results. There is no hidden instruction history.

The profile uses finite float32 inputs/results, with host double weighted
products and summation for SSUM. Unknown required values, nonfinite inputs and
unrepresentable results stop and roll back the complete advance. Late faults
and instruction-budget failures restore values, simulated time and scheduling.
Aliases, arrays, UDT members, program locals, AOI InOut bindings, routine
harnesses, Standard periodic tasks and supported detached routine replacement
use existing reference/lifecycle rules. FOR guards include record writes.

Wrong arity/types, constants, redefined schemas and other controller profiles
are rejected. Ladder forms and RES on these records are unavailable. Native
precision, intermediate overflow, EnableOut/nonfinite behavior, complete
status/lifecycle/fault behavior and packed transfers remain unverified. Reports
expose `st_signal`; traces identify each reached call.

## Try Signal Lab

Choose **Signal lab**. Input starts at 5, limits at 0..10, Negate=false,
UseLimited=true, UseNegated=false and Bias=1. Stepping yields LimitedValue=5,
NegatedValue=5 and SumValue=6. Input=10 sets HighAlarm at the endpoint.

Set Input=20, Negate=true and UseNegated=true: results become 10, -20 and -9.
LimitMode=2 removes the high clamp/alarm, giving 20, -20 and 1. LimitedGain,
NegatedGain and Bias control the sum. Summer's other six pairs are available
through record members. Turn both selections off to return Bias alone.

LimitMode outside 0..2 exercises selector diagnostics. Equal/reversed bounds
in both-limit mode exercise LimitsInvalid. CallSignals=false skips all three
calls. FaultDivisor=0 demonstrates a late fault; restore it to 1 before retrying.
An excessive selected gain demonstrates finite-result overflow; deselect or
correct that contribution to recover.

See [SignalLab.L5X](../source/samples/SignalLab.L5X),
[implementation](../source/logixlab/st_signal.py), [checks](../source/tests/test_st_signal.py)
and Rockwell's [HLL](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/select-limit-instructions/hll.html),
[SNEG](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/select-limit-instructions/sneg.html)
and [SSUM](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/select-limit-instructions/ssum.html)
references. The installed v35 help also informs these bounded software models.
