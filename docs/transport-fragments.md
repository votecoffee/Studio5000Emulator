# Temporary device-transfer fragments

Version `0.6.0-connectivity.69` adds bounded fragment staging to the
[Resilient Transport setup](resilient-transport.md) milestone. The tested native
SDK sends an entire device payload, then reaches a device-operation request
that remains denied. No device data is installed and no active project changes.

## Supported framing

Message Router instance `1`, service `0x39`, carries a little-endian container
word and UDINT position, fragment bytes, the shared native UDINT sequence counter
and a 20-byte HMAC-SHA1. Each fragment's complete wrapper is verified before
staging changes. The native context must be bound, source-correlated and own a
ready preparation lease with Run Mode Inhibit and Resilient Transport setup.

| Container word | Position meaning | Fragment content |
| --- | --- | --- |
| `0x101` | Total payload bytes | Supported 16-byte device header, then first payload bytes |
| `0x001` | Payload byte offset | Next contiguous payload bytes |
| `0x201` | Payload byte offset | Final contiguous payload bytes |

The first header is service `0x5C`, a canonical class `0x412`, instance `0` path,
then two UDINT selectors `1, 20`. Other headers/selectors are denied. The size and
offsets exclude this header. The payload remains opaque; no vendor meaning or
validity is asserted for its contents.

An accepted fragment receives outer success `B9 00 00 00`, container words
`0x301, 0`, the echoed sequence and a MAC. This empty acknowledgement accepts
temporary bytes only. It does not report successful execution of service `0x5C`
or installation of any device. The older single-inner `0x39` dialect remains
separate and retains its existing policy.

## Bounds and cleanup

One assembly belongs to the preparation lease. Its declared payload must fit
both the setup byte ceiling and the implementation's 262,144-byte maximum.
There are at most 128 fragments and an absolute 30-second assembly lifetime,
which later packets do not extend. Individual wrappers retain the codec's
65,519-byte limit; endpoint frame limits and negotiated connection sizes further
restrict wire requests. Memory grows only as validated bytes arrive.

Offsets must match the received byte count exactly. Holes, duplicates, overflow,
premature final fragments, missing final markers, conflicting starts and excess
fragment counts reject the request and discard its assembly. An expired assembly
also clears; setup remains available for a new first fragment. Another context
cannot alter the owner's buffer. Invalid MACs or sequence counters invalidate
the owning context and clear all of its temporary stages.

The transport summary adds `fragment_staging`, `received_bytes`, `total_bytes`,
`fragments`, `complete`, `max_fragments` and `assembly_timeout_seconds`.
`buffer_allocated` reports whether staged bytes exist; `setup_only` is now false.
Configuration and payload bytes are omitted. `payload_transfer` and `commit`
remain false: neither device processing nor active project transfer is enabled.

Delete, preparation end, inhibit removal, release, disconnect, context expiry,
source/generation changes, reset, reload and endpoint stop discard the assembly.
The public SDK probe checks zero fragment counts and byte totals, no completion
marker and no allocated buffer at admission and cleanup. Older endpoints may
omit the new fields. The offline capture inspector describes fragments and empty
acknowledgements without asserting MAC validity; payloads stay private by default.

## Validation and next boundary

The normal-source SDK attempt stages 82,534 payload bytes in 21 contiguous
fragments. It then requests service `0x06` on class `0x412`, instance `0`.
That operation's device-specific behavior is unverified. It remains denied with
`0x0F`; the SDK reports `RxCsE_DOWNLOAD_OF_DEVICES_FAILED`. Delete, preparation end
and lease release succeed afterwards. Its final connected-state check is Offline, with the source
ACD, model values, scans and model time preserved and all temporary state empty.

The 924-test source suite covers independent OpenSSL vectors, per-byte MAC
changes, shared counters, replay, owner/source/preparation checks, offset and
capacity failures, fragment-count and time limits, opaque capture reporting and
lifecycle cleanup. It passes on Windows with two expected skips and Linux with
one expected skip.

The rebuilt `.69` runtime's application modules and served webpage match source.
The Windows executable's embedded version and webpage were checked separately.
The running endpoint passes 291 wire checks. The public SDK verification set is:

| Probe | Verified signed requests | Native outcome |
| --- | --- | --- |
| Connection | 81 | Nine steps succeed, including Go Online and Go Offline |
| Tag reads | 83 | Online address discovery still fails before value reads |
| Upload repeat | 199 | Controller-collection upload still fails; cleanup confirmed |
| Download | 181 | 21 fragments staged; device operation `0x06` denied; cleanup confirmed |

Each case confirms an Offline final state, preserved source/model and empty
temporary stages. An earlier upload attempt returned Offline with unchanged
source/model and empty stages, but its TCP connection outlasted the probe's
eight-second cleanup window. That report remains incomplete. The connection
subsequently closed, and the repeated upload confirmed cleanup within the
original window. The verification does not erase that earlier result.

Final state has zero TCP clients, a free uninhibited lease, idle preparation,
closed transport, zero staged byte/fragment totals and no allocated buffer or
completion marker. Scans and model time remain zero. The communications and SDK
services remain running.

Offline inspection of the captured payload finds a compressed container that
expands to 371,787 bytes containing 904 length-delimited request-shaped records.
Four record paths remain unsupported by the current path decoder. This is a
structural observation of the tested payload; it does not validate those records
or their effects. The runtime fragment handler neither decompresses the payload
nor executes records, so its byte ceiling applies to the staged opaque bytes.

Next work must establish the complete device-payload and processing contract
before accepting that operation, then source validation and atomic model
replacement. Full native upload/download, tag monitoring, online edits and Studio
GUI monitoring remain unfinished or unverified.
