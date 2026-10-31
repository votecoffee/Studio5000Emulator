# FBD arithmetic

ADD, SUB, MUL, DIV, ABS and NEG execute as FBD Blocks over finite REAL values in
the bounded v35 ControlLogix 5580 graph. Two logical records now have dedicated
models: FBD_MATH and FBD_MATH_ADVANCED. Their represented fields are typed;
saved omissions remain unknown instead of inheriting declaration defaults.

| Block | Logical record | REAL inputs | REAL output |
| --- | --- | --- | --- |
| ADD / SUB / MUL / DIV | FBD_MATH | SourceA, SourceB | Dest |
| ABS / NEG | FBD_MATH_ADVANCED | Source | Dest |

Both records also contain BOOL EnableIn and EnableOut. Binary arithmetic uses
SourceA then SourceB; ABS takes magnitude and NEG changes sign. Inputs and each
block result round to float32; operations use host-double intermediates. Thus
connected blocks receive the represented rounded result of the preceding block.
Known finite values are required. Every consumed operand is read, including a
multiplier paired with zero. These blocks have no hidden history.

Prescan performs no math-specific value changes, following the installed v35
tables' N/A entries. Enables and Dest retain through prescan and Run entry.
Connected false EnableIn clears EnableOut and retains Dest; unwired EnableIn
executes. Skipped routines retain visible values. Explicit Dest writes survive
disabled/skipped calls and are replaced by the next enabled calculation.

This finite profile rejects zero divisors, nonfinite values and REAL overflow
with whole-advance rollback. Native DIV can return SourceA and generate a minor
fault for a zero divisor; that result/fault behavior is not implemented here.
Native overflow EnableOut behavior, math flags, underflow/subnormals, nonfinite
results and complete lifecycle/fault parity remain unqualified. The simulator
does not substitute a known numeric result for these excluded cases.

Other graph blocks retain their existing prescan behavior. Graph wires, all
destinations, enables, earlier block changes, later RLL errors, time and task
scheduling participate in the existing transaction. Periodic/Event/harness calls
and supported detached RLL caller replacement use the same stateless math model.
The [single-sheet graph rules](function-blocks.md) still apply.

Choose **FBD arithmetic lab** for `FBDMathLab.L5X`: 23 roots, six blocks, 19 nodes
and 23 wires. It calculates `(A+B-Offset)*Gain/Divisor`, then NEG and ABS. Initial
values 6, 2, 1, 3 and 3 yield Sum 8, Difference 7, Product 21, Quotient 7,
Negative -7 and Magnitude 7. BlockEnable gates all six; ExecuteGraph skips the
routine. Divisor zero demonstrates the excluded minor-fault case. FaultDivisor
zero adds a later ladder fault; restore valid values before retrying.

The graph inventory is 46 blocks: 21 names shared with existing ST-call entries,
18 existing RLL names and seven FBD-only forms. RLL remains 101 and
ST calls 27. Tagless FBD Function forms, integer/wide math wires, other math
operations and packed/native transfer layouts remain unsupported or unqualified.
No one-record RLL/ST call overloads are added by these FBD forms.

Schemas, operands and prescan tables were checked against installed v35 help
14598.htm, 14616.htm, 14618.htm, 14619.htm, 14621.htm and 14623.htm, alongside
Rockwell's [general-instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
The synthetic lab has no native Studio import/Verify or controller-equivalence proof.
