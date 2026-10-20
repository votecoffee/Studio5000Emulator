# Temporary native Template models

Version `.76` adds [member definition inspection](template-layout-inspection.md)
without enabling native storage mapping or device execution.

This describes the `.71` milestone. Version `.72` adds
[temporary Diagnostics Message models](diagnostic-staging.md) and publishes both
model sets atomically; failure in either leaves both empty. Full execution stays denied.

Version `0.6.0-connectivity.71` builds temporary Template (`0x6C`) objects from
the [decoded device batch](device-payload-inspection.md). This validates the
observed Create, Set Attribute List and contiguous definition-write profile.
Definitions stay opaque and are never installed into the active type catalog.
Device-operation service `0x06` still returns execution denial `0x0F`.

## Supported profile

Only unqualified controller-scope Template instances `1..4095` are modeled.
Create (`0x08`) supplies exactly one attribute: attribute 4 as a UDINT word
count. Set Attribute List (`0x04`) supplies each of attributes 1, 2, 5, 6 and 8
exactly once, in any order, with widths UINT, UINT, UDINT, UINT and USINT.
Attributes 1, 2 and 5 represent the structure handle, member count and structure
size, respectively. Their read meanings are documented in Rockwell's
[Logix 5000 Data Access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
page 52. The installed plain-text Template attribute description also identifies
attribute 6 as Family Type and attribute 8 as Recon Data. Both are retained
without assigning execution semantics. No vendor files are bundled.

Write (`0x4D`) carries a UDINT byte offset, UINT byte count and exactly that
many bytes. In the observed download profile, the assembled definition length
is `4 * attribute4 - 20`. This includes three more padding bytes than the
documented Template-read calculation `4 * attribute4 - 23`; the existing active
catalog's read representation is unchanged. This observation does not establish
a general controller programming specification.

The model requires Create before attributes and attributes before writes.
Duplicate creation/attributes, missing objects, zero or oversized writes,
overlaps, holes, trailing bytes, incorrect lengths and incomplete definitions
fail. A failure in any supported record discards the whole tentative Template
model, including objects already completed in that batch. Other object classes
and unknown Template services are counted as unsupported and never dispatched.
Compiled members, names, type references and their runtime meaning remain
uninterpreted.

## Limits and lifecycle

Each model is limited to 1,024 Templates, 65,536 definition bytes per Template,
1 MiB total declared definition bytes, 4,096 members and 1 MiB structure size.
Each write carries at most 16,384 bytes. Limits are checked before extending
the temporary buffers; the container and record limits also apply.

The transport's `template_staging` summary reports status, Template count,
definition bytes, write fragments, modeled records and unsupported records.
It omits instance IDs, handles, names, attributes and definitions. The immutable
completed models remain private to the current assembly. Invalid results retain
only a fixed reason and an empty model. Repeated inspection uses the cached
result.

All transport/lease cleanup paths and assembly expiry clear these models.
`definitions_exposed`, `active_catalog_replaced` and `commit` remain false.
Inspection still reports zero executed records. The SDK probe requires any
advertised Template stage to be empty at admission and cleanup.

## Validation and remaining work

The normal-source SDK download attempt decodes 904 batch records and models all
242 Templates: 242 Creates, 242 attribute lists and 243 writes containing
346,596 definition bytes. One definition spans two writes. The remaining 177
records are counted as unsupported. The request still fails with
`RxCsE_DOWNLOAD_OF_DEVICES_FAILED`, then returns Offline with the source/model
unchanged and all temporary stages empty.

Synthetic tests exercise fragmented and multiple objects, reordered attributes,
capacity limits, malformed requests, ordering, duplicate IDs, holes/overlaps,
late atomic failure, source/owner guards, cached errors, summary privacy and
lifecycle cleanup. Native testing confirms this profile against the public SDK;
it does not establish complete download or Studio GUI monitoring.
The 949-test suite passes on Windows with two expected skips and Linux with
one expected skip.

The rebuilt `.71` runtime's application modules and served webpage match source.
The Windows executable's embedded version, webpage and new staging module were
checked separately. The running endpoint passes 291 wire checks. Its public SDK
probes report:

| Probe | Verified signed requests | Native outcome |
| --- | --- | --- |
| Connection | 81 | Nine steps succeed, including Go Online and Go Offline |
| Tag reads | 83 | Address discovery fails before value reads |
| Upload | 197 | Controller-collection upload still fails |
| Download | 181 | 242 temporary Templates modeled; batch execution denied |

All four probes confirm Offline cleanup, unchanged source/model and empty
temporary state. Final state has zero TCP clients, an uninhibited free lease,
idle preparation, closed transport, empty fragment/inspection/Template stages,
zero scans and zero model time. The communications and SDK services remain
running. No active Template catalog, tag value or project was replaced.

Next work covers the batch's Symbol, Data Table, Program, Routine and other
object contracts, reference validation, the remaining transfer stages and an
atomic model commit. Native upload/download, online tag monitoring and online
edits remain unfinished.
