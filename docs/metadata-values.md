# Staged metadata-definition values

This records the `.67` milestone. See [Resilient Transport setup](resilient-transport.md)
for the current native-download boundary.

Version `0.6.0-connectivity.67` accepts a bounded subset of `0x4F` value proposals
for temporary Metadata Definition objects. The tested SDK advances to Resilient
Transport setup. Active project properties, library binaries and project commit
remain unsupported.

## Scope and framing

Requests address class `0x349` in a bound signed context. The client must own the
source-correlated preparation lease with scans inhibited. Target definitions and
every referenced property definition must already exist in that client's stage.
The payload target is restricted to class `0x349`; controller, tag and other
active object targets are rejected.

The supported payload begins with UDINT format `0x301`, UDINT remaining-byte
length, UINT target class, UDINT target instance and two zero UDINT selectors.
Path instance `0` selects the bulk form: a UINT count followed by records with
UINT marker `0x7F`, UINT property reference, three zero UDINT selectors and a
typed value. A nonzero path instance supplies the property reference for one
record; the count and in-record reference are omitted. The marker and zero
selectors are observed structural constants; broader selector/locale semantics
remain unimplemented.

| Value kind | Supported encoding |
| --- | --- |
| `1` | UINT byte length followed by ASCII text; tabs and CR/LF are accepted |
| `2` | UINT type (`0xC2` SINT or `0xC3` INT), UINT element count and exact packed numeric bytes |

Packets are limited to 16 KiB, with 64 fields per packet/target and 1 KiB per
field. The whole stage permits 4,096 values and 256 KiB of value bytes. Empty
strings are supported; empty numeric arrays, duplicate bulk references,
unsupported types/selectors, truncated fields and surplus bytes are rejected.
These are software limits and an explicitly supported subset.

## Atomicity, cleanup and visibility

Every packet is fully parsed and checked before any proposal is retained.
Repeated identical values are idempotent; additive fields merge atomically.
Conflicting existing values or exceeded bounds leave the previous stage intact.
Deleting a definition drops staged targets and property references that depend
on it. The shared lease lifecycle discards all names and values on preparation
exit, inhibit clearing, disconnect, expiry, invalidation, reset, reload or stop.

The active project/catalog remains unchanged. No staged value is exposed through
active metadata reads, external device snapshots or tag memory. Connectivity
reports counts, byte totals, limits and `values_scope: staged_definitions`, with
`active_values_transfer: false` and `commit: false`. Names and values are omitted.
`native_metadata_value_packets` counts accepted packets. The webpage shows staged
definition/value counts and the project-commit limitation.

The public SDK probe now checks empty descriptor/value stages before admission
and before confirming cleanup. It accepts this scoped staging capability while
rejecting active data-transfer/commit authority. Older runtimes may omit staging
fields; advertised fields must pass the checks.

## Validation and next boundary

Fourteen added tests cover hand-authored bulk/single vectors, typed arrays,
every truncated prefix, invalid selectors/types, atomic failure, duplicate and
conflicting values, exact resource bounds, deletion, privacy, ownership, source
binding, signed batches/transfers, cleanup and probe admission. All 901 tests pass
on Windows and Linux, with two Windows skips and one Linux skip.

The final-source SDK attempt verifies 158 signed requests. It accepts 41 value
packets, staging 432 values (2,483 value bytes) across 24 definitions. Three
library-data writes remain denied. The SDK then requests service `0x4B` on
Resilient Transport class `0x412`, instance `0`, which remains denied, and reports
`RxCsE_DOWNLOAD_OF_DEVICES_FAILED`. Cleanup returns Offline with empty staging,
source hashes and modeled state preserved, and scan count/model time zero.

The rebuilt and deployed `.67` runtime reproduces that 158-request download
sequence and passes 284 wire checks. Deployed modules and packaged/served browser
assets match source. The public SDK probe completes all nine connection/Offline
steps with 81 verified requests. Tag reads still fail online-address discovery
across 83 requests; upload still fails controller collection across 197 requests,
after accepting twelve scalar reads and their Symbol descriptors. These are
observed counts for the recorded runs.

All four public probes confirm SDK Offline and endpoint cleanup through the
stronger staging checks. Final state has no TCP clients, no staged names or
values, idle preparation, a free lease, zero scan inhibit and scan count zero.
Original/copy hashes and modeled state are preserved. FactoryTalk Linx and the
Logix Designer SDK service remained running.

Next work must establish the Resilient Transport contract and bounded device
preparation before further transfer stages. Full upload/download, compiled tag
addresses, Studio GUI monitoring and online edits remain unfinished. Private
ACDs, vendor definitions, SDK binaries and native payloads/traces are not included
in the repository.
