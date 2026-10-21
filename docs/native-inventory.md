# Native upload inventory discovery

Version `0.6.0-connectivity.57` extends read-only discovery used by the native
SDK before it collects controller properties. These services describe empty
software-model catalogs only when the original complete L5X proves absence.
They do not upload definitions or emulate external I/O or alarm execution.

| Class | Catalog | Empty-source requirement |
| --- | --- | --- |
| `0x69` | I/O Map | No external I/O modules, I/O tags, force data or ambiguous module declarations |
| `0x331`, `0x332` | Digital and Analog Alarm | No alarm tag types, alarm data or alarm configuration |
| `0x3A6` | Configured Alarm | Same conservative alarm-source check |
| `0x3A7` | Alarm Set | Same conservative alarm-source check |
| `0x3A8` | Alarm Condition Definition | Same conservative alarm-source check |
| `0x338` | UDI Definition (Add-On Instructions) | Exactly one explicit, empty `AddOnInstructionDefinitions` section; complete source without protected or ambiguous definitions |
| `0x71` | Data Logging (`.58`) | Complete source without configured trends, data logs, protected data or ambiguous declarations |

`Get Instance List` (`0x4B`) takes its starting instance in the path and no
payload. A proven empty catalog returns `CB 00 00 00`, including for nonzero
cursors. Configured or unavailable source returns status `0x0C`. Missing cursor,
attribute and symbolic scopes, extra payload and unsupported services
retain errors. The native signed-message policy admits these specific reads;
definition changes and tag writes remain denied.

Version `.125` also supports numeric Program scopes for Digital/Analog Alarm,
HMI Button Control and Message lists under a matching native Program identity.
Their individual absence checks remain conservative across the complete source.
Other Program-scoped catalogs remain unsupported unless separately documented.
See [Program catalog discovery](program-catalog-discovery.md).

Version `.126` adds the separate, nonempty Device Diagnostic Message (`0x3B2`)
catalog from original ACD definitions. This is source metadata rather than a
claim of empty diagnostics or active fault status. See
[device diagnostic messages](device-diagnostic-messages.md).

I/O Map class attributes `2` and `3` expose zero maximum instance and zero
instance count as separate four-byte UDINTs. Existing force and LED status
remain two-byte UINTs. A matching `Local` controller module in a native export
does not create an external I/O Map connection instance. Module instances and
their I/O Connection instances remain unsupported. Version `.59` supports the
[nested I/O Connection class revision](io-connection-discovery.md) below the root
I/O Map namespace without creating module or connection instances.
Version `.60` adds a narrowly scoped, source-backed Local root link-address
read; other module fields and connections remain unavailable. See
[programming coordination](programming-coordination.md).

The new `aoi_catalog` connectivity field identifies the source check and its
limits. The existing `alarm_catalog` reports the covered class IDs; `io_map`
reports the instance count and availability. An unavailable catalog is not
represented as a successful empty one. Loading a new project recomputes these
claims from its source XML, before runtime filtering can discard unsupported
objects.

Version `.58` adds [Data Logging and native session policy details](native-session-policy.md),
including class counts/capacities, retained Timeline UID acknowledgements and
bounded diagnostics for requests rejected before object dispatch.

TCP/IP Interface class attributes `101` and `102` return single-byte zero
values: the software PLC exposes no embedded HTTP service on its PLC interface.
The separate localhost management webpage is not that service. Setters remain
unsupported, and these reads do not query or change host network settings.
Class `Get Attributes All` retains its original revision/max/count layout.

## Evidence and limits

The v35 installed plain attribute definitions identify I/O Map, I/O Connection,
Configured Alarm, Alarm Set, Alarm Condition Definition, UDI Definition and the
TCP/IP embedded-server fields. Vendor attribute-definition files are not
distributed. Source checks and protocol handlers are original implementation.

Tests cover exact byte widths, cursors, native signed reads, source replacement,
configured/protected/context/ambiguous source, malformed requests and write
denials. The `.57` suite passes 804 tests on Windows and Linux, with two Windows
skips and one Linux skip. The rebuilt executable and running webpage match the
source version and assets; the deployed appliance passes 220 wire checks.

The deployed native SDK upload accepted the five newly admitted inventory reads
and the embedded-server enable field across 197 verified signed requests. A
separate connection probe completed all nine connection/Offline cleanup steps
with 82 verified requests. A two-tag BOOL/DINT probe verified 84 requests but
both reads failed with `RxDA_E_NO_ONLINE_ADDRESS`, without sending tag-read
packets. All probes preserved source and model values and confirmed Offline
cleanup. Full
upload still failed controller collection after the incomplete Time Sync list.
These accepted reads do not establish full native upload or GUI monitoring.

Private diagnostics also combined the embedded-server field with hypothetical
complete Time Sync replies, then platform/memory class revisions. They did not
resolve upload. None of those clock or platform substitutes is shipped. The
last missing attribute list is evidence of a protocol gap, not proof of the
SDK's root failure. Native tag-address discovery, downloads and online edits
remain unfinished.
