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

## Controller configuration

Version `26.1023.170237` stages the observed 14-field Controller Set Attribute
List after all original Tasks are configured. The supported profile is limited
to a matching original v35 `1756-L85E` source, prepared programming owner and
stopped Program mode. Current image, earlier effects and source bindings are
rechecked before publishing the complete configuration. Unknown, repeated,
missing, truncated, trailing or source-mismatched fields fail atomically.

Null handlers, Security Code, source flags, pass-through mode and the 64-bit
change-detection mask must match the source configuration. Explicit legacy time
slice/share settings must match too. When those two settings are omitted, this
download profile retains zero operands independently of the declared read
defaults; neither changes scheduler behavior. Unsupported or missing settings
remain errors. This is a compatibility profile, not native CPU scheduling.

The two 32-byte State Detection operands support only the explicit all-zero
reset profile. Their original bytes are retained as private properties;
signatures are neither calculated nor verified, and live signature reads remain
unavailable. Returned statuses preserve the request's field order.

All 14 fields have private readback and a source/effect digest. Subsequent
download catalog operations recheck both. Ending preparation, disconnect,
expiry or source replacement discards this state with the owning namespace.
Active tags, configuration, scheduling and audit values remain unchanged.

An offline reconstruction checks the demo's exact native request against its
original ACD/L5X-derived configuration and verifies preservation of the earlier
335 effects. Complete native download and activation remain separate boundaries.

The native `26.1023.170237` SDK download accepts all 14 fields and advances to
three separate Controller updates, for attributes 10, 11 and 12. Those requests
remain denied in that version; download reports `RxCsE_ASA_NO_PERMISSION` after
203 verified requests. Upload retains its Program-collection failure after 349.
Source/model preservation, actual Offline/cleanup and no reported SDK fault are
confirmed. All 221 affected checks pass; all 109 deployed modules and packaged
and served versions match.

### Additional Controller settings

Version `26.1023.170949` supports the observed one-field Set Attribute List
profiles for retain-test-edits (10) and the I/O/Data Table spare-memory
percentages (11/12). Each requires the base 14-field configuration, current
prepared owner, complete Tasks and an exact original source value of the
documented width. Missing source values do not become zero.

These properties extend the same private configuration and preserve earlier
fields when the base packet repeats. Invalid requests never publish partial
properties. Source/effect checks and cleanup apply to all 17 retained fields;
the active configuration, scheduler and audit value remain unchanged.

The native `26.1023.170949` download accepts the base packet and all three
follow-up writes. Private configuration effect events progress through 14, 15,
16 and 17 checked fields. The next denied request is metadata service `0x4F`,
class `0x349`, instance 36, for `ControllerSerialNumber`. Download reports
`RxCsE_ASA_NO_PERMISSION` after 204 verified requests; complete transfer and
activation remain unfinished. Source/model preservation, actual Offline/cleanup
and no reported SDK fault are confirmed. All 222 affected checks pass; the
executable, browser and 109 deployed modules match.
Upload retains `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` after 349 verified requests,
with unchanged source/model, actual Offline/cleanup and no reported SDK fault.
The original stopped demo is restored with zero scans, elapsed time, runtime
revision and audit updates. SDK/Linx service processes remain unchanged.

## Controller metadata properties

Version `26.1023.172357` handles the observed Controller metadata service `0x4F`
after base Controller configuration. The existing download decoder preserves
the complete target, locale, definition and typed value. Every value must match
the original ACD's bound Metadata Definition and Comments catalogs. Only root
Controller instance 1 with zero context/selector words is supported. Unknown,
changed, malformed, ambiguous or foreign-source properties remain errors.

The prepared programming owner, current complete Tasks, retained download
configuration and stopped Program mode are required. Numeric and UTF-8 values
use the original typed metadata codec, independently of the earlier definition-
only staging profile. Single-field and counted multi-field packets are atomic;
exact replays are idempotent. Packet, value and encoded-storage limits apply.

Values have private readback and a source/effect digest, including the packet
ledger. Subsequent namespace operations recheck the stored properties and the
current original catalogs. Ending preparation, disconnect, expiry or source
replacement discards this layer. Active project metadata and the Identity
object's serial number remain unchanged. Packet-local record ordinals confer
no native object identity or project-signature authority.

