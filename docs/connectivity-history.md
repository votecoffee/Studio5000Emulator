# Connectivity development history

These entries retain the validation scope at each revision. They describe
historical experiments and do not extend the current compatibility claims.
See the [README](../README.md) for current status and usage.

Version `.122` adds [runtime Program and main-Routine references](runtime-object-references.md).
Opaque aligned addresses resolve to live interpreter objects, remain separate
from logical IDs and are revoked on object replacement. The isolated native
upload accepts both fields; one synchronization setting remains unavailable in
its Program list. Complete upload still fails. The released clock profile is
unchanged; native GUI monitoring and full transfers remain unfinished.

Version `.74`
ties native mode requests and webpage controls to the same scan worker.
Version `.75` adds transactional Run-entry prescan and first-scan initialization.
Version `.76` adds [member inspection of temporary native type definitions](template-layout-inspection.md)
as groundwork for validating storage layouts; encoded offsets and trailers remain opaque.
Version `.77` [checks staged members against the original ACD type metadata](source-type-verification.md)
and rejects source/layout mismatches. Native storage mapping remains unfinished.
Version `.78` adds a [source-bound temporary download image](download-image.md),
coherent [software system time](upload-inventory.md), and an
[online-edit diagnostic](native-online-edits.md) that requests acceptance
of a generated NOP rung on a private project copy. Download now starts a real
temporary image, and online edits can acquire a separate exclusive reservation.
Subsequent transfer and edit operations remain incomplete.
Version `.79` adds the [Program Disabled read used by online imports](edit-program-state.md),
three more source-backed Controller settings and [per-record download results](download-image.md#per-operation-preparation-results).
An [isolated protocol probe](research-session-probe.md) exercises the actual
challenge and signed transfer paths independently of the optional native SDK.
Version `.80` adds [source-bound Task settings and native Task IDs](task-metadata.md),
an [SDK-independent upload inventory reader](upload-inventory-client.md) and an
[offline download capture comparison](download-replay.md).
Version `.81` extends Task metadata with ordered native Program links and exact
source period/watchdog reads. The independent inventory reader checks those
Task-to-Program relationships without using the native SDK.
Version `.82` adds [Program-scoped native Routine inventory](executable-metadata.md),
including original ACD object IDs and a limited legacy description read.
The independent inventory reader preserves parent Programs when routine IDs overlap.
SDK testing has resumed: the rebuilt demo passes connection/Offline; its isolated
edit diagnostic returns an attribute-list error and confirms cleanup without a
reported fatal SDK exception.
Version `.83` adds the source-bound [overflow-reporting setting](controller-overflow-setting.md)
requested during native online import, and retains SDK import-log error codes
in diagnostic summaries. The isolated native import advances to a denied
controller operation. A separate local pending NOP import while online succeeds;
controller acceptance and active edits remain unavailable.
Version `.84` adds [Program preparation reservations](program-reservations.md)
and explicit typed SDK tag-read diagnostics. Accepted controller edits remain
unfinished.
Version `.85` models the observed Controller open/close preparation sequence
with Run inhibition and a source-checked zero UDI-stack proposal for complete
projects without AOIs. The independent inventory reader also reads this
modeled zero stack. Active edit storage and controller acceptance remain unfinished.
The `.85` native edit probe passes this preparation and reaches a compiled
Routine fragment, which is still rejected by the transfer receiver.
Version `.86` adds [compiled Routine fragment staging](edit-transfer.md)
under the edit reservation, with source-bound targets and bounded temporary
storage. Complete binaries remain separate from active routines; installation
and accepted controller edits are unfinished.
The native edit diagnostic now delivers all 11 compiled fragments before that
installation rejection; endpoint storage clears and active logic is unchanged.
Version `.87` receives the following [compressed Routine source](routine-source.md),
resolves supported native object references using original ACD identities, and
checks translated ladder logic in a detached execution plan. It retains both
containers temporarily; applying source and accepted edits remain unfinished.
Version `.88` acknowledges validated source storage and retains the following
[post-source record](edit-post-source.md). Its signed transfer parser keeps
the native session alive through the next unsupported operation, allowing
the edit diagnostic to complete Go Offline. Active edit completion remains unfinished.
Version `.89` adds [supported Program-mode routine edits](supported-routine-edits.md).
A native SDK rung import now replaces the translated routine in the execution
model; the inserted instruction executes on the next scan. The webpage exposes
edit access and an in-memory logic revision. Original ACD/L5X files are preserved.
The `.89` Windows milestone runs 1,263 tests successfully with two platform skips.
Version `.90` verifies two accepted rung imports in the same SDK project, both
while remaining online and with Offline/Online between imports. Both edits
remain active and execute on the next scan; the logic revision advances twice.
The [native diagnostic](development.md#native-sdk-acceptance-probe) checks
each intermediate routine and reconnection against the expected logic.
Version `.91` adds scoped metadata retention needed by native rung replacement
and verifies replacements in two routines with reconnects. **Save edited L5X**
now saves a separate [working copy of edited logic](edited-logic-l5x.md)
with original imported tag initial values. That copy reloads and executes in
the emulator.
Version `.92` verifies a replacement followed by an insertion in the same
routine, with reconnects. The optional native diagnostic imports the exported
L5X, saves a new edited ACD, reopens it and checks the re-exported logic and
initial values. That new ACD also passes a fresh SDK Go Online/Offline connection
to an emulator loaded from the saved project. Studio GUI acceptance remains
unverified.
Version `.93` resolves source-bound tag/member references inside native CPT
expressions. A CPT import followed by conditional arithmetic passes SDK
reconnects and executes with queued external inputs. The edited L5X reloads
and reproduces the tested results. See the
[expression reference profile](routine-source.md#cpt-expression-references).
Version `.94` adds source-bound CMP expressions and static array operands.
Native imports reconnect and execute comparisons, indexed reads and indexed
destinations; saved L5X copies reproduce the results. Unsupported decoded logic
is rejected by a signed edit operation while preserving native Offline cleanup.
Version `.95` adds checked integer-bit operands to native imports, including
array elements. Reconnects, scan-boundary external writes and saved L5X reloads
pass. Controller references that would bind to a shadowing Program tag are
rejected. Download diagnostics now distinguish a prepared image's unsupported
result encoding from a general write-policy rejection.
Version `.96` adds [checkpointed native transfer reports](native-transfer-diagnostics.md)
for upload/download investigations, plus an offline report reader. Reports
separate object errors, fragment acknowledgements and temporary preparation
state; they preserve the distinction between protocol observations and SDK success.
Version `.97` retains complete native transfer packets within a bounded trace
ring, allowing the offline reader to check large download fragments. Capture
limits and evictions are exposed in diagnostic state. It also adds
[source-bound indirect array indices](routine-source.md#indirect-array-indices)
to supported native imports. Indexed reads and CPT destinations pass reconnect,
execution, queued external input and saved L5X reload checks.
Version `.98` adds source-bound
[indirect integer-bit operands](routine-source.md#indirect-integer-bit-operands)
to native imports and the corresponding typed CMP condition syntax. Index
references remain live, with type checks and bounds faults at execution.
Version `.99` adds bounded [atomic-array Data Table storage](atomic-array-storage.md).
Native upload now reads the tested array's descriptors and values, advancing
beyond its previous missing-storage error. Full upload and SDK tag-address
discovery remain unfinished.
Version `.100` adds [structured Data Table storage](structured-storage.md)
using the existing symbolic UDT layouts, with real network readback and queued
external member writes. Native UDT upload stops at earlier Template metadata;
native tag monitoring and full upload/download remain unfinished.
Version `.101` adds [source-known Template family metadata and aligned definition reads](template-metadata.md).
Independent signed TCP checks pass. A fresh native Go Online/Go Offline test
passes after SDK service recovery; the previously faulting metadata overrides
remain excluded.
Version `.102` extends the [SDK-free inventory reader](upload-inventory-client.md)
with bounded Template definitions, multidimensional atomic arrays and raw UDT
value bytes. Malformed replies stop decoding and release the reader's connection.
The independent reader does not require the SDK.
Version `.103` adds an [isolated signed routine-edit probe](research-session-probe.md#supported-routine-replacement)
that checks commit ordering, reconnection, next-scan execution and edited L5X
reload alongside inventory and temporary-download checks, without the SDK.
Version `.104` adds [source-bound AOI definition discovery and metadata reads](aoi-metadata.md),
including original ACD IDs, clean model state, revisions and readable vendor
headers. Protected payloads remain opaque and do not gain a clean-state value.
Version `.105` adds [AOI-scoped Routine discovery](aoi-metadata.md#aoi-scoped-routines)
with original child IDs, sparse pagination and available source descriptions.
AOI and Program parent IDs remain separate throughout imports, inventory and
diagnostics. Protected Routine inventories remain unavailable.
Version `.106` adds [source identity checks for downloaded objects](source-object-identities.md).
Program/Routine IDs and known Symbol IDs must match their source scopes before
temporary objects are published; additional internal Symbols remain unresolved.
Version `.107` adds [source-bound auxiliary Symbol identities](source-object-identities.md#auxiliary-symbol-identities).
Original component records resolve Symbols omitted by TagInfo during download
checks, while their runtime tags, values and alias behavior remain unavailable.
Version `.108` adds [original Data Table identity checks](source-object-identities.md#data-table-identities).
Staged Table IDs must match the source inventory before temporary download
objects are published; native addresses and storage/value decoding remain unfinished.
Version `.109` adds [original Template ID checks](source-type-verification.md#original-template-identities).
Known IDs must match even when a transfer consistently renumbers nested types;
cached source metadata changes also reject temporary processing and result queries.
Version `.110` includes [source identity results in transfer diagnostics](native-transfer-diagnostics.md#source-verification-results).
A fresh native download matches all 242 Template IDs, 20 Symbol IDs and 16 Table
IDs in the original demo before reaching the unfinished result-response step.
The limited Program-mode accepted-rung SDK import also passes on an isolated
controller, with native Offline and source preservation confirmed.
Version `.111` adds [null Controller handler and aggregate reads](controller-handlers.md)
from a successful v35 reference upload. Configured handler references remain
unavailable; successful object replies still do not complete native upload.
Version `.112` improves [offline capture analysis](development.md#offline-cip-capture-inspection)
for complete upload recordings and decodes bounded Time Sync attribute lists,
including partial replies and vendor descriptions. Revision-only SDK experiments
still fail upload; their substituted revisions are not shipped.
Version `.113` adds optional [source-bound native Template snapshots](native-template-snapshots.md).
Supported structures can retain their original IDs, handles and complete saved
definitions while values remain in software memory. An isolated SDK case
advances to tag upload without a reported fatal fault; full transfers remain unfinished.
Version `.114` adds [source-checked empty Energy discovery](connectivity.md#empty-energy-discovery-for-ordinary-user-types)
for ordinary user types and the newer Base/Electrical discovery request. The
isolated structured-project SDK upload passes Controller tag collection and
reaches device/extended-device/memory collection, where it still fails.
Version `.115` adds [field-level collection diagnostics](native-transfer-diagnostics.md#collection-attribute-lists)
to native transfer reports and offline capture analysis. Valid field layouts,
unavailable attributes and undecoded layouts are reported separately. An isolated
complete-clock experiment still fails device collection and is not shipped.
Version `.116` adds [supplemental schema discovery and read-only Wall Clock Time](controller-schema-discovery.md).
The clock distinguishes legacy 1972 counters from UTC 1970 counters and checks
source settings before serving legacy local values. SDK schema queries succeed;
complete upload still fails during device collection.
Version `.117` adds [source-checked Program kind and original instance reads](edit-program-state.md#program-kind-and-original-instance)
and Program collection diagnostics. A disposable complete-clock experiment
reaches Program collection; its generated clock settings remain unshipped.
Version `.118` adds [Program Task owners, logical children and null fault references](program-hierarchy.md).
The isolated upload accepts these three fields, while full transfer remains unfinished.
Version `.119` adds [measured Program scan durations and source scheduling/synchronization flags](program-timing-and-flags.md).
Program timings track successful emulator scans and roll back on a failed scan;
programs used as folders cannot execute. The isolated upload comparison accepts
three more Program fields; full native transfer remains unfinished.

Version `.120` adds [Program output/edit diagnostics and model fault records](program-diagnostics.md).
The isolated upload comparison accepts four more fields, reducing unavailable
Program fields from 9 to 5. Untested-edit reads require idle native edit staging;
unknown fault history remains unavailable until reset. Full transfer remains
unfinished.

Version `.121` adds [Standard memory reads and bounded normal Program status](program-memory-status.md).
Program and Task Data Use remain distinct from execution status; normal status
requires source/native ownership and known-clean supported execution. Offline
diagnostics also frame Task collections without exposing values by default.
