# Source-bound Task metadata

The Task object (`0x70`) supplies read-only settings from explicit
values in a complete v35 controller L5X:

| Attribute | L5X Task field | Encoding |
| --- | --- | --- |
| 1, Task Program List | Ordered schedule names and matching native Program IDs | UINT16 count followed by UINT32 IDs |
| 2, Rate | `Rate`, for Periodic Tasks only | Little-endian positive 32-bit microseconds |
| 6, Priority | `Priority` | Little-endian UINT16, 1 through 15 |
| 12, Watchdog | Positive `Watchdog` | Little-endian positive 32-bit microseconds |
| 18, Disable Output Update | `DisableUpdateOutputs` | Little-endian UINT32, false=0, true=1 |
| 19, Inhibit | `InhibitTask` | Little-endian UINT32, false=0, true=1 |

The installed plain Task attribute descriptions agree on these widths from
revision 2 onward. Task Inhibit occupies four bytes; the separately implemented
[Program Disable field](edit-program-state.md) occupies one byte. Single and
list reads use identical values and preserve requested order and duplicates.
Missing or malformed settings remain unavailable without hiding valid sibling
settings. Measured runtime timing, compiled addresses, trigger formats, native handler
references and aggregate instance reads remain unsupported.

## Native identity binding

Source order never supplies a Task ID. The optional `NativeTasks` reader obtains
the controller-scoped logical path from the original ACD's bounded `Comps.Dat`
component records and matches it to complete ordinary Task names from the L5X.
It currently understands only component type 256, header version 0 and Task
format 18. The logical path must contain class `0x70`, a nonzero UINT16 instance
and zero child words. Free records, collection records and physical database
tails cannot supply an identity. Ambiguous historical records, duplicate names
or IDs, unsupported versions and malformed bounds withhold the inventory.

The immutable manifest binds both original ACD and exported L5X SHA-256 hashes.
Loading checks the complete ordinary Task name set and rejects conflicting ACD
bindings before replacing the active project. Native ACD import carries this
optional manifest; loading plain L5X clears it unless a matching manifest is
explicitly supplied. Missing Task identity support does not discard an otherwise
usable offline project.

The source settings reader also rejects context exports, duplicate or shadow
Task declarations and noncanonical fields. Explicit Safety and unknown Task
classes are withheld. Native ordinary exports that omit `Class` can retain
their explicit settings. The exposed inventory is limited to 32 ordinary Tasks.

## Scheduling and source times

The program list requires an explicit canonical schedule container and complete
ordinary Program declarations. It preserves source order, resolves every name
through the imported native Program catalog and requires matching ACD/L5X hashes
for both the Task and Program identities. Missing lists, incomplete bindings,
duplicate or dangling names, unsupported Program classes and conflicting Task
owners remain unavailable. An explicit empty container establishes an empty
list. No source ordering generates object IDs.

`TaskTiming` converts source milliseconds to microseconds with integer arithmetic.
It accepts only positive, exactly representable values within signed 32-bit
range, preserving fractional milliseconds without rounding. It never substitutes
a webpage scan interval, a period for a continuous task or an event timeout.
Missing or zero watchdogs remain unavailable rather than applying native defaults.
These are configuration reads, not native scheduling or watchdog enforcement.
The units agree with installed v35 help and Rockwell's
[Task object reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html).

Attribute 16 remains unavailable. The documented execution-instance range is
0–31; the nonzero CIP object ID alone does not establish that execution slot.

## Read services and limits

Task class instance 0 reports the partial model's revision-2 configuration
layout. Maximum instance and count describe the exposed source-bound ordinary
Tasks, using the shared UINT32 widths in Common ASA Classes 3 and 4. Counts remain unavailable
without an exact identity binding. Instance List (`0x4B`) returns the actual
source IDs with the existing bounded cursor/pagination contract.

These fields describe source settings; reading them does not change execution,
inhibit a task, switch controller mode or accept an online edit. Native setters
remain denied. The signed research endpoint uses the same read path as ordinary
explicit messaging.

A retained native edit trace requested Task attribute 19 after successfully
reading Program Disable. Offline replay and an independent signed TCP session
now return the exact four-byte setting for that source-correlated Task. No SDK
test was performed for this change. Native edit acceptance remains unresolved,
and SDK testing remains paused.

Version `.81` adds schedule and time reads, checked through focused source,
wire and independent inventory tests. These additional fields have no new SDK
acceptance result.
