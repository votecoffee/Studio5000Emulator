# Radix MOV constants

The v35 ControlLogix 5580 ladder MOV profile accepts unsuffixed binary (`2#`),
octal (`8#`) and hexadecimal (`16#`) source constants as 32-bit DINT patterns.
Unspecified high bits are zero-filled. Bit 31 is the signed DINT top bit:

| Source | DINT value | LINT destination |
| --- | --- | --- |
| `16#FFFF` | 65535 | 65535 |
| `16#80000000` | -2147483648 | -2147483648 |
| `16#FFFFFFFF` | -1 | -1 |
| `8#1234` | 668 | 668 |
| `2#1010` | 10 | 10 |

This fixes rejection of valid top-bit patterns in MOV. Values are interpreted
before the existing [numeric destination conversion](numeric-storage.md).
Integer destinations retain low bits and signed widening. Thus `16#FFFFFFFF`
becomes ULINT 18446744073709551615, while the explicitly unsigned decimal
`4294967295U` becomes ULINT 4294967295. REAL conversion can round large DINTs;
`16#7FFFFFFF` becomes REAL 2147483648.0 or LREAL 2147483647.0.

Interior spaces and underscores group digits; hexadecimal case is immaterial.
Unsuffixed patterns with more than 32 significant bits and invalid base digits
are blocked structurally, including on false rungs. Attached L/U/UL suffixes
use the [typed source rules](#typed-radix-mov-sources) below. Decimal typed constants retain
their [existing rules](typed-mov-literals.md). Explicit signed radix extensions,
expressions, other instruction operands/consumers, ST/FBD and
other controller/firmware profiles retain their prior scope. General memory
literal parsing is unchanged.

False rungs and prescan skip live destination indices. Complete writes establish
unknown elements; untouched members remain unknown. Aliases and existing AOI
InOut, copied output and local bindings use their canonical storage. Reached
bad indices and later faults roll back the complete advance, including bindings
and scheduler/history state. Required AOI copied inputs are still consumed.

The ladder face and inspector retain the entered constant and show its converted
source as **DINT radix literal**. Other instruction views retain their existing
radix interpretation. Load **Wide expression lab**, enable RadixEnabled and
step to run **RadixMoves**. RadixSelected retains an untouched element and a
903 guard; change RadixIndex to 1 to establish the next element. A zero
RadixLateDivisor demonstrates atomic fault/retry.

## Typed radix MOV sources

App `26.1112.233829` accepts attached L/l, U/u and UL/ul/Ul/uL suffixes on
binary, octal and hexadecimal MOV sources. L selects signed 64-bit LINT,
U selects unsigned 32-bit UDINT and UL selects unsigned 64-bit ULINT. High
bits omitted from a pattern are zero filled to that declared width; bit 63
is the sign bit for LINT. Source interpretation precedes ordinary numeric
destination conversion. No floating arithmetic is used for integer results.

| Source | Declared source value |
| --- | --- |
| `16#FFFF_FFFF` | DINT -1 |
| `16#FFFF_FFFFL` | LINT 4294967295 |
| `16#FFFF_FFFF_FFFF_FFFFL` | LINT -1 |
| `16#FFFF_FFFFu` | UDINT 4294967295 |
| `16#FFFF_FFFF_FFFF_FFFFuL` | ULINT 18446744073709551615 |

Patterns must fit their declared 32/64-bit width even on a false rung. Digit
groups may contain interior spaces/underscores; the suffix must attach to the
last digit. Explicit plus/minus radix signs, decimal points, malformed suffixes,
other bases, expressions and alternate typed prefixes remain excluded.

The MOV viewer uses the same width/sign interpretation and displays integer
values as exact decimal strings. The legacy DINT viewer option retains its
existing behavior. [Bitwise/MEQ masks](typed-bitwise-operands.md#typed-radix-masks)
have a separate qualified profile. General memory/ST/expression, arithmetic,
AOI argument and SBR/RET literal parsers are not extended.

Enable RadixEnabled in **Wide expression lab** and step. RadixLongShort gives
4294967295, RadixLongNegative gives -1, RadixDwordMax gives 4294967295,
RadixUlongMax/RadixOctalMax give 18446744073709551615 and RadixBinaryMin gives
-9223372036854775808. Existing false gates, selected writes, guards and late
fault/retry examples remain. These are modeled bit-pattern rules based on the
v35 immediate-value type/zero-fill tables; native typed-radix import, numerical,
status/fault and lifecycle acceptance remains unverified.

The source basis is installed Studio 5000 v35 help 14454, *Immediate values*,
and the existing numeric MOV profile. Tests establish bounded software behavior;
native Studio acceptance, numerical/status/fault/lifecycle parity and packed
controller layout remain unverified.
