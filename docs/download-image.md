# Temporary download image

The native download path can now materialize a separate device image after
decoding the entire compressed batch and checking its supported descriptors
against source metadata. This gives subsequent transfer work real temporary
objects and storage to inspect. The active controller project remains separate.

## Prepared objects

An image retains the temporary Template definitions, diagnostic descriptors,
Program and Routine identifiers, Symbol references and Data Table descriptions.
It allocates each Data Table's declared byte count in a bounded temporary
namespace. Controller Symbols with reciprocal table links can read those bytes;
unbound Program or controller Symbols report that storage is unresolved.

The allocated bytes initially contain zero. They are allocation state, and do
not represent transferred tag initial values. Routine creation records contain
identifiers only, without executable bodies. Template trailers, family/revision
fields and other retained metadata do not execute as binary code.

Preparation requires:

- Every batch record belongs to an explicitly supported Create, attribute,
  Template write or Program coordination operation, and every record is covered
  by the corresponding descriptor model.
- All cross-object references, bounds and balanced Program coordination pass.
- Every staged Template's type/member structure matches the original ACD's
  metadata, bound to both the original ACD and converted L5X SHA-256 hashes.

An unknown operation, an incomplete descriptor, an unmatched type or missing
source binding cannot publish an image. Allocation is bounded to one MiB per
image and occurs after these checks. A SHA-256 digest identifies the exact
ordered record stream.

## Readback and lifecycle

`DownloadImage.read_table` and `read_symbol` provide readback from the temporary
cells, requiring the matching pair of source hashes for each call. Reads stay
inside one table and at most 16 KiB per request. `attribute` provides exact-width
typed bytes for supported Template, Data Table and Symbol descriptor fields.
Names and compiled or physical addresses absent from these records remain
unavailable.

The programming lease owns the image. Fragment reset, absolute assembly expiry,
transport deletion and lease cleanup discard it together with the decoded
objects. Successful inspection is cached for the same native source catalog;
changing the catalog cannot reuse an existing prepared image.

`ResilientTransport.start_prepared_image()` records the simulator's temporary
preparation transition only after complete inspection, source-bound allocation
and full record coverage. It pins both source hashes, the source catalog and
the ordered record digest. Repeating Start on that exact image is idempotent;
changing its source or record digest cannot reuse the transition. Cleanup also
clears `preparation_started`.

Status exposes counts, limits, a record digest and readiness. It omits source
hashes, identifiers, definition bytes, names and cell contents.

## Per-operation preparation results

Each prepared image now retains an immutable result for every record, in the
original order. A result includes its ordinal, service, object scope, exact
request length and SHA-256 digest, together with a typed simulator outcome:

- Template creation capacity, retained attributes and each written definition
  slice's offset, byte count and digest.
- Diagnostic revision, string lengths and digests.
- Symbol table reference, table type/dimensions/allocation, Program identity
  retention and Routine creation word.
- The before/after hold state for each balanced Program coordination operation.

`preparation_results` reads at most 64 records per page and requires the original
source-hash pair and matching record-stream digest. The result tuples, outcomes
and operation counts are immutable. These detailed reads are private Python
interfaces; HTTP and native protocol responses expose aggregate counts only.

`read_preparation_effect` reads the current temporary resource and compares it
with its retained outcome. A changed Template slice, descriptor or allocation
therefore produces a failed comparison. Coordination outcomes describe retained
historical transitions, explicitly marked as such; they do not claim the Program
remains held after the balanced release. `read_template` provides bounded byte
readback for independently checking definition-write digests.

The result ledger is built atomically before publication. It checks retained
resources against the original operation payloads, so a descriptor model that
disagrees with a Create, attribute or Write request cannot produce a prepared
image. Start requires a complete matching ledger. Repeated Start reuses it;
fragment reset, deletion, expiry and lease cleanup discard it with the image.

The owned 904-record replay produces 242 Template creation results, 242 attribute
results, 243 definition-write results and 177 other object/coordination results.
All request fingerprints and resource comparisons pass, including 243 separately
verified definition slices and the two retained coordination transitions. This
is offline preparation evidence. It supplies real outcomes for a future result
encoder without assigning a vendor status or guessing a wire layout.

