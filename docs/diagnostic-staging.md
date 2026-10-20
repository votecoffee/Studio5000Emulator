# Temporary native Diagnostics Message models

Version `0.6.0-connectivity.72` models Diagnostics Message (`0x3B2`) Create
records inside a [decoded device batch](device-payload-inspection.md). These
definitions remain temporary descriptors. They do not install controller
diagnostics, generate messages or enable batch execution.

## Supported profile

The installed plain-text DiagnosticsMessage attribute description identifies
Message ID, Message Code and Message Revision. The observed native SDK batch
creates each object with exactly these three attributes. No vendor files or
captured definitions are bundled with the application.

Only unqualified controller-scope instances `1..4294967295` and Create service
`0x08` are modeled. The payload starts with a UINT attribute count of three,
followed by each UINT attribute ID and its value, in any order:

| Attribute | Meaning | Modeled value |
| --- | --- | --- |
| 1 | Message ID | USINT byte count and 1..40 bytes forming an ASCII identifier |
| 2 | Message Code | USINT byte count and 1..255 printable ASCII bytes |
| 3 | Message Revision | UINT, retained without assigning execution semantics |

Unknown/duplicate attributes, missing values, invalid lengths, controls,
non-ASCII text and trailing bytes fail. Object instances and Message IDs must
be unique within the batch; different Message IDs can share a Message Code.
Other object classes and unknown services are never dispatched. This is an
observed programming profile, not a general controller programming specification.

Each assembly is limited to 1,024 messages and 65,536 total Message ID/Code
bytes. The existing container, record and assembly limits also apply.

## Atomic modeling, privacy and cleanup

The runtime builds the [Template models](template-staging.md) and diagnostics
locally, then publishes both temporary model sets together. A malformed
supported record discards both sets, including Templates completed before the
bad diagnostic. Structural inspection can still report `decoded`, while the
failing object model reports `invalid` with a fixed reason. Service `0x06`
returns `0x03` for this validation failure. The error is cached until cleanup.

Successful modeling still returns execution denial `0x0F` with
`device_batch_execution_unimplemented`. No active project or catalog changes.
The diagnostic event reports the combined modeled-record count and the number
of remaining unsupported records; the Template summary's `unsupported_records`
continues to mean records outside the Template model alone.

The transport's `diagnostic_staging` summary contains status, message count,
text-byte count, modeled-record count and limits. It omits instance IDs,
Message IDs, Codes, revisions and request bytes. Completed definitions are
immutable. `definitions_exposed`, `active_catalog_replaced` and `commit` remain
false, and structural inspection still reports zero executed records.

Assembly expiry and every transport/lease cleanup path clear both models.
The native SDK probe requires any advertised diagnostic stage to be idle and
empty at admission and cleanup, with installation/exposure disabled.

## Validation and remaining work

The normal-source native SDK attempt models 136 Diagnostics Messages containing
3,028 text bytes, alongside 242 Templates and 346,596 opaque Template definition
bytes. This covers 863 of 904 batch records. The remaining 41 records are
20 Symbol Creates, 16 Data Table Creates, one Program Create, two Routine
Creates and two scoped coordination operations. Full execution remains denied.
The SDK retains `RxCsE_DOWNLOAD_OF_DEVICES_FAILED`, then returns Offline with
unchanged source/model and empty temporary stages.

Synthetic tests cover all truncations, reordered attributes, unsigned revision
bounds, malformed strings/IDs, duplicate objects, exact capacity and excess,
path scopes, summary privacy, cached failures, atomic cross-model rejection,
signed requests, source/owner guards and lifecycle cleanup.
The 960-test suite passes on Windows with two expected skips and Linux with
one expected skip.

The rebuilt `.72` runtime's application modules and served webpage match source.
The Windows executable's embedded version, webpage and staging module were
checked separately. The running endpoint passes 291 wire checks. Its public
SDK probes report:

| Probe | Verified signed requests | Native outcome |
| --- | --- | --- |
| Connection | 81 | Nine steps succeed, including Go Online and Go Offline |
| Tag reads | 83 | Address discovery fails before value reads |
| Upload | 197 | Controller-collection upload still fails |
| Download | 180 | 863 records modeled; batch execution denied |

All four cases confirm Offline cleanup, unchanged source/model and empty
temporary stages. The final state has zero TCP clients, an uninhibited free
lease, idle preparation, closed transport, no fragment buffer, idle inspection
and empty Template/diagnostic models. Scans and model time remain zero. The
communications and SDK services remain running.

Next work covers the remaining object contracts and references, compiled
definition interpretation, further transfer stages and atomic model commit.
Native upload/download, online tag monitoring and online edits remain unfinished;
Studio GUI monitoring remains unverified.
