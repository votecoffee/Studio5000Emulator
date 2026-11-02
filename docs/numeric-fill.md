# Numeric file fill

The v35 ControlLogix 5580 ladder profile supports numeric FLL with scalar
SINT/INT/DINT/REAL sources and destinations of those types:

```text
FLL(Source,Destination,Length);
```

Length is a scalar SINT/INT/DINT tag or bounded DINT immediate, with an executed
value in 0..100000. Sources also accept bounded DINT or finite REAL immediates.
Whole numeric arrays or selected elements, aliases, member arrays and existing
AOI InOut/local bindings use canonical logical storage. BOOL, wide/unsigned and
aggregate sources are excluded from this numeric profile.

## Conversion

Integer narrowing preserves the low destination bits, including its signed
top bit. DINT 16#12345678 becomes SINT 120 or INT 22136; DINT 128 becomes SINT
-128. Widening sign-extends: SINT -1 becomes DINT -1. The source is sampled once
before stores, including when it overlaps the selected destination window.

REAL values use finite float32. Representable REAL-to-integer results round
ties to even: 2.5 becomes 2, 3.5 becomes 4. REAL overflow results remain excluded
and roll back the advance; this increment does not infer native overflow bits
or status. Integer-to-REAL conversion can lose precision, for example DINT
16777217 becomes REAL 16777216.0.

## Selection and lifecycle

Structural preflight checks types, shapes, permissions and immediate bounds
without consuming saved tag values or live indirect indices. False rungs and
prescan retain data and skip live source, length and destination-index values.
An executed call samples length and resolves the complete destination window,
then samples/converts the source once before filling. Thus source/length aliases
inside the destination do not change the operation midway through the fill.

Zero length validates the live destination reference but does not read the
source value or write anything. Unknown selected numeric elements can be
established by a full fill; untouched elements remain unknown. Reached unknown
operands, invalid indices/lengths, REAL range errors and later faults roll back
the complete advance, including AOI local/external data and binding metadata.
Required copied AOI inputs are still consumed before the body, independently
of an FLL instruction's lazy reads.

The window can traverse adjacent rows in row-major order within the selected
logical array/member. It must fit that boundary. Oversized requests fault;
they are not clipped or allowed to cross other members/base tags. Native FLL
can use different packed-memory boundaries and clipping; that behavior remains
unqualified. Timing, native partial effects and math-status parity remain open.

Aggregate zero fills, other controller profiles and other languages retain
their separate earlier contracts. The new numeric conversion path does not
enable general structure patterns, wide types, ST FLL calls or FBD forms.

## Data lab

Load **Data lab**, set FillNumeric true and step. With FillIndex=1 and
FillLength=3, ByteFill[1..3] become 120, WordFill[1..3] become 22136,
SignedFill[1..3] become -1 and RealFill[1..3] become 2. The first and last
elements are guards. Change FillSource or FillReal and step again to refill.

Set FillNumeric false and an invalid FillIndex to retain the results without
consuming that index. Re-enable to see a modeled bounds fault, correct the
index and retry. Existing Data Lab copy, string and flow examples still run.

The source basis is installed v35 help 14512 and the published
[FLL reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-fill-fll.html).
These software-model checks do not establish native controller or Studio
acceptance. See [implementation](../source/logixlab/numeric_fill.py).
