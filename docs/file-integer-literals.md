# Typed integer constants in FAL and FSC

The bounded v35 ControlLogix 5580 file evaluator accepts decimal L/l (LINT),
U/u (UDINT) and UL/ul/Ul/uL (ULINT) constants in FAL expressions and FSC search
conditions. The homogeneous profile requires matching numeric tags, typed constants
and FAL destinations. [Matching constants in mixed expressions](ladder-wide-expressions.md#matching-typed-constants)
also allow compatible tags when the literal matches the common actual source type.
Representable signed-DINT constants may participate. Every integer intermediate
must fit the selected type; values above 2^53 remain exact.

```text
FAL(Calc,?,?,ALL,Output[Calc.POS],9007199254740993L);
FAL(Calc,?,?,1,Output[Calc.POS],Input[Calc.POS]+2UL);
FSC(Find,?,?,INC,Input[Find.POS]>=18446744073709551615UL);
```

Use the type matching the file operands: the second example requires ULINT
input/output arrays. Literal-only FSC conditions can select their integer type
without numeric tags. Signed minima, unary signs, leading decimal zeroes and
all listed suffix cases follow the existing
[ladder integer constant rules](ladder-integer-literals.md).

## Execution and recovery

ALL processes its selected file in one modeled advance. Numeric mode continues
active work on false rungs, consuming current inputs for each later iteration.
INC processes one element per observed enable edge; a held call skips new data.
FSC retains its first-match FD/IN behavior and resumes after IN is cleared.
Completion, error inhibition, source CONTROL qualification and cursor rules are
unchanged. LEN/POS use live CONTROL members. See
[literal initialization on import](control-operations.md#literal-len-and-pos-on-import).

Declared literal ranges are checked during preflight, including false calls.
False or data-free completed/inhibited calls skip required values and live
indices. An executed expression consumes required operands eagerly, including
FSC Boolean operands. Existing exact quotient/remainder, bitwise, ABS and
comparison forms remain available.

A failed advance restores writes, CONTROL flags/cursors, private INC progress,
warm AOI bindings and local state, scheduler/timing and trace. Prior successful
advances remain committed. Fixing a required value or divisor can retry a pending
edge without consuming an extra element. Sequential overlap retains live
read-after-write behavior.

## Scope and remaining work

Explicit parser/cache options isolate FAL/FSC integer literals from generic and
array-index parsing. Direct CPT/CMP and ST retain their own profiles. This does
not add typed literals to mode, length, position or other instruction arguments.

[Typed radix constants](ladder-wide-expressions.md#typed-radix-expressions)
now share the integer file grammar and existing progress/rollback rules.
Nonmatching typed/tag combinations, narrowing, floating/radix mixtures, decimal
separators and additional functions remain blocked. Existing mixed-tag FSC
conditions remain a separate profile. Saved active INC state, native CONTROL
layout, final cursor/math/status/fault/partial-effect behavior and Studio/controller
lifecycle equivalence remain unverified. A modeled fault rolls back the advance;
that is not a claim about a controller's partial effects.

## Wide expression lab

Step Wide expression lab once, then enable FILitEnabled. IntegerFileConstants
fills LINT, UDINT and ULINT files from full-width constants and searches the LINT
file exactly. The last cell of each file is a guard. Set FILitLateDivisor=0
before enabling to exercise rollback; restore it to 1 and retry.

FILitNumericStart begins one element per scan; active work continues when this
flag becomes false. FILitOffset changes later LINT values. FILitIncrement pulses
one ULINT element and search comparison at a time. Clear FILitIncrementFind.IN
before an observed false scan, then enable again to resume a found search.
While IN is set the current model retains EN even on false calls. Repeated true
scans keep the current INC element.

See the [sample](../source/samples/WideExpressionLab.L5X),
[tests](../source/tests/test_file_integer_literals.py),
[FAL implementation](../source/logixlab/file_arithmetic.py) and
[FSC implementation](../source/logixlab/file_search.py). Source baseline:
installed v35 Immediate values (14454), Data conversions (14451), FAL (14504)
and FSC (14515). Rockwell's published
[FAL reference](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/array-file-misc-instructions/file-arithmetic_logic-fal.html)
provides context; installed v35 definitions govern this software profile.
