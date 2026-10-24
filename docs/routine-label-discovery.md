# Routine Label discovery

Version `26.1024.091940` adds bounded empty Label (`0x8C`) discovery under a
numeric Program (`0x68`) and Routine (`0x6D`). The complete three-object path
retains both parent IDs. Repeated, incomplete, symbolic and foreign scope chains
cannot flatten into a different object. Native rejection summaries retain the
Routine parent separately.

## Source and request profile

The native compatibility profile exposes the observed Label class revision `1`
for the v35 controller layout. A class revision describes a schema; it does not
provide a global inventory, Label instances or label-address attributes.

Only service `0x4B`, child cursor zero and an empty request body can read the
empty Routine Label catalog. Discovery requires matching Project, Program and
Routine identities, the original ordinary RLL Type profile, complete unchanged
readable source, idle native edits and clean simulator state. The routine's
complete parsed instruction tree must contain neither `LBL` nor `JMP`.
This proof applies to unscheduled routines too; it does not depend on the
interpreter's cache of labels for scheduled code.

Actual labels, incomplete source, changed logic, stale bindings, unknown
parents and uncertain faults remain errors. A successful empty list never
stands in for an unsupported nonempty inventory. Label reads, writes, IDs and
native code addresses are not synthesized. No scan or model value changes.

## Evidence and upload progress

The installed v35 object definition identifies class `0x8C` as Label. A retained
successful upload contains 708 Program/Routine Label queries: 622 return empty
lists and 86 contain objects. Seven class-revision reads return revision `1`.
These observations establish the narrow request and response layouts, without
independent MAC verification or association with an original ACD.

The preceding `26.1024.085425` native upload reads both original
[scoped Routine Symbols](routine-reference-symbols.md) and completes one signed
Routine-data read, returning the 13-byte metadata component for the first
Routine. It then sends the nested Label-list request, which that build rejects
as an invalid path. The SDK reports Program upload failure after 353 verified
requests, with source/model/installation preserved, actual Offline cleanup and
no SDK fault. Its complete 1,442-event recording replays identically using the
decoder available at that checkpoint. That is a confirmed change from the
earlier failure before Routine-data retrieval.

The new profile implements the source-checked empty case. Software checks cover
class revision, all three scopes, actual labels, unscheduled routines, stale
or modified source, rejected payloads/services and signed TCP requests. Native
upload acceptance is verified separately from these software checks.
