# Studio5000Emulator

An experimental offline Logix v35 emulator with a browser UI and local EtherNet/IP endpoint.

Execute supported ladder and Structured Text logic, drive inputs, inspect scan
traces and connect external device simulators. The app and executable use the
name **LogixLab**.

**Current app version: `26.1030.102258`.** Versions use `YY.MMDD.HHmmss`; the
browser title, page header, Windows tray and executable properties match.

**Development focus: full emulation before further Studio 5000 connectivity.**
The current model is partial: 101 built-in RLL instruction entries, a bounded ST
subset, supported AOIs/UDTs and explicit custom strings. FBD, SFC, motion,
cyclic module I/O and EDS-driven device models remain unimplemented.
See the [comprehensive capability checklist](docs/emulation-coverage.md),
[instruction inventory](docs/emulation-instructions.md),
[222-entry predefined type inventory](docs/predefined-data-types.md) and
[roadmap](docs/roadmap.md).

Existing native SDK connection, transfer and routine-edit profiles remain
experimental and preserved. Their acceptance does not establish full runtime
emulation or general Studio GUI compatibility. Detailed prior results are in
[native compatibility checkpoints](docs/native-compatibility-checkpoints.md)
and [connectivity history](docs/connectivity-history.md).
Development is maintained on `main`.

[Event tasks](docs/event-tasks.md) add EVENT calls in ladder/ST for qualified
instruction-only tasks. **Event lab** demonstrates immediate higher-priority
dispatch, deferred lower/equal-priority work, first scans and request diagnostics.

[System-value reads](docs/gsv-configuration.md) add explicit Task/Controller
configuration through GSV in ladder and ST. **System lab** shows task rates and
watchdogs in microseconds, typed priorities, names and controller settings.

[String conversions](docs/string-conversions.md) add LOWER/UPPER and STOR/RTOS
in ladder and Structured Text, including user strings and existing AOI bindings.
**String lab** demonstrates case conversion and decimal/REAL exchange.

[File arithmetic](docs/file-arithmetic.md) adds FAL ALL/numeric/INC modes for
indexed array transforms, scalar accumulation and arithmetic/bitwise expressions.
**Stats lab** demonstrates full-array, scan-distributed and
[incremental transforms](docs/file-incremental.md).

[File search](docs/file-search.md) adds FSC ALL/numeric/INC modes, match/inhibit
state and resumable searches using the existing comparison grammar. **Stats lab**
shows ALL/numeric searches and one comparison per enable edge in INC mode.

[File sorting](docs/array-sort.md) adds SRT in ladder and Structured Text, with
exact integer ordering and selected array dimensions. **Stats lab** demonstrates
ladder enable edges and ST sorting on each executed call.

[Array statistics](docs/array-statistics.md) add ladder AVE and sample STD with
REAL results and dimension selection. **Stats lab** demonstrates averages,
deviation, row/column selection and CONTROL rearming.

[Integer expressions](docs/integer-expressions.md) add exact narrow division in
ST/CPT/CMP and FAL/FSC consumers. **Math lab** compares truncation, remainder,
REAL promotion and cross-language results.

[Common REAL math](docs/math-operations.md) adds ladder SQR, XPY, logs, angle
conversions and trigonometry. **Math lab** compares ladder, CPT and ST values,
including the v35 absolute-value rule for negative square-root inputs.

[Numeric conversions](docs/numeric-conversions.md) add DINT FRD/TOD and
INT/DINT SWPB byte ordering in ladder, with SWPB also available in ST. Choose
**Conversion lab** to inspect packed BCD, byte orders and sign extension.

[CONTROL, bit shifts and FIFO](docs/control-operations.md) add BSL/BSR, numeric
FFL/FFU, LFL/LFU and CONTROL reset with explicit edge and bounds rules;
[matching string/UDT payloads](docs/record-queues.md) extend the queue forms.
Choose **Control lab** to inspect shifts and queues. **Sequence lab** demonstrates
a stack plus [DINT SQO/SQI/SQL](docs/sequencer-operations.md) for masked pattern
outputs, feedback comparison and teaching a table.

