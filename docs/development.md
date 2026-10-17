# Development

The tested development environment is Windows with Python 3.13. The application
runtime uses the standard library. UI assets are plain HTML, CSS and JavaScript.

## Run and test

From the repository root:

```powershell
py -3.13 -X utf8 source/launch.py --sample TextLab --data-dir .local/session
```

From `source/`:

```powershell
py -3.13 -X utf8 -m unittest discover -s tests -v
```

The bundled Conveyor, Data, AOI, Call, Text, Network and Structure labs are public L5X
fixtures. Native ACD inputs and generated ACD variants remain local.

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
```

By default the scripts create isolated loopback targets. The transfer probe
builds an atomic tag-cache adapter from supported wire attributes; this is
distinct from native firmware-address tag upload. It exercises automatic array
fragmentation and generic CIP mask writes. The installed client's malformed
single-scalar and high-level mask request paths are rejected by the endpoint;
the acceptance script uses valid client paths and records that distinction.

The structure probe creates an isolated read-only Structure Lab endpoint. It
uses the installed client's template parser to discover nested UDTs, decode
records and arrays, fragment reads over a 256-byte Class 3 connection, and observe
a modeled scan. It does not exercise native firmware-address tag upload.

Live write probes require an explicit `--write`, a loopback target and endpoint
writes enabled. The transfer probe expects Network Lab and restores changed
inputs. Do not point test clients at production controllers.

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
