# Studio5000Emulator

An experimental offline Logix v35 emulator with a browser UI and local EtherNet/IP research endpoint.

Explore supported ladder and Structured Text logic, drive inputs, inspect scan
traces, and test explicit messaging against a custom execution model. The app
and executable use the name **LogixLab**.

**Current app version: `26.1023.181855`.** Versions use the release timestamp
`YY.MMDD.HHmmss` in the release workstation's local time. The browser title,
page header, Windows tray and executable properties share this version.

This revision adds the separate PLC-2 mapping write that follows the full setup
list. It requires the original empty mapping and preserves the already retained
mapping descriptor. Complete functional native transfers remain unfinished.

The native SDK accepts all five setup profiles and the separate PLC-2 write,
then reaches the third transport batch. Its compact single-message container
is not supported yet. Download reports `RxCsE_ASA_NO_PERMISSION` after 270
verified requests; upload retains Program-collection failure after 349. Both
preserve source/model, confirm SDK Offline and disconnect cleanup, and report
no SDK fault. All 381 focused checks pass; all 112 deployed modules and delivery
versions match. The original demo is restored stopped with zero scans and
audit changes.

Version `26.1023.181323` adds [post-registration download settings](docs/download-image.md#post-registration-setup)
for Ethernet administrative state, combined device properties, PCCC mapping,
Time Sync and legacy wall-clock settings. All 14 fields have checked private
readback; host network, clock and active controller settings stay unchanged.
Complete functional native upload/download remain unfinished.

Version `26.1023.175952` adds a [temporary repository device record](docs/download-image.md#repository-device-record)
and its handle link for the prepared download owner. Fields must match the
loaded v35 L85E project and current software-device identity. The record stays
private and grants no operator authority. Complete native transfers remain
unfinished.

The native SDK accepts both registration and link, then stops at the following
setup writes after 269 verified requests: Ethernet administrative state,
combined Extended Device settings, PCCC mapping, Time Sync and wall-clock
settings. Upload retains Program-collection failure after 349 requests. Both
preserve source/model, confirm actual Offline cleanup and report no SDK fault.
All 346 affected checks pass; all 111 deployed modules and delivery versions
match. The original demo is restored stopped with zero scans and audit updates.

Version `26.1023.175203` adds the read-only Ethernet Link interface label used by native
download setup. It returns the selected local OS interface name with the
installed v35 byte-counted layout; unavailable names remain explicit errors.
The native download now passes this read and advances to Logix Repository
registration after 265 verified requests. Upload retains the Program-collection
failure after 349 requests. Both preserve source/model, confirm actual Offline
cleanup and report no SDK fault. All 317 affected checks pass; all 110 deployed
modules and delivery versions match. Complete native transfers remain unfinished.

Version `26.1023.173828` adds a bounded [controller profile marker](docs/download-image.md#controller-profile-marker)
for the post-configuration `ProjectType` metadata request. It requires a matching
complete v35 L85E source and the original numeric metadata schema. Stored
properties take precedence; active metadata and controller identity stay unchanged.
Complete native upload/download remain unfinished.

Version `26.1023.172357` adds [source-checked Controller metadata writes](docs/download-image.md#controller-metadata-properties)
after download configuration. The owning prepared client can retain original
typed metadata values with private readback; active metadata and controller
identity remain unchanged. Functional native upload/download remain unfinished.
The native trial accepts the original serial-number metadata, then reaches an
unstored `ProjectType` property and stops after 205 verified requests. Source
and model are preserved, actual Offline/cleanup succeeds and no SDK fault is
reported. Upload retains Program-collection failure after 349 requests. All
290 affected checks pass; all 110 deployed modules and delivery versions match.

Version `26.1023.170949` adds the three separate [Controller settings writes](docs/download-image.md#additional-controller-settings)
following the base configuration: retain test edits and the two memory spare
percentages. Each requires the original source value and preserves all earlier
staged properties. Functional native transfers remain unfinished; online-edit
work follows upload/download.
The native SDK accepts the base write and all three follow-up writes, retaining
all 17 checked fields. Download advances to a later Controller metadata write
and stops after 204 verified requests. The source/model are preserved, actual
Offline/cleanup succeeds, and no SDK fault is reported. All 222 affected checks
pass; the executable, webpage and 109 deployed modules match.
Upload retains `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` after 349 verified requests,
with source/model preservation, actual Offline/cleanup and no reported SDK
fault. Validation restores the original demo, stopped with zero scans/audit
updates and unchanged SDK/Linx service processes.

Version `26.1023.170237` stages the observed [Controller download configuration](docs/download-image.md#controller-configuration)
after Task configuration. All 14 fields have checked private readback. Explicit
source settings must match; omitted legacy slice settings use the observed zero
download profile, and zero signature-reset operands remain separate from signature
verification. Active configuration and scheduling remain unchanged until the
unfinished transfer commit is implemented.
The native SDK accepts all 14 fields and advances to three separate Controller
settings writes. Download stops there after 203 verified requests; upload still
fails Program collection after 349. Both preserve source/model and complete
actual Offline/cleanup without a reported SDK fault. All 221 affected checks
pass; all 109 deployed modules, executable and browser versions match.

Version `26.1023.165303` handles the observed [embedded HTTP disable request](docs/download-image.md#embedded-http-disable)
after download Task configuration. It retains the endpoint's existing disabled
state under the prepared owner's source checks. The local browser UI remains
available. Functional upload/download remain the priority, followed by online
edits; complete native transfers are still unfinished.
The native SDK accepts this request and reaches the 14-field Controller
configuration write. Download stops there after 200 verified requests; upload
retains its Program-collection failure after 349. Both preserve source/model,
confirm actual Offline/cleanup and report no SDK fault. All 195 affected checks
pass; the executable, webpage and 108 deployed modules match.

Version `26.1023.123557` adds [Task Symbol links](docs/download-image.md#task-symbol-links)
to the newly allocated download Task. The address and logical path must resolve
to that exact owned Task and original source alias. A bounded clear operation
supports cleanup without changing active tags or scheduling. Functional native
upload/download remain the priority; full transfers are still unfinished.
The native trial accepts creation, the Task Symbol link and all nine Task
configuration fields. Download advances to the TCP/IP class's HTTP-disable
request and reports `RxCsE_ASA_NO_PERMISSION` after 199 verified requests.
Upload retains `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` after 348 verified requests.
Both preserve source/model and confirm actual Offline/cleanup without an SDK
fault. All 352 affected checks pass, and all 108 deployed modules match.

Version `26.1023.122010` adds [temporary Task creation and configuration](docs/download-image.md#temporary-task-headers).
The owning download can allocate a Task header and apply its nine source-checked
configuration fields after both temporary batches complete. Returned addresses
identify simulator objects; active scheduling and logic remain unchanged. All
347 affected checks pass. Full native upload/download remain unfinished, and
further online-edit work follows functional transfers.
The native trial accepts Task Create, then stops at the Task Symbol reference
update. Download reports `RxCsE_DOWNLOAD_OF_TASKS_FAILED` after 199 verified
requests. Source/model and actual Offline/cleanup are preserved without a
reported SDK fault; the executable, webpage and 108 deployed modules match.

Version `26.1023.105500` adds [second-batch processing and completion](docs/download-image.md#second-batch-completion).
All 335 observed records have private effect readback, including two bounded
opaque Routine data writes. Completion requires Start, full record/byte coverage,
current source bindings and an intact result ledger. Completed updates survive
transport deletion separately from the original image. Active tags and logic
remain unchanged; complete transfers and Run-mode edits remain unfinished.
The native SDK download accepts both completed batches and advances to Task
creation, reporting `RxCsE_DOWNLOAD_OF_TASKS_FAILED` after 198 verified requests.
All 335 second-batch effects are checked in the native trace, then retained
separately from the first image. Actual Offline/cleanup succeeds, source/model
are preserved, and no SDK fault is reported. All 244 affected checks and 55 SDK
probe checks pass; the executable, webpage and 107 deployed modules match.
Upload retains its Program-collection failure after 349 verified requests.
The supported Program-mode import/reconnect passes across 192 requests with
one expected logic/audit update. Both preserve source and complete actual
Offline/cleanup without a reported SDK fault. Validation restores the original
demo afterward, stopped with zero scans and audit updates; SDK and Linx service
processes remain unchanged.

Version `26.1023.102014` adds [typed second-batch header updates](docs/download-image.md#typed-header-updates).
It stages Symbol, Program, Routine and Local I/O Map properties with source-name,
scope and backed-reference checks. Original Routine source-key metadata is
preserved without interpretation. Offline reconstruction now models 333 of 335
records; two inline router operations still prevent completion. All 235 affected
checks pass. Full native transfers and Run-mode edits remain unfinished.
The native SDK download confirms the same 333 modeled records and all 24
header updates, then reports `RxCsE_DOWNLOAD_2ND_PASS_AXIS` after 193 verified
requests. Source/model preservation and actual Offline/cleanup are confirmed
without a reported SDK fault. Executable, browser and 107 deployed modules match.
Normal upload still fails Program collection after 349 verified requests.
A supported Program-mode online import/reconnect passes across 188 requests
with one expected logic/audit update. Both preserve the input and confirm actual
Offline/cleanup without a reported SDK fault. Validation restores the original
stopped zero-scan/audit demo afterward.

Version `26.1023.095449` adds [isolated second-batch effects](docs/download-image.md#isolated-second-batch-effects).
It stages source-matched metadata values and private whole-table bytes, checks
empty diagnostic updates and models Program coordination. Offline reconstruction
models 309 of the observed 335 records, preserving the completed image and active
project. The remaining 26 operations still block processing and completion.
The native download trial confirms the same 309 modeled records, then reports
`RxCsE_DOWNLOAD_2ND_PASS_AXIS` after 193 verified requests. It preserves source
and active model, with actual Offline/cleanup and no reported SDK fault.
All 194 focused checks pass; executable, browser and 106 deployed modules match.
Normal upload retains its Program-collection failure after 349 verified requests.
A supported Program-mode online import/reconnect passes across 188 requests
with one expected logic/audit update. Both preserve the input and confirm actual
Offline/cleanup without a reported SDK fault. The original stopped demo is
restored after validation. Full transfers and Run-mode edits remain unfinished.

Version `26.1023.093633` adds [additional download-batch reception](docs/download-image.md#additional-batch-reception).
The owning client can send a bounded follow-on batch while its completed
temporary namespace remains available. Structural inspection reports record
counts and operation classes; processing and completion remain denied until
the additional records' effects are implemented.
Native download receives all 335 records in the second batch and reaches its
processing boundary after 193 verified requests. It still reports
`RxCsE_DOWNLOAD_2ND_PASS_AXIS`. Normal upload retains its Program-collection
failure after 349 requests. Both preserve source/model and confirm actual
Offline/cleanup without a reported SDK fault. All 150 affected checks pass.
A supported Program-mode online import/reconnect passes across 187 requests
with one expected logic/audit update, source preservation and confirmed
Offline/cleanup without a reported SDK fault. The original stopped demo is
restored after validation.

Version `26.1023.091827` adds source-backed [Local I/O Map metadata](docs/local-io-map.md).
Link Port comes from the canonical Local-module source; Map Address resolves
to the current interpreter object with source and lifetime checks. It also
fixes stale registry bookkeeping after a replaced object's allocation fails.
Native download accepts these fields and reaches its second transfer batch
after 182 verified requests. That batch remains unsupported. Normal upload
still fails Program collection after 348 requests; a supported Program-mode
import/reconnect succeeds across 188 requests with one expected audit update.
All three trials preserve the input and confirm actual Offline/cleanup without
a reported SDK fault. All 106 affected checks pass.

Version `26.1023.085003` adds capture-informed [temporary Program and Routine enumeration](docs/download-image.md#completed-program-and-routine-catalogs).
The downloading client can enumerate headers backed by its own completed image,
with exact parent scope, bounded pages and original source/type/object checks.
These handles do not install native code or replace the active project.
Native download accepts both Routine headers and the Program header, then
reaches an I/O Map instance query with fields 9 and 13 unavailable. It verifies
183 requests and preserves source/model with actual Offline/cleanup and no
reported SDK fault. Normal upload retains its Program-collection failure after
349 requests. A supported Program-mode import/reconnect succeeds across 190
requests with one expected logic/audit update. All 117 affected checks pass;
the app, executable, browser and appliance report this version. Full native
transfers and Run-mode Test/Untest/Assemble remain unfinished.

Version `26.1023.083349` adds capture-informed [temporary Data Table enumeration](docs/download-image.md#completed-download-symbol-catalog).
Descriptor handles and value addresses resolve to the completed image's own
typed tables and bounded storage; they do not expose physical memory.
Native SDK download accepts all 16 table rows and both Program-scoped Symbols,
then advances to Program/Routine handle enumeration. It now reports
`RxCsE_DOWNLOAD_OF_PROGRAMS_FAILED` after 179 verified requests, with source and
active model preserved and actual Offline/cleanup confirmed without a reported
SDK fault. Complete native download remains unfinished.
Version `26.1023.082234` retains the complete temporary Symbol catalog after
transport deletion, including internal Symbols and otherwise hidden tags.
Native download accepts all 18 controller Symbols and advances to the Data
Table query across 180 verified requests. It still reports tag download failure.

On `26.1023.083349`, two SDK `FinalizeEdits` imports and reconnects pass across
299 verified requests in stopped Program mode. Tag values remain unchanged
until a model scan executes both edits. Normal upload still stops at Program
collection after 349 verified requests. All three cases confirm source
preservation, actual Offline/cleanup and no reported SDK fault. Complete native
transfers and Run-mode Test/Untest/Assemble remain unfinished.

The preceding `26.1023.075900` release adds capture-informed [completed-batch download status](docs/download-image.md#completed-batch-execution-status).
Native download accepts this result and advances from device failure to tag
failure, across 176 verified requests, with the active model and original files
preserved. Complete native download support remains unfinished.

Version `26.1023.073618` adds an explicit [new-project upload diagnostic](docs/upload-merge-targets.md#new-project-upload)
and [SDK FinalizeEdits imports in Program mode](docs/supported-routine-edits.md#sdk-finalizeedits-in-program-mode).
The new-project path uses a fresh output ACD rather than opening a merge
baseline. Native deadlines retain an unknown outcome instead of reporting a
confirmed SDK failure or Offline state. Program-mode finalization is separate
from Run-mode Test/Untest/Assemble; complete native transfers remain unfinished.

**Status: experimental.** Native validation on `.162` demonstrates Go Online and
Go Offline to the tested demo with the v35 SDK in anonymous compatibility mode.
Remote Run/Program requests and actual mode reads also pass on `.162`.
Supported [Program-mode routine imports](docs/supported-routine-edits.md) were
validated on `.162`. Supported imports update the custom execution model while
preserving the original source files.

Version `.162` adds source-checked [Programs without an assigned main Routine](docs/unassigned-main.md),
including populated ordinary RLL catalogs. The scheduler runs no implicit main;
prescan and other Programs retain their behavior. Null main references and
stored Routine metadata require matching source and current interpreter objects.
All 248 affected checks and live signed metadata reads pass. A native Run/Program
cycle verifies 108 requests and advances scans without executing a main Routine
or changing tag values. Two upload targets, one containing the stored Routine
and one without it, both stop after 356 verified requests before source retrieval;
all 22 Routine fields succeed with no observed endpoint attribute gaps. This
comparison does not establish the SDK's process-wide cache state. Download verifies
175 requests and prepares 909 temporary records, then stops at the result query
without committing an active image. Full Routine transfers remain unfinished.
The demo Go Online/Offline check verifies 74 requests; supported Program-mode
import/reconnect verifies 190 with one expected audit update. All six native
cases confirm Offline/cleanup and original-file preservation without a reported
SDK fault. The original stopped demo is restored with zero scans and audit
updates; webpage, executable and appliance versions match `.162`.

Version `.161` adds source-bound [Routine Name reads](docs/routine-names.md)
for Program- and AOI-scoped Executable objects, plus bounded offline decoding.
The read preserves source spelling and requires the original child/parent and
project bindings. Code/edit-state guards remain independent; writes stay denied.
All 153 affected checks and live signed reads pass. SDK connection verifies 74
requests; supported Program-mode import/reconnect verifies 188. Routine names
remain readable after replacement while guarded code-state fields stay
unavailable. Original files are preserved, Offline/cleanup is confirmed and no
SDK fault is reported. The original zero-scan/audit demo is restored; webpage,
executable and appliance versions match. The one-NOP comparison on `.160`
retains the separate Program upload failure before source retrieval. Full
Routine upload and download remain unfinished.

Version `.160` adds an explicit [empty simulator component-tracking profile](docs/empty-component-tracking.md)
for Controller fields 33/34. Its empty active/test groups return zero arrays;
native membership and signatures are not imported or verified. Explicit tracked
or ambiguous source retains unavailable fields. All 187 affected checks and
live signed reads pass. Native SDK `UploadAsync` now completes on an owned
same-project fixture with an empty Routine catalog, across 971 verified
requests. Actual Offline/cleanup, source/model preservation and no reported
SDK fault are confirmed. This does not prove a valid saved uploaded ACD or
normal projects containing routines. Full download and the complete online-edit
lifecycle remain unfinished.

The normal demo still fails Program/Routine upload after 348 requests. Download
verifies 175 requests and prepares 904 temporary records before its result-query
failure, without committing an active image. Supported Program-mode import and
reconnect verify 188 requests, retain the tracking policy and record one expected
audit update. All five native cases confirm Offline/cleanup and original-file
preservation without a reported SDK fault. The original stopped Program-mode
demo is restored with zero scan/audit state; webpage/executable/appliance
versions match.

The milestone regression runs 1,832 tests: 1,830 pass and two Linux-only listener
checks are skipped on Windows. Two older assertions were updated for the
established Program source-binding guard and aligned Template read extent.

Version `.159` adds [Controller spare-memory configuration](docs/controller-memory-padding.md)
reads for fields 11/12. Explicit source percentages are preserved; complete
source with disabled redundancy selects zero reservation for omitted settings.
The API reports that policy separately from saved properties and live RAM.
All 181 affected checks and live signed reads pass. SDK Go Online/Offline
verifies 74 requests, and the supported Program-mode routine import/reconnect
verifies 192 with one audit update. The empty-routine upload accepts both new
fields after 361 requests; its remaining Controller gaps are State Detection
signatures 33/34. The normal demo retains its Program/Routine upload failure
after 349 requests. Download verifies 175 requests and prepares 904 temporary
records, then stops at the result query without committing an active image.
All five cases confirm Offline/cleanup, original-file preservation and no
reported SDK fault. The original stopped Program-mode demo is restored with
zero scan/audit state. Webpage/executable/appliance versions match. Complete
native transfers and the full Test/Untest/Assemble lifecycle remain unfinished.

Version `.158` adds [initialized Task metadata](docs/task-initial-state.md): zero Start Time before
any successful scan and zero pending/active AOI stack allocation only for a
complete source project with no AOI declarations. The API distinguishes an
initialized timestamp from a measured execution. Unknown or populated AOI
source retains its stack gaps. All 177 affected checks and live signed reads
pass. SDK connection verifies 74 requests; bidirectional Run/Program verifies
107, including real scans and timestamp reset on reload. Normal upload retains
its Program/Routine failure after 349 requests. The empty-routine fixture now
passes all 22 Task fields, Security Authority and trend discovery, then stops
at a later Controller list with fields 11/12/33/34 unavailable after 361
requests. All four cases confirm actual Offline/cleanup without a reported SDK
fault. Original files are preserved; the original zero-scan demo is restored.
Webpage/executable/appliance versions match. Full native transfers and a valid
saved uploaded ACD remain unfinished.

Version `.157` adds source-bound [empty PLC file-mapping discovery](docs/empty-plc-file-mapping.md)
for the catalog request reached by the empty-routine upload fixture. Unknown
or configured mappings remain unavailable, and writes remain denied.
All 252 focused checks and live signed clock/catalog reads pass. SDK Go Online/
Offline verifies 74 requests. Normal upload verifies 349 requests and retains
its Program/Routine failure. The empty-routine fixture now passes PLC file-
mapping discovery and reaches Task collection after 358 requests, with Task
fields 13/22/23 unavailable. All three native cases confirm Offline/cleanup,
source/model preservation and no reported SDK fault. Webpage, executable and
appliance versions match; the original demo is restored to stopped Program
mode with zero scan/audit state. Full native transfers remain unfinished.

Version `.156` adds [software Wall Clock policy](docs/wall-clock-policy.md):
UTC time-zone/DST reads and a CST offset derived from a real monotonic
application counter. This fills the remaining four clock fields for the
accepted source UTC profile. The API identifies the settings as emulator
policy; saved extended DST/time-zone settings are not inferred or imported.
All 218 focused checks and live signed reads pass. SDK Go Online/Offline
verifies 75 requests; Run/Program verifies 108, including continued clock
progress across modes and reload. Normal upload verifies 349 requests, passes
both clock collections and reaches Program/Routine metadata before reporting
Program upload failure. An empty-routine fixture gets past Programs and stops
at PLC file-mapping discovery after 355 requests. No SDK fault is reported;
the original demo is restored. Full native transfers remain unfinished.

Version `.155` adds size-bounded [inactive Time Sync reads](docs/inactive-clock-dataset.md)
for complete source projects that explicitly disable PTP. The 32-field clock
collection includes initialized, unmeasured offsets, empty master/port state
and the application's software identity. Oversized lists return a whole-record
prefix for a suffix request. Enabled or unknown PTP source retains
its unsupported fields. All 204 focused checks pass, and webpage/executable/
appliance versions match. SDK Go Online/Offline passes across 74 verified
requests with source/model preservation and no reported fault.
The supported Program-mode routine import verifies 189 requests and one audit
update; the original demo is restored afterward to stopped Program mode with
zero scans and zero audit updates. This does not complete the Test/Untest/
Assemble lifecycle.
Native upload verifies 189 requests, returns all 32 Time Sync fields successfully
and proceeds to the Wall Clock collection, whose CST offset, time zone and DST
fields remain unavailable. Upload still reports Controller collection failure;
Offline/cleanup and source/model preservation are confirmed without an SDK
fault. Complete native upload/download remains unfinished.

Version `.153` aligns native [Controller and Time Sync schema selection](docs/controller-schema-discovery.md#native-controller-and-time-sync-layout-selection)
with the observed v35 revisions, 15 and 5. The research profile retains revision
1, and the established 16-byte Controller aggregate is preserved. Schema
selection leaves unavailable instance fields and complete native transfers unfinished.
All 151 affected checks pass. The rebuilt app passes live signed schema reads
and SDK Go Online/Offline across 74 verified requests, with source/model
preservation, confirmed Offline/cleanup and no reported fault. Webpage,
executable and appliance versions match.
The mode case verifies 108 requests, both control directions, scan start/stop,
prescan behavior and six expected audit updates. The original demo is then
restored to stopped Program mode with zero scans.
Upload verifies 189 requests and receives the selected revisions, but still
fails Controller collection after the partial Time Sync list and successful
legacy aggregate. Offline/cleanup and source/model preservation are confirmed
without a reported SDK fault. Full upload/download remains unfinished.

Version `.152` adds a [local software-clock identity](docs/software-clock-identity.md)
for native inventory reads. Its Local Clock Information and Clock User Description
share one application-lifetime identity, with unknown accuracy and no asserted
PTP master, hardware OUI or clock discipline. Full native transfers remain unfinished.
All 195 affected checks and live identity/inventory reads pass. The rebuilt
SDK Go Online/Offline case verifies 74 requests with unchanged source/model,
confirmed Offline/cleanup and no reported fault. Webpage, executable and
appliance versions match.
Native upload returns both new fields successfully across 191 verified requests
and proceeds to Controller Get All before reporting its collection failure.
Offline/cleanup and original source/model preservation are confirmed, with no
reported SDK fault. Complete native upload remains unfinished.

Version `.151` adds source-backed [empty Change Log lookups](docs/native-change-log.md)
for the v35 upload cursors, preserving the requested position and original
source. A private minimal fixture now completes SDK `UploadAsync`; its temporary
Controller/clock/Task responses remain unshipped. Normal application upload
still stops earlier at Controller collection.
The optional native probe also supports `--save-uploaded-acd` to save a
successful upload to a new ACD, reopen it Offline and export an L5X for comparison.
The private fixture's save trial faults the SDK before creating a file, so a
valid reconstructed upload remains unproved.
All 222 affected checks pass. The rebuilt application passes live cursor and
Program selector reads and SDK Go Online/Offline across 74 verified requests,
with unchanged source/model state, confirmed Offline/cleanup and no reported
fault in that connection check. Webpage, executable and appliance versions match.
Normal upload verifies 188 requests, then retains the Controller collection
failure with Offline/cleanup and no reported SDK fault.

Version `.150` adds CRC-checked [Program selector reads](docs/program-upload-query.md).
All 60 saved reference replies match the calculated checksum of their returned
selector. The signed response requires a matching source Program and leaves
execution and programming authority unchanged. All 153 affected checks pass.
The rebuilt app passes SDK Go Online/Offline across 74 verified requests, with
source/model preservation and no reported SDK fault. All three new selector
replies pass live signed checks; webpage, executable and appliance versions
match. Upload still fails at the earlier Controller collection stage, with
Offline and cleanup confirmed. Full upload/download remain unfinished.

Version `.149` adds [original ACD metadata value reads](docs/native-metadata-values.md)
through signed, fragmented queries. The running app returns all 1,670 demo
records across 505 replies with byte-for-byte source matches. All 183 affected
checks pass. SDK Go Online/Offline and supported import/reconnect pass with no
reported SDK fault. The upload trial receives nonempty Controller metadata,
then fails at the later Controller collection/Time Sync boundary with Offline
and cleanup confirmed. The original demo is restored; webpage, executable and
appliance versions match. Full upload/download remain unfinished.

Version `.148` adds [fragmented metadata upload decoding](docs/metadata-upload-query.md)
and an offline replay tool. It reconstructs 10,301 saved query exchanges into
nine complete streams and decodes 43,833 records, including numeric values,
reference arrays and string blobs. Capture and checkpoint diagnostics share
the frame decoder. All 183 focused checks pass. The rebuilt app passes SDK
Go Online/Offline across 74 verified requests with source/model preservation,
confirmed cleanup and no reported SDK fault. The webpage, executable and
appliance versions match. Live metadata values, Program query `0x50` and complete
native transfers remain unfinished.

Version `.147` adds [source-bound Metadata Definition names and IDs](docs/metadata-definitions.md)
from the original ACD, including read-only instance discovery and Name reads.
It also corrects the SDK probe's missing unhandled-exception fatal check.
The rebuilt app passes SDK Go Online/Offline and 26 live CIP checks of all 23
definition names, original IDs and class counts. Upload/download trials preserve
the source and model, confirm Offline/cleanup and report no SDK fault.

Version `.146` adds [offline Program upload-query diagnostics](docs/program-upload-query.md)
to capture and checkpoint reports. It checks all 60 saved reference replies and
identifies a later upload boundary exposed by an isolated experiment. It adds no
live responses. A further private response experiment faulted the native SDK;
that hypothesis is retired. After service recovery, the established Go Online/
Offline path passes across 74 verified requests. The rebuilt executable,
appliance and webpage versions match. Full upload/download remain unfinished.

Version `.145` adds [Controller GSV reads](docs/controller-gsv.md) for
AuditValue and ChangesToDetect in ladder and Structured Text, using the same
64-bit values as CIP. The native-saved four-GSV fixture passes live scan/CIP
comparisons, SDK mode control and supported import/reconnect. The rebuilt
executable, appliance and webpage versions match. Full transfers remain unfinished.

Version `.144` adds a [simulator Controller Audit Value](docs/simulator-audit-value.md)
with mask-selected mode and supported routine-transaction events. SDK mode cycles
and a supported import/reconnect pass with the expected audit updates. The rebuilt
executable, appliance and webpage versions match. The isolated upload comparison
returns both audit/configuration fields successfully, leaving four unavailable
Controller fields; its private earlier-stage hypotheses remain unshipped.
Version `.143` added the separate [read-only change-detection configuration mask](docs/controller-change-detection.md)
and named Controller gap diagnostics.

Version `.142` adds [source-checked Controller retention and diagnostic settings](docs/controller-diagnostic-settings.md)
and offline Controller response decoding. The isolated SDK upload reads both
added settings, leaving six unavailable Controller fields. Full native transfer
remains unfinished; private Task-stack assumptions used in that trial remain
unshipped. [Empty Security Authority Binding discovery](docs/security-authority-discovery.md)
continues to require explicit original ACD evidence and matching source hashes.

Task reads also include [source-checked stored settings](docs/stored-task-configuration.md),
[serial execution status and registered slots](docs/task-execution-state.md),
and [measured scan times and live references](docs/task-runtime.md).
The [connectivity history](docs/connectivity-history.md) records earlier discovery,
source-decoding and supported import work with its validation scope.

**Full native upload/download, SDK tag-address discovery and the complete
Test/Untest/Assemble edit lifecycle remain unfinished.** Studio 5000 GUI
monitoring remains unverified. Supported instructions have bounded software
models; this project does not establish native controller equivalence.
See the [roadmap](docs/roadmap.md) and
[connectivity development history](docs/connectivity-history.md) for details.

Application development is maintained on `main`.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Current Support](#current-support)
- [External Device Simulation](#external-device-simulation)
- [Development](#development)
- [Roadmap](#roadmap)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

Studio5000Emulator is being built toward a custom Logix emulator, starting with
explicitly supported instructions and data types. It combines deterministic
local scans, a logic monitor, tag editing, coverage reports and protocol tracing.
Unsupported features are reported before execution where possible.

L5X execution uses Python's standard library. ACD import is optional and converts
a private copy through separately installed native tooling. The execution engine
runs independently after import and does not depend on FactoryTalk Logix Echo.

## Install

### Dependencies

- Windows and Python 3.13 for the tested source workflow.
- Optional ACD import: compatible Studio 5000/Logix Designer SDK tooling and an
  `l5xgit` converter. Configure it in **Import settings**, with
  `LOGIXLAB_CONVERTER`, or by placing `l5xgit` on `PATH`.
- Optional executable build: PyInstaller.
- Optional independent protocol probes: `pycomm3`.

```powershell
git clone --branch main https://github.com/votecoffee/Studio5000Emulator.git
cd Studio5000Emulator
.\INSTALL-AND-RUN.cmd
```

On Windows, double-click **INSTALL-AND-RUN.cmd** in the project root, or run it
as above. It finds Python 3.13 (installing it for the current user through
Windows Package Manager if needed), creates an ignored `.venv`, installs
PyInstaller there, builds the current source and opens LogixLab. Missing
dependencies require internet access. If `winget` is unavailable, install
Python 3.13 with pip and the Python launcher first.

Use `INSTALL-AND-RUN.cmd -InstallOnly` to prepare the executable without
launching a session. After setup, `START.cmd` opens the existing build;
rerun `INSTALL-AND-RUN.cmd` after updating the source to rebuild it.
ACD conversion and the optional VMware appliance need their separate setup.

No additional Python packages are needed to run L5X projects or bundled demos.
To run directly from source, use `py -3.13 -X utf8 source/launch.py`.
See [development guidance](docs/development.md) for optional tooling, including
an offline CIP capture inspector with bounded signed-envelope decoding for
connection research. Its format-4 reports preserve nested object paths and
requested attribute IDs while keeping symbols, values and raw bytes private by
default. These analysis features do not establish native Studio Go Online.
An optional [native SDK acceptance probe](docs/development.md#native-sdk-acceptance-probe)
records connection, tag-read, upload, download-preparation and online-edit attempts against the running emulator
using private ACD copies and reports.
The Linux appliance also exposes a documented subset of
[Ethernet diagnostic counters](docs/ethernet-counters.md) from its virtual NIC
driver, with unavailable diagnostic fields identified in the API.
Read-only [native inventory discovery](docs/native-inventory.md) now covers
source-checked empty I/O, alarm and Add-On Instruction catalogs.
[Data Logging and native policy diagnostics](docs/native-session-policy.md)
include acknowledgements that retain an existing source Timeline UID.
[Nested I/O Connection discovery](docs/io-connection-discovery.md) preserves
parent scope, and [native coordination](docs/programming-coordination.md)
provides an exclusive session lease and a source-backed Local link-address read.
Version `.63` adds a public SDK download-preparation probe and checks that
its TCP clients, lease and scan inhibit clear after cleanup. The actual native
programming service remains unfinished.
Version `.64` adds [owner-scoped download preparation](docs/programming-preparation.md)
and an acknowledgement that retains disabled redundancy from source. The SDK
reached library-object creation in that revision.
Version `.65` adds [temporary library descriptors and signed transfer envelopes](docs/library-staging.md).
The SDK reached Metadata Definition creation in that revision.
Version `.66` adds [temporary metadata definitions](docs/metadata-staging.md).
The SDK reached a metadata-value write in that revision.
Version `.67` adds [typed values for staged definitions](docs/metadata-values.md).
The SDK reached Resilient Transport setup in that revision.
Version `.68` adds [temporary Resilient Transport setup and cleanup](docs/resilient-transport.md).
The SDK reached segmented device-data transport in that revision.
Version `.69` adds [bounded temporary device-transfer fragments](docs/transport-fragments.md).
The normal-source SDK attempt stages a complete device payload and reaches a
denied device-operation request (`0x06`). Active values, library-data writes and
project commit remain unsupported.
Version `.70` adds [structural inspection of compressed device batches](docs/device-payload-inspection.md).
The SDK's staged payload decodes into request records with parent scopes preserved;
batch execution and project commit remain unsupported.
Version `.71` adds [temporary native Template models](docs/template-staging.md).
The SDK batch's 242 Templates pass descriptor and contiguous-write validation;
definitions remain opaque and the remaining batch operations are unsupported.
Version `.72` adds [temporary Diagnostics Message models](docs/diagnostic-staging.md).
Together with Templates, these model 863 of 904 records in the tested download
batch. The remaining 41 records and complete batch execution are unsupported.
Version `.73` adds [temporary object graphs and reference checks](docs/object-staging.md).
All 904 records in the tested batch now have bounded temporary models. Compiled
definitions, device processing and active-project commit remain unfinished.
Version `.74` adds [shared Remote Run/Program control](docs/controller-mode.md).
Native requests start/stop actual scans, and local controls report back through
the native identity. Closing the browser or going offline leaves Run active.
Version `.75` adds [Run-entry initialization](docs/run-entry.md), rearming
`S:FS` and applying bounded prescan rules once per transition. Initialization
failures restore prior values and leave the controller faulted and stopped.
Version `.62` adds [software clock descriptions](docs/clock-descriptions.md),
including the actual app version in native Time Sync inventory reads.
Version `.61` adds [Run Mode Inhibit](docs/run-mode-inhibit.md), with an owning
session's temporary scan guard and cleanup. Its then-current download boundary
was Controller service `0x60`, extended by `.64`.
Full native upload/download and online tag monitoring remain unfinished.
The 1,002-test suite passes on Windows and Linux with expected platform skips.
The rebuilt `.75` runtime passes 291 protocol checks and a 17-step native mode
probe covering repeated Run-entry initialization and bidirectional mode readback.
Current SDK upload, tag-read and download probes still fail their native
acceptance steps. See [Remote Run/Program validation](docs/controller-mode.md#validation-and-limits)
for the mode probe and its limits.

## Usage

Choose a bundled demo or open a complete L5X export. Check **Coverage**, then use
**Step scan** or **Run**. Edit inputs in **Tag Watch** and inspect the logic trace.
**Program** stops continuous scans and preserves the current values. The same
state is used by native Remote Run/Program requests. Scanning runs in the app
and continues with the webpage closed.
Entering Run performs modeled prescan, which can reset non-retentive values and
execute enabled AOI Prescan routines. Repeated Run requests do not repeat it.
For supported Studio edits, select **Connectivity → Allow supported Studio edits**
before connecting. This profile replaces an existing standard RLL routine in
**Program** mode. Changes stay in memory; reload the original project to restore
its logic. Native SDK import is tested; the Studio GUI edit workflow is unverified.
The browser title and header show the running app's full timestamp version;
the header also shows the PLC endpoint IP. On Windows,
its tray icon offers
**Open app** and **Quit LogixLab**; hover over it to see the version and session
address. The icon may appear under the taskbar's hidden-icons arrow.

Use **End session** or **Quit LogixLab** to stop the app and its protocol endpoint.
Closing a browser tab leaves the app running; reopen it from the tray. `--no-tray`
disables the icon for headless runs.

Original project files are preserved. Settings and imported copies normally live
under `%LOCALAPPDATA%\LogixLab`; `--data-dir` selects another private directory.

For a separate PLC IP while Linx retains the host's port 44818, use the optional
[VMware host-only appliance](docs/vmware-appliance.md). After preparation,
`START-VM.cmd` starts it with a localhost browser tunnel and Windows tray controls.
On Windows, its SSH tunnel and helper commands run without console windows.
The appliance answers ICMP ping on its guest IP for IP-scanner discovery. See
[ping and IP scanners](docs/vmware-appliance.md#ping-and-ip-scanners) for the
network to scan. The executable, tray, browser tab and webpage use the PLC
simulator icon bundled with the app.

### CLI

Start a demo with checkout-local session storage:

```powershell
py -3.13 -X utf8 source/launch.py --sample TextLab --data-dir .local/session
```

Generate an offline coverage report:

```powershell
py -3.13 -X utf8 source/launch.py --report source/samples/TextLab.L5X
```

Start the Network Lab's read-only EtherNet/IP endpoint:

```powershell
py -3.13 -X utf8 source/launch.py --sample NetworkLab --eip-port 44818 --eip-profile logix-v35-l85e --data-dir .local/network-session
```

The HTTP UI binds to `127.0.0.1`. The protocol endpoint defaults to that address;
**Bind IP** or `--eip-bind` selects another IPv4 address belonging to this PC.
See [Linx coexistence](docs/connectivity.md#linx-coexistence-and-addresses) if
another application owns port 44818. Protocol access starts disabled unless
requested. Tag writes require **Allow tag writes** or
`--eip-writes`. Use the **Connectivity** tab to start/stop the endpoint and export
its trace. See [connectivity documentation](docs/connectivity.md) for the supported
services, identity profiles and remaining Studio handshake work.
Unsupported attribute reads now show their object, field IDs and read counts in
Connectivity, with the full bounded summary in the exported trace.
Linux endpoints can restart on the same IP and port after closing connected
clients; a conflicting active listener still prevents startup.

### Build an executable

```powershell
py -3.13 -m pip install pyinstaller
powershell -NoProfile -File source/build.ps1
.\dist\LogixLab.exe
```

The build places the executable under `dist/`. `START.cmd` launches that build.
Source-authored L5X demos are bundled; generated ACD files are kept local.

## Current Support

| Area | Available behavior |
| --- | --- |
| Projects | v35 L5X import; optional native ACD-to-L5X conversion on a copy |
| Execution | Supported RLL/ST forms, routine calls, AOIs and deterministic scans |
| Inspection | Coverage checks, tag watch, traces, snapshots and routine harnesses |
| EtherNet/IP | Unicast and Linux broadcast discovery, sessions, Class 3 messaging and atomic tag services |
| Connected reply sizes | Standard/Large Forward Open replies use their negotiated size up to 4,000 bytes, including sequence and signed-message overhead |
| Atomic transfers | Reads/writes, fragmented transfers and integer OR/AND mask updates |
| Structured transfers | Aligned numeric UDTs, explicit user LEN/DATA strings, packed Boolean flags and fragmented reads/writes |
| Native compatibility | Experimental anonymous metadata/tag reads and bounded Run/Program control; fresh keys, checked single/batch MACs and counters; peer authentication unverified |
| Offline protocol analysis | `0x36`/`0x37` singles, `0x38` batches, observed `0x39` transfers and `0x3A` read chunks with bounded detached assembly; decoded captures never execute |
| ACD correlation | Source-bound Change Log identifiers and TagInfo symbol IDs; controller/program instance paths use imported IDs; native SDK passes project identity comparison for the tested demo |
| Upload discovery | Source-bound Program discovery, scoped Data Tables, backed atomic/explicit UDT values and Symbol descriptors, class metadata, bounded empty catalogs, controller settings and Linux Ethernet status/counters; native project transfer remains unfinished |
| Routine metadata | Original scoped Type/instance values, opaque source metadata, live header references and guarded ordinary RLL edit/pause/unsigned state; compiled logic and native signature verification remain unavailable |
| AOI metadata | Original definition and scoped Routine IDs, clean model state, explicit revision/vendor headers and available Routine descriptions; compiled definitions and native AOI edits remain unavailable |
| Native status | Source-checked empty I/O force/LED and SFC force status; module connections, SFC forcing and force writes remain unsupported |
| PLC message mapping | Source-checked empty PCCC mapping descriptors; configured mappings and PCCC commands remain unsupported |
| Time Sync | Source-backed PTP enable/priorities, read-only local UTC time and explicit unsynchronized/empty-port state; PTP networking remains unsupported |
| Catalog refresh | Controller class revision/inventory and source-bound comparison tokens |
| Identity revisions | Read-only virtual hardware revision and profile firmware build, alongside source-based major/minor revision |
| Controller configuration | Source-backed legacy SecurityCode, name/description and read-only pass-through configuration; limited Metadata Definition discovery; security enforcement and pass-through routing remain unsupported |
| Change detection | Explicit source mask plus a simulator-owned Audit Value; SDK mode/import updates and upload field reads verified on `.144`; State Detection signatures remain unsupported |
| Get System Value | Ladder/ST `GSV` for Controller AuditValue/ChangesToDetect into LINT or two DINTs; native-saved fixture and live scan/CIP agreement verified on `.145`; other objects/attributes and SSV remain unsupported |
| Software device metadata | Read-only location/locale and empty trusted-slot/operator state, explicitly identified as emulator defaults |
| File Manager | Read-only class discovery; reports zero emulated storage devices |
| Network metadata | Read-only CIP port/node addresses, IPv4 status/configuration, verified Linux DHCP/DNS flags and actual adapter MAC |
| Device locator | Network-triggered blinking webpage banner with timed expiry and cancellation |
| Studio online | Native SDK Go Online, bidirectional Run/Program control and Go Offline verified for the demo; native project transfer and tag/rung monitoring remain unfinished |
| Supported routine edits | Opt-in Program-mode Standard RLL replacement; consecutive SDK imports, replacement across routines and reconnection using the same updated project verified; edited L5X working-copy export |

Coverage depends on the actual project and execution scope. Full task scheduling,
motion, physical I/O, CIP Safety, FBD/SFC and broad native runtime parity remain
outside the current model. Unknown data and unsupported forms are not silently
replaced with assumed behavior.

Read the [execution model](docs/execution-model.md) before interpreting scan
results, and the [protocol contract](docs/connectivity.md) before using clients.

### External Device Simulation

The **Device I/O** tab enables queued external input writes. External monitors
read consistent cached snapshots without taking the scan lock. A separate MQTT
bridge distributes tag values and accepts atomic input batches from robot,
servo and other device simulators. Writes apply between scans, with scoped
tokens, expiry, duplicate detection and queued/applied/rejected acknowledgements.

See [setup, MQTT topics and the HTTP API](docs/device-io.md). The MQTT dependency
is optional; the app runtime remains standard-library-only. OPC UA/DDS adapters
and a SQL historian are future extensions of the same interface.

## Development

The code, public L5X fixtures, tests and browser assets are under `source/`.
Shared technical documentation is under `docs/`. Build output goes to `dist/`.
See the [community project assessment](docs/community-projects.md) for reusable
components, licensing and conversion-validation results.

Run the behavioral suite from the repository root:

```powershell
Set-Location source
py -3.13 -X utf8 -m unittest discover -s tests -v
```

Store machine-specific notes, private PLC files, settings, captures and test
receipts in ignored `.local/` storage. Generated builds and local reports are
excluded from Git. See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and repository
conventions.

## Roadmap

- Expand supported instructions, data types and execution semantics.
- Add packed BOOL arrays, built-in STRING transfers, predefined structures and more controller metadata.
- Extend the verified native SDK connection to Studio GUI acceptance.
- Resolve native tag addresses and demonstrate SDK/Studio tag and rung monitoring.
- Demonstrate online monitoring before advertising Studio Go Online support.
- Add a host-only networking backend independent of VMware, evaluating free
  container and virtual-machine tooling. See the [milestones and backend comparison](docs/roadmap.md).

## Maintainers

[@votecoffee](https://github.com/votecoffee)

## Contributing

Questions, bug reports and pull requests are welcome through
[GitHub Issues](https://github.com/votecoffee/Studio5000Emulator/issues) and
[pull requests](https://github.com/votecoffee/Studio5000Emulator/pulls).
Please read [CONTRIBUTING.md](CONTRIBUTING.md), use minimal synthetic fixtures,
and include relevant verification with changes.

## License

[MIT](LICENSE) © 2026 votecoffee.
