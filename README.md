# Studio5000Emulator

An experimental offline Logix v35 emulator with a browser UI and local EtherNet/IP research endpoint.

Explore supported ladder and Structured Text logic, drive inputs, inspect scan
traces, and test explicit messaging against a custom execution model. The app
and executable use the name **LogixLab**.

**Current app version: `26.1026.153720`.** Versions use the release timestamp
`YY.MMDD.HHmmss` in the release workstation's local time. The browser title,
page header, Windows tray and executable properties share this version.

**[Source-equivalent upload snapshots](docs/upload-value-snapshots.md) now save
and reopen a current-value ACD that goes Online.** Native SDK checks also pass
after rebuilding the source ACD through native Program imports. The rebuilt
demo upload passes across 1,137 verified requests, preserving all 14 tag values,
ten rungs and the installed correlation. The rebuilt two-Program profile passes
across 1,227 requests, preserving 29 roots, ten constants, arrays and 13 rungs.
All twelve demo and sixteen two-Program typed Online scalar reads pass.
This requires unchanged source and
a matching saved-download baseline; direct general Studio upload-save remains
unfinished.

The Windows [uploaded ACD rebuild](docs/uploaded-acd-rebuild.md) also saves
verified native Program packages and current values into a fresh source copy,
without a saved-download baseline. The rebuilt file is checked after native
reopen and requires a download before going Online.
A [single upload-to-ACD command](docs/upload-to-acd.md) now runs the native
upload, complete content checks and Offline rebuild in sequence, retaining
separate stage results and stopping on a failed or uncertain upload.

[Installed BOOL and DINT reads](docs/installed-memory-reads.md) work through the
native SDK while Online. Separate BOOL sessions verify `true` and `false`,
with Offline cleanup and no fault. The signed UserMemory request resolves to
an exact installed scalar value in current interpreter memory. General memory
and member/array monitoring remain unavailable through this native profile.
Each installed scalar read now shares its complete source/effect validation
with storage construction, avoiding repeated project-wide checks per Program.
Every subsequent read still validates the installation again.

[Program-scoped transfer storage](docs/scoped-download-tables.md) now preserves
separate Data Table identities, handles and values when Programs reuse numeric
IDs. Native download/save/reopen/Online and upload snapshot/save/reopen/Online
now pass for a two-Program profile, including current local values and
read-only BOOL, INT, DINT, REAL, LINT and array constants. General project
replacement remains unsupported.

Nested UDT constants and arrays of UDTs also preserve their complete source
values, packed bits and padding through native upload snapshot/save/reopen.

