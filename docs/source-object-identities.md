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
| `matched` | Program, Routine and Symbol ID sets match the supplied bindings |
| `partial` | Program/Routine IDs and all known Symbols match, with additional unresolved Symbols |
| `mismatch` | Source pairs conflict, parent bindings disagree, or required ID sets differ |

TagInfo can omit internal Symbols present in a download. Additional staged
Symbols remain unresolved; the model supplies no names or identity equivalence
for them. A partial result permits the existing isolated temporary image only.
Neither partial nor matched identity results grant installation authority.
Data Table IDs, native addresses, compiled routines and downloaded initial values
remain outside this comparison. Reciprocal Symbol/Table links are checked by the
separate [temporary object graph](object-staging.md).

## Atomicity and lifetime

A mismatch returns CIP `0x03` with `source_object_verification_failed`. Templates,
diagnostics, object descriptors and image storage remain unpublished. The fixed
failure is cached until transport cleanup.

Successful inspection retains a fingerprint of both source manifests, including
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
16 TagInfo Symbols match; six additional Symbols remain unresolved. All 911
temporary preparation effects retain their readback checks. Inventory, supported
routine replacement, reconnection, execution and edited L5X reload run in
separate disposable models. No SDK or physical controller is used.

The RTO result encoding, complete native upload/download, native address discovery
and the full Test/Untest/Assemble lifecycle remain unfinished.
