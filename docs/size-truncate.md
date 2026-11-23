# Array size and truncation

The v35 ControlLogix 5580 software profile adds these common ladder forms:

```text
SIZE(Grid[0,0],1,Columns);
SIZE(Message,0,Capacity);
SIZE(Message.DATA[0],0,Capacity);
TRN(RealValue,WholeValue);
```

SIZE reads the dimensions of the closest logical array, including member arrays
and string DATA storage. Selected elements retain that array's declared rank and
dimensions; leaf values and string LEN are not consumed. One to three dimensions,
aliases and existing AOI InOut/local bindings are supported. Results can be
SINT/INT/DINT/REAL, provided the size fits the destination. SIZE is also callable
from ST. It returns logical element counts.

## Direct string capacity

As of `26.1119.165909`, a scalar STRING or supported user-defined string can
be passed directly to SIZE with dimension 0. The result is the declared
capacity, even if LEN and every DATA byte are unknown. This also works through
an alias or a string member in a selected UDT. The selected member's address
must be valid when the instruction executes.

A string array and its directly selected elements keep their existing array
dimensions. For example, SIZE on either `Labels` or `Labels[1]` returns 2 for a
two-element string array. Use `Labels[1].DATA` to obtain that element's string
capacity. The v35 examples use explicit DATA operands; native verification of
the emulator's direct scalar form remains open.

The documented dimension operand is an immediate 0, 1 or 2. Ladder and ST can
express it as a grouped unsuffixed binary, octal or hexadecimal DINT word,
such as `SIZE(Grid,16#0000 0001,Columns)`. Values must select a declared dimension.
The ladder monitor shows the decoded dimension. The existing emulator
extension accepting a SINT/INT/DINT dimension tag remains available, with rank and
range checked when executed. This extension is not claimed as native syntax.

TRN truncates toward zero at the stored REAL or LREAL precision. It writes
representable results to SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, REAL
and LREAL. Floating results preserve signed zero. NaN and infinity in source
tags are supported for floating and signed integer results. Bounded DINT
and finite REAL immediates use float32. A finite floating L/l constant uses
binary64. See [LREAL truncation](lreal-truncate.md) for destination examples.
ST continues to use its separate TRUNC expression;
this change does not add a TRN ST call or expand FBD.

Preflight checks types, shape and permissions without consuming saved scalar
values or live indices. False rungs and ordinary prescan retain outputs. Executed
full writes can establish unknown destination values. A handler can
[clear a reached array subscript fault](controller-handlers.md#recover-bcd-size-and-truncation-array-faults)
during a whole-project ladder scan and skip the result write. Reached unknown
sources, uncleared faults, excluded ranges and later failures roll back the
complete advance.

Choose **Data lab**, enable `InspectData`, and inspect `SizeResult`,
`StringCapacity`, `TruncatedWide` and `TruncatedUnsigned`. The API report exposes
the profile under `size_truncate`.

The source basis is the installed Studio 5000 v35 instruction help, **Size In
Elements (SIZE)** (14517) and **Truncate (TRN)** (14671). Focused software tests
and HTTP checks do not establish native controller equivalence. Native overflow
values, math status, fault classification and lifecycle parity remain unqualified.
