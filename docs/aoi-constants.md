# Add-On Instruction parameters

The v35 ControlLogix 5580 software profile accepts decimal LINT, UDINT and ULINT
constants and finite floating LREAL constants for required scalar AOI Inputs.
The literal type must match the declared parameter type exactly:

| Declared type | Example |
| --- | --- |
| LINT | `9007199254740993L` |
| UDINT | `4294967295U` |
| ULINT | `18446744073709551615UL` |
| LREAL | `1.0000000000000002L` |

Integer suffixes are L/l, U/u and UL/ul/Ul/uL. A decimal point or exponent with
L/l selects LREAL. Signed limits and finiteness are checked during binding,
including false calls. Typed constants do not enable implicit promotion or
narrowing into another parameter type. Existing unsuffixed numeric inputs and
tag-based conversions retain their earlier rules. Output and InOut actuals
use tag references. Constant InOut parameters can use read-only references.

The instruction keeps its existing copied-input lifecycle. Required Inputs
are copied during prescan and each reached invocation, including false calls.
Normal Logic runs when enabled. An enabled EnableInFalse routine may run while
false; its outputs follow the existing copy rules. Without that routine, false
calls copy Inputs and retain the caller's output values. Constants do not seed
unknown saved locals or replace the definition's optional-parameter behavior.
Nested RLL and existing ST AOI calls use the same transfer path. ST arithmetic
and assignment limits remain separate; a supported CPS call can copy LREAL.
Failed advances
restore instance fields, outputs, bindings, clocks and scheduling.

Choose **Examples → AOI constants lab**. Step once with Enabled false to inspect
the copied Input fields while outputs remain zero. Set Enabled true and step:
SignedResult, UnsignedResult, LargestResult and PreciseResult receive the values
above. Disable Enabled and change an output tag to observe retention on a false
call. Re-enable to copy the constants again. LINT/ULINT API snapshots use exact
decimal text; LREAL retains binary64 precision.

