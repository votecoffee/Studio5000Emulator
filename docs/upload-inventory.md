# Upload inventory and remaining contracts

Native upload is still incomplete. A successful object read establishes only
that object's response; it does not establish a complete Studio 5000 upload.

The retained SDK upload traces reach scalar Data Table and Symbol reads, then
device and network inventory. The Time Sync attribute list returns known
software clock fields alongside unavailable PTP fields. The SDK subsequently
requests Controller attributes before reporting a controller-collection
failure. The last incomplete object in a trace is therefore not sufficient
evidence to assign the failure to that object.

| Object | Supported behavior | Remaining contract |
| --- | --- | --- |
| Data Table and Symbol | Bounded model descriptors and supported atomic/UDT scalar and array values correlated to imported tag identifiers | Native compiled addresses, layouts and complete type upload |
| Template | Shared explicit UDT layouts and existing basic metadata | Family Type, Multiply Code, Recon Data and complete native type upload |
| Network inventory | Actual selected interface information and supported host counters | Device-specific fields without a host or source counterpart |
| Time Sync | Imported PTP configuration, unsynchronized status, empty PTP port set, software descriptions and current host UTC | PTP master, parent, identity and synchronization measurements |
| Controller | Supported source settings, run mode and programming lease state | Native handler-reference encoding and complete upload collection |
| Task | Bound native IDs, ordered Program references and explicit source settings/times | Execution slot, measured timing and complete native Task upload |
| Executable | Bound Program-scoped Routine IDs and limited legacy descriptions | Native type/UID mapping, compiled addresses/bodies and complete native Routine upload |

Version `.99` adds [backed atomic-array storage](atomic-array-storage.md).
The native array-demo upload now passes its Data Table metadata/value read and
linked Symbol descriptors, advancing from 167 to 200 verified signed requests.
It still fails later Controller collection; this is a narrower demonstrated
improvement than a complete upload.

Version `.100` adds [structured storage](structured-storage.md) with independent
TCP readback and queued external writes. The native UDT project upload fails
earlier at Template attributes 6, 7 and 8 and does not exercise these new reads.

Isolated prior diagnostic profiles supplied hypothetical PTP descriptions or
made the clock object unavailable; both still failed controller collection.
Those hypotheses are excluded from application behavior. New upload changes
should be tested separately against the same source before combining them
with download or online-edit changes.

A current-source handler matrix varied only the two absent Controller handler
references. Two-byte and twelve-byte null-reference hypotheses changed the
final attribute list from partial failure to success at the CIP response
level. All three cases still failed the SDK upload after the same two terminal
Controller requests, with no further native request after that list. These
private hypotheses establish neither the correct `POINTER` representation
nor a unique cause for the collection failure; they are excluded from the app.

A further isolated experiment combines a two-byte absent-handler hypothesis
with Controller Get All in the installed definition's six-field order. The
Get All read succeeds and returns twelve bytes; the SDK no longer sends the
fallback attribute list, but upload still fails controller collection after
196 verified signed requests. Source/model state is unchanged, and native
Offline/endpoint cleanup are confirmed without a fatal SDK fault. This proves
the combined experiment was exercised; it does not validate the guessed
handler representation. The experiment remains outside application behavior.

An audit of every nonzero inner reply in that baseline found 48 class-revision
discovery failures, two motion-catalog class-count failures, four unsupported
energy probes followed by supported empty fallbacks, one expected absent
Safety Controller object on the standard controller, and the three partial or
unsupported Time Sync/Controller reads described above. The SDK continued
after the early discovery failures. No Program read failed in those traces;
complete native Task, Executable, Memory, Fault Log, CST and Wall Clock upload
contracts remain separate work.

## Native address-cache checks

The installed SDK documents its explicit build method as v37-or-newer only,
so it is not invoked as a v35 cache-repair step. A private comparison advertises
the captured Table/Symbol class revisions while retaining instance data and
permissions. The typed tag read still fails `RxDA_E_NO_ONLINE_ADDRESS`; native
upload still fails Controller collection. An earlier changed-download-UID
comparison failed Go Online with `RxCL_E_CANNOT_UPLOAD_PHYS_ADDR`. Combining
that UID change with the captured class revisions instead reaches Online,
but the typed tag read still fails `RxDA_E_NO_ONLINE_ADDRESS`. These cases
preserve source/model state and confirm native Offline/endpoint cleanup
without a fatal SDK fault. Neither override is
part of application behavior. Supported model descriptors and array values
remain distinct from native SDK address-cache population.

## Source Controller flags

Controller instance 1 exposes three additional read-only configuration fields:

| Attribute | Controller L5X source | Wire value |
| --- | --- | --- |
| 15, Serial Number Match | `MatchProjectToController` | One byte, 0 or 1 |
| 17, Automatic Firmware Update Inhibit | `InhibitAutomaticFirmwareUpdate` | One byte, 0 through 255 |
| 23, Can Use Producer Provided RPI | `CanUseRPIFromProducer` | One byte, 0 or 1 |

The v35 Controller ADF defines all three fields as `BITS8`. Complete source
exports supply their values; missing, malformed, ambiguous or context-only
declarations remain unavailable. Individual reads and ordered attribute lists
use the same values, preserve duplicate requests and do not pad the byte fields.
The firmware value is retained as a source byte without interpreting its bits.

These reads do not enforce project serial matching, perform firmware updates
or negotiate producer I/O rates. Setters remain unsupported. The Controller's
Common ASA Class 1 declaration supplies only its revision; it does not justify
adding generic maximum-instance/count fields or guessing an aggregate
Controller response while handler-reference encoding remains unresolved.

## Software system time and offset

Time Sync instance 1, attribute 28 exposes the relationship between the
emulator's system time and local software clock. Both use the same host UTC
clock, so their offset is zero. The v35 `cip067r03v01.adf` and
`cip067r04v01.adf` layouts put the signed 64-bit system offset first, then the
signed 64-bit system time in microseconds. The values are little endian.

Attributes 3, 4 and 28 share one host time snapshot in an attribute-list read,
including duplicate attributes. Attribute 3 and attribute 28 use microseconds;
attribute 4 uses nanoseconds. A failed or unrepresentable host clock sample
returns attribute unavailable rather than a fabricated zero timestamp. Each
unit retains its own range check, so nanosecond overflow does not hide a
representable microsecond value.

The zero system-to-local offset is not an offset-to-master measurement. The
emulator remains unsynchronized, exposes no PTP ports, does not set or
discipline the host clock, and makes no accuracy claim. Host clock adjustments
remain visible; deterministic PLC scan time remains independent.

Protocol tests cover field order, units, duplicate-list coherence, clock
failure, integer limits, denied setters and unchanged simulation values.
Native SDK upload and Studio GUI acceptance require separate checks.