## Completed-batch execution status

Version `26.1023.075900` implements the seven-byte result-query profile observed
in a user-performed successful v35 download. Across 17 batches, all 204 replies
have a one-byte state, a little-endian UDINT processed-byte count and a zero
trailing UINT. State `6` precedes completion; state `0` completes every batch
with a count equal to its announced expanded byte length. Counts stay bounded
and monotonic within each batch. The trailing word's wider semantics and other
state values remain unresolved. The capture's MACs have not been authenticated;
native SDK acceptance is a separate validation step.

The simulator prepares a supported temporary batch synchronously. Its signed
`0x412/0x4D` query can therefore return state `0`, that batch's expanded byte count
and the supported zero trailing word. It first rechecks the original lease,
source/type/object bindings, started image, ordered result ledger and full byte
coverage. Every retained operation effect must still match its actual temporary
resource. An unstarted, expired, incomplete, rebound or changed image remains
an error. Queries do not manufacture a processing delay or replay captured bytes.

This completion applies to modeled temporary operations. The per-operation
ledger remains a private typed interface, with no native per-record result
encoding. Active-project commit, compiled execution and transfer of tag initial
values are separate capabilities.

The tests cover exact encoding/decoding, progress bounds, unsupported states and
trailing words, false completion, source/expiry checks, changed resource readback
and signed replies without active-image changes. The source capture, controller
identities, project and decoded payloads remain outside public Git.

## Completed download Symbol catalog

Version `26.1023.082234` retains a completed image's Symbol handles for the
owning prepared programming lease after transport deletion. The source-checked
set includes internal Symbols and ordinary tags absent from the interpreter's
runtime browser. The observed Symbol enumeration (`0x55`, attribute 5) returns
sorted instance/handle pairs with negotiated reply limits and continuation.

Each handle resolves to its retained temporary Symbol and table reference.
These are model object handles; firmware descriptor bytes, physical addresses
and raw memory access are not inferred. Original ACD/L5X, current type/object
catalogs and operation effects must remain bound. Source changes reject reads.
Other clients continue to browse the active runtime catalog. End preparation,
release, disconnect, expiry, reset and invalid authentication discard the
temporary namespace. An incomplete or unreported batch does not retain it.
Multiple completed batches and active-project commit remain unsupported.

Version `26.1023.083349` also serves the observed Data Table enumeration (`0x55`,
attributes 3 and 7). Each 12-byte row contains the table instance, a model
descriptor handle and its temporary value address. The descriptor resolves to
the retained typed table, while bounded internal value reads resolve only
inside its allocated region. Gaps, cross-table reads and descriptor interiors
are unavailable. The native SDK's preceding query establishes the requested
fields; the successful reference capture independently contains 17 exchanges
with this row layout. This adds no raw-memory wire service or tag-value writes.

On `26.1023.083349`, native SDK download accepts 18 controller Symbols, all 16
table rows and both Program-scoped Symbols. Its next request enumerates Routine
attribute 8 within that Program (`0x6D`, service `0x55`); that operation remains
unsupported. The SDK advances to `RxCsE_DOWNLOAD_OF_PROGRAMS_FAILED` after 179
verified signed requests. The original source and active model are unchanged,
SDK Offline and endpoint cleanup succeed, and no SDK fault is reported. Passing
these descriptor queries does not establish transfer of initial values or code.
The same build retains the normal upload boundary after 349 verified requests.
Two Program-mode SDK FinalizeEdits imports and reconnects pass across 299
requests, with one later model scan executing both changes. All 236 focused
checks pass; source, executable, browser assets and all 105 guest modules match.

The `26.1023.082234` native test accepts the complete set of 18 controller
Symbols, then requests the Data Table fields above. It reaches 180 verified
requests before `RxCsE_DOWNLOAD_OF_TAGS_FAILED`. Original source and active model
remain unchanged, and native Offline/cleanup succeed without a reported SDK
fault. Normal upload retains its separate Program collection failure after
349 verified requests. Two Program-mode FinalizeEdits imports, reconnects and
subsequent custom-model execution pass across 298 verified requests.