[String search and editing](docs/string-operations.md) add FIND, INSERT and
DELETE in ladder and ST, including explicit user strings and in-place edits.
Choose **String lab** for a combined ladder/ST example.

[Masked moves and bit fields](docs/bit-transfer.md) add ladder MVM/BTD for
SINT/INT/DINT values, including mixed widths and scalar/member/array operands.
Choose **Bit lab** to try packing and extracting data.
[Data transition](docs/data-transition.md) adds DINT DTR change detection,
including reference updates during prescan and false scans.
[File bit diagnostics](docs/file-bit-compare.md) add FBC/DDT array comparisons,
all/one-mismatch modes, result-list wrapping and selective reference learning.

[Continuous/periodic scheduling](docs/task-scheduling.md) now runs mixed
Standard tasks at deterministic simulated release times. Choose **Task lab**
in the header to try the 10/25 ms example and inspect per-task counts in
Coverage. [Instruction-only EVENT tasks](docs/event-tasks.md) have a separate
bounded profile. General CPU preemption, other event sources and Safety remain unfinished.

[Wide integer ladder execution](docs/integer-execution.md) and
[wide Structured Text](docs/wide-st.md) support homogeneous LINT/unsigned
arithmetic, comparisons and bitwise operations for the v35 ControlLogix 5580
model. **Integer lab** compares RLL/ST results and demonstrates exact
[L/U/UL integer literals](docs/st-integer-literals.md). Mixed-type arithmetic,
additional expression forms and native math flags remain unfinished.

[Numeric CASE selection](docs/st-case-selection.md) supports integer and REAL
expressions with immediate lists/ranges and first-match execution. **Text lab**
demonstrates float32 comparisons, overlapping ranges and late-fault rollback.

[Runtime task inhibition](docs/task-inhibition.md) adds SSV Task InhibitTask in
ladder and ST, live GSV readback, and rollback with task progress. **System lab**
provides independent controls for its Fast and Slow tasks.

[String and UDT queues](docs/record-queues.md) extend FIFO/LIFO to complete
matching records, including custom strings, arrays and exact 64-bit fields.
Choose **Record lab** to try part tracking, a stack and a text FIFO.

[Paired MCR zones](docs/master-control.md) add controlled false scanning in
ladder and supported RLL AOIs. **Control lab** shows output clearing, retained
values, timer/counter behavior and whole-advance rollback.

[Structured Text timers](docs/st-timers.md) add TONR, TOFR and RTOR with logical
FBD_TIMER records, reset/retention, status bits and simulated elapsed time.
Choose **Timer lab** to compare on/off delays, pause/resume and fault rollback.

[Structured Text up/down counting](docs/st-counter.md) adds CTUD with logical
FBD_COUNTER records, sampled edges, reset, signed wraparound and rollback.
Choose **Counter lab** to try the count inputs and outputs.

[Structured Text edge one-shots](docs/st-oneshot.md) add OSRI/OSFI with logical
FBD_ONESHOT records, startup suppression, reached-call pulses and rollback.
Choose **Pulse lab** to try rising/falling edges and skipped calls.

[Structured Text analog scaling](docs/st-scaling.md) adds SCL with logical SCALE
records, range alarms, output limiting, status aliases and rollback.
Choose **Scale lab** to try raw/engineering ranges and invalid-range recovery.

[Structured Text signal conditioning](docs/st-signals.md) adds HLL limits, SNEG
selectable negation and SSUM weighted sums with three logical record types.
Choose **Signal lab** to combine limits, negation, selected gains and bias.

[Structured Text rate limiting](docs/st-rate-limiter.md) adds RLIM with a logical
RATE_LIMITER record, separate ramp rates, bypass and period/oversample timing.
Choose **Rate lab** to try ramps, timing diagnostics and clock rollback.

