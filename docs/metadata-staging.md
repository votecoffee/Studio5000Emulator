# Native metadata-definition staging

Version `0.6.0-connectivity.66` stages temporary Metadata Definition names during
native download preparation. The tested SDK accepts the definitions and then
attempts a metadata-value write, which remains denied. Definitions and values
are never installed in the loaded project by this feature.

## Supported contract

Create (`0x08`) and Delete (`0x09`) address class `0x349` at an explicit instance
ID from `1` through `0xFFFFFFFF`. Paths have no attribute, symbol or parent scope.
Both operations require a checked signed message, bound native context,
source-correlated lease ownership and completed preparation with scans inhibited.
The lease pins staging to the imported ACD/L5X identity and source generation.

Create accepts exactly one initializer: UINT attribute count `1`, UINT attribute
ID `1`, UINT name byte length, then the ASCII name. Supported names are identifiers
starting with a letter or underscore and containing letters, digits or
underscores, up to 128 bytes. A successful reply carries the UDINT instance ID.
Delete takes no payload and removes an existing staged definition for the owner.

At most 256 definitions can be staged. Repeating the same ID/name is idempotent.
A changed name for an existing ID or an identical name under another ID returns
a conflict. Invalid framing, unsupported names, unknown deletes and exhausted
capacity return explicit errors. Library and metadata staging have separate
namespaces and limits.

Ending preparation, clearing the inhibit, releasing the lease, disconnecting,
invalidating the context, resetting/reloading the project or stopping the endpoint
discards both staging areas. Source generation, hash and expiry are checked on
lease use or inspection. Rejected native MACs discard the owning stage immediately.
Staging never changes tag values, scan time, controller mode, Timeline UID or
the original project files.

## Catalog, values and diagnostics

The active Metadata Definition catalog remains independent of staging. Its
instance list, class counts and supported empty queries keep their existing
behavior. Staged definitions are not published as installed project metadata.

Metadata-value writes (`0x4F`) receive an explicit embedded denial, including
inside signed single, batch and observed `0x39` messages. Library-data transfer,
metadata-value transfer, project commit and online-edit authority remain disabled.
Accepting a definition name does not establish its property values or semantics.

`native_programming_lease.metadata_staging` exposes counts, bounds,
`descriptor_only`, `values_transfer: false`, `commit: false` and
`names_exposed: false`. Names and proposed values are omitted. Connectivity shows
the staged count and value-transfer limitation. Accepted Create/Delete requests
increment `native_metadata_create`/`native_metadata_delete`; structural rejection
summaries identify conflicts, missing entries, limits and unsupported value writes.

## Validation and remaining work

Ten added tests cover 8-/16-/32-bit paths, exact UDINT replies, name and resource
bounds, ownership, source binding, conflicts, independent clients, batch errors,
signed value-write denials, unchanged active catalogs and shared cleanup. The
887-test suite passes on Windows and Linux with two Windows skips and one Linux
skip.

A final-source SDK download attempt verifies 116 signed requests. It stages five
library descriptors and 23 metadata definitions, denies three library-data writes
and one metadata-value write, then reports
`RxCsE_DOWNLOAD_OF_METADATA_DEFS_FAILED`. SDK cleanup returns Offline; both
staging areas are empty, with source hashes, modeled values, scan count and model
time preserved. These results establish the bounded staging behavior; complete
native download remains unfinished.

The rebuilt and deployed `.66` runtime reproduces the 116-request download
sequence and passes 281 wire checks. Deployed modules and packaged/served browser
assets match source. The public SDK probe completes all nine connection/Offline
steps with 81 verified requests. Tag reads still fail online-address discovery
across 83 requests; upload still fails controller collection across 199 requests,
after accepting twelve scalar reads and their Symbol descriptors. These are
observed counts for the recorded runs.

All four public probes confirm SDK Offline and endpoint cleanup, unchanged
source hashes and modeled state. Final state has no TCP clients, empty library
and metadata stages, idle preparation, a free lease, zero scan inhibit and scan
count zero. FactoryTalk Linx and the Logix Designer SDK service remained running.

Next work must establish and validate the `0x4F` metadata-value format before
staging values, then address library data, project validation, atomic commit and
rollback. Native upload, compiled tag-address discovery, Studio GUI monitoring
and online edits remain separate unfinished stages. Private ACDs, vendor
definitions, SDK binaries and native payloads/traces are not distributed.