The preceding `26.1023.075900` native download test accepts the seven-byte
completion reply and advances beyond `RxCsE_DOWNLOAD_OF_DEVICES_FAILED` to
`RxCsE_DOWNLOAD_OF_TAGS_FAILED`. It verifies 176 signed requests, preserves
source/model and confirms actual SDK Offline and endpoint cleanup without a
reported SDK fault. Its next query requests Symbol attribute 5. This progress
does not establish complete tag transfer or a successful native download.

## Completed Program and Routine catalogs

Version `26.1023.085003` extends the retained temporary namespace with Routine
header enumeration (class `0x6D`, service `0x55`, attribute 8) and Program header
enumeration (class `0x68`, service `0x55`, attribute 16). The observed profiles
return eight-byte instance/header pairs. Routine requests require the original
Program parent; controller-scoped and AOI-scoped Routine requests remain
unsupported by this temporary-image profile.

Each header handle resolves to a retained typed object or Program identity,
with the same source, catalog, operation-effect and owning-lease checks as
Symbols and tables. It is a model reference rather than physical memory or a
compiled code entry point. Enumerations preserve instance ordering, reply
budgets and continuation, including equal Routine IDs in different Programs.
Cleanup drops all four catalogs together. Other clients continue to use the
active runtime catalog. No compiled code, initial values or active project are
installed by these reads.

The native `26.1023.085003` download accepts both Routine headers and the one
Program header, then requests I/O Map instance 1 attributes 9, 10 and 13. The
canonical Local route supplies field 10; fields 9 and 13 remain unavailable.
The SDK reports `RxCsE_DOWNLOAD_OF_DEVICES_FAILED` at this later device-metadata
query after 183 verified requests. This is beyond the earlier Routine
enumeration rejection. The reference capture includes a successful reply for
that query, but its remaining fields require source/schema backing before
implementation; class-level force status is a separate contract.

Original source and active model are preserved; actual SDK Offline and endpoint
cleanup succeed without a reported SDK fault. Normal upload retains its
Program collection failure after 349 requests. A supported Program-mode
import/reconnect passes across 190 requests, with one expected logic/audit
update. The original stopped zero-scan/audit demo is restored afterward. All
117 affected checks pass, and all 105 deployed modules and delivery versions
match. These trials do not establish complete native transfers.

## Additional batch reception

Version `26.1023.093633` accepts another Resilient Transport setup after the
owning client has completed and deleted its first transport. Its retained
namespace must still validate against the current source, type catalog,
object catalogs and original operation effects. The same checks precede each
follow-on fragment and inspection. Normal lease preparation, authenticated
message counters, contiguous offsets, finite buffer/fragment limits and
assembly deadlines still apply.

The new compressed batch has its own structural inspection cache. Inspection
decodes bounded records and reports aggregate service/class counts without
exposing their contents or bypassing the first batch's source-verifying
model builders. Both Start and execution-status queries explicitly reject
`incremental_download_processing_unimplemented` after successful structural
inspection. Invalid or incomplete input remains an error. Neither query starts
an image, marks results complete, executes records or changes the active model.

Transport deletion, invalid fragments and assembly expiry clear the new buffer
while retaining the previously completed namespace and its stable handles.
End preparation, lease release/expiry, disconnect, bad authentication and
project reset retain the existing whole-lease cleanup rules. Applying later
records and reporting their actual effects remain required implementation work.

The native SDK trial receives both complete batches: 371,787 expanded bytes
with 904 records in the first, then 190,318 bytes with 335 records in the second.
Its latter batch contains these structurally decoded operations:

