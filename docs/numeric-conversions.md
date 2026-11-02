# Numeric conversions and byte ordering

The v35 ControlLogix 5580 software profile supports these forms:

```text
FRD(Source,Dest);                 // Ladder, DINT -> SINT/INT/DINT
TOD(Source,Dest);                 // Ladder, SINT/INT/DINT -> DINT
SWPB(Source,REVERSE,Dest);         // Ladder and ST, INT/DINT
SWPB(Source,WORD,Dest);
SWPB(Source,HIGHLOW,Dest);
```

## BCD conversions

FRD reads a DINT bit pattern and weights its eight nibbles by successive decimal
powers. The installed v35 definition explicitly includes hex digits A–F: source
16#1234567E produces 12345684. A signed source is interpreted through its full
32-bit pattern; -1 produces 166666665. FRD does not reject nondecimal nibbles.

TOD accepts decimal values from 0 through 99999999 and packs their digits into
eight nibbles. Results preserve the signed DINT bit pattern: 80000000 produces
-2147483648, and 99999999 produces -1717986919 (16#99999999). FRD reverses this
packing for ordinary decimal digits. Neither conversion needs an initialized
destination value.

The qualified ladder combinations are:

| Instruction | Source | Destination |
| --- | --- | --- |
| FRD | DINT tag or bounded signed DINT/32-bit radix immediate | Writable SINT/INT/DINT scalar |
| TOD | SINT/INT/DINT tag or bounded DINT immediate | Writable DINT scalar |

FRD checks the decoded integer against the destination's signed range. Thus
16#127 decodes to SINT 127; 16#128 decodes to 128 and faults on a SINT result.
It does not store truncated overflow bits. The eight-nibble calculation is
unchanged, including signed DINT sources and A-F digits.

TOD consumes the signed decimal value directly, without a float32 conversion:
SINT 99 packs to DINT 16#99, INT 32767 packs to DINT 16#32767, and either
round-trips through FRD into its original signed type. Narrow FRD sources,
narrow packed TOD destinations, wide/unsigned types and BCD expression functions
remain unqualified. FRD/TOD calls are unavailable in ST, matching the installed
v35 language list. Existing [FBD conversion records](fbd-conversions.md) retain
their separate DINT-only BCD contract; no new FBD forms are added here.

Negative or excessive TOD sources stop and roll back the modeled advance.
Decoded FRD results outside the destination range also stop and roll back.
Native TOD saturation, truncation/overflow bits, math flags and configurable minor faults remain
unfinished. This valid-range profile must not be treated as native overflow
behavior.

## Byte orders

SWPB sources require INT or DINT tags. INT destinations may be INT or DINT;
DINT sources require DINT destinations. Source immediates and other types are
unsupported. Each selector swaps an INT's two bytes and sign-extends the swapped
INT result when stored in DINT. For a DINT, the selectors give these patterns:

| Selector | Input 16#12345678 | Result |
| --- | --- | --- |
| REVERSE | ABCD | 16#78563412 (DCBA) |
| WORD | ABCD | 16#56781234 (CDAB) |
| HIGHLOW | ABCD | 16#34127856 (BADC) |

Selectors are literal enum names, case-insensitive; use HIGHLOW without a slash.
In-place swapping captures the source before writing. Existing scalar array,
indirect-index, UDT member, alias and supported AOI bindings remain available.
ST FOR validation includes SWPB destination writes in bound/step protection.

## Scans and demo

Prescan and false ladder rungs retain destination data. A true rung or executed
ST call updates once per execution. Unknown required values, bounds and later
faults retain whole-advance data/time/scheduler rollback. Native status/fault
parity and other controller profiles remain unfinished.

Choose **Conversion lab** and **Step scan**. Inspect Decimal/Packed/Decoded,
Weighted, Reverse/Words/HighLow, and the sign-extended INT result. A called ST
routine swaps two INT array elements into DINTs, retaining a guard element of
999. Disable Enable to retain the ladder results while the ST routine continues.
ByteDecimal/BytePacked/ByteDecoded and WordDecimal/WordPacked/WordDecoded
add narrow round trips; NarrowOK checks them. RawByteBCD separately decodes
into RawByteDecoded. Set RawByteBCD to 296 (16#128) to exercise SINT result
overflow after earlier conversions, then correct it to 295 (16#127) and retry.
False Enable retains ladder results while the called ST routine still runs.
See [ConversionLab.L5X](../source/samples/ConversionLab.L5X) and
[implementation](../source/logixlab/numeric_conversions.py).

The baseline was checked against installed v35 help 14674 (TOD), 14675 (FRD)
and 14686 (SWPB). The published Rockwell
[SWPB reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/move-logical-instructions/swap-byte--swpb-.html)
provides context for later releases. Software checks do not establish native
controller or Studio acceptance.
