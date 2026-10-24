# Downloaded Routine source readback

Version `26.1023.205529` serves the observed Message Router `0x3A` read stream
for a Program-scoped Routine `0x5D` request with selector DWORDs `(1, 3)`.
It returns the exact source container retained from a successful
[source-equivalent download](download-image.md#source-equivalent-installation).
The download write prefix is removed; the container, TextIOI, RegionIds and
auxiliary bytes are preserved. Native compiled code is neither returned by
this selector nor executed.

## Source and session checks

The controller must have an installed, unchanged ordinary RLL model with the
original ACD correlation, native catalogs and retained Routine batch intact.
Each read revalidates the batch and resolves its source against the current
interpreter routine. An edited model, replaced Engine, changed catalog or
changed source refuses readback. Reset, reload and restart clear installation.
Active programming reservations also block this read.

The client first establishes its anonymous compatibility context. Every read
verifies its session MAC and exact next counter. This proves possession of the
emulator's challenge key; it does not establish vendor identity or operator
authorization. An unsigned request or another session cannot resume a stream.
Only one stream can be pending per context. Reconnect, expiry or an invalid
request clears that context's retained stream.

## Framing and limits

The existing [read transport codec](read-transport.md) supplies the wire framing.
An initial format `0x101` request has position zero and the scoped inner request.
Continuation format `1` carries only the next byte offset. Replies carry raw
container bytes, their stream position/total, an echoed counter and a MAC.
They fit the negotiated reply size, including the 36-byte wrapper and trailer.
The final reply uses the observed complete/final framing.

Missing starts, gaps, overlaps, second starts and excessive frame counts fail.
The stored download component limit bounds source storage, and the shared read
codec bounds frame counts. A small reply budget cannot leave a partial stream.
Other selectors, AOI paths, unknown routines and write operations stay denied.
Default object representations and aggregate trace events omit source bytes.
Explicit private protocol traces retain their existing bounded payload policy.

## Compatibility boundary

This returns retained downloaded source bytes. It does not reconstruct a new
ACD, translate an edited routine back into native source, provide arbitrary
memory reads or complete native upload. The SDK's current Program-collection
failure occurs before its first Routine source request. A working read service
does not establish that the SDK accepted or reconstructed that source.

Focused tests cover exact and fragmented TCP readback, source/model preservation,
foreign contexts, bad MACs, missing or stale offsets, catalog changes, edits,
programming reservations and reply budgets. Native acceptance checkpoints are
recorded in the [connectivity history](connectivity-history.md).

An independent client reads both routines from the deployed ConveyorDemo model:
1,140 bytes over four signed frames, matching the SDK's downloaded source
containers byte for byte. Response MACs and all ten source rungs are checked;
model values, scans and audit state remain unchanged. The SDK itself still
fails before requesting this service, so complete upload remains unfinished.
