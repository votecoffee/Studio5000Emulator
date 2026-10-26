# Program-scoped download tables

Version `26.1026.121058` retains Program identity when handling source and
temporary download Data Tables. Controller and Program tables can reuse the
same instance number. Their identities, Symbol links, model addresses and
incremental values must remain separate.

## Source binding

The bounded format-38 ACD inventory now reads ordinary Data Table records
under an explicit Program collection as well as the Controller collection.
Names and instance IDs are unique within their scope. A duplicate historical
identity, missing collection, unsupported body format or unknown Program
parent rejects the binding. Body bytes remain opaque; their length supplies
profile metadata only.

Controller manifest entries keep their existing fields. A Program entry also
contains `program_instance`, referring to the original source's Program
catalog. The ACD and complete L5X hashes must match the other source bindings.
Import does not expose native storage, infer addresses or grant programming
access.

## Temporary transfer storage

The observed first download batch creates reciprocal Symbols and Data Tables
within each reserved Program. Preparation checks every link in that scope,
including when another Program or the Controller has the same numeric IDs.
Each retained table receives a distinct model handle and value allocation.
Discovery pages select one Program; they do not mix tables from other scopes.

Later whole-table writes require the owning Program reservation. Source
headers retain the complete Program/Table reference. Initial-value preparation
and exact scalar Online reads use the same scoped binding. The effect ledger
checks the parent as well as the instance, so changing a link to another
Program cannot pass merely because its Table ID matches.

These are temporary software-model allocations. Arbitrary address ranges,
native host memory, unknown scopes and general project replacement remain
unavailable.

## Validation

Focused tests cover repeated IDs/names across scopes, missing or mismatched
parents, reciprocal links, unique handles and value addresses, independent
incremental values, reservations and cross-Program effect corruption.

A source-authored native fixture has two Programs, twenty tag roots and four
RLL routines containing thirteen rungs. Six roots are Program-local, including
duplicate local names, a constant and an array. Native Offline import, ACD
save/reopen and full export preserve its values and logic without connecting
to a controller.

The initial native download on the preceding build rejects scoped Symbol
storage after 173 verified requests, with normal Offline cleanup and no SDK
fault. Its complete recording supplies 924 preparation records. Offline
validation of those records now matches all 22 source table identities,
including six scoped tables, and all retained preparation effects. Offline
inspection does not independently reauthenticate recorded MACs or establish
a completed native transfer.

On that build, the complete two-Program download/save/reopen/Online succeeds
across 438 verified requests. Native Table pages contain sixteen Controller
tables and four/two tables in the separate Programs. All 22 model handles and
value addresses are distinct. Offline cleanup, source/model preservation and
no SDK fault are confirmed. The complete 1,768-event recording replays
identically offline.

The subsequent upload stops after 279 requests when it reaches a local DINT
constant: its basic type is available, but its storage fields return `0x14`.
The SDK reports Program upload failure and returns Offline without a fault.
Temporary local values are restored. Version `26.1026.122552` adds the narrow
[installed constant read profile](installed-memory-reads.md) needed at this
boundary; general constant storage and writes remain unavailable.

The constant follow-up passes 341 affected checks. The full software milestone
passes 2,141 tests with two platform checks skipped; all 367 Python files parse.
Software checks remain separate from the native transfer results above.

## Native snapshot checkpoint: `26.1026.122552`

The same two-Program profile completes download/save/reopen/Online across 434
verified requests. Five temporary writes then change the two Programs' local
DINTs and BOOLs independently, plus an array element. Upload snapshot/save/
reopen/Online succeeds across 1,188 requests. All twenty roots (71 bytes),
four routines and thirteen rungs match in the uploaded SDK project and the
saved full L5X. Both native Program exports independently verify all six
local roots.

Typed Online getters verify eleven BOOLs and five DINTs, including distinct
changed values for the duplicate local names. The constant retains its value
`1000` and its constant flag. Independent recorded-response inspection confirms
all seven constant Data Table fields and its four-byte value read. Original
source, installed correlation and model state are preserved; all temporary
values are restored without scanning. Native Offline cleanup and no SDK fault
are confirmed.

Complete 1,751/4,418-event download/snapshot recordings replay identically
offline. MACs are not independently reauthenticated by replay. This is the
unchanged-source [value snapshot profile](upload-value-snapshots.md); direct
saving of a reconstructed upload and general Studio GUI acceptance remain
unfinished.
