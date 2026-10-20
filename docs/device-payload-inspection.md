# Structural device-batch inspection

Version `0.6.0-connectivity.70` inspects the completed
[temporary device-transfer payload](transport-fragments.md) when its prepared
owner requests service `0x06` on class `0x412`, instance `0`. It decodes the
container and request records, reports their structure and still returns
execution denial `0x0F`. No captured operation is dispatched or project replaced.

## Supported container and records

The decoder supports the observed definite-length CMS CompressedData profile:
version zero, zlib compression with omitted or empty NULL parameters, the
firmware-package content OID and one explicit primitive OCTET STRING. Its
container syntax follows [RFC 3274](https://www.rfc-editor.org/rfc/rfc3274.html)
and the content identifier from
[RFC 4108](https://www.rfc-editor.org/rfc/rfc4108.html#section-2.1.5).
This is a bounded subset; indefinite lengths, nonminimal lengths, unexpected
fields, other algorithms/content types, truncated data and trailing bytes fail.
Signature verification is not performed or claimed.

For this profile the final setup UDINT is treated as the expected expanded byte
count. It must be positive, within the expansion limit and match exactly. The
runtime caps encoded input at 262,144 bytes and expansion at 2 MiB, including
streams with very high compression ratios. Concatenated, incomplete and trailing
zlib streams are rejected without an unbounded decompression or flush.

Expanded data is a sequence of little-endian UDINT request lengths followed by
request bytes. At most 4,096 records of 2..65,519 bytes are accepted, and every
record must have a request service and a complete path. Logical and symbolic
segments are checked, including padding, parent boundaries and a maximum of
16 object scopes. Parents stay attached to their children. Inspection does not
extend live CIP routing or establish that record payloads or operations are
supported.

## Runtime result and lifecycle

Inspection requires the owning bound context, matching native source identity,
ready preparation and a completed fragment assembly. Only the exact object path
and an empty `0x06` payload are accepted. An incomplete assembly returns `0x0C`;
invalid container/record structure returns `0x03`. A decoded batch still returns
`0x0F`, with rejection reason `device_batch_execution_unimplemented`.

The transport's `inspection` summary reports `idle`, `decoded` or `invalid`,
expanded byte and record counts, scoped-record count and operation counts by
service and leaf class. It omits raw requests, values, symbols and instance IDs.
`execution_supported`, `signature_verified` and `payloads_exposed` remain false;
`records_executed` remains zero. Invalid results contain a fixed reason code,
without payload text. Results are cached for the completed assembly.

Assembly expiry/clearing and every existing transport cleanup path clear the
inspection. Decoded records and expanded data are not retained in the runtime;
only the bounded summary remains alongside the existing encoded fragment buffer.
The SDK probe rejects nonempty inspection state or execution/signature claims
at admission and cleanup. Older endpoints may omit this summary.

The same decoder is available offline:

```powershell
py -3.13 -X utf8 source/tools/inspect_device_payload.py --payload .local/device-payload.bin --expanded-bytes 371787 --out .local/payload-summary.json
```

Use the byte count recorded for the payload being inspected. The tool preserves
and rechecks its input, refuses to overwrite input or an existing output and
emits a summary with no captured request bytes. It opens no network connection.

## Validation and remaining work

The normal-source SDK attempt assembles 82,534 encoded bytes in 21 fragments,
then decodes 371,787 expanded bytes into 904 records, including six scoped
records. All paths are structurally decoded; the four paths previously
unsupported by the live decoder remain scoped and are not enabled for routing.
The SDK retains `RxCsE_DOWNLOAD_OF_DEVICES_FAILED` at service `0x06`, then returns
Offline with the source/model preserved and temporary state empty.

The 939-test suite covers malformed containers and streams, exact expansion
capacity, excessive expansion, record/path limits, scope preservation, cached
results, owner/source guards, cleanup, summary privacy and input preservation.
The suite passes on Windows with two expected skips and Linux with one expected
skip. The public offline tool also decodes the captured sample while preserving
its input.

The rebuilt `.70` runtime's application modules and served webpage match source.
The Windows executable's embedded version, webpage and decoder module were
checked separately. It passes 291 wire checks. The public SDK probes report:

| Probe | Verified signed requests | Native outcome |
| --- | --- | --- |
| Connection | 81 | Nine steps succeed, including Go Online and Go Offline |
| Tag reads | 83 | Online address discovery still fails before value reads |
| Upload | 199 | Controller-collection upload still fails |
| Download | 181 | 904 records inspected; execution denied; no records applied |

All four probes confirm Offline cleanup, an unchanged source/model and empty
temporary state. Final state has zero TCP clients, a free uninhibited lease,
idle preparation, closed transport, no allocated fragment buffer and idle
inspection with zero byte/record totals. Scans and model time remain zero.
The communications and SDK services remain running.

Next work requires semantic validation and temporary models for the batch's
Template, Symbol, Data Table and other object operations before any execution
acknowledgement. Native upload/download, online tag monitoring, online edits and
Studio GUI monitoring remain unfinished or unverified.
