# Development

The tested development environment is Windows with Python 3.13. The application
runtime uses the standard library. UI assets are plain HTML, CSS and JavaScript.

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

The numeric-layout probe verifies all nine supported numeric widths, nested
alignment, exact 64-bit values, and fragmented read/write roundtrips of eight
64-byte records. It also checks direct atomic-array access inside record arrays,
nonzero reserved-padding rejection and scan
propagation, then restores its input records. The model's zero-padding contract
and remaining layout restrictions are documented under
[structured transfers](connectivity.md#structured-transfers).

The catalog-revision probe checks controller class revision/inventory and
comparison attributes through the independent client, then reconnects after
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
