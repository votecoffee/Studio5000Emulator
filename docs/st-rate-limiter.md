# Structured Text rate limiting

App `26.1030.102258` adds RLIM over logical RATE_LIMITER records in the bounded
v35 ControlLogix 5580 profile. Period/elapsed timing and explicit oversample
timing are supported. Module timestamp timing remains unqualified. RLIM is an
ST-only call; the RLL dispatch count stays 99. FBD graphs remain unfinished.

```text
Ramp.In := Target;
Ramp.IncRate := 8.0;
Ramp.DecRate := 16.0;
Ramp.ByPass := FALSE;
RLIM(Ramp);
Output := Ramp.Out;
```

## Rates and time

The first reached call initializes Out from In. Later calls approach the input
using separate nonnegative increase/decrease rates in units per second, with
target capture to avoid overshoot. ByPass=true passes In to Out and seeds the
next ramp from that value. Zero rates hold the established output.

TimingMode=0 uses the configured period in a Standard Periodic task. It uses
elapsed simulated milliseconds since the previous reached call in Continuous
execution or a routine harness. The first Continuous/harness call reports
DeltaT=0. Elapsed time is expressed in seconds in DeltaT.

TimingMode=1 uses OversampleDT on each call, independently of the simulation
step size. The supported positive range ends at the float32 representation of
4194.303 seconds. Repeated Periodic or oversample calls can advance the output
more than once at one timestamp. Repeated Continuous calls at that timestamp
have zero elapsed time and hold the previous output.

Skipped calls retain fields and hidden history. The next Continuous call uses
the elapsed gap; Periodic calls still use one configured period, and oversample
calls use the supplied interval. Changing timing modes or executing an
instruction repeatedly is a distinct timing scenario requiring native
qualification; this model applies the current call's timing rule.

## Records, diagnostics and lifecycle

RATE_LIMITER has BOOL EnableIn, ByPass and EnableOut; REAL In, IncRate, DecRate,
OversampleDT, Out and DeltaT; and DINT TimingMode, RTSTime, RTSTimeStamp and
Status. RTSTime defaults to 1; other numeric fields default to zero. Missing
exported values remain unknown rather than inheriting these shape defaults.

The status aliases share the backing DINT:

| Alias | Bit |
| --- | --- |
| InstructFault | 0 |
| IncRateInv / DecRateInv | 1 / 2 |
| TimingModeInv | 27 |
| RTSMissed / RTSTimeInv / RTSTimeStampInv | 28 / 29 / 30 |
| DeltaTInv | 31 |

Negative rates are written as zero with their diagnostic bits and InstructFault.
Invalid oversample intervals, including zero, set DeltaT=0 and Status.0/.31.
The word is signed DINT, so this diagnostic alone is -2147483647. The RLIM
instruction reference marks zero invalid; the generic timing reference calls
zero disabled. This profile disables the ramp and reports the RLIM diagnostic.

TimingMode values outside 0..2 set DeltaT=0 and Status.0/.27. Invalid timing
disables ramping; first-call initialization and ByPass can still establish Out.
A later valid call clears diagnostics. TimingMode=2 faults as unsupported;
RTS fields can be stored and their status aliases accessed, but module timestamp
arithmetic and RTS diagnostics are not emulated.

Reached ST calls set EnableIn/EnableOut independently of stored EnableIn.
Prescan clears only that enable pair. Run entry clears hidden history; the next
reached call initializes Out from In. Hidden previous output and call time are
keyed by resolved record. Explicit Out writes do not replace this history; use
In with ByPass to seed a new ramp. Native external-write parity is unverified.

Record values and history share whole-advance rollback, including late faults,
instruction budgets and supported detached routine replacement. Existing
aliases, arrays, UDT members, program locals, AOI InOut bindings and harnesses
use existing reference rules. FOR guards include writes to the record.

The profile rounds inputs, DeltaT and results to finite float32 values and uses
host double intermediate arithmetic. Decimal intervals such as 0.01 are inexact
and can leave small residuals across ramps. Native precision, intermediate
overflow, timing/invalid-input behavior, nonfinite values, lifecycle/fault
handling and packed transfer layouts remain unverified. Unknown required inputs
fault and roll back; unused oversample/RTS fields may remain unknown. Wrong
types/arity, constants, schema redefinitions, other profiles, ladder forms and
RES on RATE_LIMITER are rejected. Reports expose `st_rate`; traces identify RLIM.

## Try Rate Lab

Choose **Rate lab** and step once to initialize at Target=0. Set Target=10 and
step to ramp upward. IncreaseRate and DecreaseRate default to 100 and 200 units
per second. Bypass=true moves directly to Target; clear it to resume limiting.

TimingMode=1 and SampleTime=0.125 use 125 ms per call. CallRate=false skips the
call. Negative rate settings exercise IncreaseInvalid/DecreaseInvalid; invalid
SampleTime exercises TimeInvalid. Restore valid settings to recover. A late
FaultDivisor=0 fault restores both output and clock history; restore it to 1
and retry. TimingMode=2 demonstrates the explicit unsupported-mode fault.

See [RateLab.L5X](../source/samples/RateLab.L5X),
[implementation](../source/logixlab/st_rate.py), [checks](../source/tests/test_st_rate.py)
and Rockwell's [RLIM reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/select-limit-instructions/rlim.html).
The installed v35 RLIM and Timing Modes help also informs the bounded model.
