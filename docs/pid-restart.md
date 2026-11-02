# PID manual PV tracking and inhold readback

The [ladder PID profile](ladder-pid.md) supports manual PV tracking and an
explicit inhold input handshake. These are software execution contracts.
They do not create an analog output module, a connection lifecycle, a ramp or
a module acknowledgement. Native initialization, priority, precision, limits
and interacting-mode behavior remain unqualified.

```text
PID(Loop,PV,Tieback,CV,0,Inhold,Readback);
```

The master operand still requires literal zero. Inhold accepts a stored scalar
BOOL tag, including bit/member/alias references, or literal zero to disable it.
S:FS, Boolean immediates and whole BOOL arrays are outside this profile. Readback
accepts scalar SINT/INT/DINT/REAL tags or literal zero, in the same units as CV.
The inputs cannot overlap the PID record. Their declared types are validated
even when inactive; numeric readback values are consumed only during inhold.
False PID calls do not sample either input. An unknown status faults a true call.

## Manual PV tracking

With PVT set and MO or SWM actually controlling the output, this simulator
copies scaled PV into SP before computing error and tracking I/BIAS. An unknown
old SP can therefore become known through tracking. Resulting SP must fit the
engineering range; an out-of-range tracked value faults and rolls back.

PVT in automatic mode retains SP. Software/hardware manual still use their
normal output sources and NOBC rules. On returning to auto, SP retains the last
tracked PV, I holds for the first sample and D is primed as before. Changing PV
after transfer resumes ordinary control. Inhold takes priority and suppresses
manual PVT while it controls CV.

This is an explicit manual-tracking interpretation of the represented v35 PVT
flag. Exact Logix tracking transitions, limits, startup and interaction with
other modes need native qualification; the flag's presence alone does not
establish that equivalence.

## Inhold and release

A true status overrides MO, SWM and control deadband. Readback promotes to
finite REAL, converts to the declared CV type and is copied directly to CV.
The assigned value must lie inside MINCV..MAXCV after conversion. Outside-span
readback faults; this is a bounded simulator rule. Integer CV uses the existing
ties-to-even conversion/range checks and bypasses automatic deadband zeroing.

OUT is the inverse-scaled percentage of assigned CV. With integration enabled,
seed I to `OUT-P-BIAS`; with no effective I, seed BIAS to `OUT-P`, including
when NOBC is set. This restart rule differs from ordinary manual NOBC handling.
EWD and output-limit flags clear, SO follows OUT, and DATA[14] mirrors assigned
CV. The direct copy preserves the converted readback; it is not replaced by a
round trip through inverse output scaling.

Held calls re-read the value and refresh PV/error baselines, without applying
derivative action or integral accumulation. The input status remains owned by
its producer; PID never clears it. Once status is false, the selected manual
mode or automatic solver resumes. The first automatic sample holds I and
suppresses D, as after manual transfer. Current automatic limits still apply
after release; an inconsistent readback/limit configuration can change output.

Inhold can initialize on the first true call or after Run/INI reset. The usual
PID configuration and PV/SP requirements still apply. Saved DATA does not seed
opaque native state. A later fault rolls back CV, SP, record values, hidden
restart/derivative/deadband state, task releases, time and trace together.

These priority, NOBC, range and transfer rules are chosen simulator behavior.
The v35 reference describes an analog module holding its physical output,
returning status/readback, then clearing status after receiving a matching CV.
That module behavior, its tolerance and communication timing remain separate.
An external device simulator can drive the explicit input tags and acknowledge
the result without making the PLC solver responsible for a physical module.

## Try the PID lab

The two loops have separate Inhold/Readback and IntInhold/IntReadback tags, plus
PVTracking/IntPVTracking Boolean aliases. Existing mode controls still apply.

1. Load **PID lab**, set Execute true and step: CV is 45.
2. Set Inhold true and Readback 75; step: CV is 75. Keep status true to follow
   subsequent readback changes.
3. Clear Inhold and step: the first auto CV remains 75; the next reaches 90.
4. Reload, set SoftwareManual and PVTracking true, Loop.SO 70 and Execute true.
   SP becomes PV 20 and CV becomes 70. Change PV while manual to follow SP.
5. Set FaultDivisor zero to exercise rollback; correct it to one before retrying.

The INT loop uses its raw output units for IntReadback: with IntInhold true,
IntReadback 20000 copies 20000 into RawCV, independent of the REAL loop.

Reference basis: installed v35 help 14709 (PVT and operands), 14713 (inhold
restart), 14737 (configuration) and 40012 (manual transfer). Published
[Logix general instructions](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)
corroborate the inhold handshake. The older
[PLC-5 reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1785-rm001_-en-p.pdf)
describes manual SP/PV tracking conceptually; it is not evidence of exact Logix
v35 implementation or firmware behavior.