| Service | Class | Records |
| --- | --- | --- |
| Set Attribute List (`0x04`) | Program `0x68` | 1 |
| Set Attribute List (`0x04`) | I/O Map `0x69` | 1 |
| Set Attribute List (`0x04`) | Symbol `0x6B` | 20 |
| Set Attribute List (`0x04`) | Routine `0x6D` | 2 |
| Set Attribute List (`0x04`) | Diagnostic Message `0x3B2` | 136 |
| `0x33` | Message Router `0x02` | 2 |
| `0x4B` / `0x4C` | Program-scoped `0x74` | 1 each |
| `0x4F` | Metadata `0x349` | 167 |
| `0x50` | Data Table `0x6A` | 4 |

These counts identify the work ahead; decoding their framing does not validate
or apply the operations. Start receives the explicit processing rejection and
download still reports `RxCsE_DOWNLOAD_2ND_PASS_AXIS` after 193 verified requests.
The active model and original files remain unchanged, actual Offline/cleanup
is confirmed, and no SDK fault is reported. All 150 affected checks pass.

## Isolated second-batch effects

Version `26.1023.095449` builds a separate pending proposal for supported
operations in the later batch. Unknown operations produce an explicit partial
coverage report. A malformed known operation, foreign source, missing object,
duplicate value/write or incomplete coordination discards the whole proposal.
The completed base image remains unchanged in every case.

Metadata `0x4F` packets use a shared bounded value decoder. A nonzero path
instance supplies one definition; instance zero contains a counted list of
locale/definition pairs for the same target. Strings, numeric data and named
references use the existing upload value framing. Each target, locale,
definition and complete typed value must exactly match the original ACD
metadata catalog, bound to the same ACD/L5X pair. Source record words are not
copied into invented controller identities. Stored target words and reference
words remain metadata; this does not resolve them to executable objects.

Only the observed complete whole-table `0x50` write profile is supported:
zero offset, zero selector, an exact UINT byte count matching the retained
table's full allocation, and exactly that many data bytes. The table must exist
in the source-checked completed image. These writes produce independent private
bytes. They do not change its base storage, active tags, native addresses or
I/O configuration. Partial, scoped and repeated writes remain denied.

Empty Diagnostic Message attribute lists require an existing retained message.
Program coordination requires the exact existing Program parent, paired
acquire/release and no outstanding reservation at the end. These model an empty
update and local coordination transitions, respectively; they do not silently
discard changes to diagnostic attributes.

Offline reconstruction of the received batch models 309 of 335 records:
167 metadata packets with 1,255 exact source value matches, four table writes
containing 151 bytes, 136 empty diagnostic updates and two coordination records.
The remaining records are 20 Symbol, two Routine, one Program and one I/O Map
attribute update, plus two router operations. Source/type/object checks and
all existing lease/assembly cleanup rules still apply. Readback rechecks the
base image and current source metadata; summaries expose counts only.

Start and execution-status still return an explicit processing rejection.
Installing the proposal, implementing remaining operations and producing actual
completed effects are separate required steps before native download succeeds.

The native SDK trial on this version confirms the same 309 modeled records,
1,255 source-matched metadata values and four private table writes inside the
actual transfer. Start then receives the explicit unsupported-processing
response. Download reports `RxCsE_DOWNLOAD_2ND_PASS_AXIS` after 193 verified
requests. Source and active model remain unchanged, actual Offline/cleanup
is confirmed, and no SDK fault is reported. All 194 focused checks pass;
the executable, browser and all 106 deployed app modules match this version.

## Typed header updates

Version `26.1023.102014` adds exact Set Attribute List profiles for temporary
Symbol, Program, Routine and Local I/O Map headers. The installed v35 attribute
definitions establish the wire field types. Every profile requires the exact
field set, unique fields, correct extents and the original numeric parent scope.
Field order may vary; trailing or truncated data is rejected atomically.

Names and logical identities must match the original catalogs. Symbol value
addresses and logical paths must refer to the retained table, Program or
Routine, or the current interpreter Local I/O Map. Equivalent logical segment
widths are accepted without replacing their bytes. The Task reference profile
retains an explicit null data address and empty path with a matching source
Task; it does not invent an allocated Task address.

