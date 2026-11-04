# Finite LREAL numeric byte copies

App `26.1104.014542` adds LREAL to the existing v35 ControlLogix 5580 numeric
COP/CPS profile. The ten numeric formats now include eight signed/unsigned
integer types, finite REAL and finite LREAL. Existing ladder and ST calls share
the byte-copy path; no new ST expression syntax or FBD forms are introduced.

```text
COP(DoubleInput,UnsignedImage,1);
CPS(UnsignedImage,DoubleRoundtrip,1);
COP(DoubleInput,Words[0],2);
CPS(Words[0],DoubleResults[Index],1);
```

LREAL uses an eight-byte little-endian host binary64 image. Copying
1.0000000000000002 to ULINT produces 16#3FF0000000000001, decimal
4607182418800017409. Copying those bits back retains the original precision.
Copying to DINT[2] produces low word 1 and high word 1072693248. These are byte
reinterpretations, independent of the numeric conversions performed by MOV/TRN.
Signed zero, subnormal values and large finite values retain their images.
64-bit integer API results retain the existing exact decimal-string format.

Length counts destination elements. Transfers clip to the requested bytes and
the remaining source/destination logical numeric regions, with the existing
32768-byte cap. A scalar/member/array region ends at its logical boundary;
requests do not continue into sibling members or base tags. Row-major arrays,
aliases, selected members and existing AOI bindings use their resolved storage.
No native aggregate ABI is inferred from the binary64 scalar format.

If the source ends partway through a destination element, the uncopied bytes
come from that destination's known old value. For example, copying DINT 1 into
LREAL 1.0 replaces the low four bytes and produces 1.0000000000000002. Unknown
partial destinations fault; a full write can establish an unknown destination.
Mixed copies prepare all destination images before committing any writes.
Reinterpreted NaN/Infinity images fault and roll back the advance. Same-type
copies retain the existing logical unknown propagation and sequential forward
overlap behavior for both COP and CPS.

Structural preflight checks types, shapes, permissions, literal bounds and
static byte caps without consuming saved dynamic indices, lengths or values.
False rungs/prescan skip live operands. Zero length validates both live addresses
without consuming numeric values. Unknown required bytes, invalid indices,
partial unknown destinations, nonfinite images, budget exhaustion and later
faults roll back the advance, including task progress/timing and AOI local/
external values and bindings. Matching LREAL AOI InOut/local arrays have
warm-state rollback cases; copied LREAL AOI parameters remain separate.
Run-entry initialization retains its separate preceding prescan boundary.

ST FOR analysis retains existing write protection. A copy from LREAL into an
integer array cannot overwrite a loop's captured integer bounds/step. LREAL
loop-bound expressions remain outside the expression profile. Both COP and CPS
execute within one model instruction; native task/I/O interruption, remote
client synchronization, timing, nonfinite payload continuation, fault classes
and partial effects remain unverified.

Open **Byte copy lab**. DoubleCopy starts false with DoubleCopyIndex=99 dormant
and DoubleResults[1] unknown. Set the index to 1, enable the section, then Step:

- DoubleImage becomes the exact ULINT image above; DoubleRoundtrip retains it.
- DoubleWords receives [1,1072693248]; DoubleResults[1] retains the input value.
- DoublePartial demonstrates the DINT low-word patch of an existing LREAL.
- DoubleResults[0]/[2] retain fractional guards 101.125 and 999.5.

DoubleInject enables a deliberately nonfinite integer image, which faults the
copy. Disable it before continuing. DoubleDivisor=0 faults after earlier copies;
restore it to 1. Disable DoubleCopy before returning its index to 99. Existing
REAL packet and indexed examples remain independently available.

The source basis is installed Studio v35 help14516, including the ladder/ST
operand table listing LREAL on 5580 controllers, and the published
[Rockwell COP/CPS reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/copy-synchronous-copy-file--cps-.html).
The numeric byte model is narrower than native packed base-tag traversal.
FLL retains its separate narrow operand profile; this change does not infer
LREAL FLL support from COP/CPS support.

See [numeric byte-copy rules](numeric-copies.md),
[implementation](../source/logixlab/numeric_copy.py),
[focused cases](../source/tests/test_lreal_copy.py) and
[CopyLab.L5X](../source/samples/CopyLab.L5X).
