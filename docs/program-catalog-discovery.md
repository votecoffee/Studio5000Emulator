# Program-scoped catalog discovery

Version `.125` supports empty `Get Instance List` (`0x4B`) replies for four
catalogs below a source-bound Program (`0x68`) object.

| Child class | Catalog | Required complete-source absence |
| --- | --- | --- |
| `0x331` | Digital Alarm | Alarm types, data and configuration |
| `0x332` | Analog Alarm | Alarm types, data and configuration |
| `0x36E` | HMI Button Control | HMIBC types, data and parameters |
| `0x8D` | Message | MESSAGE types, data and parameters |

The path contains the original native Program ID followed by the child class
and starting instance. An empty list returns `CB 00 00 00` for zero and nonzero
cursors, without inventing an instance, count or stored definition.

## Availability

The loaded L5X must match its original ACD Project and Program bindings. The
parent must resolve to an ordinary Standard nonfolder Program with complete
source configuration and explicit scheduling eligibility. Unknown Programs
return an unknown-object error. Missing or stale source bindings withhold the
catalog; Safety Programs and unsupported Program kinds do not gain access.

Each catalog independently checks the original complete Controller source,
including Program and AOI declarations before runtime filtering. Configured,
protected, ambiguous or incomplete source does not prove absence. The checks
are conservative across the whole project: an object in another Program can
withhold an empty reply here. An Alarm declaration does not by itself create
an HMI Button or Message object.

Only list reads are added. Symbolic/mixed parent paths, missing cursors,
attributes on lists, extra payload and unrelated parent scopes retain errors.
Configuration, execution, nonempty definitions and writes remain unsupported.
The existing signed read-only policy admits the list operation without
granting a programming lease or enabling network tag writes.

The `alarm_catalog`, `hmi_button_catalog` and `message_catalog` API descriptions
identify their Program classes and required source binding.

## Offline trace inspection

Previously, the transfer analyzer depended entirely on the live path decoder.
A valid request with an unsupported parent/child combination could disappear
into its unparsed-event count. Version `.125` falls back to the existing offline
object-path inspector for well-framed scoped paths.

The report retains numeric parent and leaf objects, response status, ordering
and request counts. Unsupported scopes have an explicit `object_path` and
`dispatch_path_supported: false`; distinct parent paths stay distinct in
aggregate object counts. Malformed paths remain unparsed and mark analysis
incomplete. Unknown scoped collections are not decoded as global collections.
Symbol names and raw payloads are not added to the report. Offline recognition
does not change live routing or infer why the SDK failed.

## Evidence and limits

The saved successful v35 upload contains empty Program-scoped Digital Alarm,
Analog Alarm and HMI Button Control lists for 20 Programs each. Seventeen
Program Message lists are empty; configured Message lists remain separate.
This is offline evidence and initiates no controller connection.

Reanalysis of the isolated `.124` upload identifies the Digital Alarm request
immediately after successful Program-scoped Data Table discovery. Its status
`4` was omitted by the earlier analyzer. With the two alarm classes added, the
first isolated `.125` attempt accepts both lists and advances to a rejected
HMI Button Control list. It confirms Offline/cleanup, unchanged source/model
and no reported fatal SDK fault, while still failing full Program upload.

The final `.125` attempt accepts all four added scoped lists and advances
through Program collection, alarm-set/condition discovery and into module
collection. It then reports `RxCsE_UPLOAD_DIAGNOSTICS_MESSAGES_FAILED`. The next
rejected operation is the controller-scoped device diagnostic message list,
class `0x3B2`, status `0x0F`. All 215 native verified signed requests retain
Offline/cleanup, unchanged source/model and no reported fatal SDK fault.
The corrected trace analyzer accounts for 218 expanded leaf requests with no
unparsed events. These counts measure different layers.

Progress beyond the Program collection stage does not verify reconstructed
Routine logic or produce a completed uploaded project.

The isolated diagnostic uses an owned project, its source-bound Template
snapshot and unshipped clock/revision hypotheses. Release clock behavior is
unchanged. Successful inventory reads do not establish native project
reconstruction, complete uploads/downloads, GUI monitoring or the full
Test/Untest/Assemble lifecycle.

The restarted released `.125` demo passes SDK Go Online/Go Offline across 75
verified signed requests, confirming Offline/cleanup, unchanged source/model
and no reported fatal SDK fault. All 245 focused software checks and 63 live
readback checks pass; the full suite was not rerun. The deployed 88 app modules,
served webpage, packaged assets and Windows executable version match `.125`.
