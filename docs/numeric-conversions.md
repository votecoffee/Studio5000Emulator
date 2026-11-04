# Numeric conversions and byte ordering

The v35 ControlLogix 5580 software profile supports these forms:

```text
FRD(Source,Dest);                 // Ladder, 8/16/32/64-bit packed -> integer
TOD(Source,Dest);                 // Ladder, integer -> 8/16/32/64-bit packed
SWPB(Source,REVERSE,Dest);         // Ladder and ST, INT/DINT
SWPB(Source,WORD,Dest);
SWPB(Source,HIGHLOW,Dest);
```

## BCD conversions

FRD reads an 8/16/32/64-bit bit pattern and weights its 2/4/8/16 nibbles by decimal
powers. The installed v35 definition explicitly includes hex digits A–F: source
16#1234567E produces 12345684. A signed source is interpreted through its full
declared pattern; DINT -1 produces 166666665 and LINT -1 produces
16666666666666665. FRD does not reject nondecimal nibbles.

TOD accepts nonnegative decimal integers and packs their digits into the
destination width: 0..99 for SINT/USINT, 0..9999 for INT/UINT,
0..99999999 for DINT/UDINT and 0..9999999999999999 for
LINT/ULINT. Signed destinations retain the packed bit pattern: in DINT, 80000000 produces
-2147483648, and 99999999 produces -1717986919 (16#99999999). FRD reverses this
packing for ordinary decimal digits. Neither conversion needs an initialized
destination value.

The qualified ladder combinations are:

| Instruction | Source | Destination |
| --- | --- | --- |
| FRD | Any of the eight signed/unsigned integer tags or bounded signed DINT/32-bit radix immediate | Writable SINT/INT/DINT/LINT/USINT/UINT/UDINT/ULINT scalar |
| TOD | Any of the eight signed/unsigned integer tags or bounded DINT immediate | Writable SINT/INT/DINT/LINT/USINT/UINT/UDINT/ULINT scalar |

FRD checks the decoded integer against the destination's signed/unsigned range. Thus
16#127 decodes to SINT 127; 16#128 decodes to 128 and faults on a SINT result.
It does not store truncated overflow bits. The eight-nibble calculation is
retained for 32-bit sources, including signed DINT sources and A-F digits.

TOD consumes the integer decimal value directly, without a float32 conversion:
SINT 99 packs to DINT 16#99, INT 32767 packs to DINT 16#32767, and either
round-trips through FRD into its original signed type. [Array-index FRD/TOD](array-index-functions.md)
add a separate checked DINT expression profile; standalone BCD expressions
remain unqualified. FRD/TOD calls are unavailable in ST, matching the installed
v35 language list. Existing [FBD conversion records](fbd-conversions.md) retain
their separate DINT-only BCD contract; no new FBD forms are added here.

Negative or excessive TOD sources stop and roll back the modeled advance.
Decoded FRD results outside the destination range also stop and roll back.
Native TOD saturation, truncation/overflow bits, math flags and configurable minor faults remain
unfinished. This valid-range profile must not be treated as native overflow
behavior.

## Exact 64-bit BCD

App `26.1103.082411` adds the wide/unsigned combinations above. A 64-bit packed
result holds sixteen decimal digits, including values beyond floating-point
precision. For example, 9007199254740993 packs as `16#9007199254740993`:
ULINT stores 10378291982571407763 and LINT stores -8068452091138143853. Either
packed type decodes back to the original decimal value. ULINT `16#FFFFFFFFFFFFFFFF`
decodes to 16666666666666665 by weighting its sixteen A-F-capable nibbles.

DINT/UDINT retain eight-nibble capacity even with a 64-bit decimal source.
TOD rejects negative inputs or values above the destination's decimal capacity.
FRD rejects decoded results that do not fit the destination. It does not clip
or wrap decoded overflows. Native saturation/overflow flags remain separate
work. No REAL/LREAL conversion is introduced.

Source immediates retain signed-DINT decimal or 32-bit radix bounds. Larger
values must be held in typed tags; wider/typed literal syntax is not added.
A source literal is still a 32-bit pattern for FRD, even with a 64-bit result.
Aliases, selected array/UDT members, constant sources and supported AOI local/
InOut bindings retain structural preflight, lazy false/prescan reads, complete
unknown-result writes and whole-advance rollback. In-place conversions capture
the source before writing. FBD keeps the shared helpers' DINT defaults and gains
no wide form; ST FRD/TOD remain unavailable.

Enable `WideConversions` in **Conversion lab**. The default signed/unsigned
round trips yield 9007199254740993, `WideWeighted` yields 16666666666666665,
and `UnsignedPacked` yields 2576980377 (`16#99999999`). Set `WideDecimal` to
9999999999999999 to exercise full capacity. A value of 10000000000000000 faults
and rolls back the advance; correct it and retry. Wide watches use decimal text.

The 64-bit weighted-nibble software model extends the documented 32-bit formula
to sixteen nibbles using the listed LINT/ULINT operand types. Native calculation,
import, status, fault and lifecycle parity still need qualification.

## Byte and word packed BCD

App `26.1103.214730` adds SINT/USINT and INT/UINT packed operands, completing
all 64 integer source/destination type pairings for each ladder instruction.
FRD interprets exactly the declared pattern: SINT -1 weights FF and produces
165, INT -1 weights FFFF and produces 16665. A-F digits retain their weighted
values. FRD checks the decimal result against the destination range; 165 does
not fit SINT and faults transactionally, while it fits USINT or DINT.

TOD qualifies nonnegative inputs up to the packed destination's decimal capacity:
99 in a byte and 9999 in a word. Signed results preserve those packed bits:
99 becomes SINT -103 (99 hex), and 9999 becomes INT -26215 (9999 hex). FRD can
decode either signed pattern into a sufficiently large destination. In-place
round trips capture each source before writing. Each conversion remains exact
integer arithmetic, without float32 intermediates.

This extends the existing width-based software model. Installed v35 help 14674
and 14675 list the operand types; their native saturation/overflow behavior and
the FRD description's 32-bit formula do not establish narrow calculation parity.
The model rejects TOD inputs outside its per-width valid range and decoded FRD
results outside their destination range. It does not infer native overflow bits,
minor-fault settings or partial effects. FBD keeps the shared helpers' DINT
defaults, and ST FRD/TOD remain unavailable.

In **Conversion lab**, step with SmallBCD false; SmallBCDIndex=99 remains dormant.
Set SmallBCDIndex=1, enable SmallBCD and step. SmallBytePacked[1] becomes -103,
SmallByteUnsigned becomes 153, SmallWordSigned becomes -26215 and
SmallWordUnsigned becomes 39321. SmallDecoded holds [99,99,9999,9999]; byte-array
guards 11 and 77 remain. Set SmallDecimal=100 or SmallWordDecimal=10000 to observe
whole-advance rollback; correct the value and retry. Disable SmallBCD before
selecting an invalid index to retain the values. See
[byte/word tests](../source/tests/test_small_bcd.py).

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

## Operand selection

Preflight checks declared scalar types/shapes, index grammar, destination
permissions, immediate bounds and SWPB selectors without evaluating saved dynamic
indices or reading tag values. False ladder rungs and prescan skip live operands.
An unknown or out-of-range saved dynamic index can remain until an enabled call
reaches it. Nonnegative literal indices retain their bounds checks. Missing
references, invalid grammar/types/shapes, read-only destinations, excluded
immediates and invalid selectors remain blocked, including on false rungs.

Enabled calls retain actual source/destination index and required-source checks.
Full result writes can establish unknown selected elements or members while
preserving unwritten siblings. Existing aliases, UDT members and AOI local/InOut
bindings follow the same rules. Reached unknown/index/range or later faults roll
back the entire advance and existing AOI bindings. Preflight restores its prior
structural context after success and errors. Calculations, type combinations,
BCD range policy, byte-order selectors and the existing ST SWPB contract remain
unchanged. FRD/TOD remain unavailable as ST calls.

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
The separate `IndexedConversions` section starts disabled with `ConversionIndex`
99 and unknown result arrays. Set the index to 0, then enable the gate:
`IndexedDecimal[0]` 1234 produces `IndexedPacked[0]` 4660 (16#1234),
`IndexedDecoded[0]` 1234 and `IndexedSwapped[0]` 305397760 (16#12340000).
Unwritten siblings remain unknown. Index 2 demonstrates 80000000 packing into
signed DINT -2147483648 and decoding back; its WORD byte swap is 32768. Invalid
enabled indices or excluded TOD inputs fault and roll back; correct them and retry.

See [ConversionLab.L5X](../source/samples/ConversionLab.L5X) and
[implementation](../source/logixlab/numeric_conversions.py).

The baseline was checked against installed v35 help 14674 (TOD), 14675 (FRD)
and 14686 (SWPB). The published Rockwell
[SWPB reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/move-logical-instructions/swap-byte--swpb-.html)
provides context for later releases. Software checks do not establish native
controller or Studio acceptance.

[BCD CPT expressions](cpt-bcd.md) now have a separate v35 5580 narrow-integer
profile. CPT parser opt-in keeps other expression consumers and wider/REAL forms
separate; array-index functions retain their existing conversion rules.

[BCD CMP expressions](cmp-bcd.md) now add scoped FRD/TOD conversion
operators to integer relations and Boolean composition. File/ST expressions,
floating/wide mixtures and native parity retain separate requirements.

[BCD file expressions](file-bcd.md) now qualify FRD/TOD in narrow FAL/FSC
operands for existing ALL/numeric/INC modes. Conversion and progress/rollback
rules are explicit; wider types, ST and native parity remain separate.
