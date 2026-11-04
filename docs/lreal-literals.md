# Floating constants in LREAL ladder expressions

The bounded v35 ControlLogix 5580 CPT/CMP evaluator accepts ordinary floating
constants and explicit LREAL floating constants. Decimal points and scientific
notation are supported. A trailing L or l on a floating value selects LREAL.
The suffix requires a decimal point or exponent: `1L` is an integer spelling
and remains outside this added profile.

```text
CPT(DoubleResult,0.1);
CPT(DoubleResult,0.1L);
CPT(IntegerResult,3.5L);
CPT(DoubleResult,Source**0.5);
CMP(0.1L<>0.1)OTE(Different);
```

## Precision and selection

An unsuffixed floating constant is first represented as finite REAL, then
promoted when an LREAL tag, LREAL literal or LREAL CPT destination selects
binary64 calculation. An explicit floating L/l suffix retains finite binary64
precision. The expression continues using the existing binary64 arithmetic
and final destination conversion rules.

| Constant or expression | Software result in an LREAL destination |
| --- | --- |
| 0.1 | 0.10000000149011612 |
| 0.1L | 0.1 |
| 1.0000000000000002 | 1.0 |
| 1.0000000000000002L-1.0 | 2^-52 |
| 1e308L | 1e308 |
| 5e-324l | smallest positive binary64 subnormal |

An LREAL literal can select binary64 even without an LREAL source tag or
destination. Thus `CPT(IntegerResult,3.5L)` stores integer 4 under the model's
nearest-even representable-result policy. All ten numeric destinations retain
their [conversion rules](lreal-results.md). The difference in the table also
makes `CMP(0.1L<>0.1)` true. This is deliberate source precision, rather than a
change in comparison tolerance.

Negative values, signed zero, scientific notation, lowercase suffixes, `.5l`
and `1.L` are accepted. Unsuffixed constants must round to finite REAL; use an
explicit LREAL constant or tag for larger finite binary64 values. Nonfinite
and out-of-range literal encodings are rejected during preflight, including
false rungs. Finite small literals can underflow at their declared precision.
Required calculation domains, zero divisors, complex powers and destination
range checks still occur only when their calls execute.

## Scope and recovery

Only direct ladder CPT/CMP opt into LREAL literal parsing. The parser and
expression cache distinguish that mode from generic, FAL/FSC, array-subscript
and ST consumers. [Integer U/L/UL suffixes](ladder-integer-literals.md) have a
separate matching-type CPT/CMP profile. Other typed spellings, separators,
BCD/numeric bitwise mixtures and additional language/controller profiles
remain separate work. Existing REAL expressions without an LREAL selector
retain their previous evaluation rules.

Supported references, aliases/UDT cells, unknown full writes, dynamic-index
selection and AOI copied inputs/outputs, InOut arrays and local state retain
their existing contracts. A failed modeled advance restores earlier writes,
warm bindings, local state, trace and scheduler/timing data. CMP Boolean
composition remains eager; a required failing operand is not hidden behind an
already true or false operand. Prescan and prior successful advances remain
separate committed events.

## Wide expression lab

Open Wide expression lab and step once, then enable FPLitEnabled. The
FloatingConstants routine displays ordinary and explicit 0.1 side by side,
double precision near 1, fractional powers, large/subnormal constants, integer
and REAL final conversion, lowercase/scientific spellings and a difference
coil. FPLitSelected becomes [3.5, unknown, 903].

FPLitDomainFault enables LN of a negative constant; FPLitRangeFault enables
an overflowing SINT result. Clear each flag to recover. Set FPLitIndex=1 and
FPLitLateDivisor=0 to fail after the selected write; that cell stays unknown.
Restore the divisor to 1 and retry to establish 7.5. Disable FPLitEnabled
before leaving an invalid index dormant.

See [sample](../source/samples/WideExpressionLab.L5X),
[evaluator](../source/logixlab/lreal_expressions.py),
[scoped parser](../source/logixlab/expressions.py) and
[tests](../source/tests/test_lreal_literals.py). The source baseline is installed
v35 Immediate values (14454), CPT (14597) and CMP (14592). Rockwell's published
[CPT reference](https://www.rockwellautomation.com/en-id/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/compute-math-instructions/compute--cpt-.html)
provides context; installed v35 spellings govern this profile. Native numerical,
status, fault, partial-write, packed-layout and controller/Studio lifecycle
equivalence remain unverified.
