# Ladder PID numeric operands and tieback

The [PID software profile](ladder-pid.md) accepts scalar SINT, INT, DINT and
REAL PV/CV tags, a numeric tieback input, and the MO hardware-manual mode.
These are logical emulator behaviors; no analog module or physical station is
created. The existing controller gate, solver, lifecycle, derivative/deadband
rules and whole-advance rollback remain in effect.

```text
XIC(Execute)PID(Loop,PV,Tieback,CV,0,0,0);
```

PV must be a numeric tag. CV must be a writable numeric tag. Tieback may be a
scalar tag of the same four supported types, a signed DINT immediate or a finite
REAL immediate. The operands may use different supported types. Master requires
literal zero; [inhold](pid-restart.md) accepts status/readback tags or zero sentinels.
BOOL numeric operands, wide/unsigned types,
expressions, whole arrays and overlap with the PID record remain blocked.
Aliases and selected array/member operands use the common memory resolver.

## Conversions

PV and a consumed tieback promote to float32 before internal scaling. Large
DINT values can lose precision at this boundary; integer storage does not make
the PID calculation exact integer arithmetic. Required unknown data faults.

Output descaling produces finite REAL first. An integer CV then rounds to the
nearest integer, with ties to even, and must fit its declared range. A range
failure rolls back the record, CV, hidden solver state, tasks, time and trace.
OUT remains the requested output percentage; quantization is not fed back into
the integral. DATA[14] mirrors the value actually assigned to CV as REAL.

For an integer automatic CV and positive DB, this profile writes zero whenever
the error is inside the inclusive engineering deadband. This includes entry
before a zero-crossing hold starts. OUT still reports the calculated or held
percentage; EWD still reports active hold. Both manual modes override this
control deadband behavior. Exact native conversion, deadband/manual interaction,
overflow/minor-fault and partial-effect semantics remain unqualified.

## Hardware manual

MO takes priority over SWM. With MO true, read tieback and scale MINTIE..MAXTIE
linearly into output percent, clamped to 0..100. The tieback span must be positive.
The raw consumed operand is mirrored in TIE in this software profile. Its exact
native presentation remains unqualified. Tieback and its scaling fields are
not consumed in auto, software manual or reached false calls.

This mode uses the existing manual tracking path: back-calculate I to
`OUT-P-BIAS` when integration is enabled; otherwise adjust BIAS to `OUT-P`
unless NOBC is set. SO follows the selected output, including when MO overrides
SWM. Clearing MO with SWM still set therefore uses the last output unless SO
has been changed. The first auto call after either manual mode holds I and
suppresses D. With unchanged inputs this preserves the modeled transfer value;
native bumpless transfer and startup remain unqualified.

Manual percent uses the full 0..100 range, independent of automatic MINO/MAXO,
then follows normal CV descaling and conversion. It clears the deadband latch
and refreshes derivative samples. Invalid or unknown tieback data/ranges fault
when MO consumes them, without committing earlier work from that advance.
[Manual PVT and explicit inhold inputs](pid-restart.md) now execute. Cascade,
analog module restart/acknowledgement, smoothing and saved native solver history
remain unsupported. ST/AOI instruction forms remain deferred.

## PID lab

The existing **PID lab** has two independently enabled loops:

| Loop | Enable | PV/CV | Example |
| --- | --- | --- | --- |
| Loop | Execute | REAL PV/CV | Original P/PI/PID examples |
| IntLoop | IntExecute | INT RawPV/RawCV | 4000..20000 input scaled to 0..100; output 0..32767 |

Both use the REAL Tieback input. Manual/SoftwareManual and
IntManual/IntSoftwareManual are BOOL aliases for each record's mode bits, so
they can be toggled in the tag list. NoDerivativeSmoothing/NoZeroCrossing and
their Int-prefixed counterparts expose the NDF/NOZC controls.

Set IntExecute true with RawPV 8000: IntLoop sees PV 25, OUT 25 and RawCV 8192.
Set IntSoftwareManual true and IntLoop.SO 50: RawCV becomes 16384. Set IntManual
true and Tieback 60: MO overrides SWM and RawCV becomes 19660. The REAL loop
continues independently. FaultDivisor zero exercises rollback of both loops.

Reference basis: installed v35 help 14709, 14738 and 40012, corroborated by the
PID operand, deadband and manual-mode sections of the
[Logix general instruction reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf).
