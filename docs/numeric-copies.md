# Numeric COP/CPS byte copies

COP and CPS support little-endian numeric byte copies in ladder and Structured
Text within the v35 ControlLogix 5580 L81E–L85E software profile. Choose **Byte
copy lab**, or launch with `--sample CopyLab`, for REAL/integer bit images and
a five-byte packet copied into a DINT array.

Transfer sizing was checked against installed Studio v35 COP/CPS help and
Rockwell's [copy reference](https://www.rockwellautomation.com/en-ca/docs/factorytalk-design-studio/current/contents-ditamap/instructions/instruction-set/array--file--misc-instructions/copy-cop-synch-copy-cps.html).
This is a bounded numeric-region model. Native aggregate layouts, cross-member
copying, interruption behavior and fault/partial-effect parity remain unfinished.

## Types and transfer length

Supported numeric elements are SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT
and finite REAL. The copy moves byte images, not converted numeric values:

| Copy | Result |
| --- | --- |
| REAL 1.0 to DINT | 1065353216, the image 0x3F800000 |
| DINT 1065353216 to REAL | 1.0 |
| DINT 0x12345678 to two INTs | 0x5678, 0x1234 |
| SINT -1 to USINT | 255 |

Length is an integer destination-element count from 0 through 100000. Requested
bytes equal Length times destination element width. The actual transfer is the
minimum of that request and the bytes remaining in both numeric regions. The
actual transfer may not exceed 32768 bytes. Large requests can still succeed
when source or destination boundaries clip them to a small transfer.

The final copied source element can contribute only a prefix of its bytes. A
source ending partway through a destination element preserves the destination's
remaining bytes. For example, bytes 1,2,3,4,5 copied to DINTs whose second value
was 0x11223344 produce 0x04030201 and 0x11223305. The partial destination must
have a known finite prior value so those preserved bytes can be retained. Full
destination elements do not require known old values.

## Regions and overlap

Numeric regions can be scalar tags, members, arrays or member arrays. Array
offsets and one-/two-/three-dimensional row-major traversal are supported.
Program-local tags, aliases, AOI InOut arrays and member arrays inside nested
UDT arrays use their resolved storage identities. A traversal limit bounds work
needed to find a starting element.

Regions stop at the selected scalar/member/array boundary. Native Logix can
continue across member boundaries up to a base tag's end; this model does not
infer that aggregate ABI. BOOL bits/packed arrays, full strings, aggregate
reinterpretation and LREAL byte images remain unsupported. Existing matching
aggregate copies retain their logical-copy behavior and strict region bounds.
[Basic record/string/UDT copies](aggregate-copies.md) now have separate structural
preflight, lazy operands and bounded scalar-member work, while numeric copies
keep the byte-budget and transfer rules on this page.
Other controller profiles retain legacy matching copies; mixed numeric byte
copies require the profile above.

Matching numeric copies preserve the model's sequential forward propagation:
copying array[0] to array[1] over overlapping elements replicates the first
element through the destination. Backward copies read later source elements
in order. Both COP and CPS use this behavior. Mixed numeric regions encode and
validate their destination images before committing writes.

COP and CPS execute inside one model instruction. This does not establish
native task/I/O interruption behavior, remote-client synchronization or a
complete CPS concurrency model.

## Operand selection

Numeric COP/CPS preflight validates declared types, reference shapes, destination
permissions and length syntax without reading saved numeric values, dynamic
indices or a saved Length tag. Length tags remain scalar SINT/INT/DINT; immediate
lengths remain integers in 0..100000. Literal index bounds and fully static
transfer-cap violations are still diagnosed before execution.

False ladder rungs and prescan skip live operands. When reached, copies consume
the actual length and source/destination addresses, then apply the existing
clipped region and byte rules. A dynamic length or indirect alias/AOI start can
only determine actual transfer size at execution, including the 32768-byte cap.
Zero length validates both live addresses but reads no numeric values.

Full destination elements can be established from unknown values; partial
elements still need known bytes to preserve. Mixed-type copies require known
source values, while same-type copies retain their logical unknown propagation.
Aliased and AOI InOut/local regions use the same rules. Copy faults and later
instruction faults restore earlier writes and AOI bindings within the advance;
completed prescan remains a separate lifecycle boundary. AOI argument binding
and copied inputs retain their separate contract.

Existing ST calls share this validation without new syntax. ST FOR destination
protection retains its existing conservative analysis and separate restrictions.
This changes operand selection, not transfer algorithms, numeric encodings,
aggregate layouts, synchronization or native fault/status/lifecycle claims.

## Unknowns, finite values and rollback

Same-type copies retain logical unknown values as before. Mixed-type reads
require known numeric source values. REAL sources and reinterpreted REAL
results must be finite; NaN/Infinity payloads stop and roll back the advance.
Signed-zero images are preserved for known finite REAL values.

Each actual transferred byte consumes one advance-budget unit. Negative or
invalid lengths, unsupported references, unknown required bytes, unrepresentable
REAL images or budget exhaustion fault transactionally. The whole advance
restores tags, time, scheduler state and preceding instruction effects. A false
ladder rung and ordinary prescan do not perform the copy.

Structured Text FOR validation accounts for every destination cell, including a
partially overwritten final element. Dynamic lengths or indirect destinations
conservatively protect the destination region. This prevents a copy from
silently modifying a loop's bounds/step through a later array element.

## Byte copy lab

FloatInput is copied to BitPattern and back to Roundtrip. IntegerInput is
reinterpreted as FloatOutput. Bytes[0..4] are copied into Packed using
CopyLength, demonstrating clipped transfers and preserved upper bytes. Further
copies expose the packet as DecodedBytes and UnpackedWords. EnableCopy skips the
group; FaultDivisor provides a late-fault rollback test.

The ST routine also calls a three-rung ladder routine, CopyIndexed. Its
IndexedCopy gate starts false, both indices are 99, and selected lengths/data
are unknown. Step once to observe dormant operands. Set CopyIndex=0,
OutputIndex=0, SelectedLength[0]=4 and SelectedSource[0]=16909060, enable
IndexedCopy and step again:

| Result | Value |
| --- | --- |
| SelectedBytes[0..3] | `4, 3, 2, 1` |
| SelectedRoundtrip[0] | `16909060` |
| CopyMatches | true |

Unused bytes and sibling results stay unknown. Disable IndexedCopy before
changing an index to 99 to retain outputs and clear CopyMatches. Re-enable at
that index to fault; correct it and retry. Unknown consumed length/source values
also fault without leaving earlier ST or ladder writes behind.

The public sample is synthetic. Software tests and live application checks are
separate from native Studio transfer and controller execution acceptance.
