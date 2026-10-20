# Native session policy and diagnostics

Version `0.6.0-connectivity.58` retains the anonymous native read-only session
boundary while admitting two additional bounded compatibility operations.
Neither operation enables project transfer, online editing, tag setters,
operator authorization or controller mode changes.

## Existing Timeline UID acknowledgement

Successful v35 reference exchanges acknowledge different Timeline UID proposals
while readback retains the controller's existing UID. LogixLab implements that
already-initialized case for a source-bound ACD:

- A registered, bound native context and a valid signed request are required.
- The target is Change Log `0xAC`, instance `1`, with no attribute or symbolic
  scope in the path.
- Service `0x04` must contain exactly one Set Attributes List entry: attribute
  `10` and a nonzero four-byte UID proposal.
- The loaded ACD correlation must match the current L5X hash and already contain
  a nonzero Timeline UID. Missing, mismatched or unset correlation is rejected.

The response acknowledges that entry without assigning the proposal. All ten
Change Log fields, including the source Timeline UID, retain their existing
bytes. Subsequent single, list and all-attribute reads agree. The imported ACD,
source manifest, tag values and scan state do not change.

This is an emulator policy based on the observed already-set behavior. It does
not establish all firmware setter semantics. Initializing an unset UID,
replacing an existing UID, mixed attribute changes, unsigned setters and
unrecognized services remain unsupported. The `native_timeline_retained`
request count records these acknowledgements; the `native_session` API states
that initialization and replacement are unimplemented.

## Data Logging discovery

The Data Logging class (`0x71`) supports source-checked empty instance lists,
including the native upload cursor `101`. A complete controller export must
contain no configured trends, data logs, related references or protected data.
Absent or canonical empty `Trends` and `DataLogs` sections are accepted.
Duplicates, nesting, namespaces, context data, extra section attributes, text,
configured records and unknown related declarations withhold the empty claim.

Class revision `1` is a UINT. Maximum instance, instance count and class fields
`10` through `15` are UDINTs. For a proven empty source these counts, storage
sizes and logging capacity limits are zero: the software controller has no
native Data Logging engine. Unavailable source withholds those fields and
rejects instance listing. Log instances, configured-log uploads, captures,
storage allocation and logging control are not implemented.

The original source XML is checked before runtime filtering. Loading another
project recomputes this capability. `data_log_catalog` exposes its availability
and limits independently of external Device I/O or MQTT monitoring.

The [Logix import/export reference, chapter 16](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
documents trend declarations. The canonical empty `DataLogs` form was checked
against a native v35 export. The installed plain v35 Data Logging attribute
definition identifies the class fields; vendor definition files are not shipped.

## Rejections before object dispatch

The Connectivity page and API expose `native_rejections`. This separates
requests rejected by the native compatibility policy from ordinary object
errors and unsupported attribute reads. Groups include service, numeric object
IDs, optional numeric program scope, symbolic-path presence, CIP status, reason,
count and last-seen time. Unparsed paths are explicitly identified.

The summary stores no tag names, payloads, operator identities, Timeline UID
proposals, context tokens or keys. It keeps at most 64 groups, coalesces repeats,
evicts the oldest group and displays only the current project generation.
Endpoint replacement starts a fresh collector. Invalid signed-message MACs or
counters never reach this policy collector.

The webpage displays eight recent groups; trace export includes the full
bounded summary. Existing full protocol traces also contain raw messages and
should remain private diagnostic evidence. A rejected request does not by itself
identify the cause of a higher-level SDK failure.

## Validation boundary

Tests cover real signed TCP and batch requests, exact replies, immutable source
header readback, unavailable correlation, malformed proposals, source replacement,
configured and ambiguous logs, retained write denials, collector bounds and
payload-free summaries. These checks do not establish native tag address
discovery, complete project upload/download or Studio GUI monitoring.

The `.58` release passes 817 tests on both Windows and Linux, with two Windows
skips and one Linux skip. The executable and deployed webpage match source and
version; the running endpoint passes 236 wire checks. All nine public SDK
connection/Offline cleanup steps pass with 82 verified signed requests.

Separate deployed probes verify 84 requests for two failing BOOL/DINT reads and
198 for the failing upload. The SDK accepts the Data Logging list and Timeline
acknowledgements; subsequent UID readback matches the imported source. Tag
reads still fail with `RxDA_E_NO_ONLINE_ADDRESS` before any tag-read packet is
sent. Upload still fails with `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`
after the incomplete Time Sync list; it retains 12 scalar reads and 12 Symbol
descriptors. There is no demonstrated root-cause fix for controller collection.

A fresh private public-SDK download probe fails with
`RxCsE_ASA_INVALID_IOI_SEGMENT_TYPE` after 96 verified signed requests. It confirms
Offline cleanup; its client connection closes. The original ACD, modeled values,
scan count and scan time remain unchanged. No Windows service is reconfigured.
Native programming and Studio GUI monitoring remain unfinished.
