# Typed numeric AOI input constants

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
remain writable references.

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

Typed radix, time/date, string/aggregate literals, Output/InOut constants,
other controller profiles, protected definitions, nullable/alias parameters,
FBD definitions and native packing/status/lifecycle qualification remain outside
this increment. The separate [JSR/RET constant profile](indirect-routine-calls.md#typed-numeric-constants)
uses its own exact routine-parameter contract.

See [implementation](../source/logixlab/addons.py),
[sample](../source/samples/AOIConstantsLab.L5X) and
[focused checks](../source/tests/test_aoi_literals.py). Rockwell's
[parameter guidance](https://www.rockwellautomation.com/en-no/docs/factorytalk-design-studio/current/contents-ditamap/using-the-software/aoi/define-new-aoi/add-param-to-an-aoi.html)
describes copied Inputs and reference InOut parameters. This bounded software
profile does not establish native Studio/controller acceptance.
