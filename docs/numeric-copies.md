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

The public sample is synthetic. Software tests and live application checks are
separate from native Studio transfer and controller execution acceptance.
