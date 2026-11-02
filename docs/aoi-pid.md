# Ladder PID in Add-On Instructions

Supported ladder AOI bodies can execute the bounded [PID solver](ladder-pid.md)
against exact PID InOut parameters and represented saved local PID records.
Scalar numeric inputs use the existing copied-input rules; CV can be a writable
REAL InOut parameter, output parameter or supported numeric local. This adds
no ST PID call form or native AOI compilation/layout equivalence.

Bindings resolve to the underlying tag/member/selected array element. Hidden
I, derivative, deadband and mode history uses that canonical PID record, so
separate instances and nested AOIs stay isolated. Rebinding an InOut to another
record selects that record's history. Two true calls of the same underlying
record at the same task-release time fault, including calls through different
AOI instances. Control operands cannot overlap their own PID record.

Missing saved local fields remain unknown. Definition defaults do not establish
an existing instance's state. Known saved CTL is needed for prescan to clear EN;
other required fields must be established before a true call consumes them.
Unsupported types, dimensions, constant targets and unresolved records remain
blocked by existing AOI/PID validation.

## Lifecycle and rollback

AOI prescan visits its Logic routine and clears PID EN; entering Run resets
hidden PID history through the existing engine lifecycle. On a false AOI call,
an enabled, authored EnableInFalse routine determines what runs. The sample
uses AFI before each PID to clear EN and retain output/history. Without that
routine, skipped PID calls retain their enable and history. Required copied
AOI inputs are consumed before either path; an unknown copied actual can fault
even when the PID instruction itself is false or skipped.

[Manual/PVT/inhold](pid-restart.md), derivative/deadband and [one-way cascade](pid-cascade.md)
follow the same solver contract. Master references can resolve through InOut
bindings. Later faults restore external/local values, frames, indirect binding
caches, PID history, trace, time and scheduler state. Existing deterministic
Continuous/Periodic/Event and selected-routine execution profiles apply.

## Try the AOI PID lab

Load **AOI PID lab**. Enable EnabledA and EnabledB, then step. CVA/CVB become
45/22.5, then 60/30. Each instance also has a separate saved local PID:
DriverA.AuxValue is 5 and DriverB.AuxValue is 0. Disable EnabledA to clear its
two PID enable bits through the authored false routine, preserving the outputs.

Set HoldA true and ReadbackA 70 with EnabledA true: both CVA and the local
AuxValue become 70. Clear HoldA for the modeled automatic transfer. ManualA
and PVTrackingA control the external ControlA record; they do not change the
local record's mode flags. FaultDivisor zero demonstrates whole-advance rollback.
All sample logic is synthetic ladder and all saved local values are explicit.

Reference basis: installed v35 help 3232 (Using an Add-On Instruction) and
14709 (PID), with the reference-passing and scan-mode guidance in the
[Add-On Instructions programming manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm010_-en-p.pdf).
Broader AOI lifecycle, saved-state and native controller parity remain unqualified.
