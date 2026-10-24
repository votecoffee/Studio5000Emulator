# Structured Data Table storage

Version `.100` extends backed Data Table and Symbol descriptors to the explicit
user structures already supported by symbolic tag reads. Scalar UDTs and arrays
reuse the same template, nested member offsets, numeric encoding, packed BIT
hosts and reserved zero padding. This is the emulator's layout, not a native
controller's compiled-memory layout.

Symbol element size remains one structure's width; a Data Table read covers
the entire scalar or array. The zero-selector, exact-byte-count `0x4F` service
returns current bytes without a symbolic type prefix. Its complete response
must fit the negotiated budget. Existing symbolic reads retain their separate
fragmentation support. Neither read starts a scan or writes a value.

All aggregates share the existing 32 KiB per-cell and 1 MiB allocation limits,
including alignment. Scalar atomic slots retain their fixed stride; structured
scalars use the separate aggregate arena. Descriptors do not expose padding
between cells. Oversized cells receive no partial storage descriptor.

Each network member read rechecks access permissions. Constants, aliases,
private/safety tags, unsupported built-in structures and layouts containing
private members retain their existing exclusions. Missing values or changed
array shapes reject the complete read. Data Table setters remain denied.

## Validation and native boundary

Version `26.1023.233219` adds a separate
[source-equivalent download profile](download-image.md#source-matched-initial-values)
using original ACD member locations and structure sizes. It does not change
the software storage layouts described above; a structure accepted by download
can still fall outside the existing aggregate-read profile. A native fixture with nested
structures, packed BOOL members, UDT arrays and TIMER/COUNTER arrays completes
download/save/reopen/Online across 434 verified requests. Independent symbolic
atomic-member reads match all 61 supplied value fields. This establishes the
bounded download and value-read paths; general routine upload remains unresolved.

Focused tests cover nested structures, multidimensional root arrays, packed
bits, equal IDs in different scopes, current values, cached-layout permission
changes, allocation bounds and unchanged state after rejected writes.

A separate offline SDK import/save/reopen creates a demo containing one UDT
scalar and a two-element UDT array. Real TCP reads of their Data Tables match
the symbolic bytes, descriptor links and element widths. External writes to
a scalar member and an array member remain queued until the next scan; both
read paths then show the applied values. Original ACD and L5X files remain
unchanged.

In `.100`, the native SDK upload of that project stops earlier at Template attributes
6, 7 and 8: Family Type, Multiply Code and Recon Data. It does not reach the
new structured-storage reads. Its request-count difference is not evidence of
upload advancement. Version `.101` adds the [source-known family read and
aligned model extent](template-metadata.md). Multiply Code, Recon Data, native
address-cache population, full upload/download and Studio GUI monitoring remain
unfinished.

A separate native download of the same UDT project prepares 911 temporary
records, 243 Templates and 18 Data Tables. It reaches the unresolved transport
result query and still fails the download. Source and active model are
preserved; native Offline and endpoint cleanup succeed without a fatal SDK
fault. This validates broader temporary preparation, not active-project commit.