Time/date and string/aggregate literals, literal Output and InOut actuals,
other controller profiles, protected definitions, nullable InOut parameters,
FBD definitions and native packing/status/lifecycle qualification remain outside
this increment. The separate [JSR/RET constant profile](indirect-routine-calls.md#typed-numeric-constants)
uses its own exact routine-parameter contract.

## Aliases to scalar local tags

In the v35 ControlLogix 5580 profile, an ordinary AOI Input or Output can
declare `AliasFor` to one matching BOOL, SINT, INT, DINT or REAL scalar in
local storage. Targets can be whole scalar locals, declared UDT members,
logical TIMER, COUNTER or CONTROL fields, and array elements with fixed
decimal indices. For example, `State.Samples[1]` selects one element inside
a local UDT and `Clock.PRE` selects a timer preset. DINT fields and BOOL
flags use their declared types. One Input and one Output can share
the selected value in each instance. Required Input and Output
arguments retain the existing copy-in and copy-out rules, including prescan
and false calls.

Saved decorated values may identify the local or its alias. When both are
present they must agree. The monitor shows the alias as a public parameter.
BOOL aliases can also select a fixed bit in a local SINT, INT or DINT, such
as `Flags[1].31`. Writes preserve the other bits. A saved bit value must agree
with a saved backing word, which can come from a whole-word alias. An import
with a saved bit and an omitted backing word blocks execution. Overlapping
whole-word and bit aliases of the same direction are rejected.

A BOOL alias can also select a named UDT `BIT` member, such as
`State.Ready`, when it has a unique bit in a hidden scalar SINT host. The
emulator uses the named BOOL value. A saved alias can establish that value
when the named member was omitted. A conflicting saved value blocks execution.

Dynamic indices, visible-host overlaps and fields of other built-in records
remain outside the supported profile. Native Studio 5000 import and packed
layout remain unverified.
See Rockwell's [Add-On Instructions manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm010_-en-p.pdf).

## One-dimensional InOut arrays

In v35 ControlLogix 5580 ladder and Structured Text, a one-dimensional InOut
array can bind a same-type caller array at least as long as the formal
declaration. A two-element declaration can therefore bind a four-element
array. `SIZE` inside the AOI returns four, and references use the actual
array's bounds. The AOI shares caller storage, so writes through the
parameter update the caller's array. Scalar and multidimensional bindings
still require matching shapes, and existing read-only and writable rules
apply. Native monitor presentation remains unverified.
See Rockwell's [single-dimension InOut guidance](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm010_-en-p.pdf).

## False ladder calls

In the v35 ControlLogix 5580 profile, a false ladder call with
`EnableInFalse` disabled copies its required Inputs and leaves the caller's
Output and InOut operands unevaluated. For example, if `Out[Index]` is a
required Output and `Index` goes out of range after prescan, the false call
still copies its Inputs. The instruction instance and Input addresses must
still be valid. The false call has no live InOut binding for the monitor.

Prescan, true calls and false calls with `EnableInFalse` enabled still
resolve the Output and InOut operands. An invalid index during an active
advance faults and rolls back the advance. Project validation still checks
the full call. See Rockwell's [AOI scan-mode guidance](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm010_-en-p.pdf)
for parameter transfers. Index fault timing and monitor behavior remain
unverified in native Studio 5000.

## Constant InOut parameters

In the v35 ControlLogix 5580 profile, an AOI may declare a required InOut
parameter with `Constant="true"`. Its argument is an exact-type tag reference
with a compatible [InOut shape](#one-dimensional-inout-arrays). A constant or
mutable caller tag, including an alias, can supply that reference. The AOI
reads the caller's current value without copying it.

Ladder and Structured Text reject writes through the parameter, including
member or bit writes and attempts to pass it to a writable nested InOut or
Output. A nested constant InOut can receive the reference. A mutable caller
tag can still be updated in the caller's own scope. This is the emulator's
software behavior. See Rockwell's [InOut constant guidance](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm004_-en-p.pdf).

## Grouped DINT inputs

Required scalar Inputs in v35 ControlLogix 5580 ladder and ST calls accept
grouped, unsuffixed binary, octal and hexadecimal DINT words. Short patterns
zero-fill to 32 bits before the value is read as signed. For example,
`16#FFFF FFFE` passes -2. The existing DINT-to-input conversions, including
conversion to REAL, apply to the decoded value. The ladder viewer shows the
signed source value beside its authored operand.

An Input receives the same decoded value during prescan, on a false ladder
call, and when the AOI runs. Suffixed constants keep their exact declared type
rules. See [constant InOut parameters](#constant-inout-parameters) for read-only
bindings.

## Typed radix parameters

App `26.1113.063603` also accepts attached binary, octal and hexadecimal L/l, U/u
and UL/ul/Ul/uL constants with the same exact parameter-type contract. LINT
and ULINT patterns use 64 bits; UDINT uses 32. Short patterns zero-fill and the
LINT top bit represents a negative number. `16#FFFFFFFFL` is positive
4294967295; `16#FFFFFFFFFFFFFFFFL` is -1. Values above 2^53 stay exact.
Invalid digits, overwide patterns and type mismatches block false calls too.
These suffixed forms apply to immediate Inputs in the qualified profile.
Native Studio import, numerical/fault and lifecycle parity remain unverified.

AOI constants lab now supplies the same values using hexadecimal Signed,
octal Unsigned and binary Largest inputs. ParameterLateDivisor defaults to one;
zero demonstrates rollback after output copies, and one allows retry. False
calls still copy Inputs and retain outputs. The viewer shows exact declared
radix values for required Inputs only; nested and existing ST call transfers
retain their copied-input lifecycle.

See [implementation](../source/logixlab/addons.py),
[sample](../source/samples/AOIConstantsLab.L5X) and
[focused checks](../source/tests/test_aoi_literals.py). Rockwell's
[parameter guidance](https://www.rockwellautomation.com/en-no/docs/factorytalk-design-studio/current/contents-ditamap/using-the-software/aoi/define-new-aoi/add-param-to-an-aoi.html)
describes copied Inputs and reference InOut parameters. This bounded software
profile does not establish native Studio/controller acceptance.
