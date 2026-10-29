# Masked moves and bit fields

LogixLab models the v35 ladder forms `MVM(Source,Mask,Dest)` and
`BTD(Source,SourceBit,Dest,DestBit,Length)` for SINT, INT and DINT scalar operands.
They execute on true rungs and retain destinations on false rungs and prescan.
The implementation is in [bit_transfer.py](../source/logixlab/bit_transfer.py).

## Supported forms

MVM selects source bits with the mask and preserves destination bits elsewhere.
Each signed operand is interpreted at its declared width before zero extension;
for example, a SINT mask of -1 selects only eight bits of a DINT destination.
Result bits are stored at the destination width, including its signed top bit.
High bits outside that width are discarded; native overflow/status reporting
is not modeled.

BTD takes immediate integer positions within each declared operand's width and
an immediate length of 1..32. Source bits above its width contribute zero.
Destination bits outside the selected field are preserved; excess bits are
discarded within that scalar and never spill into the next array element.
Overlapping moves use the source value before the write.

Source and mask immediates accept signed DINT decimal values or nonnegative
32-bit `2#`, `8#` and `16#` patterns. Tags can address ordinary scalars, array
elements, UDT members, aliases and supported AOI parameter/InOut bindings.
Indirect array subscripts follow the existing bounded reference rules.

Types and shapes are checked before execution. BOOL/bit references, REAL, wide
and unsigned types, whole aggregates and read-only destinations are blocked.
BTD positions and length cannot be tag operands. MVM/BTD calls remain blocked
in ST; their distinct MVMT/BTDT instruction families are unimplemented.

## Unknown values and faults

A partial write requires the preserved destination bits to be known. A full
replacement can establish an unknown destination, and a zero MVM mask is a
no-op. Other reached unknown source/mask reads and invalid indirect references
stop and roll back the whole simulation advance, including earlier changes and
task scheduling state. This is the existing emulator fault policy, separate
from native controller major/minor faults and math flags.

## Bit Lab

Open **Bit lab** in the webpage and choose **Step scan**. The authored
[BitLab.L5X](../source/samples/BitLab.L5X) packs a signed byte and word, extracts
fields, preserves a status word, moves overlapping bits and drops destination
excess. Its first scan produces:

| Tag | Expected value | Bit pattern |
| --- | --- | --- |
| Status | 305397930 | `123400AA` |
| Packed | -305397590 | `EDCC00AA` |
| LowWord | 170 | `00AA` |
| HighByte | -19 | `ED` |
| MixedMask | -171 | `FFFFFF55` |
| Overlap | 9028 | `00002344` |
| Truncated | -15150 | `C4D2` |
| BitOK | true | — |

The scope follows installed Logix Designer v35 help topics 14691 (MVM) and
14677 (BTD). Rockwell's published [MVM reference](https://www.rockwellautomation.com/en-in/docs/studio-5000-logix-designer/37-01/contents-ditamap/instruction-set/move-logical-instructions/masked-move--mvm-.html)
and [BTD reference](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/move-logical-instructions/bit-field-distribute--btd-.html)
also describe these bit-selection rules. Later documentation does not extend
the emulator's v35 type/profile claims. Software tests and the sample do not
establish native controller or Studio instruction acceptance.
