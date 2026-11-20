# Add-On Instruction constants

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
other controller profiles, protected definitions, nullable/alias parameters,
FBD definitions and native packing/status/lifecycle qualification remain outside
this increment. The separate [JSR/RET constant profile](indirect-routine-calls.md#typed-numeric-constants)
uses its own exact routine-parameter contract.

## Constant InOut parameters

In the v35 ControlLogix 5580 profile, an AOI may declare a required InOut
parameter with `Constant="true"`. Its argument is an exact-type, matching-shape
tag reference. A constant or mutable caller tag, including an alias, can supply
that reference. The AOI reads the caller's current value without copying it.

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
