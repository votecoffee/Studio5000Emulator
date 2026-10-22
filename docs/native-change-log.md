# Source-backed empty Change Log reads

Version `.151` extends the read-only Change Log search used during v35 upload.
It preserves the imported cursor and does not create history records.

## Source evidence

The original ACD's `OfflineChangelog.Dat` supplies the existing correlation
header. Additional empty-log evidence requires a zero Change Index and exactly
four zero trailer bytes followed by EOF. Missing, nonzero, truncated or longer
trailers do not grant this profile. Compressed and plain streams use the same
bounded check; the original ACD remains unchanged.

The source manifest carries `empty_change_log` as a boolean. Legacy manifests
remain readable and default this evidence to false. The flag requires a zero
source index and cannot be inferred from an absent L5X element or zero runtime
audit updates. Refresh an older import from its original ACD to collect the
additional source evidence.

## Search contract

Change Log class `0xAC`, instance `1`, service `0x4F` takes two little-endian
UINTs: Change Index and Generation Count. The existing exact imported-cursor
lookup remains supported. With the empty source profile and an unedited
execution model, two additional observed upload lookups are supported:

| Index | Generation | Reply |
| --- | --- | --- |
| 0 | Imported generation plus one | The same four requested bytes |
| 1 | Imported generation | The same four requested bytes |

The next-generation lookup is unavailable when the stored generation is
`65535`; this subset never wraps it to zero. Unknown positions, generations,
stale source bindings and extra lookups after a structural edit remain errors.
Malformed lengths retain their CIP errors. Writes and other vendor services
retain their denials.

An empty result leaves the requested cursor unchanged. Returning the imported
cursor instead rebases the request and does not implement this empty-result
profile. No downloaded UID, fake log entry, gap-fill record or captured history
is inserted. Source UIDs, tags, scans, audit state and programming leases remain
unchanged. Endpoint `native_correlation` metadata exposes the source evidence.

The installed v35 Change Log definition independently identifies the UINT index
and generation fields. A saved successful upload contains an empty four-byte
cursor reply and a separate nonempty reply; the latter remains unsupported.

## Validation and limits

Tests cover compressed/plain source profiles, strict EOF/trailer boundaries,
legacy and malformed manifests, cursor echo and bounds, structural edit and
source changes, signed requests, retained write denial and unchanged modeled
state. Both owned native project fixtures contain the supported empty profile.
All 222 affected protocol/source and native-probe checks pass. The rebuilt `.151`
application passes live signed current, initial and end cursor reads, the existing
direct read path, unknown-history/write denials and the three Program selector
reads. Source/model/audit state is preserved. The normal SDK Go Online/Offline
case verifies 74 requests, confirms Offline/cleanup and reports no SDK fault;
the webpage, executable and appliance versions match.

A private minimal fixture completes SDK `UploadAsync` across 969 verified
requests after this change and the calculated
[Program selector replies](program-upload-query.md). Actual Offline, endpoint
cleanup, original source/model preservation and no reported SDK fault are
confirmed. This fixture also uses private Controller/clock/Task responses and
an existing source-matched type snapshot. Those temporary responses are not
shipped and do not establish full upload support in the normal application.
The retained trace suffix shows all three accepted selector replies; the
complete interval exceeds the current trace retention bound.

A subsequent successful `UploadAsync` is followed by a failed native ACD save:
the SDK service faults before creating the output file. The original files and
model remain unchanged. API-level upload success therefore does not establish
a valid reconstructed project; see the [upload-save diagnostic](development.md#native-sdk-acceptance-probe).

Normal application upload still stops at the earlier Controller collection
stage. Its `.151` trial verifies 188 requests, confirms Offline/cleanup and
preserves source/model state without reporting an SDK fault. Native download,
complete history reconstruction and arbitrary cursor
searches remain unfinished.
