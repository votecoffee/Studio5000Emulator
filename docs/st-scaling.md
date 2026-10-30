# Structured Text analog scaling

App `26.1030.094109` adds SCL over logical SCALE records in the bounded v35
ControlLogix 5580 profile. This is an ST-only call; the RLL dispatch count stays
99. FBD graph execution remains unfinished.

```text
Channel.In := RawInput;
Channel.InRawMin := 0.0;
Channel.InRawMax := 4095.0;
Channel.InEUMin := 0.0;
Channel.InEUMax := 100.0;
Channel.Limiting := TRUE;
SCL(Channel);
EngineeringValue := Channel.Out;
```

The logical record contains BOOL EnableIn, Limiting, EnableOut, MaxAlarm and
MinAlarm; REAL In, InRawMax, InRawMin, InEUMax, InEUMin and Out; and DINT Status.
InstructFault and InRawRangeInv alias Status.0 and Status.1 rather than storing
independent values. Missing exported values remain unknown. This is a logical
schema, not a native packed transfer layout.

## Calculation and diagnostics

The modeled slope calculation is:

```text
Out = (In - InRawMin) * ((InEUMax - InEUMin) / (InRawMax - InRawMin)) + InEUMin
```

The profile rounds inputs and the final result to finite float32 values and uses
host double precision for intermediate operations. Native intermediate rounding
and bit-for-bit numeric parity are unverified.

With Limiting=false, values outside the raw range extrapolate. With it true,
inputs above InRawMax map to InEUMax and inputs below InRawMin map to InEUMin.
Limiting applies before final float32 coercion in this model. Descending or
equal engineering endpoints are supported; raw endpoints must increase.

MaxAlarm reflects In>InRawMax and MinAlarm reflects In<InRawMin. The comparisons
are strict, so an input exactly at an endpoint does not alarm. Limiting and
engineering-range direction do not change these raw-input diagnostics.

InRawMin>=InRawMax produces Status=3 without a modeled scan fault. The current
profile retains Out/MaxAlarm/MinAlarm, sets EnableIn/EnableOut, and requires only
known finite raw endpoints for this diagnostic branch. Valid recovery
recalculates output/alarms and clears Status. Complete native status and
invalid-range output behavior remain unverified.

## Calls and failures

A reached ST call executes regardless of stored EnableIn and sets the enable
pair. Skipping it retains the record, including output, alarms and status.
There is no hidden sampled or elapsed-time state. Repeated calls use the current
inputs, including calls at the same simulated timestamp.

Prescan clears only EnableIn/EnableOut. Deferred import preview keeps saved
values until Run entry. Existing aliases, array elements, UDT members, program
locals, AOI InOut bindings, routine harnesses and Standard periodic releases use
the existing reference and scheduling rules. FOR dependency checks include the
record's writes. Supported detached routine replacement preserves active values.

Unknown required inputs, nonfinite inputs and results outside finite REAL range
stop and roll back the whole advance. A later fault or instruction-budget failure
also restores values, simulated time and scheduling. Correcting and retrying
does not preserve partial SCL output or status changes.

This overflow policy differs from a complete native instruction implementation:
native EnableOut/overflow/nonfinite behavior and limiting order need separate
qualification. The profile rejects wrong arity, constants, non-SCALE values,
redefined SCALE schemas and other controller profiles. Ladder SCL and RES on a
SCALE record are unavailable. Reports expose `st_scale`; traces identify SCL.

## Try Scale Lab

Choose **Scale lab**. RawValue=2047.5 produces ScaledValue=50.0 with the default
0..4095 raw and 0..100 engineering ranges. Set RawValue=8190.0 to extrapolate to
200.0 and set HighAlarm. Enable LimitOutput to clamp the result to 100.0 while
retaining the alarm. Negative RawValue exercises LowAlarm.

RawMinimum/RawMaximum and EUMinimum/EUMaximum expose both ranges. Equal raw
endpoints set ScaleFault/InvalidRange and retain the previous output. Restore a
valid range to recover. CallScale=false skips the call. FaultDivisor=0 produces
a late scan fault; restore it to 1 and retry to commit the calculation once.

See [ScaleLab.L5X](../source/samples/ScaleLab.L5X),
[implementation](../source/logixlab/st_scale.py), [checks](../source/tests/test_st_scale.py)
and Rockwell's [SCL reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/process-control-instructions/scl.html).
The installed v35 help also informs the model. Software checks remain separate
from native Studio/controller acceptance and do not emulate an analog module.
