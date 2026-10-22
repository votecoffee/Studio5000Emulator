# Simulator Controller Audit Value

Source revision `.144` adds a simulator-owned Controller attribute 27, alongside
the [source configuration mask](controller-change-detection.md) in attribute 28.
Native SDK acceptance, executable rebuild and restart are pending. The last
native-validated build remains `.142`; this change establishes no new completed
upload, download or edit lifecycle.

Rockwell describes AuditValue as a runtime value generated on project download
or storage load and updated for selected events. Mask bit 13 selects remote mode
changes; bits 2 and 32 cover transaction commits and correlation changes.
See [1756-PM015, Change detection, pages 48–52](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf).
The implementation below defines this simulator's value generation and supported
events; it does not reconstruct the vendor's generation algorithm.

## Lifetime and events

An installed execution model with an explicit supported ChangesToDetect mask
starts a random 64-bit epoch. Loading, resetting or reconfiguring the execution
model starts another epoch. Ordinary reads return the same eight little-endian
bytes. A missing or unsupported mask leaves the audit value unavailable.

| Operation | Simulator behavior |
| --- | --- |
| Successful requested Program/Run transition | Updates once when bit 13 is selected |
| Repeated same-mode request or scan-interval adjustment | No update |
| Accepted supported Program-mode routine transaction | Updates once if bit 2 or 32 is selected |
| Detached candidate preparation, rejected operation or repeated commit | No update |
| Ordinary scans, tag writes, metadata reads or prescan | No update |
| Internal scan stop, shutdown or preparation stop | Does not create a remote-mode event |
| Unclassified interpreter fault | Withholds the audit value until a new execution model is installed |

The HTTP mode control and native mode handler call the same mode service.
Routine replacement copies the existing epoch into its detached candidate;
only publication of the accepted candidate records the transaction. A retry of
an already applied transaction retains the same value. Rejected work cannot
advance the original model's epoch.

Each selected event advances the simulator sequence modulo 64 bits, with a
separate update count preventing reuse within an epoch. Exhaustion withholds
the value. A zero source mask still creates the initial epoch but selects no
events. Reserved mask bits are preserved and acquire no event behavior.

An interpreter fault has no established native major/minor classification.
The model therefore invalidates its audit value without inventing a major-fault
event. Clearing the error string or executing a later successful scan does not
restore the invalidated value. Reset creates a new execution-model epoch.

## Reads and diagnostics

The Controller route combines static source settings with the source-bound
runtime value. Single and ordered attribute-list reads, including repeated
fields, use the current epoch. Attribute writes retain their existing rejection.
An audit object bound to a different source digest supplies no value.

Endpoint state adds `controller_change_detection`: availability, invalidation,
supported event bits, update count and simulator provenance. It omits the value,
mask, source digest and source contents. Static `controller_configuration`
continues to describe source settings only. No archived controller audit value
is imported, and no event log, physical memory percentage or State Detection
signature is generated. Configuration writes and GSV/SSV remain unsupported.

## Validation scope

Fifty-eight focused pure checks pass. They cover mask selection in both words, stable byte reads,
source mismatch, wrap/exhaustion, fault invalidation, detached candidates,
shared mode control, in-memory native mode/commit handlers, retransmission,
mixed reads and write rejection. They prohibit process, worker and network starts.
Controller fields 11/12/33/34 remain unavailable in the source model. The last
native upload comparison on `.142` still retains its six reported missing
Controller fields; no source-only result is substituted for that observation.
