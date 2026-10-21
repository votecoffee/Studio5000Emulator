# Download source object identities

Version `.106` compares staged Program, Routine and known Symbol IDs with the
original ACD bindings before publishing temporary download objects. This adds
an identity check alongside the existing [type member comparison](source-type-verification.md).
It does not implement native transfer completion or active-project installation.

## Comparison

The current ACD/L5X hash pair must agree with both `native_symbols` and
`native_routines`. The complete staged Program and Routine ID sets must match
their source inventories. Routine child IDs retain their Program parent.
Every known source Symbol ID must appear in its matching controller or Program
scope. IDs reused across scopes remain separate objects.

| Status | Meaning |
| --- | --- |
| `idle` | No retained comparison |
| `unavailable` | Optional source inventories are missing or incomplete |
| `matched` | Program, Routine, Symbol and supplied Data Table ID sets agree |
| `partial` | Program/Routine IDs and all known Symbols match, with additional unresolved Symbols |
| `mismatch` | Source pairs conflict, parent bindings disagree, or required ID sets differ |

TagInfo can omit internal Symbols present in a download. Additional staged
Symbols remain unresolved unless the separate original component binding below
establishes their identities. A partial result permits the existing isolated temporary image only.
Neither partial nor matched identity results grant installation authority.
Native addresses, compiled routines and downloaded initial values remain
outside this comparison. Reciprocal Symbol/Table links are checked by the
separate [temporary object graph](object-staging.md).

## Auxiliary Symbol identities

Version `.107` adds an optional `native_auxiliary_symbols` manifest. The bounded
ACD reader accepts active controller/Program Symbol paths in `Comps.Dat`, with
header version 0, body format 63, 700-byte bodies and observed component types
256, 264 or 1288. Explicit class collection records are excluded. Free records,
unrelated object scopes and trailing database bytes supply no identities.

Every TagInfo Symbol must first match a component name and logical path. The
reader then retains the additional original identities separately. Missing
coverage, duplicate paths/names, ambiguous history, unknown parents, unsupported
formats, invalid bounds and changed hashes withhold the binding. It accepts at
most 1,024 auxiliary entries; raw/compressed streams retain size and record limits.
IDs and names are never generated from order or guessed from internal names.

Conversion attempts this optional binding automatically. Appliance forwarding
and application load retain it separately from normal tags; load checks both
source hashes, parent bindings and conflicts with TagInfo before replacing the
active project. Reload drops stale identities. Full source inventories remain
private import provenance; polled descriptions expose counts and capability flags.

The download comparison includes these bound IDs in `symbols_matched`, with a
separate `auxiliary_symbols_matched` count. Missing supplied auxiliary IDs are
mismatches; additional unbound IDs remain partial/unresolved. Fingerprints also
pin the auxiliary manifest during processing and result queries. This binding
does not expose public Symbol instances, runtime tags, native addresses, alias
semantics or values, and grants no installation authority.

## Data Table identities

Version `.108` adds an optional `native_tables` manifest for original controller
Data Table IDs. The bounded ACD reader requires active `Comps.Dat` components
with type 256, header version 0, body format 38 and a controller-scoped `0x6A`
logical path. Variable-length bodies are retained only as byte-count metadata;
their contents and generated names remain opaque.

The supported body range is 417 bytes through 416 plus 1 MiB. The reader
requires one explicit controller collection, excludes explicit empty Program
collections, and rejects positive Program-scoped Tables in this limited profile.
Free and trailing records cannot supply IDs. Duplicate paths/names/history,
unknown formats, unsupported paths, malformed bounds and excessive inventories
withhold the binding. The limit is 1,024 Tables with the existing bounded raw/
compressed stream and record limits. An empty inventory needs an explicit
collection; absent records do not become a successful empty inventory.

Conversion, appliance forwarding and application load carry the optional binding.
Both original source hashes must match any supplied project manifests before
load replaces the active model. Reload clears it. Polled descriptions expose
counts and capability flags; original names and metadata remain private.

The complete staged Table ID set must equal the supplied source set. Missing
or extra IDs produce `native_table_identity_mismatch` and atomic rejection.
`tables_matched` and `tables_unresolved` retain counts. With a supplied matching
binding and no identity mismatch, `table_identities_verified` is true. Without
that binding it stays false, even if other supplied identity sets match.
Fingerprint checks also pin the Table manifest during processing/result queries.

This flag establishes logical IDs only. It grants no native address, storage
mapping, source-value decoding, compiled-code or installation authority. Body
tails are not interpreted as initial tag values. Public/model Table catalogs
and their value reads gain no entries from this source binding.

## Atomicity and lifetime

A mismatch returns CIP `0x03` with `source_object_verification_failed`. Templates,
diagnostics, object descriptors and image storage remain unpublished. The fixed
failure is cached until transport cleanup.

Successful inspection retains fingerprints of the supplied source manifests, including
the Symbol catalog's derived Program maps. Replacing or mutating a binding after
inspection rejects repeated processing and result queries with CIP `0x0C` and
`native_object_binding_changed`. An equivalent replacement with identical
contents retains the same fingerprint. This does not authenticate the source
files or infer a vendor result-response format.

The transport's `source_object_verification` and the
`native_source_object_verification` trace event expose counts, status and fixed
errors only. Names, IDs, hashes, addresses and payload values stay out of these
summaries. Expiry, transport deletion, preparation end, lease cleanup, project
replacement and endpoint shutdown clear the retained catalogs and comparison.
Native probe admission/cleanup requires this state to be idle and empty.

## Validation

Focused tests cover complete and partial matches, missing known Symbols,
scope collisions, wrong Program/Routine IDs, cross-source catalogs, cached
mutation, atomic rejection and cleanup. Signed TCP checks exercise acceptance,
rejection and result-query guards while preserving active values and scans.

A separate independently keyed loopback session uses an unchanged source pair
and a previously saved 911-record download. Its one Program, two Routines and
16 TagInfo Symbols match. In `.107`, the original component records also bind
the six additional Symbols: all 22 identities match, with zero unresolved.
Version `.108` also matches all 18 original Table IDs. All 911
temporary preparation effects retain their readback checks. Inventory, supported
routine replacement, reconnection, execution and edited L5X reload run in
separate disposable models. No SDK or physical controller is used.

Auxiliary fixtures additionally check compressed/raw sources, exact name/path
coverage, parent reuse, bounds, history conflicts, immutable manifests, atomic
import/reload, conversion forwarding and cached binding replacement. Independently
keyed TCP checks confirm that auxiliary IDs never enter public tag discovery.
Table fixtures cover explicit collections, variable record sizes, source hashes,
history/bounds, immutable manifests, import forwarding, unchanged public catalogs,
signed mismatch rejection and stale result-query guards. These checks preserve
active values and scan counts.

The RTO result encoding, complete native upload/download, native address discovery
and the full Test/Untest/Assemble lifecycle remain unfinished.
