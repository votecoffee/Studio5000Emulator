# REAL calculations with SINT, INT and DINT results

The bounded v35 ControlLogix 5580 ladder profile supports SINT, INT and DINT
destinations in the same REAL calculation profile as LINT and unsigned results.
A REAL source tag or an unsuffixed floating immediate selects float32 math.
This applies to ADD, SUB, MUL, DIV, MOD, NEG, ABS, XPY, SQR, LN, LOG, DEG,
RAD, SIN, COS, TAN, ASN, ACS and ATN.

```text
ADD(RealInput,0UL,ByteResult);
DIV(7.0,2U,WordResult);
SUB(16777217U,16777216.0,DwordResult);
XPY(UnsignedBase,0.5,WordResult);
ADD(16#FFFFFFFF,RealInput,ByteResult);
```

Every required source first converts to finite REAL. Calculation then uses
the existing software solver, and the result rounds to REAL before conversion
to the declared integer. Integer conversion rounds to nearest, ties to even;
the rounded value must fit the destination. At RealInput=2.5 the first result
is 2. The next examples produce 4, 0, 2 for UnsignedBase=4, and 2.

This order matters: 16777217U becomes REAL 16777216 before subtraction.
An LREAL source or floating L/l literal retains binary64 priority and can
produce a different integer result. Integer-only calls keep their existing
exact arithmetic and type/range rules; a small saved integer value alone
does not authorize a new narrowing conversion. Unary calls require a REAL
source or floating immediate for this REAL profile.

SINT accepts 127.49 rounded to 127; 127.5 rounds to 128 and faults under the
emulator's range policy. -128.5 rounds to the even -128 and fits. DINT's
largest representable positive REAL below 2^31 is 2147483520; an integer
2147483647 converts to REAL 2147483648 and cannot be stored into DINT after
REAL calculation. This is separate from integer-only DINT arithmetic.

Existing decimal and declared-width radix source rules apply. Structural
preflight checks references, types, shapes, literals and permissions without
reading saved values or live indices. False rungs and prescan retain numeric
outputs and skip live operands. Full writes can establish unknown results.
Reached unknowns, invalid indices, zero divisors, domains, nonfinite results,
out-of-range destinations and later failures restore the advance, including
earlier writes, timing and supported AOI bindings.

Aliases, selected members, overlapping results and supported AOI copied
Inputs, local tags and InOut arrays retain their existing semantics. The viewer
recognizes radix source words with these REAL selectors for narrow results.
The REAL math reports now list all eight integer destination types.

Load **Integer lab**, set NarrowRealIndex=1, enable NarrowRealEnabled and
step. SINT=2, INT=4, DINT=0, Root=2, Power=2, Radix=2 and Selected[1]=2;
RoundedEven is true. Index 99 or NarrowRealLateDivisor=0 demonstrates rollback.
NarrowRealBoundaryEnabled enables the separate 127.5-to-SINT fault; change
NarrowRealBoundarySource to 127.49 to repair it. Disable the main gate to skip
invalid live operands and clear the comparison coil.

No ST/FBD forms are added. Native numerical, math-status, minor-fault and
lifecycle parity is unverified; overflow uses the emulator's existing atomic
range policy. The source basis is installed v35 Data conversions (14451),
Immediate values (14454), ADD (14623), MOD (14620), XPY (14478) and SQR (14617).

See [source selection](../source/logixlab/numeric_storage.py),
[REAL calculations](real-destination-math.md),
[radix sources](real-radix-math.md) and
[focused cases](../source/tests/test_real_narrow_results.py).
