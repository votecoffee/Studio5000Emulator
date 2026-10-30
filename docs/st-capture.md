# Structured Text maximum/minimum capture

App `26.1030.134503` adds bounded v35 ControlLogix 5580 ST MAXC/MINC calls.
Choose **Capture lab**, or launch with `--sample CaptureLab`. Input drives both
captures. ResetCapture and ResetHigh/ResetLow establish new baselines; CallCapture
skips both instructions. Maximum and Minimum expose the results. FaultDivisor
provides a later arithmetic error for rollback checks.

```text
MAXC(HighState);
MINC(LowState);
```

MAXC uses a logical MAXIMUM_CAPTURE record; MINC uses MINIMUM_CAPTURE. Both have
BOOL EnableIn, Reset and EnableOut, and REAL In, ResetValue and Out. These are
six named logical fields, without a native packed-layout claim. Missing saved
fields stay unknown; schema defaults do not replace absent exported state.
Redefined records and constant destinations are blocked. The regular resolver
supports scalar records, members, array elements, aliases, program-local tags
and supported AOI InOut bindings.

## Capture and reset

The first reached non-reset call initializes its retained extremum from In,
including negative-only input streams. Saved Out and zero are not substituted
for the first input. Subsequent MAXC calls replace the retained value only when
In is greater; MINC replaces it only when In is less. Out reports that retained
value on every reached call. Ties preserve the previous float32 value, including
its signed zero. Native signed-zero behavior remains unverified.

Reset takes priority: each reached call with Reset true copies ResetValue to
Out and makes it the new retained baseline. Reset is level-sensitive, so changing
ResetValue while Reset stays true changes the baseline again. After Reset clears,
normal comparisons resume from that baseline. The initial-reset ordering is an
explicit software policy pending native lifecycle qualification.

Only the selected input is read: ResetValue while resetting, otherwise In.
An unknown unused operand can remain unknown. Reset itself must be known BOOL.
ST calls set EnableIn and EnableOut true regardless of their saved values.
Skipped calls retain outputs, enable bits and history. Repeated calls at one
simulated timestamp compare each input; no elapsed-time sampling is involved.

The retained extremum is separate from Out. Direct Out writes do not replace
history; use Reset and ResetValue to establish a new baseline. History belongs
to the resolved record, so separate records and array elements are independent.

## Lifecycle and limits

Prescan clears the enable pair and preserves visible outputs. Run entry clears
retained extrema; the next reached call initializes again. Supported detached
routine replacement preserves the existing extrema. Continuous, Periodic,
Event, harness, supported AOI and loop calls use the same per-call model.

Values are finite float32. Required unknown/nonfinite/out-of-range operands,
instruction-budget exhaustion or a later error roll back the whole advance,
including both capture values, hidden extrema, time and scheduling. A failed
reset or failed new maximum/minimum cannot affect a corrected retry. Prescan
failure also restores existing values and history.

These are two bounded named models, not complete emulation of the predefined
types or the statistical instruction family. FBD graphs, native packed layouts,
other controller profiles, native initialization/reset/skip/postscan semantics
and native nonfinite/precision/status/fault parity remain unfinished. Studio
transfer and online-edit acceptance remain separate.

Operands and algorithms were checked against installed Studio v35 MAXC/MINC help
and Rockwell's
[Advanced Process Control and Drives reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm006_-en-p.pdf).
The installed MINC first-scan row says Maximum; this model initializes its minimum
from input consistently with MINC's algorithm. The sample is synthetic; vendor
help assets are not distributed.
