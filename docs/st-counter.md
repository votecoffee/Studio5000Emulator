# Structured Text up/down counter

App `26.1030.090800` adds CTUD over logical FBD_COUNTER records to the bounded
v35 ControlLogix 5580 profile, alongside the three [ST timers](st-timers.md).
CTUD also executes in the limited [FBD graph](fbd-stateful.md), with connected
EnableIn gating and shared sampled-edge state. General FBD and native lifecycle
parity remain unfinished.

```text
Counter.PRE := 3;
Counter.CUEnable := UpInput;
Counter.CDEnable := DownInput;
Counter.Reset := ResetCounter;
CTUD(Counter);
Count := Counter.ACC;
```

The logical record contains BOOL EnableIn, CUEnable, CDEnable, Reset,
EnableOut, CU, CD, DN, OV and UN, plus DINT PRE and ACC. Missing saved fields
remain unknown. The schema is a logical model, not a native packed layout.
Aliases, array elements, UDT members, program locals, AOI InOut bindings,
routine harnesses and Standard periodic tasks use existing reference rules.

## Edges, initialization and reset

An executed ST call sets EnableIn/EnableOut, regardless of the stored EnableIn.
CU/CD mirror the current count inputs. Edge history is stored separately per
resolved record, so writing the visible CU/CD outputs cannot create a count.
The first reached call samples both inputs without counting. This suppresses
an initial high input until a sampled low-to-high transition occurs.

Later CUEnable rising edges add one; CDEnable rising edges subtract one.
Up executes before down if both inputs rise together. Repeated calls with
unchanged inputs, including calls in a FOR loop, do not duplicate edges.
Separate records have independent history.

Reset takes priority, sets ACC=0, clears OV/UN and consumes the current input
levels. Releasing Reset while an input remains high produces no new edge.
The current model derives DN from ACC>=PRE on each call, including after Reset.
Zero and negative DINT presets are supported. Native reset/flag parity remains
unverified.

ACC wraps at the signed 32-bit limits. Incrementing 2147483647 produces
-2147483648 and sets OV; decrementing -2147483648 produces 2147483647 and sets
UN. The modeled flags retain until Reset or an explicit write. With both edges
at the positive limit, up wraps and down wraps back, setting both flags even
though the final ACC equals its starting value.

## Calls, lifecycle and failures

Skipping the call retains its values and sampled-edge history. Only input
levels observed on reached calls can form edges. Pulses occurring entirely
between those calls are not invented or counted.

Prescan clears EnableIn/EnableOut without changing saved counter data. Run
entry clears sampled-edge history; the next reached call primes it again while
retaining ACC. Deferred import preview retains the source values until Run entry.
Counter Reset can establish an unknown ACC/OV/UN, but it still needs known
count inputs, Reset and PRE to define the resulting state.

Required unknown inputs or ACC fault. Unneeded unknown wrap flags remain
unknown until a reset or boundary event establishes them. A later fault or
instruction-budget failure rolls back values, sampled edges, simulated time
and scheduling. A corrected retry therefore counts an edge once. Prescan
failure and supported detached routine replacement preserve the edge history.
FOR dependency checks treat the counter record as written by CTUD.

The profile rejects wrong argument counts, non-FBD_COUNTER values, constants,
redefined FBD_COUNTER schemas and other controller profiles. Use the Reset
member; ladder RES is not an operation on this type. Coverage reports expose
`st_counter`; ST traces identify reached CTUD calls. Complete native lifecycle,
reset/overflow/status, transfer layout and fault parity remain unfinished.

## Try Counter Lab

Choose **Counter lab** and step once. Toggle UpInput false/true with a step
after each change to count up. A held true input counts once. DownInput works
the same way in the opposite direction. Count, Done, Overflow and Underflow
mirror the counter outputs. Preset starts at 3.

ResetCounter resets the count and wrap flags. CallCounter=false skips the call.
FaultDivisor=0 demonstrates a late fault; correct it to 1 before retrying.
Counter state, edge history and CallCount then commit once. To examine signed
boundaries, write Counter.ACC and generate a new sampled edge.

See [CounterLab.L5X](../source/samples/CounterLab.L5X),
[implementation](../source/logixlab/st_counter.py) and
[checks](../source/tests/test_st_counter.py). The installed v35 help and
Rockwell's [CTUD reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/timer-and-counter-instructions/count-up-down--ctud-.html)
describe the instruction's inputs, ordering and initialization. Software checks
remain separate from native Studio/controller acceptance.