Routine headers require the original Type and opaque source-key bytes,
ordinary untested RLL source and unsigned-source proof. Program headers check
the main Routine reference, source-backed settings, absent output/fault lists,
child list and bounded zero-stack profile. Scoped Symbol and Routine updates
also require the batch's existing Program coordination reservation.

The Local I/O Map uses only the exact software profile with Key Mask 0,
Map Storage 1 and Mode 5, for a current canonical Local map. These retained
scalars do not allocate physical map storage or operate I/O. Symbol Control
DWORDs are retained as opaque properties; their bits are not interpreted or
executed, and they are not claimed to match recovered source control flags.

Scoped Routine reference data names are read from the validated original
component's counted data-name field. They remain scoped metadata and do not
enter the root Program/Task reference catalog or public tag storage. Older
manifests without these optional names cannot supply guessed Routine aliases.

Reconstruction of the received second batch now models 333 of 335 records,
including all 24 header updates and their 184 attributes. Two router operations
remain unsupported. Readback rechecks source catalogs, the base image and live
map/object references. Base headers, table storage, active tags and logic remain
unchanged. Start and execution status still reject incremental processing;
neither a property snapshot nor opaque-byte retention establishes completion.

The native trial confirms all 24 header updates and 333 modeled records, then
stops at the same two remaining operations. Download still reports
`RxCsE_DOWNLOAD_2ND_PASS_AXIS` after 193 verified requests, preserving source and
active model with actual Offline/cleanup and no reported SDK fault. All 235
affected checks pass, and all 107 deployed modules and delivery versions match.

At that release, the unresolved operations use router `0x33` to Routine service `0x5C`, with
selector words `(1,9)` and a 13-byte body. Offline inspection of decoded batches
from the saved successful-download reference finds the same body in 119 such
transfers. That is framing evidence: the field's meaning, its required effect
and its source relationship remain unresolved. The reference inspection does
not verify capture MACs or turn those bodies into successful model operations.

## Second-batch completion

Version `26.1023.105500` implements temporary processing for completely modeled
later-batch records. The two Routine transfers use an exact bounded Router
envelope, Program/Routine path, selectors `(1,9)` and the observed 13-byte data
profile. They store opaque component bytes for an original, retained, ordinary
RLL Routine while its Program is reserved. Other data profiles, targets,
selectors, truncated/trailing bytes and duplicate writes are rejected. The
bytes' internal meaning remains unknown; they are not interpreted as code,
motion/axis configuration, source or executable references.

Every record has an ordered immutable result with its request fingerprint and
expected storage effect. Actual readback covers metadata ranges, table bytes,
header properties, Routine component bytes, empty diagnostics and historical
Program coordination transitions. An unknown operation, missing result, changed
stored value, record digest, source catalog, runtime revision or backed object
reference prevents completion. This models temporary storage and coordination;
it does not establish every vendor firmware side effect.

Start must succeed before an execution-status query. Only complete record and
expanded-byte coverage can return the observed seven-byte completed progress
profile. Repeated queries recheck all effects and source bindings. A successful
result query permits transport deletion to retain the completed update model.
Deletion before that query discards the pending updates. The retained update
model overlays table readback without modifying the first image or its original
zero-allocation result ledger. Neither model writes active tags or installs
logic. Current catalog changes revoke the retained updates, and preparation
end, owner release/disconnect, expiry, reload and reset retain the established
lease cleanup rules.

Offline reconstruction now models and reads back all 335 records, including
1,255 exact original-source metadata matches, four private table writes, all
24 header updates and two opaque Routine records. The current implementation
retains one incremental batch. A further batch can be received and inspected,
but its Start/status remain explicitly unsupported and cannot overwrite the
completed updates. Complete native download, upload and the full online-edit
lifecycle still require separate acceptance.

