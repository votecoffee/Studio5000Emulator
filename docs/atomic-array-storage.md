# Atomic-array Data Table storage

Version `.99` extends the model's read-only Data Table storage to externally
readable, nonconstant base atomic arrays. The existing Symbol and Data Table
catalogs retain their source-bound IDs, dimensions, types and access checks.
Aliases, private/safety tags, structures and packed BOOL arrays remain outside
this storage profile.

Version `.100` also supports [explicit user structures](structured-storage.md).
Structures and atomic arrays share the aggregate allocation bounds below.

## Descriptors and values

Supported arrays now expose Data Table attributes 3, 6, 7 and 9, plus the linked
Symbol address/control/size/table fields. Symbol attribute 7 remains the size
of one atomic element; total storage is that width multiplied by the array
shape. Numeric values use little-endian encoding, with the final index varying
fastest for multidimensional arrays. Program-local and controller storage stay
separate even when their object IDs are equal.

Data Table service `0x4F` accepts a zero selector and the exact full byte count.
It returns current values without a tag-type prefix. The complete reply must
fit the negotiated response budget; this service does not guess an offset or
fragmentation dialect. Existing symbolic tag reads retain their separate
fragmentation support. Read operations do not execute scans or write values.

Descriptors and addresses belong to this model. They do not establish native
firmware layouts, physical memory, SDK address-cache population or full upload.
The internal address-space reader checks cell boundaries and never exposes
alignment padding or neighboring cells. Scalar value slots retain their fixed
stride; array value regions use a separate aligned range. Catalogs are rebuilt
when the source, exposed atomic set or dimensions change. Runtime values are
read afresh rather than cached in the descriptors.

## Bounds

The catalog retains at most 4,096 cells. Each array has a 32 KiB byte limit,
and all allocated array regions together have a 1 MiB limit, including alignment.
An array that exceeds either bound gets no partial storage descriptor; its
basic type/dimension catalog entry remains available. Later cells keep working
when an earlier oversized array is omitted. Unknown elements, changed shapes
and values that cannot fit their declared atomic type fail the complete read.
Writes through Data Table services remain denied.

## Native validation

An unchanged four-element DINT demo supplies the comparison. Before this change,
native upload receives partial attribute status for its array Data Table and
fails after 167 verified signed requests. With array storage, the same metadata
request succeeds, the SDK reads all sixteen value bytes as 10, 20, 30 and 40,
and the linked Symbol attribute list succeeds. Upload advances to 200 verified
requests and still fails later Controller collection. Source files and active
model state stay unchanged by both upload attempts; native Offline and endpoint
cleanup succeed without a fatal SDK fault.

A separate wire check reads the linked Data Table and Symbol descriptors.
External writes to element 2 remain queued until the next scan; subsequent
Data Table reads observe 123 and -456 at their acknowledged scan boundaries.
This verifies current array readback through that service, separately from
native SDK tag monitoring, which still lacks online addresses.
