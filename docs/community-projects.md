# Community project assessment

Assessment date: 2026-10-19. These are candidates and protocol references, not
claims of native Studio 5000 controller compatibility.

| Project | Relevant capability | License / integration status |
| --- | --- | --- |
| [OpENer](https://github.com/EIPStackGroup/OpENer) | CIP adapter object architecture, network metadata and cyclic I/O | Adapted BSD-style license with additional terms. Reference only; no upstream code bundled. |
| [libplctag](https://github.com/libplctag/libplctag), especially [ab_server](https://github.com/libplctag/libplctag/tree/release/src/tools/ab_server) | Independent client and simulated PLC target, connection and fragmented-transfer behavior | MPL-2.0 or LGPL-2+. Candidate interoperability peer; no code bundled. |
| [acd-tools](https://github.com/hutcheb/acd) | Direct ACD parsing and L5X serialization | Apache-2.0. Version `0.3a2` evaluated; not enabled as an application importer. |
| [L5Sharp](https://github.com/tnunnink/L5Sharp) | L5X component and data models | MIT. Candidate reference for broader import/edit coverage. |
| [Logix Workbench](https://github.com/ChrisMangin/logix-workbench) | Ladder rendering, editing and L5X comparison | MIT. Candidate UI reference. |
| [IronPLC](https://github.com/ironplc/ironplc) | Structured Text compilation, runtime and task scheduling | MIT. Candidate architecture/test reference; Logix semantics require separate validation. |
| [pylogix](https://github.com/dmroeder/pylogix) | Independent Logix client | Apache-2.0. Candidate additional interoperability client. |
| [pycomm3](https://github.com/ottowayi/pycomm3) | Independent CIP/Logix client | MIT. Used by optional interoperability checks; not a runtime dependency. Upstream states it is no longer actively developed. |
| [cpppo](https://github.com/pjkundert/cpppo) | Python CIP simulator and originator | GPLv3 or separately negotiated terms. Candidate separate test peer; no code bundled. |

Before incorporating third-party code, pin the exact source, retain upstream
licenses/notices, and validate the intended subset against independent fixtures.
Code from other licenses must not simply be relabeled MIT. The current runtime
continues to use Python's standard library.

## First implemented increment

Added an original read-only Port Object and TCP/IP Interface metadata subset.
The next increment adds encoded node addresses, the TCP/IP physical-link path
and the selected interface's actual MAC through the Ethernet Link Object.
Windows metadata reads use IP Helper directly to avoid shell startup latency.
Controller class revision and instance inventory now follow the common CIP
class layout reviewed in OpENer. A native SDK retest confirmed that specific
class-level revision query succeeds; the remaining vendor handshake is pending.
Linux broadcast reception now uses separate broadcast sockets, checked interface
metadata and a selected reply source. Its implementation follows the published
Linux socket interface and ODVA discovery exchange; no upstream stack code is
bundled. See [broadcast discovery](connectivity.md#broadcast-discovery).
The scope addresses concrete browser queries without inventing physical
controller manufacturing data. See the [protocol contract](connectivity.md#port-and-tcpip-interface-metadata)
and `source/tests/interop_network_objects.py` for the independent-client check.

OpENer source reviewed at commit `d8820ef41ce30dda06d213438ba81c81de33ffe2`;
libplctag source reviewed at `7712ed7f1ee05ba0ebfca641b3f5c43da52a66ed`.
Their implementations are references, not a replacement for native Studio
connection, upload/download, project correlation or debugger services.

## ACD converter evaluation

An isolated `acd-tools==0.3a2` conversion of a v35 ACD derived from the public
ConveyorDemo fixture reported success. Comparison with its native L5X export
found 14 tags and two routines in each, but total rung count fell from 10 to 9.
The `ONS` sensor-pulse rung was absent. Saved initial data, including timer and
counter presets and the speed setpoint, was not preserved in the model. Rung
documentation and some controller settings also differed.

The original ACD and reference export were preserved. Machine-specific inputs,
package-install receipts, conversion outputs and detailed comparisons stay in
ignored local storage. This one-fixture failure does not characterize every
file supported by the upstream library. It does block adopting this version as
an execution-ready importer. The native converter remains the default.

The `.29` correlation reader uses the ACD directory format reviewed in
`acd-tools==0.3a2` as a reference. It is an original bounded standard-library
implementation that reads only the offline Change Log header. No upstream code
is bundled and no new runtime package is required. Logic and initial values
still come from the native converter; this header reader is not an ACD-to-L5X
replacement. Its public tests build synthetic containers and identifiers.

Version `.52` uses the same project's
[component record layouts](https://github.com/hutcheb/acd/blob/main/acd/record/comps.py)
as a reference for an original, bounded Program identity reader. It checks
`Comps.Dat` Program format 19 paths against the active program names in
`TagInfo.XML`, including programs without local tags. It does not reconstruct
the component database or its indexes, and rejects ambiguous historical paths.
Unsupported optional metadata leaves TagInfo tag mappings available and reports
a diagnostic. No upstream parser code, native database files or additional
runtime packages are bundled.

## Reusable conversion comparison

From the repository root:

```powershell
py -3.13 -X utf8 source/tools/compare_imports.py --reference .local/projects/native.L5X --candidate .local/projects/candidate.L5X --out .local/comparisons/result.json
```

The tool compares modeled identity, tags/access, initial values, tasks/programs,
parsed routine logic/documentation, UDTs, AOIs, modules and controller settings.
XML formatting alone does not cause a difference. Missing logic, changed values,
unsupported candidate execution or input drift fails the comparison. Exit code
0 means modeled content matches; 1 means it does not. Output cannot overwrite
either input, including through a filesystem alias.

Even a passing comparison covers only the reported offline representation. It
does not prove complete binary round-trip fidelity, native controller behavior,
safe commissioning, or Studio Go Online compatibility.
