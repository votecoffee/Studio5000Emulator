# AOI definition discovery and metadata

Version `.104` extends UDI Definition class `0x338` beyond an explicitly empty
catalog. An optional `native_aois` manifest binds original definition IDs to
the exact source ACD and L5X SHA-256 hashes. ACD conversion attempts this binding
automatically, and appliance import forwards it to the shared application.
Unavailable binding does not prevent offline L5X import.

## Source identities

The bounded ACD reader accepts standalone UDI Definition records with component
type 256, header version 0 and body format 21. It reads the six UINT16 logical
words, retaining only controller-scoped class `0x338` paths for explicit source
AOI names. It excludes collection, child Routine, free, unmatched historical
and trailing records. Duplicate names/IDs, conflicting history, unknown formats,
incomplete coverage and changed source hashes withhold the complete inventory.
No ID is generated from declaration order.

The source reader requires a complete v35 Controller export and one unambiguous
AOI section. Standard and Safety declarations supply metadata only. A named
`EncodedData` declaration with `EncodedType="AddOnInstructionDefinition"` may
supply its readable header; its payload is neither decrypted nor executed.
Unknown declaration forms, ambiguous case/namespace fields, context-only source
and pending plaintext edit forms cannot claim a complete inventory.

Load validates all IDs against the complete source names and any other supplied
ACD bindings before replacing the active project. Reload drops old identities.
Every instance read rechecks the source pair. A missing binding remains
unavailable, separately from an explicitly empty source catalog.

## Read contract

| Target | Read behavior |
| --- | --- |
| Class instance 0 | Attribute 1 is UINT16 revision 6, matching the installed v35 UDI Definition ADF and saved connection traffic |
| Instance list, `0x4B` | Sorted original UDINT IDs, bounded sparse cursors and reply-size pagination |
| Attribute 1, State | Two-byte zero for the model's unchanged plaintext AOI definitions; protected content remains unavailable |
| Attributes 12/13 | Explicit major/minor revision, each UINT16 |
| Attributes 19/21 | Explicit Revision Extension/Vendor, UINT16 byte length and at most 40 ASCII bytes |

Missing, malformed, non-ASCII or oversized header fields remain unavailable.
An explicit empty string has a successful zero length. Ordered attribute lists
preserve duplicates, individual failures and exact widths. Class maximum/count
fields, compiled pointers, CRCs and other unmodeled values remain
unavailable. Setters, object creation/deletion and compiled-definition upload
are unsupported.

State zero describes immutable original definitions in this model. It does not
describe AOI instance parameters or locals, interpret native edit-state bits, or
grant native AOI editing. The protocol's safety-related execution remains
unsupported; reading a Safety declaration does not execute its logic.

The [independent inventory reader](upload-inventory-client.md) records the AOI
catalog and each available metadata row. Names absent from the wire are not
inferred. `aoi_definition_upload` remains false.

## AOI-scoped routines

Version `.105` adds optional `native_aoi_routines` bindings for readable source
Routine declarations. The ACD reader requires component type 259, header version
0 and body format 54. Its logical words must contain an original AOI `0x338`
parent and Executable `0x6D` child with no further path. Program Routine records
use component type 256 and a separate parent namespace. Numeric parent and child
IDs may repeat across those namespaces without identifying the same object.

Both original hashes, exact readable Routine coverage and all parent IDs are
validated before a load replaces the active project. Conversion and appliance
import carry the new binding automatically when available. Missing, context-only,
protected or ambiguous Routine source withholds that parent's inventory. A
readable explicit empty `Routines` section can expose an empty catalog. Names
and IDs are never generated from source order or opaque protected data.

Scoped `0x4B` discovery preserves the parent for each sparse cursor. Scoped
class instance 0 exposes the partial legacy revision-1 catalog metadata. Positive
instances expose only an available legacy attribute 7 Description: a UINT16 byte
length followed by at most 128 ASCII bytes. Missing or malformed descriptions
stay unavailable; an explicit empty description has zero length. Type enums,
UIDs, addresses, compiled code and latest-ADF equivalence remain unimplemented.

The inventory reader retains each AOI's `executable_catalog` and `executables`,
along with `aoi_executable_inventory` counts and unavailable parents. Program and
AOI children share an aggregate Routine budget. Attribute-gap, rejection and
transfer diagnostics retain the AOI parent. Writes and compiled fragments cannot
resolve through the AOI identity binding or change its logic. Safety declarations
provide metadata only, with no native safety execution.

## Validation and limits

Synthetic format-21 fixtures cover bounds, compression, history, malformed
paths, immutable manifests and atomic import/reload. Independently keyed TCP
checks cover class revision, state and partial metadata lists, missing/stale
bindings, protected headers, denied writes and unchanged values/scan state.

A separate unchanged offline project supplies 68 original AOI IDs, including
three protected declarations. Owned loopback TCP reads check all available
headers and retain protected-state errors with scan count zero and confirmed
cleanup. That project uses the explicit research identity; its GuardLogix
processor is not relabeled as the L85E compatibility profile. Signed exchange
checks use a separate matching L85E fixture. Saved connection traffic establishes
the state reply shape, not identity equivalence for a different source revision.

No SDK or Windows service is used by these checks. Native Studio acceptance,
complete upload/download, compiled AOI execution and AOI online edits require
separate implementation and validation.

AOI Routine fixtures additionally check reused IDs across parents, pagination,
stale and cross-source bindings, exact import coverage, protected children,
denied edits and inventory bounds over independently keyed TCP. An unchanged
offline source pair supplies 98 readable Routine identities under 65 AOIs;
three protected AOIs remain unavailable. This is a separate unsigned research
endpoint check with no scans, SDK use or native GuardLogix acceptance.
