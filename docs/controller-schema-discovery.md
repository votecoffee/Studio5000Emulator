# Supplemental schema discovery and Wall Clock Time

Version `.116` adds read-only metadata and time reads used while investigating
native v35 upload. Complete native project upload remains unfinished.

## Supplemental class revisions

In the experimental native compatibility profile, Message Router discovery
includes these additional class-only interfaces:

| Class | Schema revision | Supported read |
| --- | --- | --- |
| `0x66` | 3 | Class attribute 1, UINT |
| `0x72`, UserMemory | 5 | Class attribute 1, UINT |

Get Attribute Single and Get Attribute List return the same two-byte revision.
The completed reference recording contains seven successful UserMemory class
reads and seven successful single-attribute revision reads for `0x66`. The
installed v35 UserMemory definition independently identifies `0x72` and its
revision. Class `0x66` instance semantics remain unimplemented and unnamed in
the API. A schema number does not establish controller execution equivalence.

Only class instance zero is supported. Unknown class attributes return `0x14`,
including per-field errors in mixed lists; nonzero instances return `0x05`.
Instance counts, pool sizes, addresses, allocation and other instance services
remain unavailable. Neither ordinary tag-write access nor a signed read grants
those operations. These two classes remain absent from the research profile.
Connectivity metadata describes the subset under `controller_schemas`.

## Native Controller and Time Sync layout selection

Version `.153` selects the observed v35 schemas for two existing objects in
the experimental native compatibility profile:

| Object | Class | Native schema revision | Research profile revision |
| --- | --- | --- | --- |
| Controller | `0x8E` | 15 | 1 |
| Time Sync | `0x43` | 5 | 1 |

Seven paired successful reference class reads establish each revision as a
two-byte UINT. Single and ordered/duplicate list reads return the selected
value. Endpoint object metadata reports the same revision as the wire.
`controller_schemas.compatibility_classes` identifies these layout selections
separately from the two supplemental class-only interfaces above.

These numbers select the v35 response schema for native clients. They do not
assert complete instance support, firmware equivalence or support for every
field in that schema. Source-bound settings, unavailable memory/signature and
PTP fields, programming permissions and the research profile remain governed
by their existing implementations. Invalid parent-scoped paths and setters
retain errors. Native clock and Controller reads remain read-only except for
separately authorized mode and supported edit services.

The seven reference Controller Get All responses also use the existing
16-byte [legacy aggregate](controller-handlers.md#aggregate-profile). Its
framing is retained; a revision selection does not replace it with a newly
invented aggregate. Stored ACD component formats are separate from these CIP
schema revisions and are not substituted for them.

The earlier private schema-selection trials are historical evidence, not
complete upload acceptance. Native transfer success requires its own checks.

## Read-only Wall Clock Time

Wall Clock Time class `0x8B` is available in both endpoint profiles. Its class
attributes report schema revision 4 and maximum instance 1 as UINT values.
Instance-one Get Attribute Single and Get Attribute List support:

| Attribute | Data | Availability |
| --- | --- | --- |
| 1 | Eight-byte legacy microsecond counter from 1972-01-01 | Proven legacy UTC source; host time at or after that epoch |
| 2, 4 | Two-byte legacy adjustment settings, both zero | Proven legacy UTC source |
| 5 | Seven 32-bit legacy calendar fields | Proven legacy UTC source |
| 6, 11 | Eight-byte UTC microsecond counter from 1970-01-01 | Representable host time |
| 7 | Seven 32-bit UTC calendar fields | Representable host time and calendar |

Calendar fields contain year, month, day, hour, minute, second and microseconds.
One host `time.time_ns()` sample supplies all requested time fields in a read,
including duplicates. Conversion uses integer arithmetic; the two epochs differ
by 63,072,000,000,000 microseconds. These reads are independent of deterministic
scan time, and host clock adjustments remain visible.

Legacy UTC requires a complete canonical Controller L5X with exactly one
`WallClockTime` declaration, explicit `TimeZone="0"` and
`LocalTimeAdjustment="0"`, and no ambiguous/context/opaque settings. Missing,
nonzero or uncertain source disables legacy local fields while preserving the
independent software UTC reads. A clock failure does not become a fabricated
zero; a counter outside the calendar range can remain readable while calendar
fields return unavailable. Connectivity metadata exposes this boundary under
`wall_clock_time` without sampling the clock during state polling.

The installed v35 definition and successful reference reply distinguish the
legacy and UTC fields. Rockwell's [UTC conversion notice](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/studio-5000-logix-designer/navigating-the-application/-product_name_rsl5k--application-main-window/notification-or-error-messages/wall-clock-time-converted-to-coordinated-universal.html)
also explains the change from local 1972 time to UTC 1970 time. Its
[WallClockTime instruction reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-wallclocktime-object.html)
documents the UTC counter and calendar components.

CST offsets, timezone strings, DST parameters, setters and class Get All remain
unavailable. The feature does not add GSV/SSV instruction execution, a PTP
engine, physical clock settings or clock discipline. The emulator never sets
the host clock through this interface.

## Native checks

The public two-schema candidate returns both revision queries successfully;
its SDK upload still fails `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED` across
197 verified signed requests. A private comparison with complete generated
clock data still fails. A further private revision-selection comparison reaches
a previously unsupported Wall Clock read, motivating the implementation above.
Those generated clock datasets and substituted Time Sync/Controller revisions
are not shipped.

The final public-source candidate, including Wall Clock discovery, verifies 196
signed requests and retains the same device-collection upload failure. All five
isolated comparisons confirm native Offline, endpoint cleanup and source/model
preservation without a reported fatal SDK fault. The result does not establish
an individual failure cause or native project upload acceptance.

The original Conveyor project completes a separate SDK Go Online/Go Offline
check on the restarted `.116` runtime with 75 verified signed requests. Source
and model remain unchanged, cleanup and Offline are confirmed, and no fatal
SDK fault is reported. This connection check does not establish upload,
download or the full online-edit lifecycle.

The shared offline collection decoder also frames Wall Clock attribute lists,
including the unsupported runtime fields when present in recorded replies.
Default reports retain lengths and hashes rather than recorded clock values.
