# Program upload query diagnostics

The offline capture and [native transfer checkpoint reader](native-transfer-diagnostics.md)
describe the observed v35 Program service `0x50` exchange. Version `.150`
adds a bounded signed response for its three observed selector queries.

## Observed framing

The request targets one unscoped numeric Program instance. Its eight-byte
payload contains a two-byte `0x0101` word, a two-byte selector (`31`, `32` or `33`),
and a four-byte zero position. The successful reply has a `0x0301` four-byte
container word, a four-byte byte count of eight, a four-byte checksum and
a four-byte selector matching the request. The checksum is the complemented
IEEE CRC-32 of that returned selector encoded as a little-endian UDINT:
`zlib.crc32(struct.pack('<I', selector)) ^ 0xFFFFFFFF`.

All 60 matching exchanges in a saved successful upload consume exactly with
this shape and checksum. Each selector has the same checksum across all 20
Programs. It covers the returned four bytes; it is not a Program signature,
metadata record identifier or compiled-code checksum. The selectors are not
assigned Program attribute names. Replies are calculated, and captured words
are not installed in the emulator.

Reports retain the selector, status, byte count, record count and opaque-word
hash, checksum algorithm and verification result. They do not expose the word
itself. Invalid paths, unsupported selectors
or positions, truncated data, mismatched selectors and unexpected successful
reply shapes or checksum mismatches are rejected. A normal error reply retains its status without
inventing returned records. Checkpoint query/error counts continue after the
64-row retention limit; a shape error makes `analysis_complete` false.

## Live read boundary

Only a bound native compatibility session may issue this read, targeting one
known Standard Program from the matching original ACD/L5X pair. Class-level,
attribute, parent-scoped and symbolic paths are rejected. Missing, stale or
foreign Program bindings remain errors. Only version `0x0101`, selectors
`31` through `33`, zero position and the exact eight-byte request are supported.
The reply requires a 20-byte inner CIP response budget. There is no continuation
or empty-success substitute.

Reads do not reserve a programming lease, change tags, execute scans, update
audit state or install project data. Plain requests and neighboring vendor
services retain their errors. Endpoint state describes this subset under
`program_upload_query`. Checksum validation, source identity, message MACs and
successful native upload are separate checks.

## Native investigation

An isolated upload experiment with private Controller field placeholders got
past the Controller list and reached this Program query. The normal app still
withholds those Controller fields because their value contracts are unresolved.
A further private empty Program reply experiment faulted the SDK. Its original
source and model were preserved, but native Offline could not be confirmed.
The private endpoint was stopped and the main demo endpoint restored. The empty
reply is not part of this decoder's successful profile and is not a live response.
After SDK service recovery, the established `.146` demo Go Online/Offline check
passes across 74 verified requests with native Offline and endpoint cleanup
confirmed, source/model preservation and no reported fault. The experimental
response trials remain retired.

Neither earlier experiment establishes a complete upload. The `.150` response
uses the checksum relationship subsequently verified against all 60 recorded
replies. It does not reuse the retired empty response. Controller collection
remains an earlier incomplete upload stage; download result encoding and full
native transfer remain unfinished.
