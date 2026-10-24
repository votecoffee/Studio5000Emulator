# Recording long native transfers

The optional SDK probe accepts `--retain-transfer-trace` for upload and download.
It records new diagnostic events to a private compressed journal while the one
native process runs. This supports transfers whose beginning would otherwise
leave the endpoint's bounded trace ring.

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --retain-transfer-trace --output .local/native-probes/recorded-upload
```

Use the running emulator's configured address and matching original project.
The probe retains its existing instance, source, permission and idle checks.
The SDK call remains serial. Recording failure neither retries the native call
nor prevents its normal cleanup and result checks. A timeout terminates only
the probe process it launched and reports an uncertain native outcome.

## Cursor API and limits

The authenticated local `connectivity-trace-read` action returns a lightweight
page. An empty request starts at the current end without copying old events.
Subsequent requests provide that page's `trace_id` and `next_event` as
`after_event`. The optional `limit` is an integer from 1 through 256.

Each endpoint has a distinct trace identity and increasing event IDs. A stale
identity or future cursor is rejected. An evicted cursor reports the number of
missing events. Pages include the instance and source identity, current end,
continuation cursor and whether more events remain. They grant no PLC write or
execution authority.

The app retains its 2,000-event and 2 MiB packet-byte ring limits. The recorder
polls between bounded waits for its child process and writes each event once.
The journal is limited to 32,768 events and 64 MiB of expanded JSON; compression
reduces disk usage. A gap, replaced endpoint, storage limit or collection error
marks the recording incomplete. A slow recorder cannot recover evicted data.

Diagnostic reads retry a transport `TimeoutError` at most twice, using the same
cursor. Event ordering and endpoint checks still apply to the returned page.
Other read errors, gaps and identity changes stop recording immediately. This
read-only retry cannot relaunch or repeat the native SDK operation. The receipt
records timeout/retry counts and the collector exception class, omitting private
exception messages. Exhausted retries leave an incomplete recording.

## Evidence and replay

The probe writes `transfer-events.jsonl.gz`, a recording receipt and the existing
SDK checkpoints in its new output folder. Its transfer summary uses only the
exact event interval between those checkpoints. The reader verifies identity,
contiguous event IDs, file bounds and a completed footer. Missing or damaged
records produce `journal_incomplete`; a retained suffix cannot become a complete
transfer claim. Without the flag, the earlier checkpoint analysis is unchanged.

To analyze a retained recording without native tools or network access:

```powershell
py -3.13 -X utf8 source/tools/analyze_native_transfer.py --before .local/native-probes/recorded-upload/before-transfer-trace.json --after .local/native-probes/recorded-upload/after-transfer-trace.json --operation upload --sdk-result .local/native-probes/recorded-upload/sdk-result.json --journal .local/native-probes/recorded-upload/transfer-events.jsonl.gz --output .local/native-probes/recorded-upload/replayed-summary.json
```

The offline reader checks framing; it does not reverify message authentication
or infer the cause of a native failure. Complete trace retention and SDK method
success remain separate from saved uploaded ACD acceptance, logic equivalence
and native controller equivalence. Journals contain private protocol payloads
and belong in ignored local storage.
