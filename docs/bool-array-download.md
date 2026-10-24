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

## Packed table readback

Version `26.1024.023810` exposes the same complete rank-one BOOL-array profile
through Symbol discovery, Data Table metadata, full-table reads and bounded
model-address reads. The Symbol keeps type `0x20C1` and the logical bit count;
the linked Table uses type `0x20D3` and the number of 32-bit storage words.
Both descriptors refer to the same live packed value bytes. No native process
memory is exposed.

Reading BOOL[64] returns eight bytes, with bit zero in the least significant
bit of the first little-endian word. Changes to individual modeled bits appear
in subsequent table reads without scanning or reallocating the storage.
The reader rejects changed shapes, non-Boolean leaves, crossed cell boundaries
and incorrect full-table lengths. Only eligible nonconstant base arrays receive
backed storage. Partial words and multiple dimensions remain unavailable.
Whole-array symbolic reads and writes and packed BOOL member arrays remain
outside this profile. These table services remain read-only.

The preceding native SDK upload reported success for a routine-free fixture
while its retained trace contained zero requests for the omitted BOOL table.
An SDK success status alone therefore does not establish complete value
transfer. Native acceptance of this new profile is checked separately against
the actual requested table and its exact packed response bytes.

The updated runtime completes native SDK download/save/reopen/Go Online across
425 verified requests and `UploadAsync` across 965 for that routine-free
BOOL[64] fixture. Its complete upload recording contains the actual packed
table read: all eight response bytes match the 64 saved values. Independent CIP
checks verify every logical bit, both descriptor types and their different
dimensions. Source/model preservation, actual Offline cleanup and no SDK fault
are confirmed. The complete 1,720-event download and 3,426-event upload journals
replay identically offline; this checks framing without reauthenticating MACs.
An uploaded ACD save/reopen is not attempted, and routine-containing upload
remains unfinished.

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
