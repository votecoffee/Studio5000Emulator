# Development

The tested development environment is Windows with Python 3.13. The application
runtime uses the standard library. UI assets are plain HTML, CSS and JavaScript.
The PLC artwork lives in `source/web/icons/`. The multi-size ICO contains the
original 16–256 pixel PNG frames and is used by the Windows executable and tray;
the browser serves the same ICO as its favicon and PNG variants in the header.
Both the executable build and appliance image include these assets.

The running version comes from `source/logixlab/__init__.py`. Bump it for each
committed application revision; the HTML, API, tray tooltip and session receipt
use that exact value. Rebuild the executable after changing it, and restart the
app to activate new Python code. An existing process retains its loaded version.

## Run and test

From the repository root:

```powershell
py -3.13 -X utf8 source/launch.py --sample TextLab --data-dir .local/session
```

From `source/`:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -v
```

The bundled Conveyor, Data, AOI, Call, Text, Network, Structure, Layout and Flag
labs are public L5X fixtures. Native ACD inputs and generated ACD variants remain
local.

## Native SDK acceptance probe

The optional `tools/probe_native_sdk.py` runs the public Logix Designer SDK
against an already running, source-bound LogixLab endpoint. It requires Windows,
the .NET 8 SDK and a separately installed compatible Logix Designer SDK. The
client package is pinned to `2.1.974`; SDK binaries are never included in this
repository or the app. The installed SDK's local NuGet feed is detected under
the public Documents folder; `--sdk-feed` selects another local feed.

Import the matching ACD into LogixLab, enable the L85E anonymous native read-only
endpoint, and disable protocol and Device I/O writes. Use the current UI URL and
the actual Linx path for that endpoint:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0'
```

The address above is a documentation example; substitute the emulator IP. The
probe checks the endpoint address, port, profile, source ACD/L5X hashes, instance
and read-only policies before calling the SDK and again afterward. Version `.63`
also requires zero TCP clients, an available free lease, zero inhibit mask and
disabled project-transfer, edit, tag-write and mode-change authority. It builds its
helper and opens an ACD copy in a new ignored `.local/native-probes/` directory.
Windows helper processes run without console windows. No service is stopped or
reconfigured.

The default connection test records Go Online, connected state, controller mode,
Go Offline and cleanup state. Add `--tag "Controller/Tags/Tag[@Name='Example']"`
to test a generic online byte-array read; repeated `--tag` options are supported.
Use `--operation upload` for a separate upload attempt. Version `.63` adds
`--operation download` to call the public SDK's `DownloadAsync` against that same
source-bound endpoint. This tests programming preparation while the endpoint's
project-transfer authority remains disabled. Its temporary coordination lease
and Run Mode Inhibit can be exercised; full native download is unfinished and
the current implementation rejects Controller service `0x60`. This expected
SDK failure still produces exit code one. Upload/download probes reject `--tag`;
online edits, tag setters and mode changes remain outside this tool.

