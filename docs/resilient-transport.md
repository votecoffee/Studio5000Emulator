# Resilient Transport setup

Version `0.6.0-connectivity.68` implements temporary setup and deletion for the
observed Resilient Transport Object, class `0x412`, instance `0`. The native SDK
advances from setup to a segmented device-data request. Segmented transfer,
device installation and project commit remain unsupported.

## Supported contract

Only a bound signed context owning the source-correlated preparation lease can
use these operations. Preparation must be ready and its Run Mode Inhibit active.
Attribute, symbolic and nested parent paths are rejected.

| Service | Payload | Result |
| --- | --- | --- |
| `0x4B` | Exactly 16 bytes, described below | Empty success; records temporary setup |
| Delete `0x09` | Empty | Empty success; discards that setup |

Setup uses little-endian `UINT, UINT, UDINT, UDINT, UDINT` fields. The first three
must be `1, 1, 1`. This software model treats the fourth as a requested byte
ceiling, accepting `1..262144`. The tested SDK sends `262144`. The final UDINT
is retained as opaque configuration, with no asserted vendor meaning. These
interpretations describe the supported experimental dialect, not a complete
vendor specification. No buffer is allocated and no device data is accepted.

An identical setup retry is idempotent. Changing any field while setup is open
returns conflict `0x0C` and preserves the original state. Malformed or unsupported
setup returns `0x03`. Delete is idempotent. It does not release the programming
lease or clear its inhibit mask.

The lease's `resilient_transport` summary reports `open`, `setup_only`,
`buffer_bytes`, `max_buffer_bytes`, `buffer_allocated`, `payload_transfer`,
`commit` and `configuration_exposed`. Configuration bytes and the opaque word
are omitted. Payload transfer, allocation and commit remain false.

Setup clears on preparation end, inhibit removal, lease release, owner socket
closure, context expiry/invalidation, source or generation change, endpoint stop,
reset and project reload. Invalid signed framing/MAC/counters invalidate the
owning context and clear its temporary state. No active model or native source
identity is replaced.

The public SDK probe rejects an advertised open transport, nonzero byte ceiling,
allocated buffer or enabled payload/commit capability at admission and cleanup.
Older endpoints may omit this summary.

## Validation and next boundary

The final-source candidate accepts setup during the SDK's `DownloadAsync` call,
after five library descriptors, 24 metadata definitions and 41 metadata-value
packets. The definition stage holds 432 values totaling 2,483 bytes. The SDK then
sends Message Router service `0x39` with container word `0x101`, beginning a
segmented request addressed to class `0x412`, service `0x5C`.

That container is unsupported and returns outer error `0x0F`. This invalidates
the context, so subsequent cleanup packets on it are also rejected; socket
cleanup still discards the lease and all temporary state. The SDK reports
`RxCsE_ASA_NO_PERMISSION` and its final connected-state check is Offline. The
source ACD, model values, scan count and model time remain unchanged.

This result demonstrates a setup milestone only. The supported `0x39` format
`0x301` remains distinct from segmented `0x101`; setup success does not enable
either device payload writes or project transfer. Further work needs bounded
fragment framing, reassembly and acknowledgements before a verified device-data
contract, source validation and atomic model replacement.

Protocol tests cover setup bounds, conflicts, source/owner/preparation checks,
exact paths, signed batches, denied payload writes and lifecycle cleanup.
The current source suite has 910 tests, with expected platform skips.
Rebuilt-runtime acceptance is recorded separately after deployment.

Full native upload/download, native tag monitoring, online edits and Studio GUI
monitoring remain unfinished or unverified.
