# Clipped numeric fills

App `26.1103.201221` lets numeric FLL requests stop at the end of the selected
logical array/member or scalar in the v35 L81E–L85E software profile.

```text
FLL(Source,Values[3],100000);
```

For a five-element Values array, this fills elements 3 and 4. Earlier elements
stay unchanged. A scalar destination receives one value even if the requested
length is larger. Whole-array starts and fully selected one/two/three-dimensional
starts use row-major order. A member array ends at that member; sibling fields
and other tags are never included.

This advances the modeled clipping behavior toward the FLL reference, which
defines a byte request limited by the destination base tag. The simulator's
logical member boundary is deliberately narrower. Packed layouts, native
cross-member/base-tag traversal and partial effects remain unqualified.

## Operands and capture

Source/destination types remain SINT, INT, DINT and finite REAL. The installed
v35 FLL table does not qualify wide/unsigned operands. Length remains a scalar
SINT/INT/DINT or bounded DINT immediate with runtime value 0..100000. Negative,
unknown or larger values fault; the simulator limit is not removed by clipping.
Invalid starting indices still fault, including with length zero.

An executed fill samples length, selects the complete clipped window, then
samples/converts the source once before any stores. A source or length inside
the destination cannot change that window midway through filling. Existing
integer truncation/sign extension and representable nearest-even REAL conversion
remain. Unknown full destinations can be established without reading their
previous values. Zero length validates the destination and skips the source.
False/prescan paths retain their existing lazy operand rules.

Existing aliases and RLL AOI InOut/local arrays share clipping. Bounds/conversion
errors and later faults restore values, bindings, time, traces and scheduler
state for the complete advance. [Aggregate zero fills](aggregate-fill.md) keep
their separate strict logical-region contract.

## Existing emulator ST extension

The emulator already accepts ST FLL calls. They share this numeric software
path; native v35 ST FLL is unavailable. This extension does not establish native
language or Studio import compatibility.

ST FOR validation now protects the complete clipped numeric window. A static
start and literal count identify exact cells. Dynamic lengths, aliases and
indirect selections conservatively cover the member and enclosing parent
arrays. This can reject some disjoint live selections. Literal zero has an empty
write effect, while runtime destination validation remains required. Other
instruction types and native loop timing remain separate.

## Data lab

ClipNumeric is disabled initially, with ClipIndex=99 and ClipLength=100000.
Set ClipIndex to 3 and enable ClipNumeric, then Step. ClipValues changes from
[11,22,33,44,55] to [11,22,33,120,120]; ClipScalar becomes 22136 after the same
DINT source converts to INT. The source is 16#12345678.

Set ClipIndex=1 and ClipSource=-1 and Step again: elements 1..4 and ClipScalar
become -1, while element 0 remains 11. Disabling ClipNumeric skips invalid live
indices. ClipLength=100001 still produces an explicit simulator limit fault.

The baseline is installed v35 help 14512 and Rockwell's
[FLL reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-fill-fll.html).
The numeric conversion, logical clipping boundary and ST write-effect checks
are bounded software behavior; native controller equivalence remains unverified.
