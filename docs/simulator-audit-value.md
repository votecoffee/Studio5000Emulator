# Simulator Controller Audit Value

Version `.144` adds a simulator-owned Controller attribute 27, alongside
the [source configuration mask](controller-change-detection.md) in attribute 28.
Native SDK mode control and supported import/reconnect checks pass. The rebuilt
executable, appliance and webpage report `.144`. Full upload, download and the
complete edit lifecycle remain unfinished.

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
signature is generated. Controller audit/mask writes remain unsupported. Current [GSV reads](controller-gsv.md)
and [SSV Task InhibitTask](task-inhibition.md) have separate bounded profiles.

## Validation scope

Fifty-eight focused pure checks pass. They cover mask selection in both words, stable byte reads,
source mismatch, wrap/exhaustion, fault invalidation, detached candidates,
shared mode control, in-memory native mode/commit handlers, retransmission,
mixed reads and write rejection. They prohibit process, worker and network starts.
Controller fields 11/12/33/34 remain unavailable.

Twenty-two additional affected local mode/edit protocol checks pass. Frozen
executable checks exercise the configuration parser and runtime audit model;
all 98 application modules match between source, build manifest and appliance.
The executable's file/product versions, packaged assets and served webpage
version agree.

The normal-protocol SDK mode trial passes Go Online/Offline across 108 verified
signed requests. Two SDK Run/Program cycles and one web Run/Program cycle produce
exactly six audit updates; repeated Run retains its existing value. The supported
Program-mode NOP import and reconnect pass across 181 verified requests and
produce exactly one update. Original source files remain unchanged.

The isolated empty-Program upload comparison returns both eight-byte fields
27/28 successfully. Its 21-field Controller read now has four unsupported fields
(11/12/33/34), compared with six in `.142`. The SDK still reports
`RxCsE_ASA_ATTRIBUTE_LIST_ERROR` across 361 verified requests and 364 expanded
leaves. This trial uses the earlier private clock/schema/repository/Task-stack
hypotheses to reach that collection; they remain excluded from the app.

The independent normal-protocol download still fails at its preparation-result
reply across 175 verified requests. It preserves the active model and audit
value. All four SDK trials confirm actual Offline, endpoint cleanup and original
source preservation, with no reported SDK server fault. The temporary controller
is stopped after comparison. These results establish the bounded behaviors
above, not a completed native transfer or Studio GUI monitoring acceptance.
