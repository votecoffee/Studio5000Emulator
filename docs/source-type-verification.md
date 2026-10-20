# Source-bound native member verification

Version `0.6.0-connectivity.77` compares the staged
[Template member definitions](template-layout-inspection.md) with the original
ACD's offline type metadata. A matching comparison is a prerequisite for future
storage mapping. It does not enable native tag monitoring, device installation,
full transfer or online edits.

## Import and binding

The optional ACD importer reads `TagInfo.XML` schema 1.0 using the same bounded
XML reader as Symbol discovery. It imports type names/sizes and ordered member
names, data types, offsets, optional bit locations, dimensions, external access
and hidden flags. DTDs, entities, unknown schema/fields, duplicate names, invalid
indices and out-of-range values fail. UTF-8 and BOM-marked UTF-16, compressed or
plain, use the existing source-preserving container reader.

The catalog is bound to both the original ACD SHA-256 and converted L5X SHA-256.
The appliance importer transfers that separate manifest. Load validates it before
replacing the model and rejects conflicts with either native correlation or
Symbol bindings. Reset/configuration retain it; a plain L5X or demo load clears
it. Unsupported optional metadata reports `native_types_error` while leaving
offline conversion available. No generated type layout substitutes for a failed
binding.

Catalog limits are 1,024 types, 4,096 members per type, 65,536 members overall,
254-character ASCII names, 1 MiB per source structure and 32 nested levels.
Dimensions have at most three positive entries with a product no greater than
65,535. Nested types must resolve without cycles, and source member extents must
fit their declared type. Predefined structures can overlay members; this check
does not invent an alignment or non-overlap rule for them. String markers are
checked as metadata only, without adding native string execution semantics.

The full manifest remains in private import provenance and the bound catalog.
Polled state/snapshot provenance exposes a small description with counts/hashes,
not thousands of member definitions. Connectivity reports `native_types` with
the same counts and source binding. `compiled_addresses` remains false.

## Observed member profile

The comparison requires type size, ordered member names, atomic/nested types,
array count/rank, access and member location to agree with the source. Native
Template IDs must be unique; nested references must resolve to the expected
source type name. Array members currently support one dimension of non-BOOL
elements. BOOL arrays and higher-rank member arrays fail verification.

The offset normalization is an inference checked against this source, not a
general firmware specification:

- The low 28 bits of the offset word must match the source byte location.
- For a source BOOL with bit metadata, the byte location is source offset plus
  `bit // 8`, and member INFO must equal `bit % 8`.
- Direct BOOLs without bit metadata retain their source byte location and
  require zero INFO. Ordinary scalars also require zero INFO; arrays require
  their element count.
- The observed high-nibble access profile is `0`/`3` for Read/Write, `A` for
  Read Only and `F` for None. Unknown flags or disagreement with source fail.
  Other meanings of these flags, including hiding/overlay semantics, are not
  inferred or used to grant access.

Opaque name suffixes and download trailers remain unverified. CRCs/signatures,
overlap semantics, executable types and actual native addresses are outside
this comparison. Matching source metadata does not authenticate firmware or
establish equivalent execution.

## Staging and cleanup

The signed device-operation handler requires a current source-bound catalog
before using it. A mismatch returns `0x03` with a fixed
`source_type_verification_failed` reason. No completed Template, Diagnostic or
Object stage is published in that case. The failure is cached until assembly
cleanup. Replacing a catalog during cached inspection is rejected.

With no catalog, verification reports unavailable; existing opaque staging
remains possible, with device execution still denied. A match also retains the
existing `0x0F` execution denial. The `native_source_type_verification` event and
transport `source_type_verification` summary report only aggregate counts,
fixed errors and capability flags. They omit names, IDs, offsets and values.
`member_locations_verified` is true only when all staged definitions match.
Storage mapping, signature verification, definition exposure and execution flags
remain false.

Transport expiry, Delete, preparation end, inhibit removal, lease release,
disconnect, invalid MAC/counter, reset, source/generation change and endpoint
shutdown clear the verification and catalog reference together with staging.
SDK probe admission and cleanup require an advertised verification to be idle,
empty and without authority.

## Offline comparison

The existing inspector accepts an optional source pair:

```powershell
py -3.13 -X utf8 source/tools/inspect_device_payload.py --payload .local/device-payload.bin --expanded-bytes 371787 --templates --source-acd .local/source.ACD --source-l5x .local/converted.L5X --out .local/source-types.json
```

Use the actual payload size and its matching source files. This records and
rechecks the input hashes and creates a new report exclusively. It cannot
overwrite any input. The source pair is a local provenance binding, not proof
that the supplied L5X was produced by a particular converter. No controller is
contacted and captured signatures are not verified.

## Validation boundary

The preserved demo download matches all 242 source types and 13,312 members,
including the earlier 5,337 encoded offsets. Synthetic tests cover mismatches,
source replacement, atomic load/staging rejection, nested references, capacity,
BOOL locations, unsupported arrays, redacted summaries and cleanup.

The next steps are trailer/definition validation, model-owned native storage
mapping and a complete device-operation/commit contract. Full upload/download,
native tag/rung monitoring and online edits remain unfinished; Studio GUI
monitoring remains unverified.
