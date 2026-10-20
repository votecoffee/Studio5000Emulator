# Nested I/O Connection class discovery

Version `.60` adds [programming coordination](programming-coordination.md) and
one source-backed Local root link-address field. The notes below describe the
`.59` class-discovery milestone and its then-current limits.

Version `0.6.0-connectivity.59` recognizes the I/O Connection class path below
the root I/O Map namespace:

```text
I/O Map (0x69), instance 1 / I/O Connection (0x7E), instance 0
```

The native v35 SDK requests this path while discovering class revisions, even
for a controller-only project. The saved successful reference exchange and the
owned demo ACD's offline component collection both establish this nested path.
Vendor files and captured project data are not distributed.

Previously the live parser rejected its second class segment as a duplicate.
It now preserves the numeric parent as `io_map_instance`, independently of
`program_instance`. Only the two supported Program child classes and this I/O
Map child class are recognized; arbitrary repeated classes, missing child
instances, mixed scopes and deeper nesting remain invalid.

## Supported reads

The I/O Connection class exposes attribute `1`, revision `1`, as a two-byte
UINT through Get Attribute Single (`0x0E`) and Get Attributes List (`0x03`).
This is the software class revision; it does not copy the reference controller's
firmware class revision. List replies retain per-attribute status, so unsupported
fields receive `0x14` and the list receives `0x0A`.

Availability requires the existing complete-source check proving no external
I/O modules, I/O tags, force data or ambiguous declarations. Empty `Modules` or
the supported matching `Local` controller module are accepted. Configured or
unavailable source returns `0x0C`; loading another project recomputes availability.

The global `0x7E` path, another I/O Map parent or a nonzero I/O Connection
instance returns `0x05`. Symbolic scope and malformed requests retain errors.
The signed native session must be bound before these reads are dispatched.
Setters remain denied, including in signed batches.

The root namespace does not create a module instance or connection. I/O Map
instance attributes, I/O Connection instances, connection counts, instance
lists, Get Attributes All, data addresses, RPI configuration and I/O execution
remain unsupported. The existing empty external-module catalog is unchanged.

## Diagnostics

The `io_map` connectivity field reports `connection_class_revision` and
`connection_class_parent`, or `null` when source is unavailable. Attribute gaps
and native policy rejections preserve `io_map_instance` without recording
payloads or symbols. The Connectivity webpage displays the parent alongside
the child class and instance. This prevents a nested failure from being
presented as a controller-scoped request or an unparsed path.

## Validation boundary

Eight added tests cover path widths, malformed and mixed scopes, exact replies,
source availability and replacement, diagnostics, retained module/write denials,
and real signed TCP single/batch requests. A failed child request does not break
the signed counter or prevent subsequent valid reads. The 825-test suite passes
on Windows and Linux, with two Windows skips and one Linux skip.

An isolated normal-source native SDK probe accepts the nested revision response
and passes all nine connection/Offline cleanup steps. Upload still fails with
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`; its trace retains the incomplete
Time Sync list. Across those two probes, 280 signed requests verify, and the
former nested-path rejection is absent. Modeled values and scan count remain
unchanged. This closes a demonstrated protocol gap without establishing full
upload, native tag-address discovery, programming or Studio GUI monitoring.

The rebuilt and restarted `.59` appliance passes 248 wire checks. Its embedded
version, served web assets and deployed source hashes match the release. The
deployed public SDK connection probe passes all nine steps with 82 verified
signed requests. Separate tag and upload probes verify 84 and 198 requests;
the upload accepts the nested revision response and retains 12 scalar reads
and 12 Symbol descriptors. Both tag reads still fail before a tag-read packet
is sent, with `RxDA_E_NO_ONLINE_ADDRESS`.

A fresh private public-SDK download probe verifies 96 requests and still fails
with `RxCsE_ASA_INVALID_IOI_SEGMENT_TYPE`. The trace also contains a different
unsupported nested path: Controller `0x8E`, instance `1` / Semaphore `0x74`,
instance `1`, service `0x4B`. Its error alone does not establish the SDK's root
failure or the semantics of a programming session. That service is unimplemented.
All four probes confirm Offline cleanup and preserve the original ACD, modeled
values, scan count and scan time. Client connections close, both application
write gates remain disabled, and no Windows service is reconfigured.
