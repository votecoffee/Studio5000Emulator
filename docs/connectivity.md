# EtherNet/IP connectivity

The endpoint is an experimental explicit-message target backed by the loaded
project's modeled memory. The native v35 SDK can connect to the tested demo in
anonymous read-only mode. Studio GUI monitoring, upload/download, online edits
and native debugger services remain unimplemented or unverified.

## Native SDK online connection

Version `0.6.0-connectivity.30` completed the native SDK sequence: open the
preserved demo ACD, select the emulator path, Go Online, read connected state
**Online**, read controller mode **Program**, and Go Offline. All seven steps
succeeded using the normal app code and fresh challenge keys. The trace verified
87 signed requests, including batch status reads, with no correlation-loss event.
This establishes that SDK connection sequence for one fixture; it does not
establish complete Studio GUI/debugger support or native execution equivalence.

A separate public-SDK hold test stayed Online/Program across five polls spanning
about 17 seconds, without a correlation-loss event. The source ACD remained
unchanged. `GetTagValueBOOLAsync` failed with `RxDA_E_NO_ONLINE_ADDRESS` in every
sample: native tag address discovery is the next blocking layer. Standard CIP
symbolic tag reads are a separate supported interface; this result does not
establish native SDK or Studio tag/rung monitoring.

The rebuilt `.30` appliance also passed the SDK sequence with an additional
final read confirming **Offline**, plus 18 live protocol checks. Typed BOOL and
generic byte-array reads of BOOL/DINT tags all fail the same online-address
check, while an offline BOOL read succeeds. No symbolic or symbol-instance CIP
tag-read request appears for those failures. That points to native address cache
or correlation setup before the data transfer, rather than a type-specific
tag-read response. Exact traces and source-bound receipts remain private.

Version `.31` imports root-tag logical instance IDs from the original ACD's
`TagInfo.XML` metadata. Controller tags retain their Symbol object IDs; program
tags retain both Program and Symbol IDs. Numeric program paths and symbolic
program prefixes address the same modeled tag. Enumeration is ordered by
instance ID and retains gaps, including when unsupported tags are omitted.
When a catalog is bound, unmapped tags are omitted from instance discovery;
supported symbolic reads remain available. Generated IDs are never substituted
inside that catalog.

The Windows importer carries this separate manifest to the appliance. Both ACD
and converted L5X hashes must agree with the correlation manifest, and a failed
rebind leaves the existing project intact. Plain L5X/demo imports clear both
bindings; reset retains them. The API exposes `native_symbols`, and Connectivity
shows the imported symbol count. Unsupported metadata retains an explicit
provenance error while offline L5X conversion remains available.

These IDs are logical object paths, **not compiled controller addresses**.
This closes an instance-routing mismatch without establishing SDK tag address
cache population. Native type layouts and tag/rung monitoring remain separate
acceptance work. Synthetic tests cover sparse 16/32-bit IDs, repeated IDs in
different programs, array elements, paged enumeration, source mismatches,
malformed/compressed XML and signed read/write-denial behavior.
The `.31` suite passes 571 tests on Linux; Windows passes 569 with two
Linux-only skips.

The rebuilt `.31` appliance passed 23 live protocol checks, including reads
through the imported demo IDs. RockwellMCPServer/native SDK then completed all
eight connection steps, including a final Offline-state read, with 86 verified
signed requests. A separate public-SDK read test stayed Online/Program and went
Offline cleanly; typed BOOL and generic BOOL/DINT reads still failed with
`RxDA_E_NO_ONLINE_ADDRESS`. Its complete trace contains no symbolic or
symbol-instance tag-read request. This confirms that logical ID preservation
alone does not resolve native address discovery. The original ACD and all
modeled initial values remained unchanged; Studio GUI monitoring is unverified.

Use the L85E profile with **Experimental native session (read only)** enabled.
Import the matching ACD through the Windows app or VMware tray importer so its
source-bound identifiers accompany the L5X. Plain L5X imports do not establish
an ACD binding. Select the guest's EtherNet/IP address and backplane slot zero
in Linx. The appliance enables native read-only mode by default.

### Native programming status

A successful connection does not establish project transfer or online editing.
These are separate native acceptance stages:

| Operation | Demonstrated result | Remaining work |
| --- | --- | --- |
| SDK Go Online / Go Offline | Demo connects and reports Online/Program | Broader project coverage and Studio GUI verification |
| Native tag/rung monitoring | Tag reads fail `RxDA_E_NO_ONLINE_ADDRESS` | Compiled address discovery and debugger services |
| Native upload | `.47` deployed test preserves supported scalar discovery and Ethernet status; controller collection still fails, with unsupported fields reported | Handler-reference encoding, Ethernet counters, remaining controller metadata, Time Sync, tag kinds and project reconstruction |
| Native download | Attempt fails during scoped controller service setup | Programming session, transfer, validation and atomic model replacement |
| Native online edits | Connection succeeds; rung import fails in native Logix Services | Validated import preparation, edit sessions, test/assemble/rollback and change history |

Version `.33` supports Get Instance List (`0x4B`) for Symbol (`0x6B`), Template
(`0x6C`) and the model's empty Metadata Definition (`0x349`) catalog. Replies
contain packed 32-bit IDs with an inclusive starting-instance cursor. A response
that fills its negotiated budget returns partial-transfer status; it never emits
an empty partial page. Symbols reuse existing external-access checks, program
scopes and source-bound IDs. Templates reuse the software model's existing type
IDs and supported layouts; they are not compiled controller addresses.

The native channel permits these read services after session binding. Two exact
read-only metadata query shapes cover the connection's controller-attribute
query and upload's controller-definition query. Unknown selectors, changed
targets, extra bytes and mutation opcodes remain denied. An isolated native
upload accepted the empty definition list/query, then Template discovery. It
advanced from `RxCsE_UPLOAD_OF_METADATA_DEFS_FAILED`, through
`RxCsE_UPLOAD_OF_DATATYPES_FAILED`, to `RxCsE_UPLOAD_OF_TAGS_FAILED`. The final
trace stops at Data Table class `0x6A`, service `0x4B`. That object's native tag
database and physical-address mapping remain unimplemented; an empty list would
incorrectly discard the demo's tags. This is progress through initialization,
not a successful upload.

A NOP-only online rung-import attempt reported `LgxSrv_E_FATAL_ERROR` and stopped
the native SDK service. No edit was applied. Native edit attempts require further
input and service validation; the emulator does not implement edit commit/test/
assemble operations. All tested controller/source tag values remained intact.