The native SDK trial accepts Start and the completed progress response for
this second batch, then deletes the transport while retaining all 335 update
records. The trace confirms actual effect readback and the completed result
count of 190,318 expanded bytes. The next rejected request is empty Task Create
(`0x70`, instance 1, service `0x08`), which has no temporary Task implementation
yet. Download reports `RxCsE_DOWNLOAD_OF_TASKS_FAILED` after 198 verified
requests. Source and active model remain unchanged; actual SDK Offline and
endpoint cleanup succeed without a reported SDK fault. All 244 affected checks
and 55 SDK-probe checks pass. The executable, browser assets and 107 deployed
modules match this version. This advances the native boundary without claiming
a complete download or activation of downloaded logic/values.

## Temporary Task headers

Version `26.1023.122010` implements the observed empty Task Create request
(`0x70`, service `0x08`) for original ordinary Standard Tasks. The response
contains the original instance ID and an owned temporary header handle, matching
the captured two-DWORD layout. The address identifies a simulator object; it
does not expose physical memory or imply a recovered firmware descriptor.
Nonempty Create profiles, unknown/scoped identities and duplicate creation
remain errors.

The prepared programming owner must have completed and retained both temporary
batches. The Task inventory must match the same original ACD/L5X pair and the
complete source Task names. Creation requires the known Standard memory profile
and full static configuration proof. Source formats unsupported by the original
Task reader, safety/event Tasks and missing stored settings cannot create a
guessed header. Existing lease/generation/owner and Program-mode checks apply.

The captured nine-field Set Attribute List profile retains rate, empty trigger,
Task kind, priority, watchdog, timeout, output-update flag, inhibit flag and the
ordered Program list. All values must exactly match the original stored and L5X
configuration; each scheduled Program must exist in the retained image. Source
field widths, unique attribute IDs, counted-array bounds and payload extents are
checked before publishing any property. Reply statuses preserve requested field
order; missing, extra or malformed fields never get a partial success response.

Every created header and configured property has private effect readback and a
source binding. Later catalog operations recheck that binding, including current
Task source models and their Program schedule. This also corrects catalog
validation after a completed incremental batch: current metadata and header
contexts are now supplied on that path. Preparation end, release/disconnect,
source replacement and lease expiry clear these Task objects with the existing
namespace. Active task scheduling, tag values, counters and logic are unchanged.

The offline demo check matches all nine fields to its original ACD and L5X, and
all 347 affected checks pass. This establishes model/protocol behavior; complete
native download/upload remains a separate acceptance boundary.

The native `26.1023.122010` trial accepts Task Create and its two-DWORD response.
The next rejected request sets the existing Task Symbol's Data Address and
logical path to that newly allocated header. A cleanup request then clears its
logical path. Task configuration is not reached yet. Download retains
`RxCsE_DOWNLOAD_OF_TASKS_FAILED` after 199 verified requests, with unchanged
source/model, actual Offline/cleanup and no reported SDK fault. This locates a
separate reference-link step between Task creation and configuration.

## Task Symbol links

Version `26.1023.123557` implements the observed Set Attribute List update for
the original root Task Symbol after Task Create. The original auxiliary Symbol
catalog must supply the explicit `Task:` data name, and the completed second
batch must retain that same name, Task type word and initial null Data Address
and path. An unrelated Symbol, missing source alias or foreign source pair
cannot gain reference-write authority.

The two-field update contains Data Address (3) and logical path (13). The address
must identify the exact created Task header; the logical path must identify
that original Task instance in class `0x70`. Equivalent logical-segment widths
are accepted and their bytes retained. Field order may vary. Unknown, repeated,
missing, truncated or trailing fields are rejected before publication.

The separate one-field clear profile sets path 13 to its explicit empty value.
It changes only that property; the existing scalar address remains retained
until the owning namespace is discarded. Clearing an already empty, validated
source reference is idempotent. No arbitrary scalar/address write or generic
Symbol update is enabled.

The link/clear layer has its own effect digest and source checks. It leaves
the first image and the second batch's original header/result ledger intact,
while later catalog reads and Task updates recheck the current Task/alias binding. These are
private reference properties, with no active tag or scheduler mutation. The
same lease, source, generation, Program-mode and owner checks still apply.

