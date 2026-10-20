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

## Offline reader

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
