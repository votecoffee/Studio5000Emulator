# Studio5000Emulator

An experimental offline Logix v35 emulator with a browser UI and local EtherNet/IP research endpoint.

Explore supported ladder and Structured Text logic, drive inputs, inspect scan
traces, and test explicit messaging against a custom execution model. The app
and executable use the name **LogixLab**.

**Status: experimental. The native v35 SDK can Go Online to the tested demo in
anonymous compatibility mode, read its connected state, request Remote Run or
Program and read the emulator's actual mode, then Go Offline.** Version `.74`
ties native mode requests and webpage controls to the same scan worker.
Version `.75` adds transactional Run-entry prescan and first-scan initialization.
Version `.76` adds [member inspection of temporary native type definitions](docs/template-layout-inspection.md)
as groundwork for validating storage layouts; encoded offsets and trailers remain opaque.
Native SDK tag reads still fail
online address discovery. Native upload/download and online edits are unsupported;
tested attempts fail. Studio
5000 GUI monitoring remains unverified.
Supported instructions have bounded software models; this project
does not establish native controller equivalence.

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
records connection, tag-read, upload and download-preparation attempts against the running emulator
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
Version `.63` adds a public SDK download-preparation probe and checks that
its TCP clients, lease and scan inhibit clear after cleanup. The actual native
programming service remains unfinished.
Version `.64` adds [owner-scoped download preparation](docs/programming-preparation.md)
and an acknowledgement that retains disabled redundancy from source. The SDK
reached library-object creation in that revision.
Version `.65` adds [temporary library descriptors and signed transfer envelopes](docs/library-staging.md).
The SDK reached Metadata Definition creation in that revision.
Version `.66` adds [temporary metadata definitions](docs/metadata-staging.md).
The SDK reached a metadata-value write in that revision.
Version `.67` adds [typed values for staged definitions](docs/metadata-values.md).
The SDK reached Resilient Transport setup in that revision.
Version `.68` adds [temporary Resilient Transport setup and cleanup](docs/resilient-transport.md).
The SDK reached segmented device-data transport in that revision.
Version `.69` adds [bounded temporary device-transfer fragments](docs/transport-fragments.md).
The normal-source SDK attempt stages a complete device payload and reaches a
denied device-operation request (`0x06`). Active values, library-data writes and
project commit remain unsupported.
Version `.70` adds [structural inspection of compressed device batches](docs/device-payload-inspection.md).
The SDK's staged payload decodes into request records with parent scopes preserved;
batch execution and project commit remain unsupported.
Version `.71` adds [temporary native Template models](docs/template-staging.md).
The SDK batch's 242 Templates pass descriptor and contiguous-write validation;
definitions remain opaque and the remaining batch operations are unsupported.
Version `.72` adds [temporary Diagnostics Message models](docs/diagnostic-staging.md).
Together with Templates, these model 863 of 904 records in the tested download
batch. The remaining 41 records and complete batch execution are unsupported.
Version `.73` adds [temporary object graphs and reference checks](docs/object-staging.md).
All 904 records in the tested batch now have bounded temporary models. Compiled
definitions, device processing and active-project commit remain unfinished.
Version `.74` adds [shared Remote Run/Program control](docs/controller-mode.md).
Native requests start/stop actual scans, and local controls report back through
the native identity. Closing the browser or going offline leaves Run active.
Version `.75` adds [Run-entry initialization](docs/run-entry.md), rearming
`S:FS` and applying bounded prescan rules once per transition. Initialization
failures restore prior values and leave the controller faulted and stopped.
Version `.62` adds [software clock descriptions](docs/clock-descriptions.md),
including the actual app version in native Time Sync inventory reads.
Version `.61` adds [Run Mode Inhibit](docs/run-mode-inhibit.md), with an owning
session's temporary scan guard and cleanup. Its then-current download boundary
was Controller service `0x60`, extended by `.64`.
Full native upload/download and online tag monitoring remain unfinished.
The 1,002-test suite passes on Windows and Linux with expected platform skips.
The rebuilt `.75` runtime passes 291 protocol checks and a 17-step native mode
probe covering repeated Run-entry initialization and bidirectional mode readback.
Current SDK upload, tag-read and download probes still fail their native
acceptance steps. See [Remote Run/Program validation](docs/controller-mode.md#validation-and-limits)
for the mode probe and its limits.

## Usage

Choose a bundled demo or open a complete L5X export. Check **Coverage**, then use
**Step scan** or **Run**. Edit inputs in **Tag Watch** and inspect the logic trace.
**Program** stops continuous scans and preserves the current values. The same
state is used by native Remote Run/Program requests. Scanning runs in the app
and continues with the webpage closed.
Entering Run performs modeled prescan, which can reset non-retentive values and
execute enabled AOI Prescan routines. Repeated Run requests do not repeat it.
The header shows the running app's full version and PLC endpoint IP. On Windows,
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
| Offline protocol analysis | `0x36`/`0x37` singles, `0x38` batches and observed single-inner `0x39` transfers with reply correlation; decoded captures never execute |
| ACD correlation | Source-bound Change Log identifiers and TagInfo symbol IDs; controller/program instance paths use imported IDs; native SDK passes project identity comparison for the tested demo |
| Upload discovery | Source-bound Program discovery, scoped Data Tables, backed scalar reads and Symbol descriptors, class metadata, bounded empty catalogs, controller settings and Linux Ethernet status/counters; native project transfer remains unfinished |
| Native status | Source-checked empty I/O force/LED and SFC force status; module connections, SFC forcing and force writes remain unsupported |
| PLC message mapping | Source-checked empty PCCC mapping descriptors; configured mappings and PCCC commands remain unsupported |
| Time Sync | Source-backed PTP enable/priorities, read-only local UTC time and explicit unsynchronized/empty-port state; PTP networking remains unsupported |
| Catalog refresh | Controller class revision/inventory and source-bound comparison tokens |
| Identity revisions | Read-only virtual hardware revision and profile firmware build, alongside source-based major/minor revision |
| Controller configuration | Source-backed legacy SecurityCode, name/description and read-only pass-through configuration; limited Metadata Definition discovery; security enforcement and pass-through routing remain unsupported |
| Software device metadata | Read-only location/locale and empty trusted-slot/operator state, explicitly identified as emulator defaults |
| File Manager | Read-only class discovery; reports zero emulated storage devices |
| Network metadata | Read-only CIP port/node addresses, IPv4 status/configuration, verified Linux DHCP/DNS flags and actual adapter MAC |
| Device locator | Network-triggered blinking webpage banner with timed expiry and cancellation |
| Studio online | Native SDK Go Online, bidirectional Run/Program control and Go Offline verified for the demo; native project transfer and tag/rung monitoring remain unfinished |

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

- Expand supported instructions, data types and execution semantics.
- Add packed BOOL arrays, built-in STRING transfers, predefined structures and more controller metadata.
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
