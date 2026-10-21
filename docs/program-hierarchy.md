# Program Task owners and logical children

Version `.118` adds three read-only Program fields used by native upload.
They describe complete, canonical ordinary v35 source and matching original
identities. They do not change execution or allocate compiled addresses.

| Attribute | Encoding | Available value |
| --- | --- | --- |
| 9, Fault Routine | Four-byte null ACADDR | No configured fault routine in proven complete source |
| 13, Task Instance | UDINT | Original native ID of the unique source Task owner; zero for proven unscheduled Programs |
| 32, Child Program List | UINT count followed by UDINT IDs | Source-ordered logical children bound to original Program IDs |

The installed v35 Program definition establishes these field layouts. In the
saved successful upload, all 20 Program fault references and child lists are
empty. Nineteen Program Task IDs match their membership in the two returned
Task schedules; the remaining zero Task ID belongs to the one Program absent
from both schedules. Recorded IDs and addresses are not replayed.

## Complete source and original identities

The [ordinary Program kind reader](edit-program-state.md#program-kind-and-original-instance)
first establishes the supported declaration form. A missing or empty
`FaultRoutineName` can then supply a null reference. Configured routine names,
aliases, unknown kind settings and opaque declarations cannot become null.
Nonzero handler references and fault-handler execution remain unavailable.

Task ownership is the inverse of the complete [source Task schedules](task-metadata.md).
All Task declarations must be supported and every schedule must be explicit,
canonical and unambiguous before an owner or an unscheduled zero is available.
A missing list, duplicate owner, unknown target or unsupported Task prevents
this read. Native Task and Program catalogs must match the loaded source pair
and original project identity; source order never supplies a guessed ID.

Logical children come from `ChildPrograms/ChildProgram@Name`. Rockwell's
[Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
describes this as the Logical Organizer relationship, separate from Task
scheduling. A complete ordinary export with no child container establishes an
empty logical list. Unknown/context/namespaced/nested declarations, opaque text,
dangling targets, duplicate children, multiple parents and cycles withhold the
child inventory. The reader permits up to 4,096 Programs and 1,000 children per
parent; graph validation handles deep forests without recursive traversal.

Child order is preserved. The same-source native Program map must cover the
complete graph with distinct positive IDs, even for an empty returned list.
Changing source hashes or supplying foreign, partial or ambiguous bindings
returns unavailable. The graph and Task ownership snapshots are immutable.
API metadata reports aggregate availability under `program_hierarchy` and
`task_configuration`, without exposing private names or ID maps.

## Validation and remaining gaps

The before/after SDK upload comparisons use the same disposable complete-clock
experiment described in the [Program kind investigation](edit-program-state.md#program-kind-and-original-instance).
Both verify 202 signed requests and still fail `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`.
The three new fields change from unavailable to successful reads; unavailable
fields in the 22-field Program list fall from 15 to 12. This does not identify
an individual failure cause or establish a completed Program upload.

A separate unpatched public-source candidate still fails Controller collection
across 196 verified requests. All three comparisons confirm native Offline,
endpoint cleanup and unchanged source/model without a reported fatal SDK fault.
Generated clock datasets and substituted class revisions remain unshipped.

Focused checks cover empty and nonempty ordered child lists, deep forests,
cycles, conflicting parents, source/identity mismatches, configured handlers,
Task ownership and signed read/write boundaries. All 178 focused tests and 21
live reads pass. The restarted `.118` runtime separately completes SDK Go
Online/Go Offline with 75 verified signed requests, clean Offline/cleanup,
unchanged source/model and no reported fatal SDK fault. The full suite is not
rerun for this iteration. Full native upload/download,
tag-address discovery and the complete online-edit lifecycle remain unfinished.
