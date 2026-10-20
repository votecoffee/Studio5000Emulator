# Offline download replay

`source/tools/replay_download_image.py` compares a saved device payload and
emulator trace without connecting to a controller, starting the SDK or changing
services. It rebuilds the existing temporary download image, checks every
ordered request fingerprint and reads back each prepared resource effect.

Provide the original ACD and corresponding converted L5X to bind the type
metadata and replay to the same source bytes. The tool reads those files; it
does not convert, open or modify a project through Studio 5000.

```powershell
py -3.13 -X utf8 source/tools/replay_download_image.py --payload .local/device-payload.bin --expanded-bytes 371787 --source-acd .local/Controller.ACD --source-l5x .local/Controller.L5X --trace .local/download-trace.json --out .local/download-replay.json
```

Use the actual expanded byte count from the saved transport setup. The payload
is the assembled encoded device data, without its initial transport header.
Omit `--trace` to check only the payload and temporary image. The output must be
a new file. Inputs are hashed again before the report is written; changed inputs
cannot produce a completed report.

## What is compared

Replay checks the source-bound type metadata, exact per-record request hashes,
object associations and actual retained Create, attribute and Template Write
effects. Program coordination results describe historical acquire/release
transitions, separately counted from current resource readback.

When a trace is supplied, the comparison checks:

- The trace's ACD/L5X binding and its temporary preparation receipt, including
  record-stream digest, object counts, allocation size and result-ledger counts.
- Fragment order, offsets, total sizes and progress ranges against the saved
  payload. Each captured payload prefix must equal the corresponding bytes.
- The observed Resilient Transport request/response sequence after preparation,
  including request fingerprints, actual statuses and response payload sizes.

Emulator traces may truncate packet contents. The report explicitly counts
captured and uncaptured payload bytes; a matching prefix does not establish
the content of uncaptured bytes. Full request fingerprints and resource effects
come from replaying the separately supplied complete payload. Trace envelopes
are parsed structurally, without asserting session-key/MAC verification.

An ordinary comparison mismatch produces a report and a nonzero exit code.
Malformed, ambiguous or oversized inputs are rejected. By default, reports
contain aggregates and fingerprints. `--include-records` adds private object
scopes and typed per-record readbacks; keep such reports in ignored local storage.

## Current boundary

The saved `.79` trace agrees with the replayed 904-record image: 902 current
resource effects and two historical coordination transitions. Its 21 captured
fragment ranges cover the encoded payload, while the trace retains only packet
prefixes. The observed service `0x06` succeeds; the later empty service `0x4D`
is denied and followed by transport deletion.

This evidence still does not identify a valid `0x4D` result format. The tool
reports that contract as unresolved and does not generate response bytes,
assign vendor statuses or claim a complete native download. See the
[temporary image and result ledger](download-image.md) for the prepared state.
