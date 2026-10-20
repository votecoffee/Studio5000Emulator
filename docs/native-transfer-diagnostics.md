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

## Native validation

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