[Uploaded-content validation](docs/upload-content-validation.md) now verifies
all 14 offline tag values and both routines in the SDK's reconstructed demo.
Upload replaces a deliberately changed merge-baseline routine and preserves
all 45 current-value bytes and ten source rungs. Full uploaded ACD saving still
faults the tested SDK during `SaveAsAsync`, after those content checks pass.
After an earlier upload timeout, a fresh saved-project connection confirms
SDK recovery and a new upload succeeds across 980 verified requests with all
content checks passing. The timeout's cause remains unknown. Upload reliability
and uploaded ACD persistence remain the transfer priorities.
The expanded check also produces a native Program L5X package with both
routines, verifies its settings and all ten rungs, and completes normal SDK
cleanup across 983 requests.
The optional [uploaded tag definition check](docs/upload-tag-definitions.md)
also exports every controller root and independently checks declarations,
access/constant flags and current values. A requested check is revalidated
before rebuilding an Offline ACD.
A matching saved-download target can also receive a checked Online/Offline
[baseline preflight](docs/upload-tag-definitions.md#ordinary-upload-with-a-checked-online-baseline)
before ordinary upload, without saving or extending its timeout.
The checked offline rebuild command imports those packages, saves and reopens
a new ACD and verifies values, logic and scheduling. It uses the original
Controller metadata; direct upload-save remains unfinished. Program import
clears download identity, so the rebuilt file requires a download.

The SDK probe can also [check the complete saved downloaded project](docs/download-content-validation.md)
with `--verify-downloaded-content`. Values, logic, Program settings, Task
schedules and explicit UDT schemas are verified after native save/reopen.

[Installed Table identities](docs/installed-table-identities.md) now preserve
the separate Symbol and Data Table IDs produced by native Program import.
The committed catalogs, descriptors and value reads share the verified links.
Both rebuilt profiles now complete native download/save/reopen/Online and the
next upload snapshot/save/reopen/Online, with Offline cleanup and no SDK fault.

[Installed Symbol Control readback](docs/installed-symbol-control.md) now returns
the original opaque control word from validated committed download headers.
Source or effect changes revoke this view; the bits do not change simulator
flags or permissions. Native tag-operand upload is checked separately.

[TIMER/COUNTER reads](docs/builtin-template-reads.md) now use exact source-checked
definitions retained by a committed download. Discovery, structured reads and
Data Tables share current PRE, ACC and status-bit values. Packed BOOL control
readback also preserves the distinction between logical bits and storage words.

[Scoped Routine reference Symbols](docs/routine-reference-symbols.md) now expose
the original `Routine:<name>` identities under each Program. Their backed
references match the corresponding Routine headers and remain separate from
tag values and Data Tables. This closes a source-backed upload discovery gap;
native upload acceptance is checked separately. The first native trial reads
Routine data before exposing a further Label-discovery gap.

[Routine Label discovery](docs/routine-label-discovery.md) now preserves the
Program/Routine/Label path and returns an empty catalog only for complete,
unchanged source without `LBL` or `JMP` instructions. Nonempty Label inventories
remain unsupported.

[Downloaded Routine reads](docs/downloaded-routine-read.md) now support the
observed empty `(1, 4)` component for source-checked, unprotected Standard RLL
routines. The source view adds the observed `TargetClass` field while retaining
the original rung XML and compressed auxiliary bytes.

**[Native SDK upload succeeds for the two-routine conveyor demo](docs/routine-upload.md)**
across **981 verified requests**, reading all ten rungs and 30 IOI operands.
Download/save/reopen/Go Online also succeeds. Original Symbol Control metadata
clears the two-BOOL XIC/OTE fixture's reconstruction failure; source-checked
TIMER/COUNTER definitions close the demo's remaining tag-discovery gap.
A second upload verifies all 33 current-value bytes across five deliberately
changed tags; those temporary values are restored afterward. Saving an
uploaded ACD has since been tested and faults as described above.

[Packed BOOL-array readback](docs/bool-array-download.md#packed-table-readback)
keeps Symbol dimensions in logical bits and Data Table dimensions in 32-bit
storage words. Supported arrays now appear in discovery and expose their current
packed values through read-only table services. Individual symbolic bit access
retains its existing behavior.

For the owned routine-free BOOL[64] fixture, native SDK download/save/reopen/Go
Online completes across 424 verified requests and `UploadAsync` across 968
on version `26.1024.111516`.
The upload trace includes the packed table read, whose eight bytes match every
saved bit. Independent CIP checks verify all 64 bits and the linked descriptors.
Saving and reopening an uploaded ACD remains unverified.

The [appliance manager](docs/vmware-appliance.md#stop-restart-and-update) keeps
the PLC running through temporary webpage poll failures. It powers off only
for an explicit, instance-bound shutdown request. Unexpected tunnel loss leaves
the guest running so the launcher can reconnect.

[Packed BOOL-array downloads](docs/bool-array-download.md) now accept the
source-checked one-dimensional storage profile. The owned BOOL[64] fixture
completes native SDK download/save/reopen/Go Online across 433 verified requests;
independent CIP reads match every saved bit. Whole-array symbolic wire operations
remain outside this profile.

[Empty ladder routine downloads](docs/empty-routine-download.md) retain the
native source and zero-count attachment without inventing compiled code or a
NOP. This requires an explicitly empty original source routine. Missing or
protected source declarations remain blocked.
Both mixed and single-empty-routine fixtures complete native SDK
download/save/reopen/Go Online across 433 verified requests each, with complete
retained traces and actual Offline cleanup. Source/model preservation passes
without an SDK fault. Those earlier upload trials failed at the first Routine
metadata reply, including for the single empty routine. The newer scoped
reference work reaches Routine-data retrieval.

Saved-download imports recognize the checked [Program Routine headers](docs/routine-types.md)
and named Controller numeric [metadata qualifiers](docs/native-metadata-values.md).
During download, Studio may update `ControllerSerialNumber` to the endpoint's
actual Identity. The original catalog stays immutable, and the committed view
retains that serial. Other metadata replacements stay checked against source.

An owned saved ACD completes Offline save/reopen/L5X export, preserving both
routines' parsed logic and all 14 tags' saved values. Reimporting it and performing
another download, save, reopen and Go Online succeeds across 414 verified requests.
The earlier routine-upload trial failed before data retrieval after 349 verified
requests; newer upload progress is described above.

Studio's nested UDT dependency lists are validated when checking
whether an ordinary source project has no Energy objects. Every declared
dependency must match a nested member type; opaque, incomplete or foreign
dependency graphs remain unavailable.

The app accepts explicitly named packed-bit hosts in the
[UDT wire catalog](docs/native-template-snapshots.md). A declared hidden scalar
SINT with valid BIT targets can use an ordinary identifier. The hidden storage,
overlap, reserved-bit and member-access checks remain in place.
Downloads can also omit a routine-data batch when the complete original source
and prepared image both establish that there are no routines.
The owned empty-Program fixture completes SDK download/save/reopen/Online across
425 verified requests. Complete symbolic and Data Table reads match 100 UDT
value bytes. With the dependency check, SDK `UploadAsync` also completes across
975 verified requests and reads those same three UDT tables. This profile has
no routines; saving and reopening an uploaded ACD remains unverified.

[Source-defined structure downloads](docs/download-image.md#source-matched-initial-values)
support nested UDTs, numeric arrays and UDT/TIMER/COUNTER arrays, checking complete
saved values and explicit source layouts before committing a separate model.

Optional [compressed transfer recording](docs/transfer-trace-recording.md)
retains complete native upload/download traces beyond the diagnostic ring's
capacity, with gaps and interrupted recordings reported explicitly.
The nested-UDT empty-Program upload retains all 3,466 diagnostic events and an
identical offline transfer replay. Current bounded Routine upload acceptance
is described above; arbitrary projects remain unfinished.

Committed Controller metadata and [signed Routine readback](docs/downloaded-routine-read.md)
retain the exact accepted download values and source/component bytes. Earlier
independent readback verified both routines and all 1,671 metadata records.
Changed source, logic or catalogs revoke the corresponding reads.

The [saved-download workflow](docs/development.md#saved-download-reconnection) can
save a new ACD after a source-equivalent download, close it, reopen it and verify
Go Online. The native SDK completes that sequence across 433 verified requests;
a separate SDK process reopens the saved ACD and goes Online across 74.
Both confirm Offline cleanup, preserve original ACD bytes and report no SDK fault.
The saved ACD retains the new download identity; the emulator installation
remains memory-only. Resetting or reloading it revokes that correlation.

Program-mode routine replacement now retains the committed download identity
while reporting the changed runtime logic separately. A native SDK test
completes download, Program-mode rung import and Offline/Online reconnection
across 547 verified requests. General project replacement remains unsupported.
The routine-containing demo now completes existing-project SDK upload with
both Routine source streams. Uploaded ACD saving still faults the tested SDK.

This revision passes 398 affected checks and 372 Python syntax checks.
The full milestone runs 2,163 Windows tests, with two platform checks skipped.
Small revisions use affected checks.

**Reliable general upload and uploaded ACD saving, replacement with another project, general SDK tag monitoring and the complete
Test/Untest/Assemble edit lifecycle remain unfinished.** Studio 5000 GUI
monitoring remains unverified. Supported instructions have bounded software
models; this project does not establish native controller equivalence.

See [compatibility checkpoints](docs/connectivity-history.md) for earlier
revision results and the [roadmap](docs/roadmap.md) for remaining work.
Application development is maintained on `main`.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Current Support](#current-support)
- [External Device Simulation](#external-device-simulation)
- [Development](#development)
- [Roadmap](#roadmap)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

Studio5000Emulator is being built toward a custom Logix emulator, starting with
explicitly supported instructions and data types. It combines deterministic
local scans, a logic monitor, tag editing, coverage reports and protocol tracing.
Unsupported features are reported before execution where possible.

L5X execution uses Python's standard library. ACD import is optional and converts
a private copy through separately installed native tooling. The execution engine
runs independently after import and does not depend on FactoryTalk Logix Echo.

## Install

### Dependencies

- Windows and Python 3.13 for the tested source workflow.
- Optional ACD import: compatible Studio 5000/Logix Designer SDK tooling and an
  `l5xgit` converter. Configure it in **Import settings**, with
  `LOGIXLAB_CONVERTER`, or by placing `l5xgit` on `PATH`.
- Optional executable build: PyInstaller.
- Optional independent protocol probes: `pycomm3`.

```powershell
git clone --branch main https://github.com/votecoffee/Studio5000Emulator.git
cd Studio5000Emulator
.\INSTALL-AND-RUN.cmd
```

On Windows, double-click **INSTALL-AND-RUN.cmd** in the project root, or run it
as above. It finds Python 3.13 (installing it for the current user through
Windows Package Manager if needed), creates an ignored `.venv`, installs
PyInstaller there, builds the current source and opens LogixLab. Missing
dependencies require internet access. If `winget` is unavailable, install
Python 3.13 with pip and the Python launcher first.

Use `INSTALL-AND-RUN.cmd -InstallOnly` to prepare the executable without
launching a session. After setup, `START.cmd` opens the existing build;
rerun `INSTALL-AND-RUN.cmd` after updating the source to rebuild it.
ACD conversion and the optional VMware appliance need their separate setup.

No additional Python packages are needed to run L5X projects or bundled demos.
To run directly from source, use `py -3.13 -X utf8 source/launch.py`.
See [development guidance](docs/development.md) for optional tooling, including
an offline CIP capture inspector with bounded signed-envelope decoding for
connection research. Its format-4 reports preserve nested object paths and
requested attribute IDs while keeping symbols, values and raw bytes private by
default. These analysis features do not establish native Studio Go Online.
An optional [native SDK acceptance probe](docs/development.md#native-sdk-acceptance-probe)
records connection, tag-read, upload, download-preparation and online-edit attempts against the running emulator
using private ACD copies and reports.
The Linux appliance also exposes a documented subset of
[Ethernet diagnostic counters](docs/ethernet-counters.md) from its virtual NIC
driver, with unavailable diagnostic fields identified in the API.
Read-only [native inventory discovery](docs/native-inventory.md) now covers
source-checked empty I/O, alarm and Add-On Instruction catalogs.
[Data Logging and native policy diagnostics](docs/native-session-policy.md)
include acknowledgements that retain an existing source Timeline UID.
[Nested I/O Connection discovery](docs/io-connection-discovery.md) preserves
parent scope, and [native coordination](docs/programming-coordination.md)
provides an exclusive session lease and a source-backed Local link-address read.

[Source-equivalent download](docs/download-image.md#source-equivalent-installation)
validates the prepared object graph, typed values, settings and routine source
before replacing the loaded demo's interpreter state. Native compiled code stays
opaque. General replacement with another project remains unsupported.

[Remote Run/Program control](docs/controller-mode.md) starts and stops actual
scans, and local controls report the same state through the native endpoint.
[Run-entry initialization](docs/run-entry.md) rearms `S:FS` and performs bounded
prescan once per transition. Historical transfer checkpoints and their limits
are kept in the [connectivity history](docs/connectivity-history.md).

## Usage

Choose a bundled demo or open a complete L5X export. Check **Coverage**, then use
**Step scan** or **Run**. Edit inputs in **Tag Watch** and inspect the logic trace.
**Program** stops continuous scans and preserves the current values. The same
state is used by native Remote Run/Program requests. Scanning runs in the app
and continues with the webpage closed.
Entering Run performs modeled prescan, which can reset non-retentive values and
execute enabled AOI Prescan routines. Repeated Run requests do not repeat it.
For supported Studio edits, select **Connectivity → Allow supported Studio edits**
before connecting. This profile replaces an existing standard RLL routine in
**Program** mode. Changes stay in memory; reload the original project to restore
its logic. Native SDK import is tested; the Studio GUI edit workflow is unverified.
The browser title and header show the running app's full timestamp version;
the header also shows the PLC endpoint IP. On Windows,
its tray icon offers
**Open app** and **Quit LogixLab**; hover over it to see the version and session
address. The icon may appear under the taskbar's hidden-icons arrow.

Use **End session** or **Quit LogixLab** to stop the app and its protocol endpoint.
Closing a browser tab leaves the app running; reopen it from the tray. `--no-tray`
disables the icon for headless runs.

Original project files are preserved. Settings and imported copies normally live
under `%LOCALAPPDATA%\LogixLab`; `--data-dir` selects another private directory.

For a separate PLC IP while Linx retains the host's port 44818, use the optional
[VMware host-only appliance](docs/vmware-appliance.md). After preparation,
`START-VM.cmd` starts it with a localhost browser tunnel and Windows tray controls.
On Windows, its SSH tunnel and helper commands run without console windows.
The appliance answers ICMP ping on its guest IP for IP-scanner discovery. See
[ping and IP scanners](docs/vmware-appliance.md#ping-and-ip-scanners) for the
network to scan. The executable, tray, browser tab and webpage use the PLC
simulator icon bundled with the app.

### CLI

Start a demo with checkout-local session storage:

```powershell
py -3.13 -X utf8 source/launch.py --sample TextLab --data-dir .local/session
```

Generate an offline coverage report:

```powershell
py -3.13 -X utf8 source/launch.py --report source/samples/TextLab.L5X
```

Start the Network Lab's read-only EtherNet/IP endpoint:

```powershell
py -3.13 -X utf8 source/launch.py --sample NetworkLab --eip-port 44818 --eip-profile logix-v35-l85e --data-dir .local/network-session
```

The HTTP UI binds to `127.0.0.1`. The protocol endpoint defaults to that address;
**Bind IP** or `--eip-bind` selects another IPv4 address belonging to this PC.
See [Linx coexistence](docs/connectivity.md#linx-coexistence-and-addresses) if
another application owns port 44818. Protocol access starts disabled unless
requested. Tag writes require **Allow tag writes** or
`--eip-writes`. Use the **Connectivity** tab to start/stop the endpoint and export
its trace. See [connectivity documentation](docs/connectivity.md) for the supported
services, identity profiles and remaining Studio handshake work.
Unsupported attribute reads now show their object, field IDs and read counts in
Connectivity, with the full bounded summary in the exported trace.
Linux endpoints can restart on the same IP and port after closing connected
clients; a conflicting active listener still prevents startup.

### Build an executable

```powershell
py -3.13 -m pip install pyinstaller
powershell -NoProfile -File source/build.ps1
.\dist\LogixLab.exe
```

The build places the executable under `dist/`. `START.cmd` launches that build.
Source-authored L5X demos are bundled; generated ACD files are kept local.

## Current Support

| Area | Available behavior |
| --- | --- |
| Projects | v35 L5X import; optional native ACD-to-L5X conversion on a copy |
| Execution | Supported RLL/ST forms, routine calls, AOIs and deterministic scans |
| Inspection | Coverage checks, tag watch, traces, snapshots and routine harnesses |
| EtherNet/IP | Unicast and Linux broadcast discovery, sessions, Class 3 messaging and atomic tag services |
| Connected reply sizes | Standard/Large Forward Open replies use their negotiated size up to 4,000 bytes, including sequence and signed-message overhead |
| Atomic transfers | Reads/writes, fragmented transfers and integer OR/AND mask updates |
| Structured transfers | Aligned numeric UDTs, explicit user LEN/DATA strings, packed Boolean flags and fragmented reads/writes |
| Native compatibility | Experimental anonymous metadata/tag reads and bounded Run/Program control; fresh keys, checked single/batch MACs and counters; peer authentication unverified |
| Offline protocol analysis | `0x36`/`0x37` singles, `0x38` batches, observed `0x39` transfers and `0x3A` read chunks with bounded detached assembly; decoded captures never execute |
| ACD correlation | Source-bound Change Log identifiers and TagInfo symbol IDs; controller/program instance paths use imported IDs; native SDK passes project identity comparison for the tested demo |
| Upload discovery | Existing-project SDK upload verified for bounded fixtures; a value snapshot retains Online correlation using a matching saved baseline. An Offline Program rebuild saves/reopens without that baseline and requires a download before Online. Direct general uploaded-project saving and arbitrary projects remain unfinished |
| Download preparation | Three source-checked batches, task/controller/setup metadata, Map and Change Log headers, and bounded installation with exact scalar, numeric-array, supported structure and structure-array values; general project replacement remains unsupported |
| Routine metadata | Original scoped Type/instance values, opaque source metadata, live header references and guarded ordinary RLL edit/pause/unsigned state; compiled logic and native signature verification remain unavailable |
| AOI metadata | Original definition and scoped Routine IDs, clean model state, explicit revision/vendor headers and available Routine descriptions; compiled definitions and native AOI edits remain unavailable |
| Native status | Source-checked empty I/O force/LED and SFC force status; module connections, SFC forcing and force writes remain unsupported |
| PLC message mapping | Source-checked empty PCCC mapping descriptors; configured mappings and PCCC commands remain unsupported |
| Time Sync | Source-backed PTP enable/priorities, read-only local UTC time and explicit unsynchronized/empty-port state; PTP networking remains unsupported |
| Catalog refresh | Controller class revision/inventory and source-bound comparison tokens |
| Identity revisions | Read-only virtual hardware revision and profile firmware build, alongside source-based major/minor revision |
| Controller configuration | Source-backed legacy SecurityCode, name/description and read-only pass-through configuration; limited Metadata Definition discovery; security enforcement and pass-through routing remain unsupported |
| Change detection | Explicit source mask plus a simulator-owned Audit Value; SDK mode/import updates and upload field reads verified on `.144`; State Detection signatures remain unsupported |
| Get System Value | Ladder/ST `GSV` for Controller AuditValue/ChangesToDetect into LINT or two DINTs; native-saved fixture and live scan/CIP agreement verified on `.145`; other objects/attributes and SSV remain unsupported |
| Software device metadata | Read-only location/locale and empty trusted-slot/operator state, explicitly identified as emulator defaults |
| File Manager | Read-only class discovery; reports zero emulated storage devices |
| Network metadata | Read-only CIP port/node addresses, IPv4 status/configuration, verified Linux DHCP/DNS flags and actual adapter MAC |
| Device locator | Network-triggered blinking webpage banner with timed expiry and cancellation |
| Studio online | Native SDK Go Online, bidirectional Run/Program control, Go Offline, installed scalar BOOL/DINT reads and bounded source-equivalent transfers verified for the demo; Studio GUI acceptance and general tag/rung monitoring remain unverified |
| Supported routine edits | Opt-in Program-mode Standard RLL replacement; consecutive SDK imports, replacement across routines and reconnection using the same updated project verified; edited L5X working-copy export |

Coverage depends on the actual project and execution scope. Full task scheduling,
motion, physical I/O, CIP Safety, FBD/SFC and broad native runtime parity remain
outside the current model. Unknown data and unsupported forms are not silently
replaced with assumed behavior.

Read the [execution model](docs/execution-model.md) before interpreting scan
results, and the [protocol contract](docs/connectivity.md) before using clients.

### External Device Simulation

The **Device I/O** tab enables queued external input writes. External monitors
read consistent cached snapshots without taking the scan lock. A separate MQTT
bridge distributes tag values and accepts atomic input batches from robot,
servo and other device simulators. Writes apply between scans, with scoped
tokens, expiry, duplicate detection and queued/applied/rejected acknowledgements.

See [setup, MQTT topics and the HTTP API](docs/device-io.md). The MQTT dependency
is optional; the app runtime remains standard-library-only. OPC UA/DDS adapters
and a SQL historian are future extensions of the same interface.

## Development

The code, public L5X fixtures, tests and browser assets are under `source/`.
Shared technical documentation is under `docs/`. Build output goes to `dist/`.
See the [community project assessment](docs/community-projects.md) for reusable
components, licensing and conversion-validation results.

Run the behavioral suite from the repository root:

```powershell
Set-Location source
py -3.13 -X utf8 -m unittest discover -s tests -v
```

Store machine-specific notes, private PLC files, settings, captures and test
receipts in ignored `.local/` storage. Generated builds and local reports are
excluded from Git. See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and repository
conventions.

## Roadmap

- Complete uploaded ACD save/reopen and broader project replacement before the full online-edit lifecycle.
- Expand supported instructions, data types and execution semantics.
- Expand packed BOOL-array coverage, built-in STRING transfers, predefined structures and controller metadata.
- Extend the verified native SDK connection to Studio GUI acceptance.
- Resolve native tag addresses and demonstrate SDK/Studio tag and rung monitoring.
- Demonstrate online monitoring before advertising Studio Go Online support.
- Add a host-only networking backend independent of VMware, evaluating free
  container and virtual-machine tooling. See the [milestones and backend comparison](docs/roadmap.md).

## Maintainers

[@votecoffee](https://github.com/votecoffee)

## Contributing

Questions, bug reports and pull requests are welcome through
[GitHub Issues](https://github.com/votecoffee/Studio5000Emulator/issues) and
[pull requests](https://github.com/votecoffee/Studio5000Emulator/pulls).
Please read [CONTRIBUTING.md](CONTRIBUTING.md), use minimal synthetic fixtures,
and include relevant verification with changes.

## License

[MIT](LICENSE) © 2026 votecoffee.