For example, run the same probe with the explicit operation:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation download
```

`summary.json`, `sdk-result.json`, before/after app state and protocol traces,
and build/SDK logs remain private. These files contain project paths and tag
values. SDK results include each step, error types/messages, timings and
timestamped events. Exit zero requires the requested steps to succeed, cleanup
to confirm Offline, endpoint cleanup and source/model checks to pass. Endpoint
cleanup passively waits up to eight seconds for asynchronous socket closure,
lease release and a zero inhibit mask. `cleanup_confirmed` records that check;
it does not turn an unsupported operation into a success. The source-copy hashes,
tags, scans, model time, change history and mode must remain unchanged.
Failed tag reads, upload or download are retained as failures even when
connection succeeds. A timeout is incomplete;
inspect the retained diagnostics before starting another attempt. Concurrent
client traffic can contribute to the endpoint's request-count delta. These
results do not establish Studio GUI monitoring or native controller equivalence.
Reports hash the helper sources and runtime files, including its managed DLL;
the .NET apphost EXE alone does not identify the executed implementation.

Windows appliance subprocesses use `tools.vmware_appliance.background_options()`
to request `CREATE_NO_WINDOW`; apply the same policy to private SSH validation
scripts. Preserve stdout/stderr and exit-status checks. Launcher regressions
cover the persistent tunnel's process options, diagnostics on failure and an
actual Windows child process with no console. That OS-specific check is skipped
on Linux.

`ethernet_counters.py` reads bounded `e1000e` tables on demand and caches them for
one second. Its API distinguishes observed values from unimplemented wire-zero
fields. Counter reads and API snapshots share an immutable sample; invalid or
failed refreshes remove expired availability. See the
[counter model and limitations](ethernet-counters.md) before extending driver
mappings or interpreting a zero as a measurement.

`aoi_catalog.py` inspects original complete source before permitting an empty
UDI Definition (`0x338`) list. `alarm_catalog.py` applies the same conservative
alarm-absence check to instruction and tag-alarm catalogs; `io_map.py` admits
an empty module list only without external I/O configuration. Keep these source
checks independent of runtime type filtering. Their native read-policy entries
authorize discovery only. See [native inventory discovery](native-inventory.md)
for schemas, source boundaries and deployed validation.

`data_log_catalog.py` checks both `Trends` and the native v35 `DataLogs` section.
`native_rejections.py` collects only structural IDs for pre-dispatch failures,
separately from ordinary CIP errors. Native Timeline UID acknowledgements retain
every source header field and never initialize or replace UIDs. See
[native session policy](native-session-policy.md) before extending these paths.

Nested I/O Connection paths retain a separate `io_map_instance` in the live
parser, attribute-gap summaries and native rejection summaries. Keep that scope
when dispatching or diagnosing the child; do not flatten it into a global class.
Only a source-checked class-revision read is supported. See
[I/O Connection discovery](io-connection-discovery.md) for the namespace and limits.

`programming_lease.py` keeps one native context's coordination ownership under
the endpoint lock. Close, invalidation, reload and stop paths clear ownership;
expiry is also checked before state inspection or another acquisition. The
`controller_instance` path field is distinct from Program and I/O Map parents.
The lease does not authorize a project write. See
[programming coordination](programming-coordination.md) before extending
download preparation or transfer dispatch.

The owning lease's `run_inhibit` mask overlays Controller attribute `7`; it is
separate from immutable source configuration. `Application.command('step')`
checks it before applying device inputs or advancing logic. Keep cleanup paths
and source-generation checks shared with lease ownership. See
[Run Mode Inhibit](run-mode-inhibit.md) for the signed setter contract and the
unimplemented Controller `0x60` programming boundary.

## Device I/O

`device_io.py` holds immutable scalar snapshots and a bounded input queue.
Application mutation paths capture committed state; consumer JSON encoding and
HTTP/MQTT I/O run outside `app.lock`. Input transactions are drained before each
scan, with root-value rollback if a batch fails. `device_http.py` exposes scoped
tokens and cached/queued routes. The optional `tools/mqtt_bridge.py` runs in its
own process with bounded outgoing/incoming queues. See [Device I/O](device-io.md)
for the wire schema, sampling limits and optional real-broker validation.

## ACD symbol identity

`data_table.py` encodes the supported read-only Data Table fields. The router
builds scoped catalogs through existing symbol type/access checks, excluding
aliases from storage instances. IDs reuse the model's Symbol IDs and never
stand in for physical addresses. See [Data Table scope and limits](connectivity.md#data-table-catalog).

Its bounded scalar address space has separate model descriptor/value regions.
Value reads use current committed memory under the application lock; they never
read host or controller memory. Only ordinary nonconstant scalar atoms receive
these allocations. A zero-selector `0x4F` request must read the complete scalar
within the negotiated reply budget. Keep all other tag kinds and selectors
unavailable until their layouts and transfer semantics are implemented.

`native_symbols.py` reads the optional `TagInfo.XML` schema 1.0 stream using the
bounded container reader shared with `native_project.py`. It accepts root
controller Symbol paths and Program/Symbol paths, with separate IDs per scope.
Compressed members are limited to 4 MB and expanded XML to 16 MB; DTDs, entities,
duplicate names/IDs and conflicting program mappings are rejected. It never
extracts archive paths or imports native binaries.

The importer hashes the original ACD and binds each manifest to the converted
L5X hash. Server validation precedes project replacement. Instance reads and
enumeration use those IDs when present, with no generated fallback for missing
entries. Plain L5X fixtures retain their model-generated catalogs. Native type
handles/layouts and compiled memory addresses are separate from this logical
mapping; preserving IDs does not prove the SDK's online address cache is valid.

## Offline CIP capture inspection

The optional capture inspector reads completed PCAP/PCAPNG files through a
separately installed [Wireshark TShark](https://www.wireshark.org/docs/man-pages/tshark.html).
It uses offline decoding with name resolution disabled. Wireshark remains a
development tool; the application runtime has no new dependency.

From the repository root:

```powershell
py -3.13 -X utf8 source/tools/inspect_cip_capture.py --capture .local/reference.pcapng --out .local/reference-report.json
```

Use `--tshark` to select its executable when it is unavailable on `PATH` or in
the usual Windows installation directory. Keep captures and reports under
ignored `.local/` storage. Capture-file extensions are also ignored repository-wide.

The report includes numeric object paths, service codes, response statuses,
byte counts, hashes and frame references. By default it omits addresses, symbol
names and message bytes. `--include-payloads` adds full CIP bytes to the private
report when investigating an unknown service.

Pairing requires an explicit TShark response-to frame reference, the same TCP
stream and matching request/response service codes. Missing or conflicting
evidence stays unpaired. Only one outer CIP message per frame is analyzed;
multiple PDUs and unsupported paths are listed as skipped. Report format 2 also
decodes one observed Message Router `0x36` or `0x37` layer, exposing the counter
and embedded service/path/status fields. Successfully paired wrapper replies
must echo that counter and match the embedded reply service. Malformed or unknown
envelopes retain the outer evidence and an explicit structural error. Symbol
names and bytes remain omitted by default, including inside decoded envelopes.

Report format 3 also decodes observed `0x38` batch offset tables and correlates
ordered child replies, including outer `0x1E` and embedded errors. Batches are
limited to 256 children and 65,519 total message bytes. Their child descriptions
use `children` and `child_count`; single-message envelopes retain `inner`.
Nested wrappers are not decoded recursively. Malformed batches keep their outer
evidence without exposing partially decoded children. Default privacy settings
apply to every child.

Every decoded envelope says **integrity: NOT VERIFIED**. The capture inspector
does not accept session keys or verify MACs. The separate pure Python codec in
`source/logixlab/signed_messages.py` provides `verify_request(raw, key,
expected_sequence=...)` for local known-key tests. It checks HMAC-SHA1 over the
complete CIP request before the final MAC, with an exact expected counter.
Callers own session state and replay tracking; the codec retains neither.
Version `.22` adds `verify_response(raw, key, request=...)` and
`encode_response(request, inner, key)`. They correlate the embedded service and
echoed counter, preserve embedded CIP errors and check or produce the MAC over
the complete reply before its final 20 bytes. These functions never dispatch an
operation. Native positive/negative denial tests establish request/reply MAC
compatibility for both `0x36` and `0x37`; registration and confirmation semantics
remain separate work. Version `.24` supports structural
batch parsing through `parse_request` and `parse_response`, returning a
`BatchEnvelope`. Version `.30` adds batch MAC verification and
`encode_batch_response`, using the complete message and one counter per batch.
The optional native read-only mode dispatches single and batch reads without
claiming confirmation-proof verification or peer authentication. See the
[observed envelope layout](connectivity.md#offline-signed-envelope-codec).

Embedded services inside other routed requests or Multiple Service Packets
require separate inspection. The tool does not infer embedded vendor-service
meanings or successful Studio Go Online, and it never executes decoded requests.

Analysis is bounded to 64 MiB input, 50,000 input packets, 128 MiB decoded JSON
and 60 seconds. Capture completeness is reported as unassessed. The input hash
must remain unchanged during analysis; copying a finished capture avoids races
with a live capture writer. Validation includes synthetic request/reply,
malformed-header, ambiguous-pairing and privacy checks. Reference PLC projects,
captures and native connection receipts remain local.

## Optional protocol probes

The probes use the optional `pycomm3` client. Version 1.2.16 is used by the
existing acceptance scripts; it is not an application dependency.

```powershell
py -3.13 -m pip install pycomm3==1.2.16
New-Item -ItemType Directory -Force .local/checks
Set-Location source
py -3.13 -X utf8 tests/interop_pycomm3.py --out ../.local/checks/atomic.json
py -3.13 -X utf8 tests/interop_logix_identity.py --out ../.local/checks/identity.json
py -3.13 -X utf8 tests/interop_atomic_transfers.py --out ../.local/checks/transfers.json
py -3.13 -X utf8 tests/interop_structure_reads.py --out ../.local/checks/structures.json
py -3.13 -X utf8 tests/interop_structure_writes.py --out ../.local/checks/structure-writes.json
py -3.13 -X utf8 tests/interop_user_strings.py --out ../.local/checks/user-strings.json
py -3.13 -X utf8 tests/interop_numeric_layouts.py --out ../.local/checks/layouts.json
py -3.13 -X utf8 tests/interop_catalog_revision.py --out ../.local/checks/catalog.json
py -3.13 -X utf8 tests/interop_packed_bits.py --out ../.local/checks/flags.json
py -3.13 -X utf8 tests/interop_device_locator.py --out ../.local/checks/locator.json
```

By default the scripts create isolated loopback targets. The transfer probe
builds an atomic tag-cache adapter from supported wire attributes; this is
distinct from native firmware-address tag upload. It exercises automatic array
fragmentation and generic CIP mask writes. The installed client's malformed
single-scalar and high-level mask request paths are rejected by the endpoint;
the acceptance script uses valid client paths and records that distinction.

Automatic-port targets (`port=0`) choose a shared TCP/UDP port with up to eight
bind attempts. A failed attempt releases its sockets before selecting another
port. Explicit ports are used exactly as requested; an unavailable port returns
an error rather than moving the listener.

The structure probe creates an isolated read-only Structure Lab endpoint. It
uses the installed client's template parser to discover nested UDTs, decode
records and arrays, fragment reads over a 256-byte Class 3 connection, and observe
a modeled scan. It does not exercise native firmware-address tag upload.

The structure-write probe also creates an isolated loopback target. It transfers
a 1,072-byte nested-record array with automatic fragmentation, writes small
records through Multi Service, checks wrong-handle and read-only rejection,
observes a scan consuming a written field, and restores the input records.
It uses the same documented-attribute catalog adapter. The installed pycomm3
1.2.16 single-write builder duplicates payload bytes for small writes; the probe
uses its valid Multi Service path rather than relaxing endpoint length checks.

The user-string probe imports a generated public LEN/DATA fixture into an
isolated loopback target. It uses the independent client's template parser and
string codec for scalar, array and nested reads, automatic fragmented array
reads/writes on a 24-byte connection, and rejection of a read-only tag write.
The behavioral tests also cover individual member restrictions, unknown backing
bytes, split atoms, padding and rollback. Built-in STRING transfers remain
unsupported.

The numeric-layout probe verifies all nine supported numeric widths, nested
alignment, exact 64-bit values, and fragmented read/write roundtrips of eight
64-byte records. It also checks direct atomic-array access inside record arrays,
nonzero reserved-padding rejection and scan
propagation, then restores its input records. The model's zero-padding contract
and remaining layout restrictions are documented under
[structured transfers](connectivity.md#structured-transfers).

The catalog-revision probe checks controller class revision/inventory and
comparison attributes, plus File Manager revision and zero storage count using
the client's UINT/UDINT decoders. It then reconnects after
isolated source imports. It verifies
that runtime edits preserve tokens, an added tag shifts symbol instances, and
a changed nested UDT changes the record layout from 64 to 72 bytes. It refreshes
the catalog and reads the new member and record array. Fixtures in the repository
remain unchanged; generated project copies and receipts stay local.

Live write probes require an explicit `--write`, a loopback target and endpoint
writes enabled. The transfer probe expects Network Lab and restores changed
inputs. Do not point test clients at production controllers.

The packed-bit probe uses the client's template parser and structure codec to
read and write Flag Lab's 336-byte record array over a 256-byte connection. It
checks multiple hosts, sparse bit numbers, nested arrays, direct atomic flag
writes, rejection of unused host bits, read-only access and modeled scan
propagation, then restores its input records. Like the other structure probes,
it uses the documented-attribute catalog adapter; native tag upload and Studio
Go Online remain separate work.

The device-locator probe uses an independent Class 3 client against a temporary
read-only endpoint. It checks start, replacement and stop requests, invalid
durations and lengths, and preservation of application memory. It does not
operate the FactoryTalk Linx interface. Browser checks should also cover the
global banner, tab changes, cancellation, expiry and page reload during an
active request.

The network-object probe checks Port Object class/instance data and actual local
TCP/IP configuration through an independent Class 3 client. Node addresses are
compared with that client's own EPATH encoder. MAC reads match the selected
interface or return an explicit unavailable status on loopback. It rejects unknown
ports, unknown attributes and configuration writes while preserving modeled
memory:

```powershell
py -3.13 -X utf8 tests/interop_network_objects.py --out ../.local/network-objects.json
```

The optional Linux broadcast probe creates a temporary read-only endpoint on an
explicitly selected local Ethernet IP and an automatic port. It sends discovery
datagrams through that interface to the PLC IP, subnet broadcast and limited
broadcast. It checks reply sources, equivalent payloads, ignored malformed
requests and preserved application memory. Run it inside the host-only backend,
using its actual address in place of the documentation address below:

```sh
python3 -X utf8 tests/interop_broadcast_discovery.py --bind-address 192.0.2.128 --out ../.local/broadcast-discovery.json
```

It does not test the Linx UI's range-browse behavior or Studio Go Online.

See the [community assessment](community-projects.md#reusable-conversion-comparison)
for the separate read-only comparison tool used to evaluate converter output.

## Optional ACD conversion

Configure `l5xgit` through **Import settings**, the `LOGIXLAB_CONVERTER` environment
variable, or `PATH`. Saved Import settings take precedence over automatic
environment/PATH discovery. No checkout-specific converter path is built in.

ACD conversion requires separately installed native tooling and compatible
Studio 5000/SDK availability. Conversion operates on a private copy and records
source/export hashes in the private import directory.

Optional `native_*_scenario.py` scripts accept explicit inputs and output paths.
For example, from `source/`:

```powershell
py -3.13 -X utf8 tests/native_import_scenario.py --acd ../.local/projects/ConveyorDemo.ACD --work-dir ../.local/native-import
```

The input must be the native ACD counterpart of the public Conveyor Demo L5X.
Native import acceptance does not establish native instruction execution parity.
See [connectivity documentation](connectivity.md) for the separate SDK connection
diagnostic.

## Executable build

```powershell
py -3.13 -m pip install pyinstaller
powershell -NoProfile -File source/build.ps1
```

Run the command from the repository root. The output is `dist/LogixLab.exe`, and
`START.cmd` launches it. Only the public L5X demos are bundled. Native SDK build
folders, generated ACDs, local receipts and private inputs stay out of source
control.

Source checks and packaged-executable checks are different validation steps.
Record which runtime was actually exercised when reporting a result.
