# Native library descriptors and transfer envelopes

Version `.66` extends the lease with [metadata-definition staging](metadata-staging.md).
The notes below record the `.65` milestone and its then-current Metadata
Definition Create boundary.

Version `0.6.0-connectivity.65` adds temporary library descriptors and the
observed single-inner Message Router `0x39` envelope. The tested SDK now reaches
Metadata Definition creation. Library binaries, project replacement and native
commit remain unimplemented.

## Descriptor staging

A bound, signed client must own the source-correlated coordination lease and
complete [download preparation](programming-preparation.md). Create (`0x08`)
on class `0x37D` accepts explicit instance IDs `1..65535` and the observed
ordered two-attribute initializer: attribute `3` as UDINT type `0`, followed by
attribute `2` as a UINT byte length and ASCII library name. Supported names
contain letters, digits, `_`, `+`, `.` and `-`, with a maximum of 256 bytes.
The reply contains the UINT instance ID. No name is used as a filesystem path.

At most 64 descriptors may be staged. Repeating the same instance/descriptor is
idempotent. Changed descriptors or duplicate names under different IDs return
a conflict; unsupported types, framing and limits return explicit errors.
Delete (`0x09`) with an empty payload removes an existing staged descriptor for
the prepared owner. It cannot delete source objects or compiled libraries.

Ending preparation, clearing the inhibit or ending the lease discards every
descriptor. Disconnect, invalidation, reset, reload and stop use the same
cleanup; source generation, hash and expiry are checked before lease use or
inspection. A rejected native MAC immediately discards the owning stage.
No staged object survives as part of the project.

`native_programming_lease.library_staging` exposes instance/name-byte counts,
bounds and explicit `descriptor_only`, `data_transfer: false` and
`commit: false` fields. Names are omitted. Connectivity displays the descriptor
count and the library-data limitation. Counters distinguish accepted Create and
Delete requests; rejection summaries retain structural IDs only.

## Observed `0x39` contract

The supported request has the two-word Message Router instance `1` path,
UDINT format `0x301`, UDINT control `1`, one inner CIP request, then the usual
UDINT counter and 20-byte HMAC-SHA1. Control is retained as an observed constant;
other values and multiple-inner interpretations remain unsupported. The codec
uses the same container fields in its signed reply and correlates the inner
service and echoed counter.

The live endpoint checks the complete MAC and shared session counter before
dispatch. This wrapper requires an already bound context and uses the existing
native policy. Library-data writes receive an authenticated embedded denial;
the wrapper grants no transfer or commit authority. Replies reserve 36 bytes
for wrapper, container, counter and MAC within the negotiated CIP budget.

The offline capture inspector now exposes this envelope and its inner structural
path. Default reports omit raw payloads and label integrity **NOT VERIFIED**.
Parsing never authenticates a peer or executes captured requests.

## Validation and remaining work

Sixteen added tests cover independent OpenSSL MAC vectors, changes to every
request/reply byte, framing, counters, response budgets, capture privacy,
ownership, resource limits, source binding, signed batches, write denial and
cleanup. The 877-test suite passes on Windows and Linux with two Windows skips
and one Linux skip.

A final-source native SDK download attempt verifies 115 signed requests,
stages five descriptors and denies three `0x39` inner writes. The SDK continues
to Metadata Definition Create on class `0x349`, which remains denied, and reports
`RxCsE_DOWNLOAD_OF_METADATA_DEFS_FAILED`. It then returns Offline with source
hashes, modeled values, scan count and model time preserved. Preparation ends
and the descriptor stage is empty. Library binaries remain uninstalled.

The rebuilt `.65` runtime reproduces that 115-request download sequence and
passes 277 wire checks. The deployed modules and packaged/served browser assets
match source. The public SDK probe completes all nine connection/Offline steps
with 81 verified requests. Tag reads still fail online-address discovery across
83 requests; upload still fails controller collection across 197 requests,
after accepting twelve scalar reads and their Symbol descriptors. These are
observed counts for the recorded runs.

All four public probes confirm SDK Offline and endpoint cleanup, unchanged
source hashes and modeled state. Final state has no TCP clients, an empty
descriptor stage, idle preparation, a free lease, zero scan inhibit and scan
count zero. FactoryTalk Linx and the Logix Designer SDK service remained running.

Next work must define validated metadata staging and the actual library-data
contract, followed by source-aware project validation, atomic commit and
rollback. Full native upload/download, tag monitoring, Studio GUI acceptance
and online edits remain unfinished. Private ACDs, native traces, vendor library
payloads and definitions are not distributed.
