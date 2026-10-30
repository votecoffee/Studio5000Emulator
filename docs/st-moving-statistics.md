# Structured Text moving statistics

App `26.1030.132924` adds bounded v35 ControlLogix 5580 ST calls using logical
MOVING_AVERAGE and MOVING_STD_DEV records. Choose **Moving statistics lab** or
launch with `--sample MovingLab`. Input, TakeSample, Window, Weighted,
ResetStatistics and InputFault control the example; Average, PopulationMean,
Deviation and the visible sample arrays show the results. CallStatistics skips
both calls. FaultDivisor provides a late arithmetic fault for rollback checks.

```text
MAVE(MeanState,MeanSamples,Weights);
MSTD(DeviationState,DeviationSamples);
```

MAVE also accepts two operands for uniform averaging. Weighted sampling requires
the third operand. Storage and optional weights must be whole one-dimensional
REAL arrays with 1–4096 elements. Static members, array-of-UDT members, aliases,
program-local tags and supported AOI InOut bindings work. Storage is writable;
weights may be constant. Record/storage/weight overlap, indirect references,
multidimensional queues and other element types are blocked.

## Records and calculations

Both logical records have BOOL EnableIn, InFault, Initialize, SampleEnable and
EnableOut; REAL In and Out; and DINT NumberOfSamples and Status. MOVING_AVERAGE
adds BOOL UseWeights. MOVING_STD_DEV adds REAL Average. Status aliases are
InstructFault (bit 0), InFaulted (bit 1) and NumberOfSampInv (bit 2). They share
the backing Status word. Missing exported values remain unknown; default shapes
do not substitute for saved instance state. MAVE's declared SampleEnable default
is true; MSTD's is false. Both NumberOfSamples defaults are one.

Each sampled call inserts In at queue index zero and moves older active values
toward higher indices. Only the active prefix is read or written. At startup the
active count grows from one to NumberOfSamples; saved or unknown unused slots
are not included. Once full, each new value discards the oldest active sample.

For an active count n, uniform MAVE returns sum(samples)/n. With UseWeights set,
it returns sum(samples[i] * weights[i]); weights are used directly, without
division by their sum. Weight zero applies to the newest sample. Negative
weights and a zero total weight are permitted within the finite numeric profile.
Unused weights are not read.

MSTD calculates Average over the active prefix and Out as
sqrt(sum((sample - Average)^2)/n). This is population deviation, distinct from
the sample divisor n-1 used by the separate ladder STD model. A single sample
has zero deviation. Operands, intermediate sums/products/differences and results
use float32. Native intermediate precision and numerical stability are unverified.

## Sampling, initialization and diagnostics

ST calls set EnableIn and EnableOut true. Each reached call with SampleEnable
set takes one sample, including repeated calls at the same simulated timestamp.
The instruction does not derive sampling intervals from elapsed time. Skipping
the call retains its outputs, queues and active count.

On the first unguarded call, the active queue starts empty and Out starts at zero;
MSTD also initializes Average from In. With SampleEnable false, those initial
outputs are retained until sampling or explicit initialization. Later calls with
SampleEnable false hold outputs and queue values.

Initialize overrides ordinary sampling: MAVE sets Out to In; MSTD sets Out to
zero and Average to In. Both discard the active count without erasing the queue.
Clearing Initialize starts a new incremental fill on the next sampled call.

InFault holds the saved outputs and sets Status to 3. An invalid NumberOfSamples
(below one or beyond storage capacity, including weight capacity when weighted)
holds outputs and sets Status to 5. Both conditions together produce 7. These
guards take precedence over initialization and initial output changes. They
discard the active count; valid sampling then starts a new fill. Successful
unguarded calls clear these status bits. This ordering is an explicit software
policy pending native lifecycle qualification.

Increasing NumberOfSamples preserves the active prefix and fills gradually.
Decreasing it truncates the active count to the new size. If sampling is paused,
outputs and storage hold, while the active count still reflects that truncation;
the next sampled call uses the retained newest prefix. Native resize/hold
interaction and physical queue order remain unverified.

## Lifecycle and boundaries

The active count is per resolved record, separate from its visible outputs.
Changing Out does not replace sample history. Direct writes to active queue
values affect the next sampled calculation. A record cannot switch storage
bindings within a Run; that operation faults explicitly.

Prescan clears the enable pair and preserves saved outputs/queues. Run entry
resets hidden counts. Supported detached routine replacement preserves counts
and queues. Periodic, Continuous and harness calls share the same per-call
sampling rules. Element processing consumes the shared instruction budget.

Queue changes, counts, output/status changes, simulated time and scheduling
commit with the complete advance. Unknown required values, nonfinite values,
float32 overflow, unsupported bindings or a later fault roll back that advance.
The model does not reproduce controller nonfinite propagation, EnableOut overflow
behavior or minor-fault reporting.

These are two bounded named models, not complete predefined types. FBD graph
forms, packed native layouts, other controller profiles, shared-storage native
semantics, precision/status/fault parity and native first-scan/postscan behavior
remain unfinished. Studio transfer and online-edit acceptance are separate.

The equations and operand forms were checked against installed Studio v35 help
for MAVE/MSTD and Rockwell's
[Advanced Process Control and Drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
The public sample is synthetic; vendor help files are not included.
