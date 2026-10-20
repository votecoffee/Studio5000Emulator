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

`Get Instance List` (`0x4B`) takes its starting instance in the path and no
payload. A proven empty catalog returns `CB 00 00 00`, including for nonzero
cursors. Configured or unavailable source returns status `0x0C`. Missing cursor,
attribute, program and symbolic scopes, extra payload and unsupported services
retain errors. The native signed-message policy admits these specific reads;
definition changes and tag writes remain denied.

I/O Map class attributes `2` and `3` expose zero maximum instance and zero
instance count as separate four-byte UDINTs. Existing force and LED status
remain two-byte UINTs. A matching `Local` controller module in a native export
does not create an external I/O Map connection instance. Module instances and
their I/O Connection children remain unsupported.

The new `aoi_catalog` connectivity field identifies the source check and its
limits. The existing `alarm_catalog` reports the covered class IDs; `io_map`
reports the instance count and availability. An unavailable catalog is not
represented as a successful empty one. Loading a new project recomputes these
claims from its source XML, before runtime filtering can discard unsupported
objects.

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
denials. A leased normal-source `.57` native SDK run accepted the five newly
admitted inventory reads and the embedded-server enable field, preserved source
and model values, and completed its connection/Offline cleanup sequence. Full
upload still failed controller collection after the incomplete Time Sync list.
These accepted reads do not establish full native upload or GUI monitoring.

Private diagnostics also combined the embedded-server field with hypothetical
complete Time Sync replies, then platform/memory class revisions. They did not
resolve upload. None of those clock or platform substitutes is shipped. The
last missing attribute list is evidence of a protocol gap, not proof of the
SDK's root failure. Native tag-address discovery, downloads and online edits
remain unfinished.
