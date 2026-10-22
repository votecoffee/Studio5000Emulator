# Local software-clock identity

Version `.152` adds two read-only Time Sync fields for the emulator's local
software clock. They identify the running application independently of the
controller compatibility identity and the loaded ACD.

## Identity and lifetime

The eight-byte identity is derived from SHA-256 of a fixed application namespace
and the application instance ID. Its first byte marks local administration.
It is generated locally, carries no assigned manufacturer OUI and is not a
network adapter address or an identity copied from a controller capture.

Reads, project reloads and endpoint reconfiguration retain the same identity
within one application lifetime. A new application instance receives a new
identity. Missing or malformed instance IDs leave these fields unavailable;
they never produce a zero fallback identity. Project files are not modified.

## Wire contract

Time Sync class `0x43`, instance `1`, supports Get Attribute Single (`0x0E`)
and ordered Get Attributes List (`0x03`) for the additional fields:

| Attribute | Value |
| --- | --- |
| 10, Local Clock Information | Eight-byte identity followed by six little-endian 16-bit fields |
| 105, Clock User Description | The same identity followed by two USINT-counted empty strings |

Attribute 10 uses Clock Class `248`, Time Accuracy `0xFE` (unknown), Variance
`0xFFFF` (not computed), an invalid/unassigned UTC offset of zero, clear time
property flags, and Time Source `0xA0` for the internal software clock model.
The clear flags assert no valid UTC offset, leap announcement, PTP timescale
or time/frequency traceability. This is local software-clock information;
neither an observed PTP master nor measured clock accuracy is supplied.

Attribute 105 carries unassigned user and physical-location text, consistent
with the existing empty attribute 23. The wire sizes are exactly 20 and 10
bytes, respectively, before their CIP response headers. A list preserves
order and duplicate fields. Mixed time/identity lists retain the existing
single host-time sample per request.

The installed plain v35 definitions establish the field layouts and IDs.
Rockwell's [TimeSynchronize reference](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/input-output-instructions/access-the-timesynchronize-object.html)
documents the Local Clock Information structure. Nokia's
[IEEE 1588 local clock parameter table](https://documentation.nokia.com/sr/22-10/pdf/Basic_System_Configuration_Guide_22.10.R1.pdf)
independently describes the unknown-accuracy and uncomputed-variance codes.
The generated identity and its lifetime are emulator design choices.

## Behavior and limits

Endpoint `time_sync.software_clock` metadata exposes this identity and its
scope. State polling and static reads do not sample or set the host clock.
PTP remains unsynchronized with zero ports, regardless of the imported PTP
enable setting. Master/parent identities, offsets, delays, domain, clock type,
manufacturer OUI and vendor device/port structures remain unavailable. Writes
retain their errors and acquire no programming authority.

These reads do not complete upload, download or native clock discipline.
Validation keeps the normal application separate from private upload fixtures.

## Validation

All 195 affected checks pass. Cases cover identity lifetime and app separation,
missing/malformed instance IDs, exact field sizes and unknown-quality values,
ordered/duplicate lists, one shared time sample, exposed endpoint metadata,
source/model/audit preservation, unknown master fields and retained write denial.

The rebuilt `.152` passes signed and direct identity reads, mixed-list checks
and the complete 32-field Time Sync query with twelve remaining unavailable
fields. The normal SDK Go Online/Offline case verifies 74 requests, confirms
Offline/cleanup and reports no SDK fault. Webpage, executable and appliance
versions match. The original project and zero-scan Program state are preserved.

The normal native upload verifies 191 requests and receives both new fields
with successful statuses and exact matching hashes. It proceeds from the
partial Time Sync list to Controller Get All, whose modeled legacy response
succeeds at the CIP layer, then reports
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`. This does not establish the
cause of the native collection failure or complete project reconstruction.
Offline/cleanup, original source/model preservation and no SDK fault are
confirmed. No private clock overrides or upload-save trial are used.
