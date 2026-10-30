# Structured Text edge one-shots

App `26.1030.092825` adds OSRI and OSFI over logical FBD_ONESHOT records in the
bounded v35 ControlLogix 5580 profile, alongside the three [ST timers](st-timers.md)
and [CTUD](st-counter.md). These calls also execute in the limited
[FBD graph](fbd-stateful.md), with connected-enable gating and shared edge state.
Native FBD lifecycle/layout/fault parity remains unqualified.

```text
Rising.InputBit := Sensor;
Falling.InputBit := Sensor;
OSRI(Rising);
OSFI(Falling);
RisePulse := Rising.OutputBit;
FallPulse := Falling.OutputBit;
```

The logical record has four BOOL fields: EnableIn, InputBit, EnableOut and
OutputBit. Missing exported values remain unknown. This schema does not define
a native packed transfer layout. Aliases, array elements, UDT members, program
locals, existing AOI InOut bindings, routine harnesses and Standard periodic
tasks use the existing reference and scheduling rules.

## Pulses and calls

A reached ST call sets EnableIn/EnableOut, regardless of stored EnableIn.
OSRI sets OutputBit on a sampled false-to-true transition. OSFI sets it on a
sampled true-to-false transition. Every other reached call clears OutputBit.
The pulse lasts for one execution of that record; calling it again during the
same scan with the same input clears the pulse.

Input history is separate from the four visible fields, keyed by resolved
record. Writing OutputBit cannot create or consume a sampled input edge.
Separate records have independent histories. Calls in loops or different
routines share history when they resolve to the same record.

Skipping a call retains its output and history. An output can therefore stay
true across skipped scans. A change observed on resumption can produce a pulse,
but an input pulse occurring entirely between reached calls is not sampled.
Applications should consume OutputBit with those call rules in mind.

## Initialization and failures

For the first reached call, OSRI starts with previous input true and OSFI starts
with previous input false. Neither initial input level creates a pulse. Later
sampled transitions operate normally.

Prescan clears EnableIn/EnableOut while retaining represented InputBit and
OutputBit. Run entry resets hidden history; the next reached call is primed
again. Deferred import preview retains the saved enable values until Run entry.
An uncalled saved OutputBit can remain true until the record executes.

Unknown InputBit faults instead of being treated as false. Reached calls can
establish unknown outputs, but cannot invent a missing input. A later fault or
instruction-budget failure rolls back record values, sampled history, simulated
time and scheduling. Correcting the fault and retrying preserves the pending
edge. Prescan failures and supported detached routine replacements also preserve
the original history and values.

Wrong argument counts, constants, non-FBD_ONESHOT values, redefined schemas and
other controller profiles are blocked. Sharing one record between OSRI and
OSFI faults and rolls back; that native interaction remains unqualified. Ladder
OSRI/OSFI and RES on FBD_ONESHOT are unavailable. Complete native layout,
first-run/Postscan/lifecycle and fault parity remain unverified. Reports expose
`st_oneshot`; traces identify the reached calls.

## Try Pulse Lab

Choose **Pulse lab** and step once to initialize. Set Input=true and step:
RisingOutput pulses and RisingPulses increments. Step again with the input held:
the output clears and the count stays unchanged. Set Input=false and step to
produce FallingOutput and increment FallingPulses.

CallEdges=false skips both calls and retains their outputs. Pulse counts update
only inside the call block. FaultDivisor=0 demonstrates a late fault; correct
it to 1 and retry to observe one committed pulse and count increment.

See [PulseLab.L5X](../source/samples/PulseLab.L5X),
[implementation](../source/logixlab/st_oneshot.py) and
[checks](../source/tests/test_st_oneshot.py). The installed v35 instruction help
and Rockwell's [OSRI reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/bit-instructions1/osri.html)
and [OSFI reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/bit-instructions1/osfi.html)
inform the model. OSFI's introductory sentence describes a rising transition;
its detailed description, initialization and example specify falling behavior,
which this model follows. Software checks remain separate from native
Studio/controller acceptance.