The demo's rejected `ControllerSerialNumber` packet matches its original ACD
value exactly and has been staged/read back offline. Captured properties from
other projects are not installed when their target or value does not match.
Complete native transfer and active-project commit remain separate boundaries.

The native `26.1023.172357` trial accepts the original `ControllerSerialNumber`
property with checked private readback, then rejects a `ProjectType` property
absent from the original comments catalog. Download reports
`RxCsE_ASA_OBJECT_STATE_ERROR` after 205 verified requests. Upload retains its
Program-collection failure after 349. Both preserve source/model, confirm actual
Offline/cleanup and report no SDK fault. All 290 affected checks pass; all 110
deployed modules and packaged/served versions match.

### Controller profile marker

Version `26.1023.173828` adds a bounded compatibility property when `ProjectType`
is absent from the original comments catalog. The current native v35 client
writes DINT `0x4C` for the matching complete `1756-L85E` demo source. Support is
limited to that tested controller profile. A saved successful reference uses a
different value, `0x62`; this is not a universal Logix family code or a complete
native project-type enumeration.

The source must declare the original `SystemNumeric` definition and its numeric
value schema. Only root Controller `ProjectType`, the observed locale marker,
one DINT element and the exact profile value are supported. A stored source
property takes precedence; this fallback cannot replace a conflicting value.
Other missing metadata remains an error.

This property is labeled separately in the private staging description. The
actual source Project object, hash, version and processor remain bound, and
later operations recheck its complete unedited source profile. It adds no row
to the original metadata catalog and changes no active project or controller
identity. Existing owner, Program-mode, atomicity and cleanup checks apply.

The native `26.1023.173828` trial accepts the bounded `0x4C` property, then
stops at the Ethernet Link attribute list because interface label 10 is missing.
It records 206 verified requests with source/model preservation, actual
Offline cleanup and no reported SDK fault.

### Ethernet interface label

Version `26.1023.175203` supplies Ethernet Link class `0xF6`, instance 1,
attribute 10 from the selected local interface name. The installed v35 object
definition specifies one byte of length followed by up to 64 characters. The
read has no word padding. The emulator returns only an available printable
ASCII name that fits this field, without truncation or an invented hardware
label. The cached OS observation is shared with the existing network inventory.

Single and list reads are supported; the bounded offline collection decoder
recognizes the same layout while omitting payloads by default. Unknown names
remain unavailable, and network setters stay unsupported. All 317 affected
checks pass, including malformed labels, truncation, list ordering and privacy.

The native trial accepts the full requested Ethernet Link list, passes the
following optional class discovery, and reaches Logix Repository class `0x378`,
instance 1, service `0x4B`. It stops there with `RxCsE_ASA_NO_PERMISSION` after
265 verified requests. Upload retains `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` after
349 requests. Both preserve source/model, confirm actual Offline cleanup and
report no SDK fault. The 110 deployed modules and delivery versions match.

### Repository device record

Version `26.1023.175952` handles the observed post-network Logix Repository
class `0x378`, instance 1, service `0x4B` device record. Only the owning prepared
download client in Program mode can register it, after source-checked Controller
configuration. The exact bounded UTF-16 record must match the loaded project
name, this emulator's current serial and its advertised product name. The
source must match the complete unedited v35 L85E profile.

The returned DWORD is a simulator-owned namespace handle. The following
Extended Device class `0x64`, instance 1, Set Attribute List for attribute 8 can
link only that exact handle. Both operations are idempotent. Changed source,
device identity, registration content or retained effects revoke later namespace
operations. Malformed records, other attribute writes and foreign handles fail
without partial publication.

This retains the requested System Operator Identity reference privately. It
does not authorize an operator, create a trusted authority, alter active device
attributes or reuse the captured reference handle. Ordinary attribute 8 reads
retain the software-device default. Ending preparation or disconnecting the
owner discards the temporary namespace with its registration and link. Native
transfer completion and active-project commit remain separate requirements.

The native `26.1023.175952` trial accepts the exact device registration and
returns its local handle, then accepts the subsequent attribute 8 link using
that handle. It advances to 269 verified requests and stops with
`RxCsE_ASA_NO_PERMISSION` in the following setup writes: Ethernet Link attribute
9; the combined Extended Device attributes 1, 2, 3, 6, 7 and 8; PCCC Mapping;
Time Sync; and wall-clock settings. These require further source-checked staging,
not blanket write acknowledgement.