The `.33` suite passes 598 tests on Linux; Windows passes 596 with two
platform-specific skips. Tests cover sparse 32-bit IDs, program isolation,
pagination, private tags, malformed paths/payloads and signed read-only policy.
The rebuilt `.33` appliance passed 26 live protocol checks and all eight native
SDK connection steps, including a final Offline-state read, with 86 verified
signed requests. Upload on that deployed build verified 149 signed requests and
failed at the same Data Table discovery step. Initial model values and the
original ACD remained unchanged; no scans ran during these checks.
Wire-format reference: Sandia's
[Get Instance List reader](https://sandialabs.github.io/PEAT/_modules/peat/modules/rockwell/clx_cip.html#get_instance_list_data_from_reply).
No PEAT source is copied or included in the runtime.

### Data Table catalog

Version `.34` adds Data Table class `0x6A` to discovery and read-only native
dispatch. Get Instance List supports bounded pages and inclusive cursors, for
controller tags and Program/Data Table paths. Instances describe supported,
externally readable base tags. Aliases do not create duplicate storage; private,
safety and unsupported tags are omitted. This is the model's partial catalog,
not a claim of a complete native tag database.

Each table uses its corresponding scoped Symbol ID as a **model-owned** instance
ID. When an ACD catalog is bound, the Symbol link retains its source ID; Data
Table IDs are not imported compiled IDs. Missing mappings are not replaced with
generated IDs inside that binding. Class metadata reports revision 1, the maximum
visible instance and visible instance count, with separate 32-bit counts.

In `.34`, supported instance attributes were `1` (three 32-bit array dimensions),
`2` (the model's type word) and `8` (32-bit Symbol link). Address, data-value
address, formal-type and data-use fields were unavailable. A mixed attribute list keeps
the requested order and individual errors. It does not substitute a logical ID
or zero for a compiled address. The Connectivity API reports these limits in
`data_table`.

An isolated native SDK upload accepted a 12-entry demo Data Table list, then
requested attributes `1, 2, 3, 6, 7, 8, 9` for its first tag. The supported fields
were returned; missing fields `3, 6, 7, 9` returned per-attribute unavailable
status. Upload still failed with `RxCsE_UPLOAD_OF_TAGS_FAILED`. This establishes
the next required descriptor/address layer, not a successful project upload.

The `.34` suite passes 607 tests on Linux; Windows passes 605 with two
platform-specific skips. Tests cover sparse IDs, class counts, scope isolation,
aliases/access checks, source replacement, descriptor ordering, malformed paths,
pagination, signed requests and denied value/writing services. Installed v35
attribute descriptions were consulted for field numbers and widths; vendor
files are not modified or distributed.

The rebuilt `.35` appliance passed 34 live protocol checks. All eight native SDK
connection steps succeeded, including Online/Program reads and final Offline
confirmation, with 85 verified signed requests. A separate native upload verified
148 signed requests, accepted the 12-entry Data Table list and reached the same
unavailable descriptor fields before failing with `RxCsE_UPLOAD_OF_TAGS_FAILED`.
The original ACD and modeled values remained unchanged. Upload, download, native
tag/rung monitoring and online edits remain unfinished.

Version `.35` also fixes the Device I/O panel's tab navigation; browser checks
verified that each of the five tabs shows only its own panel. The served version
and assets match the rebuilt app. Cached device reads and queued-write
cancellation checks passed, with external writes disabled at the end.

Version `.37` adds backed storage for up to 4,096 ordinary, nonconstant base
scalar atoms. Their descriptor attributes `3` and `7` point to separate model
descriptor/value regions; `6` and `9` describe ordinary local storage with zero
data-use flags. These are catalog-local addresses in the software model, not
imported controller addresses or host-process pointers. Descriptor bytes and
current scalar bytes back each allocation. Replacing the project or changing
the exposed scalar catalog replaces its address map.

Data Table service `0x4F` accepts exactly four zero selector bytes followed by
a UINT byte count equal to the full scalar width. Its reply contains raw value
bytes without a tag-type prefix. The native v35 client was observed requesting
one byte for BOOL and four for DINT. Other selectors, partial/oversized reads,
short reply budgets and unknown values return explicit errors. Constants,
arrays, structures, aliases and inaccessible tags do not receive scalar storage;
their supported catalog fields remain available where applicable. General
physical-memory services, formal types and all Data Table writes remain
unsupported. Signed sessions permit this scalar read without enabling setters.

An isolated normal-source `.37` upload candidate returned all 12 supported demo
scalar values, then reached Axis Group class `0xB0`, Get Instance List `0x4B`.
That request remains denied and upload still fails with
`RxCsE_UPLOAD_OF_TAGS_FAILED`. This is partial tag-data transfer, not native
project upload or native tag-monitor acceptance. The fixture's other tag kinds
and later project objects still require implementation. Model values and scan
count were preserved; private wire-shape probes are not included in the app.

The `.37` suite runs 618 tests: Windows passes 616 with two Linux-only skips;
Linux passes 617 with the Windows console check skipped. New checks cover every
supported scalar width, scope isolation, current-value reads, unknown values,
catalog replacement, address/padding boundaries, storage limits and signed
read-only dispatch. Public client implementations were consulted as protocol
references, including [pycomm3's symbol parser](https://github.com/ottowayi/pycomm3/blob/master/pycomm3/logix_driver.py)
and [PEAT's class-instance read routines](https://github.com/sandialabs/PEAT/blob/main/peat/modules/rockwell/clx_cip.py);
the v35 scalar request shape above comes from the local native-client exchange.
No third-party implementation or vendor reference files are bundled.

The rebuilt `.37` appliance passed 40 live protocol checks and all eight SDK
connection steps, including final Offline confirmation, with 85 verified signed
requests. Native upload verified 173 signed requests and accepted all 12 supported
scalar values before failing at Axis Group discovery. The original ACD and
modeled values remained unchanged. A separate unchanged public-SDK probe stayed
Online/Program and went Offline; typed BOOL and generic BOOL/DINT reads still
failed with `RxDA_E_NO_ONLINE_ADDRESS`. The scalar upload service does not yet
resolve the SDK's native online-address cache or establish tag/rung monitoring.

### Empty motion catalogs

Version `.38` supports Get Instance List (`0x4B`) for Axis Group (`0xB0`),
Axis (`0xB1`) and Coordinate System (`0x32B`) only when the source establishes
that all three catalogs are empty.
An empty result has success status and no instance IDs. The starting cursor is
inclusive, as for the other instance lists. These paths must be global and
include an instance cursor; attributes, payload bytes and program scopes are
rejected. Signed read-only sessions allow these lists without enabling setters.

The check requires a complete Controller export (`ContainsContext="false"`),
one target Controller and one complete controller Tags section. It inspects
source XML before unsupported tags can be filtered out of the runtime. A
`MOTION_GROUP`, `AXIS_*` or `COORDINATE_SYSTEM` data type, motion-specific data format/parameters,
unknown controller-tag entries or ambiguous context prevents an empty response.
Such sources return unavailable (`0x0C`). These classes do not invent instance IDs,
class revisions, axis configuration or motion execution. Catalog availability
is exposed in connectivity state and follows project replacement.

The tag and configuration shapes are documented in
[Rockwell's Import/Export reference, chapter 6](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf).
The installed v35 object descriptions identify classes `0xB0`, `0xB1` and `0x32B`;
the native upload exchange supplies their list request shapes. No vendor files
are included. An isolated `.38` candidate read all 12 supported demo scalars and
accepted all three empty motion lists, then requested Digital Alarm class
`0x331`, Get Instance List `0x4B`. That request remains denied; upload still fails
`RxCsE_UPLOAD_OF_TAGS_FAILED`. Model values and scan count were preserved.
Complete upload and native monitoring remain unverified for this revision.

The `.38` suite runs 624 tests: Windows passes 622 with two Linux-only skips;
Linux passes 623 with the Windows console check skipped. Checks cover source completeness, motion tag/data
detection, project replacement, instance cursors, invalid paths/payloads, object
inventory and signed read-only dispatch. Motion detection uses the original XML,
including definitions that the execution model cannot parse.

The rebuilt `.38` appliance passed 49 live protocol checks and all eight SDK
connection steps, with 85 verified signed requests and final Offline confirmation.
Its upload recheck verified 177 signed requests: all 12 supported scalar values
and the three empty motion catalogs were accepted before the Digital Alarm list
failed. This remains a partial upload. The original ACD, source-bound project
configuration, model values and scan count were preserved.
A separate unchanged public-SDK probe verified 93 signed requests, stayed
Online/Program without correlation loss and finished Offline. Typed BOOL and
generic BOOL/DINT reads still failed `RxDA_E_NO_ONLINE_ADDRESS`; empty motion
discovery does not resolve native tag/rung monitoring.

### Empty instruction alarm catalogs

Version `.39` supports Get Instance List (`0x4B`) for Digital Alarm (`0x331`)
and Analog Alarm (`0x332`) when complete source establishes an empty alarm
catalog. Replies contain no IDs and use success status. These lists require a
global class path with an instance cursor, no attribute and no payload. Setters,
other alarm services and nonempty catalogs remain unsupported. Signed sessions
allow the lists without granting write permission.

The source check includes controller/program tags and AOI local declarations,
before runtime type filtering. `ALARM_DIGITAL` / `ALARM_ANALOG` data types,
`Data Format="Alarm"`, alarm parameters or alarm configuration prevent an empty
reply. Incomplete/context exports, ambiguous tag/program containers and unknown
tag entries also return unavailable (`0x0C`). Connectivity state reports
availability and a zero count only for a proven empty catalog; project replacement
recomputes that state. Alarm execution, configuration, events, acknowledgements
and tag-based alarm discovery remain separate unfinished work.

[Rockwell's Import/Export reference, chapter 6](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
documents the alarm tag/configuration shapes. The installed v35 object
descriptions identify Digital and Analog Alarm class numbers; vendor files and
private native exchanges are kept outside the public source tree.

An isolated `.39` native candidate accepted the demo's 12 supported scalar reads,
three empty motion lists and both empty alarm lists, then requested HMI Button
Control class `0x36E`, Get Instance List `0x4B`. That request remains denied;
upload still fails `RxCsE_UPLOAD_OF_TAGS_FAILED`. Model values and scan count
were preserved. This is partial transfer, not complete native project upload.

The `.39` suite runs 631 tests: Windows passes 629 with two Linux-only skips;
Linux passes 630 with the Windows console check skipped. New checks cover
controller/program/AOI alarm declarations, alarm data/configuration, incomplete
source, replacement, cursors, malformed/scoped requests and signed read-only
dispatch. Alarm configuration and runtime semantics remain unsupported.

The rebuilt `.39` appliance passed 55 live protocol checks and all eight SDK
connection steps, including final Offline confirmation, with 85 verified signed
requests. Its upload trace verified 180 signed requests and successful replies
for all 12 supported scalars, three motion catalogs and both alarm catalogs.
The next HMI Button Control list was denied. This deployed upload job ended
indeterminate after an SDK worker timeout, rather than a completed failed-upload
result. No complete upload is demonstrated. The worker closed, network clients
disconnected, and the original ACD, model values and scan count were unchanged.
A subsequent unchanged public-SDK probe verified 93 signed requests, stayed
Online/Program without correlation loss and finished Offline. Typed BOOL and
generic BOOL/DINT reads still failed `RxDA_E_NO_ONLINE_ADDRESS`. The timeout did
not prevent that later connection check; tag/rung monitoring remains unfinished.

### Empty HMI Button Control catalog

Version `.40` supports Get Instance List (`0x4B`) for HMI Button Control
(`0x36E`) when complete L5X source establishes an empty HMIBC catalog. It uses
the same global cursor and payload/path validation as the other instance lists.
The source check includes controller/program tags and AOI local declarations,
before runtime type filtering. `HMIBC` data types, HMIBC data formats or
HMIBC-specific elements prevent an empty reply. Incomplete or ambiguous source
also returns unavailable (`0x0C`). Project replacement recomputes the catalog.
Button configuration, runtime behavior and client ownership are not implemented.

Alarm and HMIBC readers share the export-context and declaration checks in
`tag_catalog.py`; their object-presence checks are independent. A source with
alarm objects can establish an empty button catalog, and vice versa.
[Rockwell's Import/Export reference, chapter 6](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
documents the HMIBC source shape. The installed v35 object description identifies
class `0x36E`. Vendor files are not bundled.

The `.40` candidate reads all 12 supported demo scalars and accepts three empty
motion lists, two alarm lists and the HMIBC list. It then sends the exact request
`3b02204e2400` to Base Energy class `0x4E`, instance zero. The model has no energy
implementation. A bound signed session now returns unsupported-service (`0x08`)
for that exact probe without dispatching it or inventing a successful energy
response. Other instances, attributes, payloads and setters retain the existing
policy. Unbound sessions still receive permission denied.

The native client accepts that error and falls back to Get Instance List `0x4B`
on Base Energy class `0x4E`. That list remains denied and upload fails
`RxCsE_UPLOAD_OF_TAGS_FAILED`. The model's values and scan count were preserved.
No energy inventory, measurements or controls, complete project upload or native
tag/rung monitoring are demonstrated by this change.

The `.40` suite runs 641 tests: Windows passes 639 with two Linux-only skips;
Linux passes 640 with the Windows console check skipped. New checks cover HMIBC
presence across scopes, independent alarm/button catalogs, invalid export roots,
source replacement and signed requests. The energy-probe checks verify session
binding, exact request matching, batch errors, no inner dispatch and denied writes.

The rebuilt `.40` appliance passed 58 live protocol checks and all eight native
SDK connection steps, including final Offline confirmation, with 85 verified
signed requests. Its upload recheck verified 180 signed requests: the 12 supported
scalar values and all six empty motion/alarm/HMIBC catalogs were accepted. The
unsupported energy probe triggered the Base Energy instance-list fallback,
which remains denied. The SDK upload job failed with `RxCsE_UPLOAD_OF_TAGS_FAILED`.
The original ACD, model values and scan count were unchanged.

A separate unchanged public-SDK probe verified 93 signed requests, stayed
Online/Program without correlation loss and finished Offline. Typed BOOL and
generic BOOL/DINT reads still failed `RxDA_E_NO_ONLINE_ADDRESS`; HMIBC discovery
and the energy error response do not resolve native tag/rung monitoring.

### Bounded empty energy inventory and Message catalog

Version `.41` provides Get Instance List (`0x4B`) for Base (`0x4E`), Electrical
(`0x4F`) and Non-Electrical (`0x50`) Energy. This software controller has no energy
meters, proxies, aggregation or controls. An empty inventory is available only
for complete ordinary-tag projects with no custom data types, AOIs, external
modules or explicit energy declarations. The only optional module is the
controller itself, with a matching catalog number. Unknown/context configuration,
unrecognized controller sections, tag types or data formats return unavailable
(`0x0C`). This deliberately restricts larger projects until their inventory can
be represented; it does not report a physical controller's energy inventory.

Energy lists use global paths, inclusive cursors and the same strict payload/path
checks as other lists. The exact no-payload `0x3B` probe at instance zero for
each energy class returns unsupported (`0x08`) without dispatch, allowing the
native client to fall back to `0x4B`. Other probe variants and all signed setters
remain denied. No measurements, class revisions or energy control state are
invented. [ODVA's energy object overview](https://www.odva.org/wp-content/uploads/2022/06/2012_ODVA_Conference_Blair_FINAL.pdf)
describes the three related classes; no third-party implementation is bundled.

Message class `0x8D` also supports a source-checked empty list. Complete source
must contain no `MESSAGE` types, Message data format or `MessageParameters`,
including declarations in programs and AOIs. Alarm text messages alone do not
constitute MESSAGE objects. Nonempty/ambiguous catalogs return unavailable.
Message configuration, transmission and MSG instruction execution are not
implemented. The [Import/Export reference, chapter 6](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
documents the source shape; the installed v35 object description identifies the
class number.

The `.41` candidate accepted 12 supported scalar reads, the prior six empty
motion/alarm/HMIBC lists, Base and Electrical Energy lists, and the Message list.
The Non-Electrical class is covered by model/protocol tests; it was not requested
in that native exchange. Upload then enumerated Symbol class `0x6B` and requested
attributes `1,2,3,5,6,7,8,10,11,12,14,9` for the first supported tag. Unsupported
address/configuration fields cause partial attribute-list status (`0x0A`);
upload still fails `RxCsE_UPLOAD_OF_TAGS_FAILED`. Model values and scan count
were preserved. Full transfer and native tag/rung monitoring remain unfinished.

The `.41` suite runs 660 tests: Windows passes 658 with two Linux-only skips;
Linux passes 659 with the Windows console check skipped. Energy checks cover the
ordinary-source boundary, unknown configuration, module identity/context,
replacement, all three energy lists and negative newer probes. Message checks
cover declarations across scopes, data/configuration, alarm text, malformed
paths and signed read-only dispatch.

The rebuilt `.41` appliance passed 70 live protocol checks. All eight native SDK
connection steps passed across 85 verified signed requests, ending Offline.
Native upload accepted the same 12 scalar reads and nine empty catalog responses
across 187 verified signed requests, then failed at the Symbol attribute list
above. A separate SDK hold/read check completed 93 verified signed requests,
reported Online/Program and ended Offline without correlation loss. Typed BOOL,
generic BOOL and generic DINT reads still report `RxDA_E_NO_ONLINE_ADDRESS`.
These checks preserved the source ACD, model values and zero scan count; network
writes remained disabled. Deployed modules, browser assets and the Windows build
matched the source, including the displayed version. Studio GUI monitoring,
complete upload/download and native online edits remain unverified or failing.

### Backed scalar Symbol descriptors

Version `.42` adds Symbol attributes `3` (value address), `5` (Symbol descriptor
address), `6` (ordinary-base control), `7` (element size), `12` (Data Table link)
and `14` (no signature types) for supported ordinary nonconstant base scalars.
The source also supplies `9` (Standard tag) and `11` (constant flag). Existing
name, type, dimensions and external-access fields retain their encoding.
Single/list reads and `0x55` enumeration use the same values; unavailable storage
fields return unsupported rather than a zero address. Formal types and logical
references remain unsupported. The [pycomm3 Symbol discovery implementation](https://github.com/ottowayi/pycomm3/blob/master/pycomm3/logix_driver.py)
independently identifies the common address/control fields; installed object
descriptions identify the additional fields. No vendor files are distributed.

The value address points into the existing model value bank. The Symbol address
points into a separate bounded bank containing a 32-byte model descriptor with
value/table links, type, size, instance, control and scalar dimensions. This is
an explicit model layout, not a recovered firmware layout. Reads cannot cross
cell boundaries or expose padding/host memory. Program scopes retain distinct
storage even when their instance numbers match. Catalog/source/access changes
rebuild or reject the map. Arrays, structures, aliases, constants and inaccessible
tags do not gain this scalar storage. Network setters remain denied in the
anonymous native session.

The `.42` candidate passed all 12 demo scalar Symbol descriptor lists and the
preceding scalar reads/catalogs across 199 verified signed requests. Upload
advanced to controller/device collection and failed
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`. Ethernet Link class `0xF6`
attributes `1,2,4,5,6,7,8,9` and Controller `0x8E` attributes
`3,6,1,7,8,16` remain incomplete. This is progress through native tag discovery,
not complete tag/project transfer or demonstrated SDK tag monitoring.

The suite runs 670 tests: Windows passes 668 with two Linux-only skips; Linux
passes 669 with the Windows console check skipped. New tests cover exact widths,
backed address links, atomic values, scoped IDs, source replacement, access
changes, unavailable tag kinds, range/response bounds and signed setter denial.

The rebuilt `.42` appliance passed 82 live protocol checks, including the full
native-requested Symbol attribute list and address/link/size checks. All eight
SDK connection steps passed across 85 verified signed requests, ending Offline.
Upload reproduced the candidate's 199 verified requests and controller-collection
failure after accepting all 12 supported Symbol descriptors. A separate
hold/read test completed 93 verified requests, reported Online/Program and ended
Offline without correlation loss. Typed BOOL, generic BOOL and generic DINT SDK
reads still fail `RxDA_E_NO_ONLINE_ADDRESS`. The original ACD, modeled values
and zero scan count were preserved; network writes stayed disabled. Deployed
modules, webpage assets and the Windows executable matched the source and version.
Full upload/download, native online edits and Studio GUI monitoring remain
unfinished or unverified.

### Controller settings and Linux Ethernet status

Version `.43` exposes Controller compatibility attributes `3` (communication
time slice), `16` (share unused slice) and `8` (no multi-workstation edit slot).
Explicit `TimeSlice` values from 10 through 90 and `ShareUnusedTimeSlice` values
`0`/`1` use the source; invalid explicit values stay unavailable. Missing values
use declared model compatibility settings of 20 and 1, with default provenance
reported by the Connectivity API. These settings do not change the software
scheduler or claim native CPU time allocation. Rockwell's
[Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
documents the source fields. The
[Design Considerations reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm094_-en-p.pdf)
also distinguishes newer controllers where the system overhead time slice does
not apply.

Complete source can establish that power-loss and fault handlers are absent.
Named, UID-only, context, namespaced or ambiguous declarations remain unknown.
Their native reference encoding is unresolved, so attributes `1` and `6` remain
unsupported even when source absence is known. Handler execution and edit-slot
ownership are not implemented. Power-loss handlers also appear in the model's
unsupported-execution issues when declared.

Ethernet Link `0xF6` instance 1 adds read-only Linux attributes `1`, `2`, `6`, `7`,
`8` and `9`: speed, flags, interface control, type, operational and administrative
state. The selected interface's sysfs and read-only `ETHTOOL_GSET` observations
provide the values. Negotiation status is inferred from carrier and the observed
autonegotiation configuration. No adapter or PHY setting is changed. The first
query caches the same interface used for IP/MAC metadata; restarting the endpoint
refreshes it. Missing, non-Ethernet, unsupported or unrepresentable observations
stay unavailable without invalidating IPv4/MAC data. Windows retains IPv4/MAC
discovery; these additional link observations currently require Linux.

The wire fields follow Rockwell's
[Ethernet Link object table](https://literature.rockwellautomation.com/idc/groups/literature/documents/qs/2080-qs002_-en-e.pdf)
and the Linux [ethtool UAPI](https://github.com/torvalds/linux/blob/master/include/uapi/linux/ethtool.h).
Interface/media counters `4` and `5` remain unsupported. A mixed attribute list
preserves supported values and per-field errors; no counter is replaced with an
invented zero. Network setters remain rejected even when tag writes are enabled.

The `.43` normal-source candidate preserved all 12 scalar reads and Symbol lists
across 199 verified signed requests. It returned the three Controller settings
and six Ethernet status fields, while the lists retained errors for handler
references and counters. Upload still fails
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`; this does not establish which
remaining field or object is responsible. Private codec experiments did not
resolve the failure and are not part of the shipped protocol.

The suite runs 682 tests: Windows passes 680 with two Linux-only skips; Linux
passes 681 with the Windows console check skipped. New checks cover source and
default provenance, invalid settings, incomplete/ambiguous handler declarations,
exact link encodings, read-only ioctl framing, missing driver data, cached
interface selection, malformed requests and signed setter denial.

The rebuilt `.43` appliance passed 93 live protocol checks. Its eight SDK
connection steps passed across 85 verified signed requests, ending Offline.
Deployed upload reproduced the candidate's responses across 199 verified
requests and retained the controller-collection failure. A separate SDK hold/read
check completed 93 verified requests, reported Online/Program and ended Offline
without correlation loss. Typed BOOL, generic BOOL and generic DINT reads still
fail `RxDA_E_NO_ONLINE_ADDRESS`. Source ACD bytes, model values and zero scan count
were preserved, with network writes disabled. Deployed modules, browser assets,
displayed version and the Windows artifact matched the source. These checks do
not establish native tag/rung monitoring, complete upload/download or online edits.

### Unsupported attribute diagnostics

Version `.44` adds `attribute_gaps` to the Connectivity state and trace export.
It records unsupported single-attribute reads and the unavailable fields in a
mixed attribute list, including object class, instance, program scope, service,
field IDs/names, status `0x14`, count and last-seen time. Protocol replies are
unchanged. A missing field does not establish why an SDK operation failed.

The endpoint retains at most 64 groups and the panel displays the eight most
recent. Repeated reads increment a group's count. Only the current project load's
groups are exposed; a new endpoint starts empty. The summary contains no field
values, message bytes or session keys. Scope names can still identify project
content, and the existing trace events can contain tag values.

The suite runs 690 tests: Windows passes 688 with two Linux-only skips; Linux
passes 689 with the Windows console check skipped. New checks cover grouping,
eviction, scoped reads, project replacement, immutable snapshots, malformed
requests and unchanged partial replies. The normal-source candidate preserves
12 scalar reads, their Symbol descriptors and nine empty catalogs across 197
verified signed requests. Its last ordinary read is the Ethernet Link list, with
counter attributes `4` and `5` unavailable; this exchange does not request the
Controller handler list. Upload still fails
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`. The client sequence can vary;
the diagnostic reports observed requests rather than assuming the earlier order.

The rebuilt `.44` appliance passed 93 live protocol checks, including the new
field summaries. Its eight SDK connection steps passed across 85 verified signed
requests and ended Offline. Deployed upload verified 196 signed requests and
reproduced the candidate's supported replies and controller-collection failure,
without requesting the handler list. A separate hold/read check completed 93
verified requests without correlation loss and ended Offline; the three SDK tag
reads still fail `RxDA_E_NO_ONLINE_ADDRESS`. Source ACD bytes, model values and
zero scan count were preserved with writes disabled. Deployed modules, served
browser assets, displayed version and Windows artifact matched the source. A
hidden browser check confirmed the field summary renders without JavaScript
errors. Full upload/download, online edits and native monitoring remain unfinished.

### TCP/IP configuration status

Version `.45` adds TCP/IP Interface `0xF5` instance 1 attribute `1` when the
selected IPv4 configuration is available. Attributes `2` and `3` report DHCP/DNS
capability and startup/control flags only for the recognized Linux combination:
one explicit ifupdown DHCP stanza and a live udhcpc process whose executable,
interface and PID-file arguments match. Configured resolver addresses determine
whether DNS is enabled. Includes, mappings, duplicate or static declarations,
other managers, missing files and stale/mismatched processes remain unavailable.
The same lazily captured interface snapshot supplies all network fields.

The Configuration Settable flag stays clear. Single/list reads do not change
adapters, spawn a DHCP client or query a DNS server. Network setters remain
rejected, including with tag writes enabled. Unsupported fields retain their
individual errors in mixed lists, and the diagnostic now names TCP/IP fields.
The wire flags follow Rockwell's [TCP/IP object tables](https://literature.rockwellautomation.com/idc/groups/literature/documents/qs/2080-qs002_-en-e.pdf).

An isolated SDK diagnostic accepted the five-field TCP/IP list and next requested
PCCC mapping object `0x67` attributes `1`/`2`, which remain unsupported. That diagnostic
temporarily substituted earlier missing metadata; those substitutes are excluded
from the app and this result does not demonstrate successful native upload.

The suite runs 701 tests: Windows passes 699 with two Linux-only skips; Linux
passes 700 with the Windows console check skipped. Checks cover exact flags,
missing and mismatched clients, ambiguous configuration, unavailable observations,
cached interface selection, mixed lists and denied setters. The normal-source
candidate preserves 12 scalar reads/descriptors and nine empty catalogs across
196 verified signed requests, then still fails controller collection after the
Ethernet Link list. It does not reach the new TCP/IP list in that exchange.

The rebuilt `.45` appliance passed 97 live protocol checks, including single and
list reads of the observed TCP/IP flags. Its eight SDK connection steps passed
across 85 verified signed requests and ended Offline. Deployed upload reproduced
the candidate's partial transfer and controller-collection failure across 196
verified requests. A separate hold/read check completed 93 verified requests
without correlation loss and ended Offline; typed BOOL, generic BOOL and DINT
reads still fail `RxDA_E_NO_ONLINE_ADDRESS`. Source ACD bytes, model values and
zero scan count were preserved with writes disabled. Deployed modules, served
web files, app version and Windows artifact matched source. Native GUI monitoring,
full upload/download and online edits remain unfinished.

### Empty PLC message mapping metadata

Version `.46` adds read-only PCCC object `0x67` discovery and instance 1
attributes `1` (PLC-2 file, UINT) and `2` (mapping descriptor, UDINT). Their empty
values are zero. This subset is available only when a complete Controller export
establishes that no PLC message mappings are configured.

The reader examines `ProduceInfo` attributes `PLC2Mapping` and `PLCMappingFile`
before runtime tag filtering. Absent mapping attributes and explicit disabled
PLC-2 flags (`0`/`false`) can establish empty. A configured file, file zero,
malformed or ambiguous reference, misplaced attribute, context, namespace variant,
UID-only reference or duplicate declaration leaves the descriptor unavailable.
Unknown source is never returned as an empty mapping. Class metadata advertises
one model instance, and the Message Router inventory includes the object.

Rockwell's [Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
locates these attributes on `ProduceInfo`. A native offline L5K-to-ACD-to-L5X
round-trip preserved a configured file mapping there. Configured mappings,
compiled references, Execute PCCC and setters remain unsupported, including with
tag writes enabled. Connectivity state exposes `pccc_mapping` and its limits.

An isolated SDK diagnostic accepted the source-checked zero descriptors and next
requested Time Sync `0x43`. The diagnostic supplied temporary substitutes for
earlier missing metadata; those substitutes are excluded from the app. Partial
Time Sync settings did not resolve controller collection. This is not a completed
native upload or proof of PCCC execution.

The suite runs 713 tests: Windows passes 711 with two Linux-only skips; Linux
passes 712 with the Windows console check skipped. New checks cover source
completeness, mapping flags/references, namespaces and scope, exact empty wire
values, mixed-list errors, object inventory, project replacement and denied
commands. The normal-source candidate preserves all 12 scalar reads and Symbol
descriptors and nine empty catalogs across 198 verified signed requests. It
returns the existing Controller settings and Ethernet status, but still fails
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`; the normal exchange does not
reach PCCC mapping. Client request ordering can vary.

The rebuilt `.46` appliance passed 102 live protocol checks, including the new
PCCC class revision, single/list empty descriptors and denied Execute PCCC.
Its eight SDK connection steps passed across 85 verified signed requests and
ended Offline. Deployed upload verified 196 requests and retained the same
12 scalar reads/descriptors and nine empty catalogs, but failed controller
collection after the Ethernet Link list. This exchange did not request the
Controller handler list. A separate hold/read check completed 93 verified
requests without correlation loss and ended Offline; SDK BOOL/DINT reads still
fail `RxDA_E_NO_ONLINE_ADDRESS`. Source ACD bytes, model values and zero scan
count were preserved with writes disabled. Deployed modules, browser assets,
version and Windows artifact matched source. Full upload/download, native
monitoring and online edits remain unfinished.

### Time Sync configuration

Version `.47` adds read-only Time Sync object `0x43` configuration. Instance 1
returns attribute `1` (PTP enable), `16` (priority 1) and `17` (priority 2), each
encoded as one byte. These values come from explicit `PTPEnable`, `Priority1`
and `Priority2` attributes on the Controller's `TimeSynchronize` element in a
complete L5X export. Missing fields have no assumed defaults. Invalid fields
remain unavailable; ambiguous, duplicate, nested, context, namespace or UID-only
declarations do not establish settings. Priorities accept decimal values 0–255.

This reports project configuration, including a requested PTP enable value;
it does not run a PTP engine. Synchronization status, dynamic clock readings,
offsets, clock descriptions, ports and vendor-specific fields are unsupported.
Single reads return `0x14` for those fields. Attribute lists retain the supported
settings and report per-field errors for the remainder. The native 32-field
upload query therefore remains a partial reply, rather than invented clock data.
Connectivity diagnostics label the missing Time Sync fields; state exposes
`time_sync` with available attributes and explicit implementation limits.

Class metadata describes one model instance at revision 1, and Message Router
inventory includes the object. Setters, Get Attributes All and clock/network
operations remain unsupported even when tag writes are enabled. Configuration
reads never alter host clocks or start PTP traffic.

The suite runs 724 tests: Windows passes 722 with two Linux-only skips; Linux
passes 723 with the Windows console check skipped. The normal-source native
candidate preserves 12 scalar reads and Symbol descriptors and nine empty
catalogs across 195 verified signed requests, but still fails
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED` after the Ethernet Link list.
It does not request Time Sync. Source bytes, tag values and zero scan count
were preserved with writes disabled; complete upload remains unsupported.

The rebuilt `.47` appliance passed 109 live protocol checks, including all three
source settings, class revision, list encoding, unavailable synchronization
status and denied writes. Its eight native SDK connection steps passed across
84 verified signed requests and ended Offline. Deployed upload preserved the
same 12 scalar reads/descriptors and nine empty catalogs across 196 verified
requests, but still failed controller collection after the Ethernet Link list;
it did not request Time Sync or the Controller handler list. A separate hold/read
check completed 92 verified requests without correlation loss and ended Offline;
typed/generic BOOL and DINT reads still fail `RxDA_E_NO_ONLINE_ADDRESS`. Original
ACD bytes, tag values and zero scan count were preserved with writes disabled.
Deployed modules, served web assets, version and Windows artifact matched source.
Native GUI monitoring, complete upload/download and online edits remain unfinished.

### Change Log correlation

The Change Log class advertises revision 5 in this mode. Its `0x4F` search accepts
only the exact imported index/generation cursor and returns those two UINTs,
without a length prefix or invented history. An older/different cursor or a
missing ACD binding returns unavailable (`0x0C`); malformed lengths are rejected.
This model has no structural edits after the imported cursor. It cannot replay
native editing history or reconcile a changed offline project.

`0x38` batch requests use the same full-message HMAC-SHA1 coverage as `0x36` and
`0x37`. The complete batch is checked before any child dispatch, and one batch
consumes one session counter. Ordered replies retain individual CIP errors;
the outer status is `0x1E` when a child fails. Each child follows the same bounded
read-only policy. Nested transports, context registration inside batches,
setters, mode changes and downloads remain denied. Reply accounting reserves
space for every remaining child's error header before dispatching each read.

The native identity reports virtual Program/Idle status `0x0070`, consistently
across discovery and attribute reads. The SDK reads it as Program. This is model
state: browser-driven Step/Run scans do not change the native PLC mode, and native
mode changes are not implemented. The idle status encoding follows Rockwell's
[Identity Object status table](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/icm-um002_-en-e.pdf).

The opaque confirmation proof and peer identity remain **unverified**. Successful
MAC verification proves possession of this endpoint's fresh nonce, not vendor
identity or operator authority. The endpoint remains anonymous and read-only.

The `.30` suite passes all 559 tests on Linux; Windows passes 557 with two
Linux-only skips. Synthetic tests cover exact source cursors, independent batch
MAC vectors, altered bytes, replay, child errors, reply bounds, denied writes,
and matching identity status across discovery and explicit reads. The following
`.29` section records the earlier milestone and its then-unresolved search.

## Experimental native read-only session

Version `0.6.0-connectivity.29` adds an opt-in anonymous compatibility session.
Select **Experimental native session (read only)** with the L85E profile, or pass
`--eip-native-read-only` with `--eip-port` and `--eip-profile logix-v35-l85e`.
The VMware appliance enables this mode. Ordinary tag writes cannot be enabled
with it. The default desktop endpoint retains the earlier challenge-only behavior.

The opaque `0x64` / `0x4C` proof is acknowledged **without verification**. This
mode does not authenticate Rockwell software, verify a vendor signature or grant
operator authority. It retains a fresh challenge key per registered TCP session,
checks each `0x36` / `0x37` request MAC and exact counter, and signs replies.
An anonymous context must be established before bounded metadata/tag reads are
dispatched. Setters, downloads, mode changes, nested transports, signed batches
and locator commands are rejected through this channel. Idle expiry, bad MACs,
replay, project replacement, endpoint shutdown and TCP disconnect invalidate keys.
The API exposes these limits in `native_session` and `key_exchange`.

ACD imports read the original file's bounded `OfflineChangelog.Dat` header and
bind its comparison identifiers to the converted L5X SHA-256. The original is
never changed or extracted. The Windows appliance importer carries this manifest
to the Linux model; a mismatched L5X hash is rejected before replacing a project.
Unsupported ACD layouts remain usable through native L5X conversion but have no
native correlation binding. Plain L5X/demo imports clear the previous binding.
These identifiers do not prove equivalent runtime behavior or firmware identity.

Class `0xAC` in this mode exposes the 32-byte, ten-attribute Change Log header.
UID uses the ACD download UID; Image UID uses its project UID. Copy UID, timeline
UID and online index/generation retain their distinct source meanings. The model
has no editable change history. Standard L85E models report the Safety Controller
object absent. Source redundancy configuration and virtual run-inhibit/download
flags support the controller-status reads needed during connection setup.

The native v35 SDK completed session/context setup and passed project identity
comparison against the demo's own preserved ACD using this implementation. It
sent 83 MAC-valid requests before failing on class `0xAC`, instance 1, service
`0x4D` (Change Log search). **Go Online still failed.** Inputs and modeled memory
were unchanged. No controller write was dispatched. Private projects, captures,
UID values and native diagnostic scripts are excluded from the repository.
The earlier investigations below describe the versions named in each section;
their challenge-only limitations still apply when this optional mode is disabled.

The `.29` suite passes 553 tests on Linux and 551 on Windows with two Linux-only
tests skipped. Synthetic tests cover container bounds and source binding, fresh
keys, context setup, counter/MAC failures, cross-connection replay, read-only
dispatch and lifecycle cleanup. The Windows executable embeds matching browser
assets and both new session/correlation modules. These checks are separate from
the failed native Go Online result above.

A final check used the rebuilt appliance and the normal Windows ACD importer,
including conversion and manifest transfer. Fifteen live wire checks passed;
the native SDK again reached request 83 and stopped at Change Log search. The
running model retained scan count zero and every imported initial tag value.
This result uses the normal application with fresh challenge keys and no
temporary router or correlation overrides. The current read-only gate rejects
the unimplemented search with CIP `0x0F`, surfaced by the SDK as
`RxCsE_ASA_NO_PERMISSION`; that error does not establish a password failure.

## Start an endpoint

In the app, load a project and open **Connectivity**. Choose an identity profile,
bind IP and port, then select **Start endpoint**. **Load network lab** opens a public
fixture with a 1,200-element DINT array, ControlWord, Command and read-only
Observed. Each modeled scan copies Command to Observed.
**Load structure lab** opens nested numeric UDTs for template discovery and
fragmented transfers. Each scan copies Command into Machine.Axis and copies
Machines[0].Axis.Command into the read-only Machine.History[0].Command.
**Load layout lab** exercises mixed-width numeric fields, nested alignment and
64-bit values. Each scan copies Records[0].Count into the read-only Observed tag.
**Load flag lab** opens 28-byte records with multiple packed Boolean hosts,
nested groups and a 12-record array. Each scan copies Records[0].Ready and
Records[0].Count into the read-only Observed and ObservedCount tags.

The default address is `127.0.0.1:44818`, with TCP and UDP listeners and a modeled
backplane route of port 1, slot 0. The target never forwards traffic externally.
Writes are disabled until explicitly enabled before startup. Network writes and
the UI use the same memory; Step/Run controls modeled scan execution.

## Linx coexistence and addresses

Use **Bind IP** or `--eip-bind` to select a specific IPv4 address belonging to
the emulator's PC. TCP, UDP and the ListIdentity socket address all use that
address. The HTTP UI stays on loopback. Wildcard, multicast, limited-broadcast and
hostname bindings are rejected. A reachable non-loopback address makes the
experimental protocol endpoint accessible to other devices; tag writes remain
opt-in. The app does not assign IP addresses, change firewall rules or configure
Linx.

Two applications can use port 44818 on different local addresses when both
bind specifically. A wildcard listener on `0.0.0.0:44818` can prevent a second
application from binding even a different loopback address. Changing only the
emulator's IP does not resolve that case. A temporary nonstandard port supports
protocol testing, but does not establish normal Studio discovery or Go Online.

FactoryTalk Linx documents **Ethernet driver properties → Advanced → IP Address**
for limiting its listener to one address. Its **Listen on EtherNet/IP encapsulated
ports** setting controls incoming TCP/UDP 44818 services. Existing unsolicited
messages can depend on that listener. Coordinate any Linx configuration change
with the applications using it; the emulator never stops or reconfigures that
service. See the official
[Ethernet Advanced settings](https://www.rockwellautomation.com/en-us/docs/factorytalk-services-platform/6-60/factorytalk-services-platform-help-ditamap/factorytalk-linx-help/config-stand-alone-apps/add-a-driver/ethernet-ppt-advanced-sets.html).
The optional [VMware host-only appliance](vmware-appliance.md) supplies an isolated
guest network stack when the host's Linx listener must remain unchanged. Its
launcher provides a localhost browser tunnel and Windows tray controls.

## Endpoint restarts

Version `0.6.0-connectivity.23` allows a Linux TCP endpoint to restart immediately
on the same selected IP/port after it closes an active client connection. Earlier
builds could leave that port unavailable until the kernel's `TIME_WAIT` timeout
expired, even though no process was listening there.

Linux TCP sockets now use `SO_REUSEADDR`. A live TCP listener at that address,
a wildcard listener covering it, or an occupied UDP port still makes startup
fail. `SO_REUSEPORT` is not enabled. Explicit ports are never relocated, and the
Windows socket policy is unchanged. These rules follow the Linux
[socket option and address-reuse contract](https://man7.org/linux/man-pages/man7/socket.7.html).
A connection left by an older build without address reuse can still require
its timeout to expire during the first transition to the new socket policy.

The Linux regression test establishes server-side `TIME_WAIT` through a real
connected session, then restarts and registers a new client on the same port.
Separate controls check active listener ownership and wildcard conflicts.
The `.23` suite passed all 504 tests on Linux; Windows passed 502 tests with two
Linux-only tests skipped. The restart regression fails against the prior socket
policy and passes with address reuse enabled.
A read-only host-only appliance check completed three successive restarts on
its fixed EtherNet/IP address, preserved the modeled snapshot and source hash,
and rejected a competing reusable TCP bind.

## Broadcast discovery

Linux endpoints on an Ethernet interface with an IPv4 subnet prefix shorter than
`/31` also listen at that subnet's directed-broadcast address and
`255.255.255.255`. These are separate, specific UDP bindings; the TCP and unicast
UDP listeners remain on the selected PLC address. Windows and loopback endpoints
continue to use unicast discovery.

Linux `IP_PKTINFO` metadata must identify the selected interface, its local IP
and the matching broadcast destination. Missing, ambiguous or truncated metadata
is rejected. Only empty ListIdentity, ListServices and ListInterfaces requests
with zero session/status/options are answered; other broadcast datagrams are
ignored. Replies are unicast to the sender, with the selected PLC IP and interface
explicitly supplied to the kernel. This does not require a raw socket or network
configuration privileges.

If either additional socket cannot bind, both are closed and the endpoint
continues with unicast discovery. **Connectivity** shows broadcast availability
and the reason when unavailable. The API exposes this under `discovery`; traces
include `broadcast_discovery`, `broadcast_ignored` and send-error events. No host
adapter, Linx, firewall or routing configuration is changed.

Broadcast reception and FactoryTalk Linx range browsing are separate acceptance
checks. A successful broadcast reply does not establish range browsing, path
selection or Studio Go Online. The discovery exchange follows ODVA's
[IPv4 ListIdentity description](https://www.odva.org/wp-content/uploads/2022/06/2012_ODVA_Conference_XuYuBrooksBatke_FINAL.pdf)
and Linux's [IPv4 socket interface](https://man7.org/linux/man-pages/man7/ip.7.html).
The interface/destination control message follows
[IP_PKTINFO](https://man7.org/linux/man-pages/man2/IP_PKTINFO.2const.html).

Validation on 2026-10-19 with `0.6.0-connectivity.17` passed 445 behavioral tests
on each of Windows and Linux. An unprivileged Linux datagram probe completed nine
discovery exchanges across unicast, subnet broadcast and limited broadcast,
with matching payloads and the selected PLC reply source. Six malformed
broadcast requests received no reply. A Windows `pycomm3` 1.2.16 client then
discovered the running host-only appliance with one subnet-broadcast query.
Exact addresses, packet traces and receipts remain local. These checks do not
establish Linx range browsing or change the native Go Online result below.

## Virtual chassis

The modeled port-1/slot-0 route is an EtherNet/IP routing response; it does not
register this application in Rockwell's native virtual chassis. That requires
a separate virtual-backplane provider integration. Rockwell historically offered
a toolkit for third-party network or specialty modules in SoftLogix, including
the L30 and L60 variants; it was not exclusively limited to Rockwell modules.
See the official [SoftLogix product overview](https://www.rockwellautomation.com/en-tr/products/hardware/programmable-controllers/softlogix-controllers.html).
That history does not establish a supported way to register a custom v35 CPU in
the installed chassis. This project has no such provider yet. Changing an IP
or adding an EDS file cannot supply that integration or the remaining native
Studio project/debugger services.

## Identity profiles

- `research` is the default: an experimental LogixLab identity using vendor
  value `0xFFFF`.
- `logix-v35-l85e` is an optional compatibility profile for a matching `1756-L85E`
  v35 source. It advertises vendor 1, device type 14, product code 168 and the
  loaded source's minor revision.

Both profiles use a research serial. A compatible identity response does not
establish an authentic Rockwell target or native controller equivalence.
Incompatible project imports are rejected while the compatibility profile is
active. Compatible replacements update identity data and invalidate old sessions.

Version `0.6.0-connectivity.26` adds read-only Identity instance 1 attributes
`101` and `102`, available through single and list reads. Rockwell documents
`101` as the hardware major/minor byte pair in its
[Dynamix Identity Object table](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/1444-um001_-en-p.pdf),
and `102` as a UDINT firmware build number in its
[ArmorStart Identity Object table](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/290e-um001_-en-p.pdf).
The observed v35 native query and reply match those two- and four-byte widths.
These publications describe other Rockwell products; the Logix wire observation
is separate compatibility evidence.

Both emulator profiles deliberately report **virtual hardware 1.0** and
**profile firmware build 0**. These are model values, not physical-controller
provenance or an inferred Rockwell firmware build. The API and Connectivity tab
identify them as virtual. The app release version remains a separate value.
The Identity class advertises maximum instance attribute 102; unknown attributes
retain per-attribute errors. Standard Get Attributes All and ListIdentity retain
their existing field layouts, and attribute writes remain unsupported.

## Supported services

| Surface | Implemented subset |
| --- | --- |
| Encapsulation | ListIdentity, ListServices, ListInterfaces, Register/Unregister Session |
| Explicit transport | SendRRData, slot-0 Unconnected Send, Class 3 SendUnitData |
| Connections | Standard/Large Forward Open and Forward Close; sequence/replay checks |
| Objects | Identity attributes including read-only virtual hardware/build metadata, Message Router class inventory and controller name |
| Network metadata | Port/node addresses `0xF4`, TCP/IP configuration `0xF5`, Ethernet MAC `0xF6` |
| Device locator | Identity instance 1, `0x4B` Flash_LEDs; timed webpage indicator |
| Catalog refresh | Controller class `0xAC`: class revision/inventory and instance 1 comparison attributes |
| File Manager | Class `0x31A`, instance 0: revision and zero storage-instance count |
| Controller configuration | Class `0x8E` source SecurityCode and class revision; `0x64` name/description reads; `0x349` class discovery only |
| Vendor key challenge | Extended Device `0x64`, instance 1, `0x4B`; confirmation and authenticated wrappers remain unsupported |
| Symbol metadata | Paginated `0x55`; single/list basic metadata and backed ordinary scalar descriptors |
| Templates | Class `0x6C` attributes 1, 2, 4 and 5; offset-based `0x4C` definition reads |
| Atomic access | BOOL and supported signed/unsigned integers and REAL; arrays and atomic members |
| Structured access | Numeric, explicit user LEN/DATA string and packed-BIT UDTs, including nested structures and arrays |
| Transfers | `0x4C` read, `0x4D` write, `0x52` fragmented read, `0x53` fragmented write |
| Integer masks | `0x4E` Read Modify Write, applying OR then AND masks |
| Multiple service | Bounded Multiple Service Packets with independent child operations |

Nonzero encapsulation-status packets from a peer are recorded as `peer_error`
and are not answered. This prevents an error-response loop during client
interoperability; the session remains available for later valid requests.

Symbol attributes provide name, type, dimensions and effective external access.
Constants, aliases and member restrictions are honored. Private tags, AOI locals
and Safety program tags are not exposed. Firmware-internal attributes 3, 5 and 6
remain unsupported, so full native tag-upload initialization is still pending.

Supported atomic wire types are BOOL, SINT, INT, DINT, LINT, USINT, UINT, UDINT,
ULINT and REAL. Explicit user-defined LEN/DATA string structures support whole
and fragmented transfers. Built-in STRING transfers and packed BOOL arrays
remain unsupported. Atomic built-in STRING members can be addressed individually.

## Vendor key challenge

Version `0.6.0-connectivity.20` adds the observed first phase of the native v35
key exchange: Extended Device class `0x64`, instance 1, service `0x4B`. The
bounded offer parser checks format words, unique feature IDs/versions, parameter
tags and lengths, a public exponent of 65537, an odd 1,024-bit modulus and the
declared offer boundary. The final 128 opaque bytes are length checked; their
trust/signature semantics are unimplemented. Peer identity is not authenticated.

Each accepted request generates a fresh 20-byte nonce and applies the raw RSA
public primitive. The modulus is big-endian; the nonce integer and resulting
ciphertext use little-endian encoding. The response contains a UINT length of
128 followed by those ciphertext bytes. This is the observed vendor format,
using the mathematical primitive described in
[RFC 8017 section 5.1.1](https://www.rfc-editor.org/rfc/rfc8017.html#section-5.1.1).
The vendor format has not been established as an RFC encryption scheme.

With native read-only mode disabled, the endpoint discards the nonce after constructing its reply. It does
not retain a session secret, validate confirmation service `0x4C`, or dispatch
authenticated Message Router services `0x36`–`0x38`. Those services return explicit
unsupported errors. The API's `key_exchange` metadata reports these boundaries.
The challenge works with tag writes disabled and preserves modeled memory,
project generation and catalog state. Identity class `0x01` service `0x4B` remains
the separate device-locator operation below.

Separate, temporary native SDK trials established the raw-RSA encoding and
verified HMAC-SHA1 requests over the complete outer CIP request plus its counter,
excluding the final 20-byte MAC. Three trials matched using generated nonces,
including a deterministic test vector. The MAC uses the nonce's little-endian byte sequence as its
key. Confirmation proof and session-bound live dispatch remain research work.
The offline codec below covers observed request/reply containers; temporary
native trials reject their embedded operations.
The generic HMAC construction is defined in
[RFC 2104](https://www.rfc-editor.org/rfc/rfc2104).

The implementation uses the Python standard library. Public tests use a
synthetic public key and an independently generated ciphertext vector. Vendor
keys, captured replies, private projects and diagnostic harnesses are not bundled.
The `.20` behavioral suite passed 482 tests on each of Windows and Linux.

## Offline signed-envelope codec

Version `0.6.0-connectivity.21` adds an offline codec and capture-report fields
for the observed Message Router class `0x02`, instance 1 envelopes. It does not
enable their live dispatch or change the unresolved `0x64` / `0x4C` confirmation.

| Field | Observed `0x36` | Observed `0x37` |
| --- | --- | --- |
| Outer request | Service, two-word path `20 02 24 01` | Same path |
| Container header | None | Little-endian UDINT `0x301`, then embedded CIP byte length |
| Content | One complete embedded CIP request | One complete embedded CIP request |
| Trailer | Little-endian UDINT counter, then 20-byte HMAC-SHA1 | Same trailer |

The request verifier covers every outer CIP byte before the MAC, including the
path, container header when present, embedded request and counter. A known-nonce
native SDK `0x37` trace matches this calculation. Reference `0x36`/`0x37` framing,
independent synthetic vectors and altered-byte tests cover both formats. The
[native signed-sequence investigation](#native-signed-sequence-investigation)
also verifies `0x36` with a known key. `verify_request` requires a 20-byte supplied key and
the exact expected counter. It is a stateless diagnostic function: key possession
does not establish peer identity or permission to execute an operation.

Structural reply decoding requires a successful outer response, the corresponding
embedded reply service, valid additional-status bounds and an echoed counter.
The `0x37` reply uses the same observed container header with its reply length.
Captures without keys receive structural analysis only, explicitly labeled
**NOT VERIFIED** for integrity. Unsupported format words, length mismatches and
malformed inner headers are rejected by the codec. Capture reports retain their
outer evidence. Version `.24` adds the separate structural batch format below.

The codec accepts immutable byte messages up to 65,519 bytes and decodes one
layer. It opens no connection, stores no key and never calls the protocol router.
The normal endpoint still returns unsupported errors for `0x36`–`0x38`, including
requests whose MACs are valid in an offline test. Private captures, known-nonce
traces and operator identity payloads remain outside the public tree.
The `.21` behavioral suite passed 496 tests on each of Windows and Linux. Offline
validation decoded 32 paired reference exchanges and verified the saved native
known-nonce `0x37` request; these checks do not establish native Go Online.

Version `0.6.0-connectivity.22` adds known-key reply verification and reply
encoding. Both directions use HMAC-SHA1 over the complete outer CIP message
through the echoed counter, excluding the final MAC. Verification also requires
the corresponding embedded reply service and exact request counter. Encoding
frames and signs supplied reply bytes; it performs no embedded operation.
An authenticated embedded error remains an error.

An isolated native SDK test returned an explicit CIP `0x0F` privilege denial
inside a correctly signed `0x37` reply. The client reported access denied. A
second reply differing in exactly one MAC byte produced a data-integrity error.
Repeating the correctly signed denial with a different nonce again produced
access denied. Public encoder output matches both accepted reply byte sequences;
the verifier rejects the damaged-MAC control. CIP `0x0F` is defined as privilege
violation in Rockwell's
[generic CIP status table](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/1444-um001_-en-p.pdf).

Those private tests supplied a temporary capability response solely to reach the
wrapper experiment, without validating `0x64` / `0x4C`. The normal endpoint still
rejects confirmation and all signed dispatch. No embedded operator-identity
operation was performed. Those initial native MAC tests covered `0x37`;
independent synthetic vectors cover both formats. The later `0x36` results are
described below. At that revision, service `0x38` remained unsupported by the
offline codec.

A separate repeated-nonce test produced identical confirmation bytes across
different EtherNet/IP session IDs, with identical offers and ciphertexts. This
narrows the confirmation investigation but does not establish its calculation.
The `.22` behavioral suite passed 501 tests on each of Windows and Linux,
including independent reply vectors, altered bytes, wrong keys, mismatched
request contexts, malformed headers and maximum-length replies.

### Native signed-sequence investigation

Additional emulator-only tests used native SDK 2.1.974 through RockwellMCPServer
0.18.0, a known nonce and a matching offline project copy. The normal endpoint
continues to reject confirmation. Temporary wire-format stubs supplied the
capability reply and the following observed registration replies solely to
inspect later messages; they did not validate the confirmation proof, register
an operator, create a controller context or dispatch an embedded operation.

| Counter | Wrapper | Embedded request | Observed reply payload |
| --- | --- | --- | --- |
| 1 | `0x37` | Class `0x8E`, instance 1, service `0x5C`; 98 payload bytes | Empty successful reply |
| 2 | `0x36` | Class `0x378`, instance 1, service `0x4B`; 112 SDK payload bytes | One DWORD; a synthetic test value advances the client |
| 3 | `0x36` | Class `0x8E`, instance 1, service `0x63`; one DWORD | An empty test reply now advances the client to metadata queries |

The passive reference has the same sequence, with a 114-byte payload at counter
2 and an empty successful reply at counter 3. Payload sizes and wire replies do
not establish the semantics or permissions of these vendor operations.

The counter-2 native `0x36` request verifies using HMAC-SHA1 over the complete
outer request through the counter, with the known nonce's little-endian bytes
as its key. The public encoder produced a matching `0x36` reply carrying an
embedded CIP `0x0F` denial. The SDK reported access denied. A control differing
in exactly one reply MAC byte produced a data-integrity error. The public
verifier accepts the denial and rejects the damaged control. The same control
on the counter-1 registration reply also stopped the client with a
data-integrity error; the valid reply advanced it to counter 2.

Native MAC evidence therefore covers requests and denial replies for both
`0x36` and `0x37`. It does not validate `0x38` MACs, confirmation, registration
semantics, replay protection or native Go Online. These tests leave the normal
endpoint's unsupported-service behavior unchanged.

Three separate confirmation trials kept the nonce, public-key offer and
encrypted challenge identical while independently changing the reported CIP
serial number or product label. The SDK read each changed identity, but its
confirmation bytes stayed identical across all three trials and different
EtherNet/IP sessions. These tested identity fields do not explain the proof;
its calculation remains unresolved.

### Metadata reads after context binding

A subsequent bounded native experiment acknowledged the observed counter-3
wire reply, then permitted only attribute reads against the isolated model.
Registration and context replies remained temporary stubs: confirmation and
their vendor semantics were not validated or enabled in the normal endpoint.

The first counter-4 read requested Identity instance 1 attributes `101` and
`102`. Before `.26`, that list had unsupported-attribute results. With the
candidate virtual revision metadata above, the native SDK received a successful,
MAC-valid list reply. This verifies the reply shape and read compatibility, not
physical hardware equivalence or completed Go Online.

In the `.26` experiments, the next unresolved reads concerned class `0x8E`,
instance 1, attribute `13`: the SDK tried a one-entry attribute-list read and a
single read. They were unsupported at that revision, and the SDK reported that
security access information could not be
obtained. The harness also denied a zero-entry Set Attribute List request to
class `0xAC`, instance 1. It performed no attribute writes or controller-state
changes; its final memory comparison matched the original model values.

The observed signed counters remained ordered through these requests, but this
does not validate a complete session lifecycle or replay policy. Unknown
security flags, permissions and cache-write semantics are not guessed. The
normal endpoint still rejects `0x64` confirmation and all signed dispatch.

Later emulator-only trials supplied a synthetic four-byte zero field for
attribute `13`. The SDK accepted that reply shape and next requested class
`0x349`, instance 0, service `0x53`, with 26 payload bytes. An additional trial
supplied an empty eight-byte container for that request, after which the SDK
requested the Message Router's object inventory. Returning the model's real
inventory did not complete the connection. All three trials still failed with
`RxSEC_E_SECURITY_INFO_NOT_READ`; no native online session was established.

These temporary replies measure client progression only. They do not establish
the security field's meaning, authorize an operator or implement class `0x349`.
The `.27` endpoint continued to reject both requests. Each trial retained the
original model memory and dispatched no writes. The isolated native service
and leased harness were stopped afterward, and the normal endpoint restored.

The [Import/Export reference, page 58](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
defines the L5X `Security` element's `Code` as legacy RSI Security Server
configuration. The installed attribute definitions subsequently established its
CIP mapping for `.28`, as described under
[source configuration](#source-configuration-and-class-discovery). FactoryTalk
permission semantics remain unimplemented.

The `.28` candidate's source-backed attribute `13` and class-revision replies
were accepted in a later isolated SDK test. Adding the Extended Device name and
description list also removed that read failure. The final trial recorded 53
ordered, MAC-valid signed requests. Its remaining reads targeted Safety
Controller class `0x334`, instance 1: attributes `3` (Locked State) and `4`
(Signature Exists), followed by an attribute-3 single-read fallback. Those
remain unsupported, and the SDK still reported `RxSEC_E_SECURITY_INFO_NOT_READ`.

These tests still used temporary confirmation, registration and empty-container
wire replies. They validate the new metadata responses, not authentication,
safety state or native Go Online. No controller write was dispatched, and the
final memory comparison matched the original model values.

The `.28` behavioral suite passed 536 tests on Linux; Windows passed 534 with
two Linux-only skips.

### Capability-response investigation

Additional isolated SDK trials varied the entries in the temporary `0x4C`
capability response while retaining the same known nonce and offer. These tests
did not validate the confirmation proof or dispatch the next embedded operation.

| Response variation | Observed next step |
| --- | --- |
| Empty list | SDK reports an unspecified error before a signed request |
| Entry 2 omitted | Same early failure |
| One of entries 3, 4, 5 or 6 omitted | SDK sends a MAC-valid `0x37` request; harness rejects it |
| All five entries, with entry 2's value zero | SDK still sends a MAC-valid `0x37` request |
| Entry 2 alone | SDK reports an unspecified error before a signed request |

These observations do not fully define the entries or establish a simpler
transport path. Confirmation remains unsupported by the normal endpoint.

Offline analysis of a bounded reference sample also found 157 paired `0x38`
exchanges containing 4,138 child request/reply pairs. Requests contain a UINT
count, that many UINT relative offsets and the child CIP requests. Replies have
matching child counts, corresponding reply services and echoed counters;
observed outer statuses are zero and `0x1E`. This establishes reference framing
for further work. A known-key native `0x38` MAC test is still needed; no `0x38`
dispatch or MAC verification is enabled in the app.

### Structural batch decoding

Version `0.6.0-connectivity.24` extends the offline codec and capture inspector
to the observed Message Router `0x38` batches. The codec returns an immutable
`BatchEnvelope` with the counter and ordered child CIP byte strings. It accepts
the following bounded profile:

- A request uses the same two-word Message Router path as `0x36`/`0x37`.
- The body starts with a little-endian UINT child count and that many UINT byte
  offsets, relative to the count field. The first child starts immediately
  after the table; subsequent offsets strictly increase and remain in the body.
- Every child has a complete CIP request header and bounded path. Reply child
  counts and services must match the paired request in order, with valid reply
  reserved bytes and additional-status lengths.
- A reply has service `0xB8`, outer status zero or `0x1E`, no outer additional
  status, and the exact request counter. Child statuses and data remain intact;
  a partial-error reply is not reported as success. Odd child byte lengths are
  supported without inserting or removing padding.
- The trailer is a UDINT counter and 20 opaque bytes. Batch MAC verification and
  reply encoding remain unavailable; the codec raises an explicit error rather
  than applying the unvalidated MAC calculation from another service.

The implementation limits each batch to 256 children and the complete message
to 65,519 bytes. These are decoder limits, not claims about controller limits.
Malformed batches are rejected as a whole. Nested wrappers remain opaque child
bytes, so the inspector still decodes only one envelope layer.

Capture report format 3 adds `child_count` and ordered `children` fields for
batches, while preserving the `inner` field for `0x36`/`0x37`. Default reports
omit child symbols, values and raw messages. Raw bytes require the existing
explicit `--include-payloads` option. All batch integrity fields remain
**NOT VERIFIED**.

Version `0.6.0-connectivity.27` produces capture report format 4. Requests with
multiple class/instance scopes retain their ordered `object_path` entries.
Their flat `class_id`, `instance` and `attribute` fields are null, preventing a
scoped target from being mistaken for its directly addressable leaf. Every
parent scope must contain only a class and instance; malformed segments,
duplicate fields within a scope and paths deeper than 16 objects are rejected.
This is an offline description, not a change to live path routing.

Structurally complete Get Attribute List requests also expose ordered
`requested_attributes` IDs, including duplicates, up to 256 entries. Replies
retain their status, size and payload hash; unknown value widths and security
meanings are not inferred. Missing or malformed lists retain their original
payload hashes without a decoded ID list. Symbols and values remain absent
from default reports, including scoped paths and embedded batch children.

Reanalysis of the same saved sample retained all 1,685 paired exchanges and
decoded six previously opaque signed requests containing scoped paths. It
exposed 7,668 attribute-list requests across outer and embedded messages.
Integrity remains **NOT VERIFIED** and native Go Online remains unimplemented.
The `.27` behavioral suite passed 526 tests on Linux; Windows passed 524 with
two Linux-only skips.

Offline validation decoded all 157 saved reference batch exchanges and 4,138
child request/reply pairs. The `.24` suite passed all 517 tests on Linux; Windows
passed 515 with two Linux-only skips. This checks modeled behavior, framing and
correlation only: no reference session key was available, no embedded operation
was executed, and native Go Online still requires the unresolved confirmation
and session behavior.

## Device locator

Identity class `0x01`, instance 1 supports the `0x4B` Flash_LEDs service. The
request contains exactly one USINT duration: zero stops identification, and
9 through 255 starts it for that many real seconds. Values 1 through 8 are
invalid. A later valid request replaces the remaining time. Success returns an
empty service response. The timing contract follows the
[ODVA CIP Object Tests, section 4.1 test 6.8](https://ticket.hilscher.com/secure/attachment/260555/CIP_PCTS.pdf).

The webpage displays a global **DEVICE LOCATOR ACTIVE** banner with a countdown
and a repeating red/green/off color cycle. It remains visible while switching
tabs and automatically clears on expiry, cancellation or endpoint shutdown.
Page refresh reads the current request from the endpoint. Browser reduced-motion
preferences show a steady indicator. Idle pages poll at two-second intervals;
local countdowns continue between responses.

Identification works with tag writes disabled. It does not change application
memory, scan execution, project generation, device identity or catalog tokens.
Its monotonic timer runs independently of modeled scan time. Protocol traces
record requests and durations. Application resets preserve identification of
the same endpoint; stopping or replacing the endpoint clears it.

FactoryTalk Linx discovery and device-location support are separate from native
project selection, Go Online and upload/download. Extended identity and vendor
metadata remain incomplete. Manufacturing dates, warranty identifiers and other
physical-device data are not inferred from an ACD or invented to fill empty
fields in a device-information view.

## Port and TCP/IP interface metadata

The Port Object (`0xF4`) describes two modeled interfaces: local slot-zero
backplane routing on port 1 and the selected EtherNet/IP endpoint on port 2.
Class attributes 1, 2, 3, 8 and 9 support single/list reads and class
Get_Attributes_All. The entry port is 2; the port-info array includes the reserved
zero entry. Instance attributes 1 through 5 and 7 support single/list reads and
instance Get_Attributes_All. Attribute 7 describes local slot zero on port 1,
and the selected IPv4 address as a padded extended-link segment on port 2. Port 2's
link path points to TCP/IP Interface instance 1. Port 1 has an empty link-object
path because no physical backplane object is implemented. Unknown ports are
rejected rather than advertised as additional hardware.

The TCP/IP Interface Object (`0xF5`) supports class attributes 1 through 3 and
class Get_Attributes_All. Instance 1 exposes attribute 1 (configuration status),
5 (IPv4 configuration) and 6 (hostname). Attributes 2/3 expose configuration
capability/control for the [verified Linux DHCP combination](#tcpip-configuration-status).
Attribute 4 returns the path to Ethernet Link instance 1 when its
MAC address is known, or a zero-length path when physical-link metadata is
unavailable. IPv4 values are CIP little-endian UDINTs; domain/hostname values use
length-prefixed, even-padded CIP strings. The configuration uses the selected
local address, actual subnet mask, default gateway, IPv4 DNS servers and domain.

Configuration is captured lazily on the first IPv4/physical-link query and retained for
that endpoint. Linux queries interface ioctls, its route table and resolver file;
Windows calls the read-only IP Helper API directly. It does not launch a shell
on a CIP request. Restart the endpoint to refresh
the snapshot after an OS configuration change. If the selected configuration
cannot be read or validated, the request returns a CIP error; no subnet, gateway
or MAC address is guessed. Snapshot availability and errors are exposed in the
connectivity state. Ethernet Link (`0xF6`) supports class attributes 1 through 3,
class Get_Attributes_All, and single/list reads of instance 1 attribute 3, with
additional [Linux link-status fields](#controller-settings-and-linux-ethernet-status). The MAC
is six octets in adapter order, read from that exact OS interface. Unknown,
non-Ethernet, zero or multicast addresses are not replaced with invented MACs;
the request returns an explicit CIP error. Loopback normally has no Ethernet MAC.

Network configuration writes, TCP/IP instance Get_Attributes_All, the remaining
TCP/IP attributes, Ethernet Link counters and physical-backplane services
remain unsupported. Enabling tag writes does not enable network reconfiguration.
These responses do not establish native Studio path selection or Go Online.

The layouts follow the published
[Port/TCP-IP object tables](https://productinfo.se.com/pm5500/595e2aa946e0fb0001f715da/PM5500%20user%20manual/English/PM5500SeriesUserManualv02_0000044889.ditamap/$/R_Communications_EthernetIP_MessagingExplicitExchanges_PM5500_0000178841)
and the [Rockwell port-object description](https://www.sprecherschuh.com/content/dam/sprecher-schuh/downloads/tech-docs/CEP7-UM014B-EN-P_12-11.pdf).
This is an original, bounded implementation; no upstream stack code is bundled.
Windows adapter layouts follow Microsoft's
[IP Helper documentation](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getadaptersaddresses).

## Catalog refresh

Controller class `0xAC`, instance 0 supports Get Attribute Single and Get Attribute
List for the common class attributes 1 (object revision), 2 (maximum instance)
and 3 (instance count), each a UINT. The modeled object revision is 1, with one
implemented instance numbered 1. This revision describes the model's object
interface, independently of the source comparison tokens or advertised firmware
identity. Class-level Get Attributes All and configuration writes are unsupported.
The common attribute definitions follow the
[OpENer class implementation](https://github.com/EIPStackGroup/OpENer/blob/d8820ef41ce30dda06d213438ba81c81de33ffe2/source/src/cip/cipcommon.c#L329).
No upstream code is bundled.

Controller class `0xAC`, instance 1 supports Get Attribute Single and Get Attribute
List for attributes 1, 2, 3, 4 and 10. Their wire widths are 2, 2, 4, 4 and 4 bytes
(INT/INT/DINT/DINT/DINT). This comparison interface is described in
[Data Access, chapter 2](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf).

The model derives opaque comparison tokens from the imported source bytes and
model version. Compare all five attributes together. Values stay stable during
scans, tag writes, resets and scope changes. Importing identical source bytes
preserves tokens; different source bytes conservatively change them, including
changes to comments or initial values. These are not native firmware signatures.
The connectivity API exposes the combined token as `catalog_revision.token`
while the endpoint is enabled.

Imports, resets and scope changes still require clients to reconnect and refresh
their cached symbols/templates. Old sessions are rejected. A metadata check and
tag reads may share a Multiple Service Packet. For writes, check the revision
before and after writing; a grouped metadata check is not a conditional write
guard because Multiple Service children execute independently.

Only the read-only comparison attributes are implemented. Native project
correlation, mode changes and Studio Go Online remain pending.

## Source configuration and class discovery

Version `0.6.0-connectivity.28` adds the following Get Attribute Single and Get
Attribute List subsets. Revision 1 describes this implementation, not a native
controller's object revision.

| Class / instance | Attributes | Modeled values and encoding |
| --- | --- | --- |
| Controller `0x8E` / 0 | 1 | UINT object revision 1 |
| Controller `0x8E` / 1 | 13 | Source `Controller/Security@Code`, four-byte unsigned value |
| Extended Device `0x64` / 0 | 1 | UINT object revision 1 |
| Extended Device `0x64` / 1 | 1, 2 | Source controller name and description, each prefixed by a UINT byte length |
| Metadata Definition `0x349` / 0 | 1, 2, 3 | UINT revision 1; UDINT maximum instance 0 and instance count 0 |

The layouts were checked against the installed v35 Controller, Extended Device
and Metadata Definition Attribute Description Files. They are neither modified
nor bundled; reference hashes remain in local receipts. The implementation
supports only these fields, with no Metadata Definition instances or vendor
`0x53` operation.

The [Import/Export reference, page 58](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
defines L5X `Security@Code` as the legacy RSI Security Server configuration.
The model accepts decimal values from 0 through 4,294,967,295, with at most ten
digits. Missing, duplicated, malformed or out-of-range source settings leave
attribute `13` unavailable (`0x14`, including per-attribute list errors). They
never become an assumed zero. Zero and nonzero source values are returned
exactly; neither enables security enforcement or grants permission.

Extended Device text currently supports ASCII: up to 40 bytes for the name and
128 for the description. An absent optional description is empty. Oversized,
non-ASCII, localized or ambiguous descriptions remain unavailable, without
truncation or a guessed language. The earlier name-only Get Attributes All
reply retains its existing layout. Unknown attributes keep explicit errors.

Message Router inventory includes the two added object classes. Connectivity
state exposes availability and implementation boundaries under
`controller_configuration` and `metadata_definition`. Source replacement updates
the metadata and invalidates old sessions. Setters, operator registration,
authority services, Safety Controller status, confirmation and authenticated
dispatch remain unsupported even when ordinary tag writes are enabled.

## File Manager discovery

File Manager class `0x31A`, instance 0 supports Get Attribute Single and Get
Attribute List for attribute 1 (object revision, UINT) and attribute 3 (instance
count, UDINT). The modeled object revision is 1 and the count is zero: this
implementation has no emulated removable-storage devices. The four-byte count is
specific to this object's layout; it must not use the two-byte count from the
controller metadata class. Message Router inventory includes this implemented
class, and connectivity state exposes its limited scope under `file_manager`.

The layout was checked against the installed Studio v35 File Manager Attribute
Description Files. These reference files are neither modified nor bundled;
the implementation is original. Reference paths and hashes stay in local
validation receipts.

Attribute 2, instance attributes, capacity, file contents and file operations
remain unsupported. Requests for a storage instance return path-unknown
(`0x05`); unsupported class attributes return attribute-unsupported (`0x14`),
including per-attribute statuses in mixed lists. Class Get Attributes All and
mutating services remain rejected. Enabling tag writes does not enable storage
operations. This discovery subset does not implement SD-card project loading,
upload/download or native Studio correlation.

## Structured transfers

Explicit `User` UDTs in `NoFamily` may contain SINT, INT, DINT, LINT, USINT, UINT,
UDINT, ULINT and REAL members, explicitly mapped BIT flags, nested supported
UDTs and one-dimensional member arrays. Numeric values use little-endian
encoding. Root arrays may have up to three dimensions. Symbol types link to
template instances; templates describe
member types, offsets, names, structure size and the handle returned in reads.
See the [data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
chapter 2, for the protocol formats.

Numeric fields align to their byte width. Arrays align to at least four bytes
and include trailing alignment padding. Structures align to four bytes, or
eight when they contain a 64-bit member, including through nested types.
Structure sizes are rounded to that alignment. These rules follow
[Design Considerations, chapter 6](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm094_-en-p.pdf).

Reserved alignment padding is canonical zero data in this software model.
Reads emit zero padding; writes reject nonzero bytes in reserved padding before
changing application values. A zero-only padding fragment is a no-op. This is
a model policy, not a claim about native controller padding contents. Unknown
application values still reject reads, independently of the padding policy.

The model limits each layout and requested transfer to 32 KiB, nesting to eight
levels, each type to 256 members and member arrays to 4,096 elements. Private,
inferred-only, predefined and AOI layouts are excluded. Hidden storage is allowed
only for the validated BIT hosts described below. Unmapped BOOL declarations,
BOOL/BIT arrays, built-in STRING fields, LREAL and other overlays remain unsupported in
whole UDT transfers. Eligible atomic members remain accessible separately.

Template IDs and CRC-derived handles belong to this software model and are not
native compiled type identifiers. Only templates reachable through externally
accessible tags are exposed. Unknown member values reject the requested read;
unknown backing data is never replaced with zeroes.
Reset and import invalidate sessions; project replacement rebuilds the catalog.

Structured `0x4D` and `0x53` writes require the `A0 02` type marker and the matching
template handle before the element count. Fragment offsets address bytes in the
requested record region. Writes validate root access and every touched member,
including aliases, constants and read-only nested members. A whole-record write
touches every member; a fragment may update writable fields while leaving a
read-only field untouched. Complete atoms can establish unknown leaf values;
split atoms require known bytes for the remainder of that atom.

### User-defined strings

Explicit `User` / `NoFamily` UDTs with a scalar DINT `LEN` and one-dimensional
SINT `DATA` array use the same supported structure layout. Whole and fragmented
transfers work for scalar tags, arrays and nested fields. For example, a nine-byte
DATA array has LEN at offset 0, DATA at offset 4 and three zero padding bytes,
giving a 16-byte record. Member access restrictions apply to both direct atomic
access and whole-structure transfers.

LEN transfers as a DINT, including values outside the DATA capacity. String
execution validates LEN before using the string. Unknown backing bytes still
reject whole reads, and successful reads do not discard unused DATA bytes.
Whole writes can establish all unknown fields; split atoms require known
remaining bytes. Built-in STRING and inferred-only string layouts remain outside
this wire subset. The user-created string form is described in the
[data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
chapter 2, page 45.

Version `0.6.0-connectivity.19` passed 473 behavioral tests on each of Windows
and Linux. An independent `pycomm3` 1.2.16 probe discovered the templates, decoded
scalar, array and nested values, and performed automatic fragmented reads and
writes over a 24-byte Class 3 connection. Read-only tag writes were rejected.
These checks exercise modeled structures and explicit messaging.

The independent structure probe uses the client's template parser and value
codec over a negotiated 256-byte Class 3 connection to exercise fragmentation.
Its tag-cache adapter uses supported symbol attributes. This does not establish
native firmware-address tag upload, native UDT layout parity or Studio Go Online.

### Packed Boolean flags

Visible scalar `BIT` members must explicitly name a preceding hidden scalar
`SINT` host through `Target`, with unique `BitNumber` values from 0 through 7.
Host names must start with `ZZZZZZZZZZ`. Multiple hosts, sparse bit positions,
nested UDTs and arrays of these UDTs are supported. Templates describe both the
host and each visible flag, using the shared byte offset and the flag's bit
number. This follows the UDT mapping described in the
[data access manual, chapter 2](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf).

The model stores visible flag values, with unused host bits reserved as zero.
Reads assemble the host bytes from known flag values; unknown visible flags
reject the read. Unused bits are not native backing-memory values. Writes reject
nonzero reserved bits, and never create or expose a separate hidden host value.
Arbitrary hidden members and overlapping, missing, forward or non-SINT mappings
are rejected.

A structured write that touches a host byte checks write permission for every
visible flag mapped to that byte, even when the requested value is unchanged.
An atomic symbolic write to one flag checks that flag alone. Host-byte fragments
can establish previously unknown flags without reading unrelated fields. Hidden
hosts cannot be read or written directly. The existing per-request rollback and
fragment rules apply.

## Write semantics

Each write request validates its payload and rolls back that request on failure.
Accepted fragments take effect immediately; a later failed fragment does not
undo prior fragments. Scans may run between separate requests. Fragments can
split an atomic element, but untouched bytes within that atom must already be
known. This applies to both atomic and supported numeric UDT transfers. A failed
member or nonfinite REAL rejects the entire request, including earlier members
or records in that request.

Integer masks may cover 1, 2, 4 or 8 low bytes of a sufficiently wide integer.
Upper bytes are preserved; OR is applied before AND. BOOL, REAL and aggregate
mask writes are unsupported.

Multiple Service Packet children are independent operations. Later child failure
does not roll back earlier writes, and an oversized combined response can fail
after earlier children executed.

## Bounds and traces

The target permits up to 16 TCP clients and 8 Class 3 connections per session.
Request payloads are bounded to 32 KiB. CIP replies are bounded to 480 bytes and
the negotiated connection size. Nested messages and dispatch work are bounded.
Reset, scope changes and project replacement require clients to reconnect.

The trace retains up to 1,000 events with peer/session, path, service, status,
error and bounded request/reply hex samples. Samples have a truncation flag.
Trace exports may contain project tag names and data; keep them in `.local/`.

## Native SDK diagnostic

`source/research/NativeStudioProbe` uses the optional official Logix Designer SDK
client to open a private ACD copy and attempt a mode query or GoOnline. The target
must be configured and visible in FactoryTalk Linx. The diagnostic accepts only
loopback slot-0 paths and never downloads, saves, changes mode or writes tags.

From the repository root, with native tooling available and the local endpoint
running:

```powershell
dotnet run --project source/research/NativeStudioProbe -- --acd .local/projects/demo.ACD --comm-path 'Ethernet\127.0.0.1\Backplane\0' --operation mode --out .local/probes/mode.json
```

Use `--operation go-online` for the broader connection attempt. Retain receipts
and before/after protocol traces locally. A native failure before any endpoint
traffic does not identify the next missing CIP service. A successful identity
query is still distinct from successful project correlation or online monitoring.

### Observed native connection gaps

On 2026-10-19, an isolated RockwellMCPServer 0.8.2 instance used the native SDK
with a matching private v35 ConveyorDemo ACD and the host-only appliance running
`0.6.0-connectivity.15`. The project opened offline, setting and reading its
configured Linx Ethernet/backplane/slot-zero path succeeded, and the Go Online
attempt reached the endpoint. It returned
`RxE_COMM_ASA_SERVICE_NOT_SUPPORTED - Unimplemented service`.

The baseline endpoint trace contains these unsupported requests:

| Object path | Request | Response in `.15` |
| --- | --- | --- |
| Class `0xAC`, instance 0 | Get Attribute List for attribute 1 | Unknown metadata instance (`0x05`) |
| File Manager class `0x31A`, instance 0 | Get Attribute List and Get Attribute Single for attribute 1 | Unsupported service (`0x08`) |
| Extended Device class `0x64`, instance 1 | Vendor service `0x4B` | Unsupported service (`0x08`) |

The same native operation was repeated against `0.6.0-connectivity.16` after
adding controller class metadata. Its class `0xAC`, instance 0 revision request
received a successful reply with object revision 1. The `0x31A` requests and
class `0x64` service `0x4B` still returned unsupported-service errors. Go Online
still failed with `RxE_COMM_ASA_SERVICE_NOT_SUPPORTED`. Both native attempts used
the same preserved ACD content; the original and private input hashes remained
unchanged. Independent client checks and 433 behavioral tests on each of Windows
and Linux passed for `.16`.

The `.18` retest added the File Manager class-discovery subset. Its native
class-revision request received a successful UINT revision-1 reply; the earlier
Get Attribute Single fallback was no longer sent. Of the 11 CIP events recorded
during this attempt, the sole unsupported request was Extended Device class
`0x64`, instance 1, service `0x4B`. Go Online still failed with
`RxE_COMM_ASA_SERVICE_NOT_SUPPORTED`. The ACD inputs, shared native-service
configuration and installed attribute-reference files retained their original
hashes. Independent client checks and 452 behavioral tests on each of Windows
and Linux passed for `.18`.

The normal `.20` endpoint was then tested with the matching private ACD through
RockwellMCPServer and the native Logix Designer SDK. Open Project, Read Connected
State and Get Communications Path succeeded. Its 12 CIP events include a
successful `0x64` / `0x4B` response containing the 130-byte challenge payload.
Studio next sent a 22-byte `0x64` / `0x4C` request, which returned unsupported
service (`0x08`). That was the sole unsupported request in this attempt.
Go Online still failed with `RxE_COMM_ASA_SERVICE_NOT_SUPPORTED`; the failure
phase advanced to confirmation. The original and private ACD hashes and shared
native-service configuration were preserved. Tag writes remained disabled.

### Passive reference handshake

A separate passive Studio v35 reconnect capture from a real v35 controller on
2026-10-19 contains the same 297-byte Extended Device `0x4B` request payload as
the emulator's native probe. Nine observed successful responses each contain
130 payload bytes: a UINT value of 128 followed by 128 bytes that differ between
exchanges. Studio next sends Extended Device `0x4C` with a 22-byte payload; its
successful reply contains 32 payload bytes. Subsequent requests use Message
Router services `0x36`, `0x37` and `0x38`.

This establishes request/reply shapes and ordering in the reference trace.
The varying data and vendor semantics require further analysis;
recorded controller replies are not used as emulator responses. The capture and
project details remain local. This passive observation does not change the
emulator's native Go Online result.

These are observed gaps, not a complete list of requirements for native online
operation. The trace does not establish the vendor payload layouts or which
response prevents later phases. Service `0x4B` on class `0x64` is a different
object request from the implemented Identity Object device locator. Unknown
requests retain explicit errors until their behavior is established.

This probe did not demonstrate the Studio GUI's Set Project Path, upload,
download or online monitor. ACD inputs, exact target configuration, job receipts
and packet samples remain in ignored local storage. The diagnostic CLI above
retains its loopback restriction; the appliance test used the separately
configured, target-allowlisted RockwellMCPServer instance.

The ASA naming in the native error refers to CIP in the
[FactoryTalk Linx SDK reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/lnxsdk-rm001_-en-e.pdf),
chapter 4. The remaining vendor request's response layout and later connection
stages still require separate evidence.

## References

- [Rockwell Logix data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf)
- [Rockwell Logix Designer SDK guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf)
- [pycomm3 client implementation](https://github.com/ottowayi/pycomm3)
