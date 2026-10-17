# LogixLab: Studio 5000 connectivity branch

Experimental build **0.6.0-connectivity.2**, October 17, 2026.

This branch adds a local EtherNet/IP target to the existing custom emulator.
It uses LogixLab's execution engine and does not require FactoryTalk Logix Echo.
**Studio 5000 Go Online is not implemented or verified at this milestone.**

## Branch and baseline

This folder is a local Git repository. `main` preserves the v0.5 source baseline;
development is on `feature/studio5000-connectivity`. No remote is configured.
`BASELINE.json` records the original release manifest and source hashes.
The separate v0.5 release folder and ZIP remain unchanged.

## Run

1. Launch `LogixLab.exe` (Python is not required), or run `source/run-from-source.cmd`.
2. Choose **Text lab**, or import an ACD/full L5X.
3. Open **Connectivity**. Choose an identity profile and port, then click **Start endpoint**.
4. The default address is `127.0.0.1:44818`, with a modeled backplane route of
   port 1, slot 0. Both TCP and UDP bind only to the local computer.
5. Tag reads are enabled. **Allow tag writes** is an explicit option selected
   before starting. Network writes change the same memory shown by Tag Watch.
6. Use Step/Run in LogixLab to execute scans. Refresh values updates the view;
   while the endpoint is active, paused views also refresh every two seconds.
7. Export the protocol trace to inspect unsupported client requests. Stop endpoint
   closes its listeners and client connections. End session closes the app.

If the selected port is already occupied, the app reports a bind error. A different
port works with configurable test clients. No existing Rockwell service, adapter,
firewall setting or network route is changed by this app.

Command-line source example:

```powershell
cd source
py -3.13 -X utf8 launch.py --sample TextLab --eip-port 44818
```

Add `--eip-writes` to opt into atomic tag writes. Without `--eip-port`, connectivity
starts disabled. The UI starts/stops the endpoint without restarting the app.
Add `--eip-profile logix-v35-l85e` for the experimental compatibility identity.

## Implemented protocol surface

- TCP/UDP ListIdentity, ListServices and ListInterfaces; session registration and
  unregistration; stream framing handles split and coalesced TCP packets.
- SendRRData, local slot-0 Unconnected Send, and bounded Multiple Service Packets.
- Identity object Get Attributes All, Single and List; per-attribute error status;
  Message Router class inventory; controller-name query (class `0x64`).
- Standard/Large Forward Open and Forward Close for bounded point-to-point Class 3
  explicit messaging; connected SendUnitData and sequence/replay checks.
- Symbolic paths and synthetic symbol-instance addressing. Symbol enumeration
  supports attributes 1 (name), 2 (type) and 8 (dimensions), with pagination.
- Atomic BOOL, SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT and REAL reads/writes;
  atomic arrays, supported atomic structure members, program-scoped tags and aliases.
- Fragmented atomic reads; unknown values return errors instead of invented zeros.
- Read/Write, Read Only, None, constants, aliases, hidden members and AOI-local
  restrictions are enforced. Safety-class tags are not exposed.

The default identity is **LogixLab v35 research target**, with experimental
vendor value `0xFFFF`. The optional **Experimental 1756-L85E v35** profile advertises
vendor 1, device type 14 and product code 168. It requires a loaded `1756-L85E`
v35 source and takes the minor revision from that source. Text Lab advertises
35.11. Both profiles use the research serial `4C4C0001`; neither establishes
native controller equivalence. Incompatible imports are rejected while this
profile is active, preserving the previous project. Compatible imports update
the identity and invalidate existing sessions.

FactoryTalk Linx native browsing remains unverified. Protocol discovery and client
initialization do not prove that Studio recognizes a supported controller.

The endpoint has at most 16 TCP clients, 8 Class 3 connections per session,
32 KiB request payloads, 4 levels of nested messages and a 128-dispatch budget.
Replies are bounded to 480 CIP bytes and the negotiated connection size.
Reset, project replacement and scope changes invalidate old registered sessions;
clients must reconnect. Disconnects discard session connection state.

The trace retains the last 1,000 events. Each request/reply hex sample is limited
to 1,024 bytes and has a truncation flag. Events include peer, session, path,
service, status and errors. Unsupported-request summaries retain a bounded set
of keys. Trace export contains local project tag names and request data.

Individual multi-element writes validate their full payload and roll back on
failure. Multiple Service Packet children are independent operations; a later
child failure does not roll back earlier successful children. An oversized
combined response can also fail after earlier children executed.

## Pending Studio connectivity work