Upload retains `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` after 349 verified requests,
before Routine source retrieval. Both trials preserve source/model, confirm
actual Offline cleanup and report no SDK fault. All 346 affected checks pass;
all 111 deployed modules and delivery versions match. The original demo is
restored stopped with zero scans, elapsed time, runtime revision and audit
updates; SDK/Linx service processes remain unchanged.

### Post-registration setup

Version `26.1023.181323` retains five observed Set Attribute List profiles in
the prepared download owner's private namespace. Source configuration must be
complete, unedited and match the v35 L85E controller profile. Repository device
registration and its handle link must already be complete; writes require
Program mode.

| Object | Attributes | Accepted values |
| --- | --- | --- |
| Ethernet Link `0xF6` | 9 | Current administrative state from the cached selected OS interface; no adapter setter |
| Extended Device `0x64` | 1, 2, 3, 6, 7, 8 | Source project name/description, empty location and trusted slots, the observed private unset-locale marker, and the existing repository handle |
| PCCC Mapping `0x67` | 1, 2 | Proven empty source mapping |
| Time Sync `0x43` | 16, 17, 1 | Source priorities and PTP-enable setting |
| Wall Clock `0x8B` | 4, 2 | Explicit source legacy UTC adjustments |

Each profile requires its exact field order, lengths and values. A mismatch or
truncation rejects the whole write without partial publication. Retained values
have actual private readback, idempotent replay and source/device/effect binding.
Subsequent namespace operations recheck those bindings. Unknown mappings,
incomplete clock settings, unavailable interface state, foreign clients and
other property writes stay unsupported.

These are staged download properties. The empty locale marker does not replace
the management UI's English locale; the repository reference grants no operator
authority. No adapter, clock, active PTP configuration or source catalog is
changed. Ending preparation or disconnecting discards the staged setup. A
successful download and active-project commit remain separate requirements.

The original demo's five saved native setup requests match all 14 expected
fields and their retained readback in the offline model. Native acceptance is
assessed separately.

The native `26.1023.181323` trial accepts all five full setup writes and retains
all 14 fields, then reaches a separate PCCC Mapping attribute 1 write. It stops
there with `RxCsE_ASA_OBJECT_STATE_ERROR` after 271 verified requests. Upload
retains Program-collection failure after 347 requests. Both preserve source/model,
confirm actual Offline cleanup and report no SDK fault. All 380 affected checks
pass and all 112 deployed modules and delivery versions match.

Version `26.1023.181855` adds that separate PLC-2 attribute 1 write only after the
full PCCC mapping profile is staged. It requires the same source value and keeps
the existing descriptor in attribute 2. Its shorter reply has its own checked
budget. Other partial mapping writes remain unsupported.

The native `26.1023.181855` trial accepts the five setup profiles plus the
separate PLC-2 write. All 14 staged fields remain checked, and a third RTO setup
is accepted. Download then rejects a compact single-message transfer before
processing its payload, with `RxCsE_ASA_NO_PERMISSION` after 270 verified
requests. Upload retains Program-collection failure after 349. Both preserve
source/model, confirm SDK Offline and disconnect cleanup, and report no SDK
fault. All 381 focused checks pass; all 112 deployed modules and delivery
versions match. The original stopped demo is restored.

### Compact third transfer boundary

The observed third payload fits one `0x39` request with container format `0x301`.
Its count is the encoded payload length, excluding the 16-byte device header.
The `26.1023.181855` decoder supports fragmented transfers and separate legacy
`0x39` control forms; it rejects this compact form as an unsupported control. That
framing rejection closes the compatibility session, so later cleanup requests
also fail at the wrapper. SDK Offline and endpoint cleanup are confirmed after
disconnect; successful on-wire End Preparation is not claimed for this trial.

Offline inspection decodes the retained 3,599-byte payload into eight records
and 7,153 expanded bytes: Program coordination and six wrapped Routine writes
for two Routines. This establishes byte framing only. The request MAC has not
been verified offline, and these records have not been accepted or executed.
Next work needs bounded compact framing, its correct acknowledgment, and a later
batch model that preserves the earlier retained image and update ledger.

