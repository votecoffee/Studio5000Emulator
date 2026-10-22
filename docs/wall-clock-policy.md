# Software Wall Clock policy

Version `.156` adds the four remaining Wall Clock Time fields for the existing
complete-source legacy UTC profile. The runtime uses an explicit UTC policy
with daylight saving disabled, and an application-lifetime monotonic counter
provides its software coordinated-time reference.

## Policy and source boundary

A complete, unambiguous `WallClockTime` source declaration must specify legacy
`TimeZone="0"` and `LocalTimeAdjustment="0"`. Absent, nonzero, context-only or
opaque declarations retain the unsupported local-time fields. Host UTC reads
remain available independently, as before.

The accepted legacy declaration selects the emulator's runtime UTC policy;
it does **not** prove the saved extended `DSTAdjustment`, `ApplyDST` or time-zone
string. Those settings are not imported. The original ACD/L5X stays unchanged.
The API exposes `local_time_policy` and
`source_extended_timezone_dst_imported=false` to distinguish these values.

## Wire contract

Wall Clock Time class `0x8B`, instance `1`, supports the existing single and
ordered-list read services. Its revision remains 4.

| Attribute | Software value |
| --- | --- |
| 3, CSTOffset | UTC microseconds minus the sampled application elapsed counter |
| 8, TimeZoneString | UDINT byte count followed by UTF-8 `UTC+00:00 Coordinated Universal Time` |
| 9, DSTAdjustment | Two-byte signed zero minutes, chosen by runtime policy |
| 10, ApplyDST | One-byte false, chosen by runtime policy |

The coordinated counter starts with the application, uses elapsed
`time.monotonic_ns()` microseconds, and survives project replacement and reset.
It advances independently of Program/Run mode and deterministic scan time.
One Wall Clock list samples host UTC and the coordinated counter once;
duplicates reuse the resulting values. The relation is:

`coordinated elapsed microseconds + attribute 3 = UTC attribute 6`

Attribute 1 retains its separate legacy 1972 epoch. The offset is related to
the modern 1970 UTC counter, not that legacy value. Host wall-clock steps
change the offset without resetting the monotonic counter. Clock errors,
backward/invalid monotonic samples or a negative/unrepresentable relation
withhold attribute 3 rather than supplying a fallback zero.

Static policy reads and API state polling sample neither clock. All clock,
time-zone and DST setters remain denied. This software counter does not
expose a native CST object or GSV attribute, establish a synchronized chassis
clock or discipline the host.

Rockwell's [WallClockTime reference](https://www.rockwellautomation.com/en-be/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-wallclocktime-object.html)
defines the offset relation and DST units. The
[E300 Wall Clock Time object table](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/193-um015_-en-p.pdf)
documents the UDINT-counted time-zone string and `UTC+hh:mm` syntax. The
[controller Date/Time dialog reference](https://www.rockwellautomation.com/en-au/docs/studio-5000-logix-designer/37-02/contents-ditamap/studio-5000-logix-designer/controller-properties/editing-controller-properties/controller-properties-dialog-box---date-time-tab.html)
describes controller-local display and externally supplied zone strings.
The monotonic counter lifetime and selected UTC policy are emulator design
choices. Wire framing is independently checked by the offline collection decoder.

## Validation scope

Focused checks cover all eleven fields, exact UTC/legacy epoch distinctions,
paired samples and duplicates, counter lifetime, host time steps, invalid
clock/range handling, API metadata, signed TCP replies, denied setters and
source/model/audit preservation. Native SDK acceptance remains a separate
check from these software-model and protocol checks.

On the rebuilt `.156`, all 218 focused checks and live signed eleven-field
reads pass. SDK Go Online/Offline verifies 75 requests. Normal upload verifies
349 requests, passes both clock collections and reaches Program/Routine
metadata before `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`; its final Routine metadata
list returns all 22 requested fields with successful CIP status. The native
Wall Clock reply preserves the epoch/counter relations and UTC policy.

An independent empty-routine fixture verifies 355 requests and gets past
Programs before PLC file-mapping discovery fails. It uses the public runtime
without private protocol overrides. These fixtures differ in other project
metadata too, so this comparison does not prove a sole cause of the populated
Routine failure. No saved upload is validated.

The SDK/web Run/Program cycle verifies 108 requests and six expected audit
updates. The elapsed counter continues across modes and project reload, while
the original demo is restored to stopped Program mode with zero scan/audit
state. All four native cases confirm actual Offline/cleanup and no reported
SDK fault. Webpage, executable and appliance versions match `.156`.