[Ladder FOR/BRK](docs/ladder-loops.md) adds indexed subroutine loops, nested
early exits, shared limits and transactional rollback. Choose **Loop lab** to try
ascending/descending ranges and conditional breaks.

[Structured Text moving statistics](docs/st-moving-statistics.md) adds MAVE
uniform/weighted averages and MSTD population deviation with logical records and
visible REAL sample queues. Choose **Moving statistics lab** to try sampling,
window changes, initialization and fault recovery.

[Structured Text maximum/minimum capture](docs/st-capture.md) adds MAXC/MINC
with retained extrema, reset baselines and transactional history. Choose
**Capture lab** to try extrema, held resets, skipped calls and fault recovery.

[Structured Text LPF software filtering](docs/st-low-pass-filter.md) adds three
filter orders with periodic/oversample timing, diagnostics and rollback. Its
bilinear recurrence is a documented software approximation; native numerical
parity remains unverified. Choose **Filter lab** to try step responses.

[Structured Text Boolean memory](docs/st-digital-memory.md) adds DFF/JKFF clocked
state and reset-/set-dominant latches with complements and transactional history.
Choose **Digital lab** to try clock edges, Clear, dominance and skipped calls.

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
For saved upload exchanges, [Change Log sequence inspection](docs/native-change-log.md#inspect-a-saved-sequence)
checks cursor links, repeated queries and rejections offline. It keeps opaque
records separate from demonstrated history or native upload acceptance.
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
| Execution | Supported RLL/ST forms, routine calls, AOIs and deterministic Continuous/Periodic releases and qualified immediate/deferred EVENT dispatch |
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
| Get System Value | Ladder/ST audit values plus [explicit Task/Controller configuration](docs/gsv-configuration.md) with typed destinations. Prior `.145` native fixture acceptance applies to audit reads; configuration reads have separate software checks. [SSV Task InhibitTask](docs/task-inhibition.md) controls bounded Standard tasks; broader attributes/classes remain unfinished |
| Software device metadata | Read-only location/locale and empty trusted-slot/operator state, explicitly identified as emulator defaults |
| File Manager | Read-only class discovery; reports zero emulated storage devices |
| Network metadata | Read-only CIP port/node addresses, IPv4 status/configuration, verified Linux DHCP/DNS flags and actual adapter MAC |
| Device locator | Network-triggered blinking webpage banner with timed expiry and cancellation |
| Studio online | Native SDK Go Online, bidirectional Run/Program control, Go Offline, installed scalar BOOL/SINT/INT/DINT/LINT/REAL reads and bounded source-equivalent transfers verified for demo and expanded fixtures; Studio GUI acceptance and general tag/rung monitoring remain unverified |
| Supported routine edits | Opt-in Program-mode Standard RLL replacement; consecutive SDK imports, replacement across routines and reconnection using the same updated project verified; edited L5X working-copy export |

Coverage depends on the actual project and execution scope. Preemptive/event scheduling,
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

1. Prioritize common execution: Continuous/Periodic tasks, basic RLL/ST forms,
   timers/counters, ordinary strings/arrays/UDTs/AOIs and frequently used instructions.
2. Add common data manipulation, shift/FIFO/sequencer operations and faults/status;
   then event scheduling, messaging and virtual I/O.
3. Expand AOIs and Structured Text, then implement FBD and SFC.
4. Build generic cyclic I/O and device models, including EDS mappings, POINT I/O
   and FANUC handshakes; then virtual drive/motion execution.
5. Qualify mixed-feature projects with explicit conformance evidence.
6. Resume broader Studio uploads/downloads and the complete online-edit lifecycle.

Follow the [full-emulation tracker](https://github.com/votecoffee/Studio5000Emulator/issues/1).

The [full remaining-work inventory](docs/emulation-coverage.md) includes current
limitations and specialized controller profiles. The [milestones](docs/roadmap.md)
define acceptance gates. Preserve existing connectivity and external HTTP/MQTT
interfaces while executing this plan.

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