### Compact transport storage

Version `26.1023.183656` recognizes a distinct complete `0x39` device-transfer
container. Format `0x301` carries the exact encoded payload count, excluding its
fixed 16-byte RTO device header. Existing legacy controls 1 and 8 retain their
interpretation. A malformed count, different header, unsupported format or
message exceeding the codec limit cannot become a complete transfer.

The same session MAC and exact counter are verified before dispatch. Only the
prepared download owner with matching source and open RTO setup can retain the
payload. It must fit the negotiated buffer; partial or completed assemblies
cannot be overwritten. Invalid storage clears temporary bytes while preserving
setup for cleanup. Expiry, replay, source replacement and owner disconnection
use the existing cleanup rules. Compact device transfers are not enabled for
native edit preparations.

A complete payload uses the shared signed empty transport acknowledgment. That
confirms temporary storage, not acceptance or execution of the records. The
retained payload has exact private readback; offline tracing identifies the
compact form without exposing its bytes by default. The earlier image and
incremental-update ledger remain separate. Later batch processing still needs
its own source verification and completion model.

The retained original compact frame parses with its payload count and bytes
intact. A copy signed with the public synthetic test key verifies its MAC and
counter and decodes to the same eight records, without executing them. The
original captured request MAC is not claimed verified by that offline test.
Native acceptance is assessed separately.

The `26.1023.183656` native SDK download accepted the compact transfer and its
storage acknowledgment, then reached the later-batch processing guard at RTO
Start. Delete, End Preparation and lease release also succeeded on the wire.
The trial ended with `RxCsE_PACKAGE_DOWNLOAD_PAYLOAD_ERROR` after 275 verified
requests; upload retained its Program-collection failure after 349. Both
preserved source and model, confirmed SDK Offline and reported no SDK fault.

### Source-matched routine batch

Version `26.1023.185759` adds a separate third-batch model. It requires the
retained first image, completed incremental updates and all five source-checked
setup profiles. The prepared owner must remain in Program mode with the same
original v35 L85E project and native catalogs. The earlier image and update
ledger remain intact and are revalidated before each namespace operation.

Only balanced mode-0 Program reservations and wrapped Routine component writes are
supported. Every original Routine must have exactly one code, source and
attachment component in that order. Container sizes, markers, target scopes,
component bounds and aggregate storage are checked. Decoded source names and
resolved ladder instruction trees must match the loaded original source;
detached edit-plan validation must also pass. A different source or unsupported
operand resolution rejects the whole proposal without publishing partial data.

Start retains immutable private components and an individual record ledger.
The result query rechecks source bindings, record digest, stored effects and
expanded-byte coverage before returning completed temporary processing. Delete
retains the batch only after that result was queried. Expiry, disconnect and
End Preparation clear temporary state. Subsequent batches remain unsupported.

These checks establish source equivalence and exact storage, not native ELF
validity or execution. Compiled code and auxiliary source data stay opaque.
No active-project commit, replacement of tag values or complete functional
Studio download is claimed by this stage.

The `26.1023.185759` native SDK trial accepts the mode-0 reservation, all eight
records, two Routines and 10 source-matched rungs. Start and the completed result
query succeed; Delete retains the separate routine batch alongside the earlier
image and 335-record update ledger. The next request is Get Attribute List on
I/O Map instance 1, attribute 2. That attribute remains unsupported and ends the
download with `RxCsE_ASA_ATTRIBUTE_LIST_ERROR` after 277 verified requests.

Upload still ends at Program collection with
`RxCsE_UPLOAD_OF_PROGRAMS_FAILED` after 349 verified requests. Both trials
preserve source and model, confirm SDK Offline and normal cleanup, and report
no SDK fault. The original demo is restored in stopped Program mode with zero
scans or audit updates. This confirms native acceptance of the routine storage
stage while leaving complete transfer and installation unimplemented.

### Local Map identity

Version `26.1023.190840` adds read-only attribute 2 on Local I/O Map instance 1.
Its eight-byte value contains the software device's vendor, type, product code
and major/minor firmware revision. The supported successful reference response
matches Identity attributes 1 through 4; acceptance of the emulator's response
is tested separately from that structural observation.

