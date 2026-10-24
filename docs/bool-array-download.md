# Packed BOOL array downloads

Version `26.1024.021104` adds source-equivalent download preparation for the
observed one-dimensional root BOOL-array profile. Source declarations must
contain a complete list of actual Boolean values in groups of 32, within the
existing 65,536-element source limit.

## Storage and validation

The native BOOL[64] fixture declares a reciprocal Symbol and a Data Table with
type `0x20D3`, dimensions `(2, 0, 0)` and two storage elements. Each element is a
32-bit word. The source preparation packs bit zero first within each word and
compares every byte with the transferred values before permitting installation.

The temporary table model accepts this type only as a one-dimensional packed
array with an ordinary reciprocal Symbol. Scalar, multidimensional and internal
unbound variants remain unavailable. The preparer separately checks the complete
source shape, exact Boolean leaf types, word dimensions, element count and
packed bytes. Integer substitutes for Boolean values, incomplete words and
changed bits reject the whole preparation.

Scalar BOOLs retain their existing byte representation. Numeric and structure
array layouts retain their existing checks. The new download layout does not
add whole-array symbolic wire reads/writes or packed BOOL member-array support.
Individual BOOL element reads remain available through the existing interface.

## Native source checkpoint

The owned fixture passes Offline import, ACD save, close, reopen and L5X export.
All 64 Boolean values, including bits on both sides of the word boundary, and
the original 14 saved tag values are preserved. Its preceding native download
fails after 174 verified requests with the explicit `unsupported_table_type`
reason. The complete retained first batch contains 906 records and establishes
the packed table descriptor used here. No physical PLC is involved.

The updated runtime completes native SDK download, ACD save, close, reopen and
Go Online across 433 verified signed requests. All originals and modeled values
are preserved, with actual Offline cleanup and no SDK fault. Its complete
1,751-event recording replays identically offline; the replay checks framing
and does not reverify message authentication.

After installation, ordinary CIP reads independently check all 64 Boolean
elements against their saved source values, including both sides of the word
boundary. They preserve the model with zero scans. This validates the narrow
download profile and individual reads, without establishing general Routine
upload, whole-array wire operations or native controller equivalence.
