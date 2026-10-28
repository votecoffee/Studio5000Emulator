# Native scalar tag writes

Version `26.1028.184545` adds an explicit **Allow Studio tag writes** control in
the connectivity panel. Enable it before connecting the native client. The
setting is off at startup and changes only while native clients are disconnected
and the controller is in Program mode. General EtherNet/IP writes remain a
separate setting.

## Supported contract

The observed signed Data Table service `0x50` accepts a numeric installed Table
instance, optionally beneath its original Program instance. This profile
requires the zero selector, the observed zero marker, an exact byte count and a
complete scalar value. BOOL, SINT, INT, DINT, LINT and REAL are supported.

Each write verifies the committed source, namespace, Table/Symbol linkage,
declaration, current storage and external write access. It requires stopped
Program mode and no active programming transfer. Constants, aliases, arrays,
structures, partial values, nonzero selectors/markers and invalid values remain
denied. BOOL data must be canonical and REAL data finite. Unsigned requests do
not acquire this native write path. Values enter the same interpreter memory and
device-monitoring snapshot path as ordinary model tag writes. No force, source,
logic, mode, history or arbitrary-memory operation is supplied by this service.

## Native checkpoint

A private six-type SDK probe first receives normal permission denials on the
preceding app version, preserving all values and confirming Offline cleanup
without an SDK fault. Its requests establish the exact Table write framing;
success responses and effects are checked separately on this version.

With access enabled, eight SDK setter/readback/restore round trips pass across
BOOL, SINT, INT, DINT, LINT and REAL, including Program-local INT and LINT tags.
The same eight round trips pass after an accepted rung replacement and native
reconnection. Both sessions confirm actual Offline cleanup without an SDK fault.
Each changed value is read back through the typed Online getter, then restored
through the native setter and checked again. Source files remain unchanged.

The expanded fixture also passes download/save/reopen/Online across
439 verified requests and upload snapshot/save/reopen/Online across
1232. All 32 roots, 140 value bytes, four routines, thirteen rungs,
Program packages and controller tag definitions verify, including 24 typed
scalar checks. The supported edit/reconnection passes across
185 requests.

Independent signed peers check malformed/partial writes, constants, arrays,
structures, unknown Tables, noncanonical BOOL and nonfinite REAL data before and
after the edit. Rejections preserve the model. Fresh response MACs are checked;
recorded exchanges are not reauthenticated and peer identity is unverified.
No scans execute during these tests. This verifies the bounded SDK profile;
Studio GUI tag editing, Run-mode native writes and complete edited-project
upload remain unverified or unsupported.