An offline reconstruction verifies creation, linking, all nine configuration
fields, detachment and preservation of all 335 earlier effects using the
original demo catalogs. Native Task configuration and complete transfers still
require live acceptance.

The native `26.1023.123557` trial accepts Task Create, the Task Symbol update and
all nine Task configuration fields. It then rejects a separate Set Attribute
Single on TCP/IP class instance zero, attribute 101, containing one zero byte.
Download reports `RxCsE_ASA_NO_PERMISSION` after 199 verified requests. Upload
retains its Program-collection failure after 348 verified requests. Both
preserve source/model, confirm actual Offline/cleanup and report no SDK fault.
All 352 affected checks pass; the executable, webpage and 108 deployed modules
match. Full transfer acceptance remains incomplete.

## Embedded HTTP disable

Version `26.1023.165303` accepts the observed one-byte zero Set Attribute Single
on TCP/IP class `0xF5`, instance zero, attribute 101. The saved successful
download contains the same request and an empty success reply. Its capture MAC
has not been verified. This profile retains the endpoint's existing disabled
embedded HTTP value; it does not change interface configuration or the separate
local management UI.

The signed session must own a prepared download with current source/catalog
bindings, intact retained image/effects and all original ordinary Tasks fully
configured. Program mode is required. Wrong scopes, malformed values, attempts
to enable HTTP, unsigned/foreign callers and stale sources remain errors.
The disabled value remains readable through the existing attributes 101/102;
no new active project, tag, scheduler or audit change occurs.

The native `26.1023.165303` download accepts the disable request and advances to
a 14-field Controller Set Attribute List. That later write remains denied, with
`RxCsE_ASA_NO_PERMISSION` after 200 verified requests. Upload retains its
Program-collection failure after 349. Both preserve source/model and confirm
actual Offline/cleanup without a reported SDK fault. All 195 affected checks
pass; all 108 deployed modules, served assets and executable versions match.

## Native boundary

Preparing and reading this image establishes simulator state only. It does not
establish native Resilient Transport service semantics, compiled execution,
transfer of initial values, successful Studio download or an active-project
commit. The anonymous research endpoint now acknowledges service `0x06` on class
`0x412` only after this temporary preparation transition succeeds. Incomplete
coverage or a missing source binding remains an error. The later empty `0x4D`
request now uses the bounded completed-batch profile above; earlier releases
rejected it while that contract was unresolved.

In the `.78` native SDK test, preparation retained all 904 records, 242 Templates,
136 diagnostics, one Program and two Routine identifiers. Sixteen temporary
tables allocated 172 bytes, with 15 linked Symbols and five unresolved storage
references. Start succeeded and the SDK advanced to `0x4D`; the complete download
still failed. Source and active model were preserved, and cleanup cleared the
temporary objects. A separate private experiment returned an empty successful
`0x4D` response and still failed at the same stage, without advancing to another
transfer operation. That hypothetical result response is absent from the app.

Version `.95` recognizes the exact empty result query as a separate diagnostic
boundary. It requires the prepared programming lease, original source binding,
an already started image, the same current type catalog and an intact result
ledger. Expired, unstarted or rebound images fail those checks. A valid query
records aggregate preparation state, then returns an explicit
`device_image_result_encoding_unavailable` rejection. It does not prepare a new
image, return guessed native results or commit the temporary image. This makes
the remaining download blocker identifiable in native rejection reports while
preserving the existing negative wire response.

The `.95` native SDK retest reaches one such query with all 904 prepared records
and their 904 retained results. Download still fails with
`RxCsE_DOWNLOAD_OF_DEVICES_FAILED` across 182 verified signed requests; separate
library-data writes remain denied. Native Offline and endpoint cleanup succeed,
the original source and active model are unchanged, and no fatal SDK fault is
reported. This validates the diagnostic boundary without establishing a native
result codec or a completed download.

The unit tests cover independent temporary allocation, typed attributes,
source checks, unknown operations, allocation/read bounds, unresolved symbols,
atomic failure, cached inspection and cleanup. Owned native traces can be
replayed offline without including their private payloads in this repository.
