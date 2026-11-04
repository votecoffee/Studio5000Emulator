# Array size and truncation

The v35 ControlLogix 5580 software profile adds these common ladder forms:

```text
SIZE(Grid[0,0],1,Columns);
SIZE(Message.DATA[0],0,Capacity);
TRN(RealValue,WholeValue);
```

SIZE reads the dimensions of the closest logical array, including member arrays
and string DATA storage. Selected elements retain that array's declared rank and
dimensions; leaf values and string LEN are not consumed. One to three dimensions,
aliases and existing AOI InOut/local bindings are supported. Results can be
SINT/INT/DINT/REAL, provided the size fits the destination. SIZE is also callable
from ST. Direct scalar string operands and packed layout traversal remain outside
this profile; use the represented DATA array for string capacity.

The documented dimension operand is an immediate 0, 1 or 2. The existing emulator
extension accepting a SINT/INT/DINT dimension tag remains available, with rank and
range checked when executed. This extension is not claimed as native syntax.

TRN consumes a finite REAL or LREAL tag and truncates toward zero, preserving
float32 or binary64 source precision respectively. It writes SINT/INT/DINT/LINT/
USINT/UINT/UDINT/ULINT/REAL/LREAL destinations when the result fits. Bounded DINT
and finite REAL immediates retain the existing float32 source policy. See
[LREAL truncation](lreal-truncate.md) for precision and destination examples.
ST continues to use its separate TRUNC expression;
this change does not add a TRN ST call or expand FBD.

Preflight checks types, shape and permissions without consuming saved scalar
values or live indices. False rungs and ordinary prescan retain outputs. Executed
full writes can establish unknown destination values; reached unknown sources,
bad indices, excluded ranges and later failures roll back the complete advance.
Other controller profiles retain their previous behavior.

Choose **Data lab**, enable `InspectData`, and inspect `SizeResult`,
`StringCapacity`, `TruncatedWide` and `TruncatedUnsigned`. The API report exposes
the profile under `size_truncate`.

The source basis is the installed Studio 5000 v35 instruction help, **Size In
Elements (SIZE)** (14517) and **Truncate (TRN)** (14671). Focused software tests
and HTTP checks do not establish native controller equivalence. Native overflow
values, math status, fault classification and lifecycle parity remain unqualified.
