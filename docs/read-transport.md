# Signed read streams

Version `.132` decodes the observed Message Router `0x3A` read transport. The
successful saved upload uses it after Routine metadata. It carries an initial
CIP request followed by raw stream chunks. The chunks are not embedded CIP
replies and do not receive invented operation status codes.

## Framing and integrity

| Direction | Format | Position field | Body |
| --- | --- | --- | --- |
| Initial request | `0x101` | Zero | One bounded CIP request |
| Continuation request | `1` | Bytes already received | Empty |
| Complete initial reply | `0x301` | Total bytes | Entire stream, possibly empty |
| Fragmented initial reply | `0x101` | Total bytes | First chunk |
| Continuation reply | `1` | Requested byte offset | Next chunk |
| Final continuation reply | `0x201` | Requested byte offset | Last chunk |

Requests use the observed Message Router instance-1 path. Successful replies
use the corresponding wrapper service. Both directions retain the four-byte
counter and 20-byte MAC. Known-key verification checks the complete message
before its MAC and the requested counter/context. Parsing saved traffic alone
does not verify a MAC or authenticate a controller.

The codec supports framing, verification and encoding separately. An encoded
frame is data; it does not dispatch the inner request. Unsupported formats,
wrong response counters, inconsistent lengths and malformed request extents are rejected.
The same successful-wrapper profile does not decode other response dialects.

## Detached assembly

`logixlab.read_transport.Assembly` accepts ordered parsed request/chunk pairs in
a caller-owned session context. It requires an initial request, exact subsequent
offsets, increasing counters and completion at the declared total. Missing,
overlapping, repeated, reversed or premature final chunks cannot produce a
completed value. Rejected frames leave the retained stream unchanged.

The defaults bound a stream at 8 MiB and 4,096 frames, in addition to the shared
65,519-byte message limit. Callers may choose smaller limits. Bytes are available
only after completion; `clear()` discards the pending stream. The caller must
keep sessions separate and clear obsolete context. The assembler retains no
keys, contacts no endpoint and executes no assembled content.

## Inspection tools

The existing capture inspector recognizes `0x3A` and retains the first request's
Program or AOI scope, chunk lengths, offsets, completion flags and hashes. Values
stay omitted by default. Full frame or chunk bytes require the explicit private
payload option. Keep captures and generated reports in ignored local storage.

The transfer checkpoint analyzer reports `read_transport_frames`, their total
count and byte count separately from embedded CIP requests and download fragment
acknowledgements. A stream-complete flag describes a transport frame, not native
upload acceptance. Wrapper rejections and malformed frames retain their existing
reporting boundaries.

## Validation and native boundary

All 4,333 saved exchanges frame and reassemble into 2,394 complete streams:
1,100,885 bytes in total. The largest stream is 7,020 bytes across 16 frames.
These include Program/AOI-scoped Routine reads and AOI definition reads. Counts,
offsets and complete-stream hashes are retained privately; captured content is
not copied into the running emulator. MAC integrity of the saved capture remains
unverified. Synthetic known-key checks cover MAC changes and replay/offset errors.

A separate native trial changed only the unscoped Executable class revision to
11. Studio read that value, but the same Program upload failure followed the
successful 22-field Routine reply. That change does not resolve the current
failure and is not shipped. The next successful reference step uses `0x3A`;
the failing SDK attempt does not reach it.

The live endpoint still rejects `0x3A`; this revision adds analysis primitives
without native stream-read or write authority. Routine source semantics, full
native upload/download and native client reconstruction remain unfinished or
unverified.

All 324 affected checks pass; the full suite was not rerun. The restarted demo
passes 274 live checks and native SDK Go Online/Go Offline across 75 verified
signed requests, with actual Offline/cleanup, unchanged source/model and no
reported fatal SDK fault. Inputs, logic and edit configuration match across the
restart. The webpage, packaged assets, executable version and all 93 deployed
app modules match `.132`.
