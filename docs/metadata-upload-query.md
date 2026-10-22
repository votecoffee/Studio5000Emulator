# Metadata upload query decoding

Version `.148` adds a bounded decoder and offline replay tool for the observed
v35 Metadata Definition service `0x53`. It reconstructs fragmented metadata
streams and inventories their values without loading them into the emulator.

## Framing

Requests target the unscoped class `0x349`, instance zero. Three exact selections
are recognized: all Controller metadata, Controller attribute 26 and all-object
metadata. Initial requests use format `0x0101` and position zero; continuations
use format `1` and the number of body bytes already received.

The reply's second DWORD echoes that position, including zero in the initial
reply. It is not a total byte count. A single complete reply uses `0x0301`;
fragmented replies use `0x0101`, then format `1`, then `0x0201`. Each fragment
can end anywhere in a record. The assembly checks the selection, exact cursor,
frame order, nonempty intermediate fragments and byte/frame limits before
changing its state. Missing, duplicate or reordered fragments prevent a complete
inventory. A new initial request cannot conceal an abandoned earlier stream.

## Records

The detached reader consumes each target's class and opaque instance/context/
selector words, length-prefixed qualifier, locale word, definition ID, distinct
record word and three observed zero DWORDs. Supported value kinds are string
blobs, SINT/INT/DINT numeric arrays, object-reference arrays and empty values.
Reference entries retain their own length-prefixed name and target.

Identifiers and qualifiers remain detached from live objects. The record word's
relationship to source storage and MUID APIs is not established. String blobs
can contain an additional compressed representation; this reader retains their
exact bytes without expanding them. Unknown kinds, numeric layouts, nonzero
trailer words, duplicate record identities, invalid counts and truncation reject
the whole inventory. Record, reference, frame and byte limits bound the work.

A selected saved successful-upload reference contains 10,301 query exchanges.
All nine streams reconstruct and consume exactly: seven empty selections, three
Controller records and 43,830 all-object records. The large all-object stream
contains 4,714,153 body bytes across 10,293 fragments. These are framing and
record-layout observations, not proof of a source/value mapping or a completed
emulator upload. No captured values are replayed to Studio or copied into Git.

## Offline tool

Create a private capture report with complete payloads using
[capture inspection](development.md#offline-cip-capture-inspection), then run:

```text
py -3.13 -X utf8 source/tools/metadata_upload_query.py --input .local/metadata-capture.json --output .local/metadata-report.json
```

The input is an `inspect_cip_capture.py --include-payloads` JSON report or a
selected report preserving its paired request/response objects. Plain, decoded
signed and signed-batch query exchanges are supported. Unrelated decoded
requests are skipped. Unsupported request envelopes could hide a query and
remain errors; filtering a capture is a separate evidence-selection step.
Concurrent or interleaved streams need separate input reports.

The output path must be new. Reports contain aggregate counts, formats, cursor
positions and hashes. They omit names, target IDs, record words, qualifiers and
values. Error, incomplete-stream and query counts continue beyond the 64-stream
report retention limit. Exit status is zero for complete supported analysis,
one for an incomplete analysis and two for invalid input or output failure.
The tool opens no network connection and invokes no SDK.

Capture inspection and [checkpoint diagnostics](native-transfer-diagnostics.md)
also annotate individual query frames with the shared decoder. Per-frame
checkpoint decoding does not prove that a complete stream was retained; use
the replay tool for assembly and record validation.

## Remaining work

The live endpoint's existing bounded empty selections are unchanged.
[Source-bound definition names and IDs](metadata-definitions.md) are separate
from metadata values. Mapping original ACD values to runtime targets, qualifier
and locale semantics, string expansion, the [Program `0x50` query](program-upload-query.md)
and complete native upload remain unfinished. Download still needs the separate
class `0x412` result-response contract. This decoder verifies neither MACs nor
source binding, native acceptance or controller equivalence.
