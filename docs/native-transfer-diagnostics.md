# Native transfer diagnostics

Version `.96` adds transfer-specific trace checkpoints to the optional
[native SDK probe](development.md#native-sdk-acceptance-probe). It captures
`before-transfer-trace.json` immediately before Upload or Download, and
`after-transfer-trace.json` in a `finally` block before the probe's native
Offline cleanup. HTTP reads pin the emulator instance and source ACD hash on
both sides of each checkpoint. SDK operations are never retried by these reads.

The probe includes a `transfer_trace` section in `summary.json`. It reports:

- Signed envelope and inner-request counts, with the last 16 object requests.
- Up to 64 failed inner requests and separate outer wrapper rejections.
- Numeric object scopes, requested attribute IDs and CIP additional statuses.
- Fragment acknowledgements and byte counts, separately from object replies.
- Aggregate temporary download inspection, preparation and result-query state.
- Newly observed endpoint attribute gaps, excluding counts from earlier probes.

The report matches the retained checkpoint event instead of comparing SDK host
timestamps with guest timestamps. It counts outer signed envelopes only, so
duplicate inner CIP trace entries do not inflate the request count. Batch
children retain their order and Program/object scope. Malformed replies,
sequence mismatches and truncated events make analysis incomplete. A missing
or ambiguous checkpoint does not select a guessed interval.

Version `.97` retains complete CIP packets up to 65,519 bytes per request or
reply. The trace ring has two independent bounds: 1,000 events and 2 MiB of
retained binary payload (at most 4 MiB after hexadecimal encoding). Reaching
either bound evicts whole oldest events. `trace_capture` reports the limits,
retained bytes and dropped-event count; each event includes original request
and response lengths and an explicit truncation flag. Protocol counters keep
counting after trace eviction. An initially empty checkpoint also checks the
dropped-event counter before reporting a complete interval.

This removes the earlier 1 KiB prefix limit for native download fragments.
Capture retention and framing validation remain distinct from MAC verification,
image acceptance and execution. Busy endpoints can still evict a checkpoint;
the reader then reports an incomplete interval.

Version `.126` increases the event limit to 2,000 after the 136-definition
diagnostic upload exceeded the earlier 1,000-event ring. The 2 MiB retained-byte
budget and per-packet limit remain unchanged. Both bounds still evict whole
events and report loss. A discarded checkpoint still makes analysis incomplete.

## Offline reader

Version `.125` retains well-framed object paths even when the live path decoder
does not support that parent/child combination. Numeric parent scopes and
rejected replies remain visible, with `object_path` and
`dispatch_path_supported: false` identifying the offline fallback. Distinct
unsupported parents stay separate in aggregate counts. Malformed paths remain
unparsed; this does not authorize new live routes or infer an SDK failure cause.
See [Program catalog discovery](program-catalog-discovery.md).

### Collection attribute lists

Version `.126` adds Device Diagnostic Message (`0x3B2`) instance framing:
USINT-counted Message ID and Message Code strings, bounded at 40 and 128 bytes,
and a two-byte revision. Class instance zero and parent-scoped paths are excluded
from this instance schema. The [source-bound runtime catalog](device-diagnostic-messages.md)
and offline decoding are separate capabilities.

Version `.115` decodes established instance-one attribute-list layouts for
Time Sync (`0x43`), Extended Device (`0x64`), PLC message mapping (`0x67`),
TCP/IP Interface (`0xF5`) and Ethernet Link (`0xF6`). Both saved capture analysis
and checkpoint reports use the same bounded decoder. No SDK or network call is
needed to analyze existing files.

Checkpoint reports retain up to 64 `collection_attribute_lists`, with total
observations, layout-error counts and a truncation flag. Each row retains its
signed request sequence, ordinal, numeric object target and requested fields.
Field rows contain ID, status, value byte count and a hash for successful values.
These are responses correlated to the specific signed request, independently
of the endpoint-wide attribute-gap counters. Attribute values remain omitted.
The capture reader also permits explicit `--include-payloads`; its existing
`time_sync_attribute_list` field remains compatible, and other recognized
objects use `collection_attribute_list`.

The decoder verifies request order, duplicates, exact field bounds and general
versus field statuses. Partial replies retain their unreturned suffix separately.
Unknown successful fields, unsupported nonempty trusted-slot layouts, truncation
and trailing data retain an explicit `UNSUPPORTED OR MALFORMED` result. A
malformed collection keeps the request in the checkpoint report and makes
`analysis_complete` false. It does not hide other requests or count as native
upload failure by itself. Value meanings and failure causes remain unassessed.

Version `.116` adds [Wall Clock Time](controller-schema-discovery.md#read-only-wall-clock-time)
class `0x8B` to the shared decoder. It preserves the separate legacy/UTC counter
widths, calendar arrays and UINT32-length timezone string framing. Decoding a
recorded field does not enable that field in the runtime.

Version `.117` adds [Program collections](edit-program-state.md#program-kind-and-original-instance)
at their actual nonzero instances. Shared framing includes opaque address
widths, 44-byte fault records, counted names and up to 1,000 child IDs. Class
instance zero and nested parent scopes are excluded. All 40 Program lists in
the completed reference upload frame without errors; values remain omitted by
default. Runtime support remains limited to separately implemented fields.

Extended Device strings use the installed v35 UINT-length profile without word
padding. TCP/IP domain and hostname strings use their separate padded profile;
[OpENer's string encoder](https://github.com/EIPStackGroup/OpENer/blob/master/source/src/cip/cipcommon.c)
provides an independent implementation reference. Ethernet Link counter fields
retain their fixed array widths. No third-party implementation is bundled.

Validation frames all 130 recognized collection lists in a completed successful
v35 reference upload, including both partial Time Sync replies. Reanalysis of
the `.114` structured-project SDK trace finds seven recognized lists with no
layout errors and fourteen unavailable Time Sync fields. A separate disposable
comparison supplies complete generated software-clock datasets with corrected
counted vendor-address framing. It receives a successful full clock list but
still fails `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED` across 200 verified
signed requests. Native Offline, cleanup and source/model preservation pass
without a reported fatal SDK fault. The generated no-master conventions are
experimental and are not loaded by the released app; they do not establish
physical clock semantics or a completed native upload.

### Source verification results

Version `.110` includes `source_verifications` in the derived report. Ordered
type and object verification events retain their advertised status, aggregate
match/unresolved counts and capability flags, including original Template and
Table identity checks. Error contents, object IDs, source hashes, names and
member definitions are omitted; `error_categories` counts the reported entries.

These events use the same retained checkpoint interval as the signed requests.
Earlier transfer matches cannot supply evidence for the current operation.
Older events retain only fields they actually advertised; missing fields do
not become successful identity checks. At most 16 valid rows are retained,
with observation/invalid counts and a truncation flag. Invalid statuses, integer
counts, boolean flags or error-list bounds make analysis incomplete. Malformed
rows are omitted without hiding the other request/phase diagnostics.

This reports the emulator's source comparisons alongside its temporary image
preparation. It does not independently verify their provenance, a native MAC,
device execution or installation, and does not infer the SDK failure's cause.

The same report can be generated later from saved files, without starting the
SDK, connecting to a controller, or reading a packet-capture interface:

```powershell
py -3.13 -X utf8 source/tools/analyze_native_transfer.py --before .local/probe/before-transfer-trace.json --after .local/probe/after-transfer-trace.json --operation upload --sdk-result .local/probe/sdk-result.json --output .local/probe/transfer-analysis.json
```

The output must be a new file. Each JSON input is bounded to 32 MiB; analysis
accepts at most 2,048 trace events and 4,096 inner requests. Exceeding the request
limit stops analysis and marks it incomplete. Smaller display limits retain
total counts and truncation flags. The original inputs are preserved.

## Evidence limits

Raw payloads, tag names, signature bytes and attribute values are omitted from
the derived report. Original trace files still contain private material and
belong in ignored local storage. Preparation fields are numeric aggregate
simulator state; they are not native execution results or a download commit.

The reader checks framing without verifying MACs. Endpoint attribute-gap
counters include all readers during the interval, so they do not independently
identify one SDK request. An observed protocol error is not automatically the
cause of a later SDK collection failure. SDK status, native Offline confirmation
and endpoint cleanup remain separate fields in the probe summary. Failure to
decode the diagnostic does not prevent the Python probe from checking cleanup.

The [download result codec](download-image.md#native-boundary), Controller
handler-reference encoding, full upload/download, native tag-address discovery
and the full native edit lifecycle remain unfinished.

## Native validation

### Recovered-service baseline

The fresh `.109` baseline after SDK service recovery passes native Go Online
and Go Offline with 78 verified signed requests. It preserves the source ACD
and active model and confirms endpoint cleanup without a reported fatal fault.
The separate DINT tag-read case still reports `RxDA_E_NO_ONLINE_ADDRESS` and
also confirms Offline and cleanup. Failed metadata hypotheses are not retried.

The fresh demo download matches all 242 original Template IDs and 13,312
members, one Program, two Routines, 20 Symbols (including six auxiliary entries)
and 16 Data Tables. It prepares all 904 temporary records and reaches the RTO
result query; `RxCsE_DOWNLOAD_OF_DEVICES_FAILED` remains the SDK result. The
report decodes 183 inner requests and all 21 fragment acknowledgements, with
zero malformed events. Native Offline, endpoint cleanup and source/model
preservation pass, and the SDK service remains running.

The `.110` offline reader reproduces this saved exchange and retains both
identity verification events with no new native calls. Full transfer, native
tag addresses and the vendor result encoding remain unfinished.

The `.96` demo upload verifies 195 signed requests and still reports
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`. Its checkpoint report decodes
198 inner requests without malformed/truncated events. The last request reads
Time Sync attributes 1 through 28 and 102 through 105, returning aggregate CIP
attribute-list status `0x0A`. This case does not reach the Controller handler
reads present in earlier traces. The last observed request does not independently
establish the cause of the SDK failure or a missing field's correct encoding.

Download verifies 180 signed requests and still reports
`RxCsE_DOWNLOAD_OF_DEVICES_FAILED`. The report retains preparation and result-query
events for all 904 records, including 242 Templates and 16 temporary tables.
The unsupported result query remains an inner error. Twenty-one large request
events exceed the endpoint's 1 KiB trace-byte limit, so framing analysis is
explicitly incomplete; their omitted bytes are not reconstructed or counted as
verified fragment acknowledgements.

Both cases preserve source/model state and confirm native Offline and endpoint
cleanup without a reported fatal SDK fault. The standalone reader reproduces
both saved summaries. A fresh connection/Offline case passes across 79 verified
requests. Fifty-three focused software tests pass; the full suite is not rerun.

The SDK harness also compiles successfully after a conventional local build and
with isolated intermediate/output folders. Its explicit `Program.cs` input
prevents a prior build's generated C# files from entering a later isolated
compilation.

### Complete capture in `.97`

The rebuilt `.97` upload verifies 197 signed envelopes and decodes 200 inner
requests, with no incomplete events. It reaches Controller Get All and the
six-attribute handler/configuration read after the unchanged Time Sync profile.
The SDK still reports `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`. The
different final request in `.96` therefore does not establish a clock-code fault;
no speculative Time Sync values or handler encodings are added.

Download verifies 181 signed envelopes and decodes 185 inner requests plus all
21 fragment acknowledgements. Framing analysis is complete, with zero unparsed
or truncated events. The fragments contain 82,550 bytes, including the 16-byte
device header. Offline reconstruction retains the complete 82,534-byte encoded
payload, expands 371,787 bytes, and matches all 904 per-operation fingerprints
and preparation effects against the captured receipt. No payload bytes remain
uncaptured. This is framing/model evidence; the reader does not verify MACs or
establish native execution.

The SDK still reports `RxCsE_DOWNLOAD_OF_DEVICES_FAILED`. The image result query
retains its explicit unsupported error; temporary preparation does not replace
the active model. Both transfer cases preserve source/model state, confirm
native Offline and endpoint cleanup, and report no fatal SDK fault. A separate
native indexed-edit case succeeds across 315 signed requests and reproduces its
scans with queued external inputs and a saved L5X reload. Seventy-two focused
software tests pass; the full suite is not rerun.