This endpoint does **not** yet implement Studio project correlation, compiled
project transfer, upload/download, online edits, native debugger services, native
controller status/mode changes, template/UDT layout services, whole-structure or
STRING transfers, packed BOOL arrays, fragmented writes, or physical I/O/CIP Safety.
Atomic STRING members such as `Message.LEN` and `Message.DATA[0]` can be addressed.
Runtime semantics retain all v0.5 software-model boundaries in `README-v0.5.txt`.

The next native milestone is to make the loopback target visible in FactoryTalk
Linx, repeat the SDK connection attempt, and implement the first observed missing
handshake. Full online ladder monitoring must be demonstrated in Studio before
being advertised as supported.

## Native SDK probe result

This build includes a small diagnostic at `source/research/NativeStudioProbe`.
It uses the installed official Logix Designer SDK client 2.1.974 against a private
copy of the bundled TextLab ACD. It opens the ACD, sets a loopback communications
path and attempts either ReadControllerMode or GoOnline. It never downloads,
saves, changes controller mode or writes tags. SDK binaries are not bundled.

Both actual probes opened the project and accepted
`Ethernet\127.0.0.1\Backplane\0`, then failed with
`RxE_COMM_DTLERROR - Failed to call Linx communication software.`
The GoOnline probe's before/after endpoint traces contain the same single startup
event, with no client connections, discovery or CIP traffic. The ACD SHA-256 was
unchanged. See `validation/native-connection-result.json`, its paired traces and
the native receipts/logs. This is a Linx communication failure before any emulator
handshake was observed; it does not establish whether the current protocol surface
would satisfy Studio.

To repeat on a machine with the SDK available:

1. Start Text Lab with the experimental L85E profile on port 44818.
2. In FactoryTalk Linx, configure and verify **only** the local `127.0.0.1` target.
   The SDK guide requires the target to be configured and visible in Linx.
3. Export a protocol trace, run the probe below, then export another trace.
4. Compare counts and requests. A successful identity query is still short of a
   successful GoOnline/correlation result. Record any native dialog or error.

```powershell
dotnet run --project source/research/NativeStudioProbe -- --acd source/samples/TextLab.ACD --comm-path 'Ethernet\127.0.0.1\Backplane\0' --operation go-online --out validation/native-recheck.json
```

Use `--operation mode` for the smaller mode query. The probe accepts only loopback
slot-0 paths and retains the private ACD copy beside its receipt. Build/package
output excludes SDK build folders and diagnostic private copies. FactoryTalk Linx
configuration has not been changed by LogixLab.

## Validation and development

The behavioral suite has **237 passing tests**, including 33 existing protocol
tests and 13 identity/profile tests.
The independent `pycomm3` 1.2.16 client also verifies discovery, atomic-symbol
enumeration, Large Forward Open, connected reads/writes and Forward Close. A scan
uses a CIP-written input to update the custom engine's AOI output.
An additional `pycomm3.LogixDriver` probe initializes both profiles with
`init_tags=False`, reads the source controller name and identity, queries an
attribute list and closes its Class 3 connection. Its full native tag upload is
deliberately rejected because native address attributes are not implemented.
The raw trace and unsupported-request count record this rejection.
These checks establish bounded protocol interoperability, not Studio Go Online
or native runtime equivalence. See `validation/` for delivery receipts.
The EXE build succeeded. Automatic approval review rejected its shell launch
without a detailed reason, so this milestone's UI/runtime checks use the same
source directly; packaged-EXE execution remains unverified.

```powershell
cd source
py -3.13 -X utf8 -m unittest discover -s tests -v
py -3.13 -X utf8 tests/interop_pycomm3.py --out ..\validation\interop.json
py -3.13 -X utf8 tests/interop_logix_identity.py --out ..\validation\identity-interop.json
```

The client probes require the optional test-only `pycomm3` package; it is not an
application dependency. By default it creates an isolated in-process target.
To probe a running Text Lab endpoint read-only:

```powershell
py -3.13 -X utf8 tests/interop_pycomm3.py --target 127.0.0.1:44818 --out ..\validation\live-interop.json
```

The probe is restricted to loopback. Add `--write` only with endpoint writes enabled;
the probe restores its changed Step input. Build with `source/build.ps1`.

Protocol references: [Rockwell 1756-PM020 data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
[ODVA CIP network overview](https://www.odva.org/wp-content/uploads/2020/06/PUB00123R1_Common-Industrial_Protocol_and_Family_of_CIP_Networks.pdf),
and [pycomm3 client implementation](https://github.com/ottowayi/pycomm3).
Native setup reference: [Rockwell Logix Designer SDK guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf).
L85E product identity reference: [Rockwell 1756 declaration of conformity](https://literature.rockwellautomation.com/idc/groups/literature/documents/ct/1756-ct119_-en-e.pdf).
No Rockwell binaries, firmware, EDS files or copied vendor SDK source are included.
