# Downloaded Routine source readback

Version `26.1024.095632` adds the observed `TargetClass="Standard"` root
attribute to the served nonempty Routine source view. The retained download
container is unchanged. Conversion preserves every other XML byte, including
CDATA, declaration, TextIOI and RegionIds, and copies the original compressed
auxiliary block and padding exactly. Only the source compression block and its
header offsets are rebuilt. Every chunk revalidates the original source, native
bindings and installed model. Other classes and edited or protected profiles
remain unavailable. Empty downloads retain their existing byte-exact readback;
that profile has no demonstrated complete native upload.

The preceding native trial accepts selector `(1, 4)`, then reads all 676 source
bytes for the first routine before reporting `RxE_CORRUPT_RECON_DATA` after
367 verified requests. Its downloaded XML lacks `TargetClass`, which is present
in the saved successful upload profile. The new conversion addresses that
observed difference; only a subsequent native trial can establish acceptance.
Both source/model preservation and actual Offline cleanup are confirmed, with
no SDK fault and an identical replay of the complete 1,496-event journal.

Version `26.1024.094038` adds selector `(1, 4)` for an unchanged, installed
Standard RLL routine with its original unprotected Type `0x07FF` and source-key
metadata. The saved successful v35 upload returns an empty signed stream in all
708 Program-scoped requests for this selector. Its semantic name is unproven;
the emulator does not substitute compiled code or source for those zero bytes.
Unknown types, protected or missing source and edited models remain denied.


Version `26.1023.211522` also returns the opaque Routine component for selector
DWORDs `(1, 9)`. These thirteen bytes come from the validated incremental
download ledger. Each chunk rechecks that ledger and the original source;
the component is not interpreted or executed.

Version `26.1023.205529` serves the observed Message Router `0x3A` read stream
for a Program-scoped Routine `0x5D` request with selector DWORDs `(1, 3)`.
It returns the exact source container retained from a successful
[source-equivalent download](download-image.md#source-equivalent-installation).
The download write prefix is removed. This historical version preserves the
container byte for byte; the later upload view above adds its explicit class
while preserving TextIOI, RegionIds and auxiliary bytes. Native compiled code is neither returned by
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
Selectors other than `(1, 3)`, `(1, 4)` and `(1, 9)`, AOI paths, unknown routines and write
operations stay denied.
Default object representations and aggregate trace events omit source bytes.
Explicit private protocol traces retain their existing bounded payload policy.

## Compatibility boundary

This returns retained downloaded source bytes. It does not reconstruct a new
ACD, translate an edited routine back into native source, provide arbitrary
memory reads or complete native upload. The SDK now reads both Routine data components, completes Label discovery and
reaches routine building. The next observed request is selector `(1, 4)`. A working read service
does not establish that the SDK accepted or reconstructed that source.

Focused tests cover exact and fragmented TCP readback, source/model preservation,
foreign contexts, bad MACs, missing or stale offsets, catalog changes, edits,
programming reservations and reply budgets. Native acceptance checkpoints are
recorded in the [connectivity history](connectivity-history.md).

An independent client reads both routines from the deployed ConveyorDemo model:
1,140 bytes over four signed frames, matching the SDK's downloaded source
containers byte for byte. Response MACs and all ten source rungs are checked;
model values, scans and audit state remain unchanged. Complete routine-containing native upload remains unfinished; later checkpoints
record each observed SDK request separately from this independent-client check.
