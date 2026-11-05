# String case and REAL conversions

The explicit v35 ControlLogix 5580 profile adds these ladder and Structured Text
calls. Operands are scalar tags, including supported aliases, indexed array
elements, UDT members and existing AOI InOut/input/output bindings.

```text
LOWER(Source,Dest);
UPPER(Source,Dest);
STOR(Text,RealValue);
RTOS(RealValue,Text);
```

Strings use STRING or an explicit user type with scalar DINT LEN and a
one-dimensional SINT DATA array. Numeric operands must be REAL tags. Immediate
and general ST expression operands, wider numeric types and FBD calls remain
unfinished. See [implementation](../source/logixlab/string_conversions.py).

## Case and storage

LOWER maps ASCII A-Z to a-z; UPPER maps a-z to A-Z. Other bytes, including NUL,
punctuation and values 128..255, remain unchanged. Empty input is valid. Source
text is captured before writing, including in-place and alias destinations.

Writes replace LEN and active result bytes, retaining unused destination DATA,
including unknown tail bytes. Output must fit the declared capacity. An unknown
destination LEN/active byte can be established by a write, while unknown active
source bytes or invalid LEN fail explicitly. Constant sources are allowed;
constant destinations remain blocked. [Operand selection](string-operations.md#operand-selection)
checks shapes and permissions without saved values or dynamic indices in the
v35 5580 profile; reached calls still require their actual inputs.

Prescan, false ladder rungs and skipped ST branches retain outputs. Reached
calls execute each scan and ladder output follows input power. ST FOR checks
include these destination writes when protecting bound/step dependencies.

## Decimal and REAL policy

STOR finds the first contiguous decimal run, with an optional adjacent minus
sign and decimal point. Leading text/control bytes are skipped; later groups
separated by delimiters are ignored. For example, W=-12.5 kg / 99 produces
-12.5. A comma is a delimiter, not a locale decimal/thousands separator.
The result rounds to float32. Very small values can round to signed zero.

Empty/no-digit input, malformed decimal/sign runs and exponent notation are
explicitly unqualified and fail. Their native edge behavior is not guessed.
Output overflow and nonfinite values also fail.

RTOS uses a deterministic software formatting policy: finite binary32 values
are rounded to nine significant decimal digits, with exponents expanded to
fixed notation. Redundant fractional zeros are omitted and signed zero is
preserved as -0. This policy round-trips finite REAL values through STOR,
including subnormals. Small user strings may be too short for expanded output.

The installed v35 example 15.3001 becomes 15.3001003 in this profile. That one
example does not establish native formatting for all values: exact native
precision, trailing zeros, exponent spelling and target-specific cases remain
unverified. The coverage report explicitly marks native_formatting_parity false.
This format is not offered as a complete controller formatting contract.

Errors roll back the whole modeled advance, including earlier text/numeric/AOI
writes, time and scheduler state. Native fault records, continuation, partial
writes and math/status flags remain separate work.

## DTOS with REAL input

In the v35 ControlLogix 5580 software profile, `DTOS(RealTag,Text)` uses the
stored binary32 value and rounds to a signed DINT before formatting decimal
text. Halfway values round to the nearest even integer. For example, 2.5 gives
`2`, 3.5 gives `4`, and -3.5 gives `-4`. Ladder and ST share the conversion.
REAL immediates and wider types are outside the supported form. The existing
SINT/INT/DINT sources and bounded DINT immediates continue to work.

A reached call with an unknown or nonfinite input, DINT overflow, or insufficient
output capacity rolls back the modeled advance. False ladder rungs and skipped
ST branches retain the last output. The model uses the documented [DTOS
conversion](https://www.rockwellautomation.com/en-se/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/ascii-conversion-instructions/dint-to-string-dtos.html)
and [REAL-to-integer rounding rule](https://www.rockwellautomation.com/en-mde/docs/studio-5000-logix-designer/37-02/contents-ditamap/elementary-data-types.html).
Native overflow and math-status behavior remain unverified.

## String Lab

Select String lab and step once. Convert gates the new ladder calls and the ST
conversion block; set it false to retain the previous results.

| Input | Ladder / ST result |
| --- | --- |
| CaseText = aBc 09 | Lowered / StLowered = abc 09 |
| CaseText = aBc 09 | Uppered / StUppered = ABC 09 |
| NumericText = W=-12.5 kg | ParsedReal / StParsedReal = -12.5 |
| RealSource = 15.3001 | FormattedReal / StFormattedReal = 15.3001003 |
| RealSource = 15.3001 | RoundedText / StRoundedText = 15 |

Existing FIND/INSERT/DELETE examples remain. See [StringLab.L5X](../source/samples/StringLab.L5X)
and [string editing](string-operations.md).

The baseline uses installed v35 help 14548, 14561, 14562 and 14563. Rockwell's
published [RTOS reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/ascii-conversion-instructions/real-to-string-rtos.html)
provides context. Software tests do not establish native controller or Studio
acceptance.
