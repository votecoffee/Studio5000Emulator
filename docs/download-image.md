# Temporary download image

The native download path can now materialize a separate device image after
decoding the entire compressed batch and checking its supported descriptors
against source metadata. This gives subsequent transfer work real temporary
objects and storage to inspect. The active controller project remains separate.

## Prepared objects

An image retains the temporary Template definitions, diagnostic descriptors,
Program and Routine identifiers, Symbol references and Data Table descriptions.
It allocates each Data Table's declared byte count in a bounded temporary
namespace. Controller Symbols with reciprocal table links can read those bytes;
unbound Program or controller Symbols report that storage is unresolved.

The allocated bytes initially contain zero. They are allocation state, and do
not represent transferred tag initial values. Routine creation records contain
identifiers only, without executable bodies. Template trailers, family/revision
fields and other retained metadata do not execute as binary code.

Preparation requires:

- Every batch record belongs to an explicitly supported Create, attribute,
  Template write or Program coordination operation, and every record is covered
  by the corresponding descriptor model.
- All cross-object references, bounds and balanced Program coordination pass.
- Every staged Template's type/member structure matches the original ACD's
  metadata, bound to both the original ACD and converted L5X SHA-256 hashes.

An unknown operation, an incomplete descriptor, an unmatched type or missing
source binding cannot publish an image. Allocation is bounded to one MiB per
image and occurs after these checks. A SHA-256 digest identifies the exact
ordered record stream.

## Readback and lifecycle

`DownloadImage.read_table` and `read_symbol` provide readback from the temporary
cells, requiring the matching pair of source hashes for each call. Reads stay
inside one table and at most 16 KiB per request. `attribute` provides exact-width
typed bytes for supported Template, Data Table and Symbol descriptor fields.
Names and compiled or physical addresses absent from these records remain
unavailable.

The programming lease owns the image. Fragment reset, absolute assembly expiry,
transport deletion and lease cleanup discard it together with the decoded
objects. Successful inspection is cached for the same native source catalog;
changing the catalog cannot reuse an existing prepared image.

`ResilientTransport.start_prepared_image()` records the simulator's temporary
preparation transition only after complete inspection, source-bound allocation
and full record coverage. It pins both source hashes, the source catalog and
the ordered record digest. Repeating Start on that exact image is idempotent;
changing its source or record digest cannot reuse the transition. Cleanup also
clears `preparation_started`.

Status exposes counts, limits, a record digest and readiness. It omits source
hashes, identifiers, definition bytes, names and cell contents.

## Native boundary

Preparing and reading this image establishes simulator state only. It does not
establish native Resilient Transport service semantics, compiled execution,
transfer of initial values, successful Studio download or an active-project
commit. The anonymous research endpoint now acknowledges service `0x06` on class
`0x412` only after this temporary preparation transition succeeds. Incomplete
coverage or a missing source binding remains an error. The later empty `0x4D`
request still requires its own verified result contract and is rejected.

In the `.78` native SDK test, preparation retained all 904 records, 242 Templates,
136 diagnostics, one Program and two Routine identifiers. Sixteen temporary
tables allocated 172 bytes, with 15 linked Symbols and five unresolved storage
references. Start succeeded and the SDK advanced to `0x4D`; the complete download
still failed. Source and active model were preserved, and cleanup cleared the
temporary objects. A separate private experiment returned an empty successful
`0x4D` response and still failed at the same stage, without advancing to another
transfer operation. That hypothetical result response is absent from the app.

The unit tests cover independent temporary allocation, typed attributes,
source checks, unknown operations, allocation/read bounds, unresolved symbols,
atomic failure, cached inspection and cleanup. Owned native traces can be
replayed offline without including their private payloads in this repository.