The source must contain a complete canonical controller-only Local module,
including explicit Vendor, ProductType, ProductCode, Major and Minor fields.
The module and Controller revisions must agree. Its route must be Local ICP
port 1 at slot zero, and its identity must match the supported v35 L85E
software-device profile. The current Engine, project hash and profile are
rechecked on each read. Missing fields, contradictory revisions, a different
product, external I/O or a research-profile identity cannot supply this value.

Get Attribute List and Get Attribute Single share the same bytes. List order,
duplicate requests, partial errors, unknown instances and write denials retain
their existing behavior. Serial numbers and hardware revision are not part of
this attribute. No captured physical identity is copied, and this read confers
no I/O configuration or download-commit behavior.

The native SDK trial accepts this identity response and reaches the following
Map attribute 7 write. Version `26.1023.190840` still rejects that write and ends
with `RxCsE_ASA_NO_PERMISSION` after 279 verified requests. Source/model remain
unchanged, SDK Offline and cleanup are confirmed, and no SDK fault is reported.

### Prepared Map flag

Version `26.1023.191802` retains the observed late Map attribute 7 value `1`
in a separate private header. Its earlier incremental header value `5` remains
intact. The bit meanings are not interpreted, and the active Map is unchanged.

Only the prepared download owner in Program mode may write the exact one-field
attribute list. All three earlier batches, complete setup, the original header,
source-equivalent Routine components and explicit Local identity must still
validate. The proposal is checked before publication; a malformed request,
changed binding or insufficient reply budget cannot publish a partial flag.

Private readback rechecks the same source/effects and supports the owner's
Get Attribute Single or List, including lists mixed with public Map fields.
Other clients and unsigned requests do not gain access to the retained flag.
End Preparation and disconnection clear it with the temporary namespace.
This is prepared-state storage, not I/O activation, native code execution or an
active-project commit. A complete download remains a separate acceptance step.

The `26.1023.191802` native SDK trial accepts the Local Map identity read and
the prepared flag write with the expected attribute-list acknowledgment. The
private effect is retained while active I/O, project state and audit values
remain unchanged. Download then reaches Change Log class `0xAC`, instance 1,
Create (`0x08`), which remains unsupported. It ends with
`RxCsE_ASA_NO_PERMISSION` after 280 verified requests. Upload still reports
`RxCsE_UPLOAD_OF_PROGRAMS_FAILED` during Program collection after 348. Both
preserve source/model, confirm SDK Offline and normal cleanup, and report no
SDK fault.

### Prepared Change Log header

Version `26.1023.193356` supports the observed Change Log instance 1 creation
profile after the prepared Map flag. The exact creation parameter is attribute
6 value 1000; its units remain uninterpreted. The returned handle identifies an
actual private header in the owning namespace. It is not a physical address or
an allocation of native Change Log records.

The seven-field configuration profile accepts a proposed download UID while
requiring the original copy, project and timeline anchors and the existing
source-backed header scalars. The proposal is pinned after configuration.
Malformed, duplicate, partial or foreign-source fields cannot publish a header.
The original ACD correlation object remains immutable, and the proposed UID
does not authenticate or authorize a controller operation.

Create/configure require the prepared owner in Program mode and adequate reply
space. All earlier batches, source catalogs, routine effects, setup and Map
state are rechecked. Single, List and All reads return the owned private header;
ordinary unsigned reads retain the active original correlation. End Preparation
and disconnection clear the proposal. No history is fabricated or imported.

Controller service `0x61` now diagnoses the next boundary after a fully
configured header. It revalidates preparation and returns the explicit
`download_commit_unimplemented` rejection. This does not install the image,
change active identifiers, execute compiled code or report a successful download.

The native `26.1023.193356` trial accepts Create, seven-field configuration and
exact private readback in sequence. Source copy/project/timeline anchors match
the original ACD; the new caller download UID is retained privately. The SDK then
reaches service `0x61` and receives the explicit commit rejection. It ends with
`RxCsE_ASA_NO_PERMISSION` after 281 verified requests. Upload still fails Program
collection after 348. Both trials preserve source/model, confirm SDK Offline and
normal cleanup, and report no SDK fault. All 115 deployed modules and delivery
versions match; 133 affected checks pass. This establishes native acceptance of
the prepared header, with final installation still unfinished.

### Source-matched initial values

