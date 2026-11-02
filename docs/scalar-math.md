# Scalar arithmetic and bitwise operand selection

The v35 ControlLogix 5580 ladder profile validates these existing operations
without requiring saved scalar values or live indices:

| Arithmetic | Integer bitwise |
| --- | --- |
| ADD, SUB, MUL, DIV, MOD, NEG, ABS | AND, OR, XOR, NOT |

Declared scalar types, references, destination permissions and the existing
homogeneous wide-integer rules remain checked. Invalid shapes, BOOL operands,
unsupported bitwise floating-point forms and mixed wide types still fail static
validation, including on false rungs.

False rungs and ordinary prescan skip operand values and dynamic indices. A true
instruction consumes every required source value. Its complete numeric write
can establish an unknown destination element or member without reading the old
value. Aliases and existing AOI InOut/local bindings use the same storage rules.
Unwritten siblings remain unknown. Reached unknowns, invalid indices, zero
divisors, excluded ranges and later faults roll back the complete advance,
including values, task/time state and existing AOI bindings.

This increment changes validation and operand selection. Existing calculations,
destination coercion and overflow handling remain in place. Integer division
into integer destinations truncates toward zero; integer remainder retains the
dividend's sign. Wide arithmetic stays homogeneous and exact. Arithmetic overflow
still stops and rolls back the model rather than reproducing native status and
partial effects.

Complete mixed-type arithmetic and bitwise promotion, additional types/forms,
REAL MOD, native overflow/status/fault/lifecycle and packed layout parity remain
unfinished. In particular, this change does not qualify the complete bitwise
width-conversion matrix. ST expressions and FBD are unchanged; other controller
profiles retain their separate validation paths.

Choose **Math lab** and enable `BasicMath`. `BasicA` and `BasicB` drive eleven
named results for the operations above. Start with 7 and 3 to see sum 10,
quotient 2, remainder 1 and complement -8. The original advanced-math and called
ST examples remain available. The report exposes the profile as `scalar_math`.

Reference basis: installed Studio 5000 v35 instruction help for these eleven
instructions, including DIV 14621 and MOD 14620. Software-model and HTTP checks
do not establish native controller equivalence.