Version `26.1023.195217` validates the initial values before the Controller
installation boundary. Every source tag must have exactly one retained table;
aliases, incomplete symbol coverage, unsupported types or dimensions, changed
source values and unaccounted tables reject preparation as a whole.

Supported scalar encodings and explicitly source-declared TIMER/COUNTER layouts
are compared byte for byte with the saved source values. Builtin member offsets,
flag bits and Template IDs must agree with the original type catalog. Local-port
XML is checked against the original L5X's bounded ICP/Ethernet profile. The
observed zero `__CONTAINER` DINT is retained as opaque auxiliary configuration;
it does not become an application tag or native executable state.

Preparation also builds a separate execution model, checks its complete initial
memory and rejects execution blockers. Prescan is deferred until a future Run
entry. Failure publishes no value preparation and never replaces the active
model. The private preparation revalidates on subsequent namespace reads and is
cleared with End Preparation or disconnection.

Controller service `0x61` continues to return `download_commit_unimplemented`
after successful preparation. This revision does not switch execution models,
activate native compiled code, change active correlation or complete a download.

The live SDK download validates all 14 demo tags (45 value bytes), accounts for
the two auxiliary tables and successfully constructs the separate execution
model. It still ends at the explicit installation rejection after 281 verified
requests. Source and active model stay unchanged, SDK Offline and cleanup are
confirmed, and no SDK fault is reported. All 116 deployed modules and delivery
versions match; 140 affected checks pass.

### Source-equivalent installation

Version `26.1023.200635` adds a bounded installation service for the fully
validated v35 L85E profile. The downloaded routines, configuration, catalogs
and supported initial values must match the loaded original source. It cannot
replace the controller with an unrelated project or execute native ELF code.

Controller service `0x61` builds a separate interpreter model and publishes it
only after preparation and execution validation finish. Saved values replace
current tag values; scan counters, timing and instruction state restart, and
prescan is deferred to Run entry. Backed project-object references remain valid
through the owning session's completion and cleanup. Queued external inputs are
rejected and their write token rotates at publication.

The original ACD correlation and catalogs stay immutable. The new Engine retains
the installed header and caller download UID separately; native Change Log reads
use this committed runtime view. End Preparation, lease release and disconnection
clear temporary ownership while preserving the installed model. A local project
reset, reconfiguration or reload replaces that model and clears the runtime view.
Repeated commit requests from the same prepared owner do not install twice.

Installation is synchronous, so Controller status attribute 26 is zero once the
new model has been published. A saved successful native exchange shows status 4
during processing followed by zero; this interpreter has no outstanding native
compilation work after publication. The model receives a fresh simulator audit
epoch independently of the monitored event mask, following the download rule in
[Rockwell's change-detection documentation](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf#page=49).
This does not reproduce Rockwell's audit-value generator or native Change Log
history. Native transfer completion remains a separately measured outcome.

The native SDK completes `DownloadAsync` for the original ConveyorDemo after
361 verified requests. Its committed download UID and original source anchors
have exact independent wire readback, and completion status is zero. A separate
private diagnostic completes Download → Go Online in the same SDK project and
verifies the SDK's Online state after 433 requests. Both confirm SDK Offline and
normal cleanup, preserve original ACD bytes, and report no SDK fault.

Opening a fresh original ACD after download fails Go Online with
`RxCL_E_CANNOT_UPLOAD_PHYS_ADDR`; its trace stops before descriptor requests.
The [saved-download workflow](development.md#saved-download-reconnection) retains
the downloaded SDK project's updated identity in a new ACD, closes/reopens it
and verifies Online across 432 signed requests. A separate native process opens
the saved ACD and verifies Online across 74 requests. The emulator model still lasts only until reset/reload or
restart. Upload fails Program collection both standalone and after a download
within the same SDK project. These results do not establish general upload,
GUI monitoring or arbitrary project replacement.

Program-mode routine replacement preserves the committed controller header
through each validated detached candidate. The new Engine retains the download
UID and original source anchors while its routine revision increases. Status
reports `source_equivalent: false` once the logic changes; the retained native
transfer is a historical snapshot, not newly compiled executable code.

All 117 deployed modules and delivery versions match. The Windows milestone
suite passes 2,003 checks with two platform skips; 206 focused checks pass.

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
