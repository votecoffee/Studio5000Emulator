# Connectivity development history

These entries retain the validation scope at each revision. They describe
historical experiments and do not extend the current compatibility claims.
See the [README](../README.md) for current status and usage.

Version `.149` adds [source-bound original metadata values](native-metadata-values.md)
from supported `Comments.Dat` records. Stored ValueType declarations drive the
string, numeric and reference readers, including ten observed locale profiles.
The immutable catalog preserves source targets and supplies simulator-local
record IDs. Signed query cursors are session/source-bound and response sizes
respect the native wrapper's budget. Original metadata does not describe edited
runtime logic, so nonempty reads become unavailable after a supported edit.
Project-specific source data remains private; two owned projects each match
1,638 shared built-in records from a saved upload. Complete native transfer,
Program `0x50` and download-result behavior remain unfinished.

Version `.148` adds [Metadata Definition `0x53` stream decoding](metadata-upload-query.md).
The reply header carries the echoed cursor, including zero in the initial
reply, rather than a total byte count. Bounded assembly retains exact fragment
order and selection; detached records retain target/context/qualifier words,
locales, definition and record IDs, string blobs, numeric arrays, reference
arrays and empty values. A saved reference's 10,301 selected query exchanges
consume as nine complete streams and 43,833 records. Capture and checkpoint
readers share frame diagnostics; the replay tool checks whole streams and
records. Reports omit values and IDs. Live metadata values, source mapping,
Program `0x50`, complete upload and the download result response remain
unfinished. No new native response is dispatched by this change.
All 183 focused checks pass. The rebuilt `.148` passes SDK Go Online/Offline
across 74 verified requests with actual Offline, endpoint cleanup and original
source/model preservation confirmed, and no reported SDK fault. All 101 source/
build/guest module hashes and webpage/executable/appliance versions match.

Version `.147` adds [original ACD Metadata Definition names and IDs](metadata-definitions.md)
to the read-only CIP catalog. The stored format-0 Name field must agree with the
component name, with one explicit collection and unambiguous active records.
ACD/L5X hashes bind the catalog to the loaded project. Unsupported records retain
the converted offline export without inventing a catalog. Class counts, cursor
discovery and Name reads do not implement metadata values or Program query `0x50`.
The SDK probe also recognizes `LgxSrv_E_UNHANDLED_EXCEPTION` as fatal immediately.
One hundred fifty-three focused checks pass. The original demo catalog contains
23 definitions; 26 live CIP checks verify every Name and ID plus class counts.
The native SDK connection/Offline case passes across 74 verified requests.
Download reaches the existing result-response gap across 175 requests. The
isolated upload comparison reaches the denied Program `0x50` query across 362
requests; its earlier Controller/clock/Task hypotheses remain unshipped. All
three trials preserve the source/model, confirm actual Offline and endpoint
cleanup, and report no SDK fault. The packaged reader executes successfully,
and all 100 source/build/guest module hashes and served versions match.

Version `.146` adds [offline Program service `0x50` framing](program-upload-query.md)
to capture and checkpoint reports. Sixty saved reference exchanges have the three
observed request selectors and one-record successful replies. Opaque words stay
hashed, and selector mismatches or unknown success shapes make checkpoint
analysis incomplete. An isolated Controller response-shape experiment reaches
this service, which the live app still denies. A subsequent private empty-reply
experiment faulted the native SDK; native Offline was not confirmed for that
trial. The source and model were preserved, the private endpoint was stopped,
and the main demo endpoint restored. Both response hypotheses remain unshipped.
This revision does not complete upload or change download's unresolved result
encoding. Experimental response trials stopped after the fault. Following
service recovery, the rebuilt `.146` passes the established SDK Go Online/
Offline path across 74 verified requests, preserving the source, model and audit
value with actual Offline and endpoint cleanup confirmed and no reported fault.
The executable, appliance and served webpage versions match, with all 99 app
module hashes checked. The decoder passes 118 focused checks. Mode and
supported-import validation remains on `.145`.

Version `.145` adds [Controller GSV reads](controller-gsv.md) for the
simulator AuditValue and explicit ChangesToDetect mask. Ladder and Structured
Text preserve all bits in LINT or two DINT elements, skip prescan/false paths,
validate the entire destination and retain scan rollback. FOR dependency checks
include both written words. Eighty-nine focused checks and native offline
save/reopen/export of a four-GSV fixture pass. Live scan results agree with
Controller attribute and symbolic CIP reads. SDK mode control passes across 109
verified requests, and supported NOP import/reconnect preserves GSV execution
across 182 requests. Download retains its result-encoding gap across 176
requests, preserving the model and audit value. Offline/cleanup and original
source preservation are confirmed, without a reported SDK fault. An initial
mode trial's HTTP transport failure remains separately recorded. The rebuilt
executable, appliance and served webpage versions match, with 99 app module
hashes checked. Full transfer and complete edit-lifecycle work remain unfinished.

Version `.144` adds a [simulator Controller Audit Value](simulator-audit-value.md).
An explicit supported source mask enables an execution-model epoch, stable reads,
selected successful mode changes and supported routine-transaction updates.
Detached preparation and repeated commits preserve the original value.
Unclassified faults withhold it until reset. The generator is simulator-owned;
no archived audit value or native signature is substituted. Fifty-eight pure
checks and 22 affected local runtime/protocol checks pass. The rebuilt executable,
appliance and webpage versions match, with all 98 app module hashes checked.
Normal-protocol SDK mode control passes across 108 verified requests with six
updates for six transitions. Supported Program-mode NOP import and reconnect
pass across 181 requests with one audit update. The isolated upload comparison
returns fields 27/28 successfully, leaving four Controller gaps across 361
verified requests and 364 leaves; private earlier-stage hypotheses remain
unshipped. Download retains its preparation-result gap across 175 requests,
without active model or audit-value change. All four SDK trials confirm actual
Offline/cleanup, unchanged originals and no reported SDK server fault.

Source revision `.143` adds [change-detection configuration reads](controller-change-detection.md)
and named Controller field gaps. An explicit canonical L5X ChangesToDetect
mask supplies the eight-byte Controller field 28 without inventing audit values,
memory percentages, event history or signatures. Missing, ambiguous and malformed
source declarations remain unavailable. Thirty pure source/in-memory checks
pass with process, worker and network starts prohibited and no resource-start
attempts. Native SDK acceptance, executable build and restart have not been
performed for this revision. `.142` remains the last native-validated build;
no reduction in native upload gaps is claimed for `.143`.

Version `.142` adds [Controller retention and diagnostic settings](controller-diagnostic-settings.md)
for attributes 10/35, plus strict offline Controller upload/connection-response
framing. The settings require complete canonical source declarations; missing,
ambiguous and unknown values stay unavailable. They do not enable switchover or
diagnostic delivery. Two new offline SDK save/reopen/export trials preserve
each changed setting in private ACDs without changing originals or contacting a
physical controller. One saved Controller bulk reference confirms the framing
widths, independently of value semantics or source association.
All 101 affected tests pass without a full suite run. The isolated SDK upload
accepts the two settings, leaving six Controller fields unavailable:
11/12/27/28/33/34. It also accepts the existing legacy 16-byte fallback, then
reports the attribute-list diagnostic across 361 verified requests and 364
expanded leaves. The complete interval frames without layout errors. Private
clock/schema/repository/Task-stack assumptions remain unshipped.
The normal-protocol SDK Program-mode NOP import and reconnect preserve the
settings, authority catalog and existing Task state across 181 verified requests;
the next scan executes normally. The independent download retains the result
response gap across 175 verified requests and 909 temporary records, without
active commit. All three cases confirm actual Offline/cleanup, original-file
preservation and no fatal SDK fault. Full native transfer and the complete
Test/Untest/Assemble lifecycle remain unfinished.

The restarted `.142` normal demo passes SDK Go Online/Go Offline across 74
verified requests with actual Offline/cleanup, preserved source/model and no
fatal SDK fault. All 26 deployment checks pass, including live Controller setting
reads and frozen source/shadow guards. All 97 deployed app modules match the
build. Served assets, packaged resources and webpage/executable versions agree
on `.142`; the model and edit configuration survive restart.

Version `.141` adds [explicit empty Security Authority Binding discovery](security-authority-discovery.md).
The original ACD must contain one checked format-0/body-74 collection with no
active binding definitions. The optional immutable manifest, original hashes,
atomic loader and appliance forwarding retain its source evidence. Missing,
nonempty, scoped and unknown profiles remain unavailable; original pointers,
authority administration and authentication decisions are excluded.
All 182 affected tests pass without a full suite run. The isolated SDK upload
uses the same private assumptions as the preceding stack-field trial. It now
accepts revision 1 and empty authority discovery, passes empty Data Logging and
reaches a later 21-field Controller attribute list. Eight fields remain
unavailable: 10/11/12/27/28/33/34/35. Upload fails with the attribute-list
diagnostic across 360 verified requests and 363 expanded leaves. The private
clock/schema/repository/stack substitutes remain unshipped. The normal-protocol
SDK Program-mode NOP insertion/reconnect preserves the new source binding and
existing Task state across 182 verified requests; the next scan executes the
changed model. The independent download retains the result-response gap across
175 verified requests and 909 temporary records, without active commit. All
three cases confirm actual Offline/cleanup, unchanged original files and no
fatal SDK fault. Full native transfer and the complete edit lifecycle remain
unfinished.
The restarted `.141` normal demo passes SDK Go Online/Go Offline across 74
verified requests with actual Offline/cleanup, preserved source/model and no
fatal SDK fault. All 24 deployment checks pass, including the live source-bound
authority list/revision and frozen strict reader. All 97 deployed app modules
match the build. Served assets, packaged resources and webpage/executable
versions agree on `.141`; model and edit configuration survive restart.

Version `.140` adds [Task Start Time](task-start-time.md), sampled from the
simulator WALLCLOCKTIME before scheduled Programs and committed only after a
successful whole-Task scan. Monotonic measurements remain independent. Unavailable
clock samples withhold only the current timestamp; prescan, reset and failed
scans do not invent or overwrite a successful timestamp. Reads do not resample.
All 185 affected tests pass, without a full suite run. The isolated SDK upload
accepts attribute 13 after one scan and leaves only fields 22/23 unavailable,
still failing Task collection across 358 verified requests and 361 expanded
leaves. A separate private stack-field hypothesis makes all 22 requested Task
fields readable and advances to Security Authority Binding (`0x36A`) discovery,
where the client fails with the SABO diagnostic after 359 verified requests.
The stack association and values remain unverified and unshipped. Existing
private clock/schema/repository hypotheses remain unshipped as well.
The normal-protocol SDK Program-mode NOP insertion and reconnect preserves
Start Time and the separate Task settings/status/slot/timing record across 183
verified requests. The next scan updates the timestamp. The independent download
retains its result-response gap across 176 verified requests and 909 temporary
records, with no active commit. All four cases confirm actual Offline/cleanup,
unchanged original files and no fatal SDK fault. Full native transfer and the
complete Test/Untest/Assemble lifecycle remain unfinished.

The restarted `.140` normal demo passes SDK Go Online/Go Offline across 75
verified requests with actual Offline/cleanup, preserved source/model and no
fatal SDK fault. All 22 deployment checks pass, including frozen Start Time
sampling, epoch and invalid-clock isolation. All 96 deployed app modules match
the build. Served assets, packaged resources and webpage/executable versions
agree on `.140`; the prior model and edit configuration survive restart.

Version `.139` adds [original stored Task configuration](stored-task-configuration.md).
Controlled offline SDK saves/reopens correlate the fixed format-18 layout with
Continuous/Periodic type, rate, priority, watchdog and Boolean changes. An optional
immutable native manifest retains only the supported static settings and checks
current Project/Task/Program bindings, source settings and ordered schedule.
Legacy manifests remain supported; runtime state is excluded. All 176 affected
tests pass, without a full suite run. The isolated SDK upload accepts all five
new fields, reducing unavailable Task fields from 8 to 3 across 358 verified
requests and 361 expanded leaves. It still fails Task collection. Actual Offline,
cleanup, unchanged originals/model and no fatal SDK fault are confirmed. Private
clock/schema/repository hypotheses remain unshipped; full transfer is unfinished.
The normal-protocol SDK Program-mode NOP insertion and reconnect retains all
five stored settings, Task status, slot and timings across 183 verified requests.
The next scan executes the changed logic normally. The source-matched download
retains the result-response gap across 176 requests and 909 temporary records,
without active commit. Both confirm actual Offline/cleanup, unchanged original
files and no fatal SDK fault; the supported import changes only its authorized
Routine in the custom execution model.
The restarted `.139` demo passes SDK Go Online/Go Offline across 75 verified
requests, confirming actual Offline/cleanup, preserved source/model and no fatal
SDK fault. All 21 deployment checks pass, including the frozen stored-record
reader and binding/legacy checks. All 96 deployed modules match the build;
served assets, packaged resources and webpage/executable versions agree on
`.139`. The prior model and edit configuration survive restart.

Version `.138` adds [serial Task status and registered execution slots](task-execution-state.md).
Known clean status and overlap reads use the single serial executor; an
unclassified simulator fault withholds them until reset. Slot lookup resolves
the current registry's actual Task object independently of CIP IDs and DWORD
references, rejecting changed registrations and foreign projects. All 158
affected tests pass; the full suite was not rerun. Native transfer remains unfinished.
The SDK upload accepts all three added fields, leaving 8 unavailable Task fields
across 358 verified signed requests and 361 expanded leaves. The comparison reuses
the exact-source `.137` control and identical private hypotheses, which remain
unshipped. A normal-protocol Program-mode NOP import and reconnect preserves
Task status, slot and timings across 183 verified requests. The source-matched
download retains the same result-response gap across 176 requests and 909
temporary records, without active commit. All three trials confirm actual
Offline/cleanup, preserved originals and no fatal SDK fault.
The restarted `.138` normal demo passes SDK Go Online/Go Offline across 75
verified requests, with actual Offline/cleanup and preserved source/model.
All 19 deployment checks pass, including frozen status, slots, fault history
and reset. All 95 deployed modules match the build; served/packaged assets and
webpage/executable versions match `.138`. The previous model and edit
configuration survive restart.

Version `.137` adds [whole-Task execution measurements and a backed Task reference](task-runtime.md).
Measurements cover all scheduled Program calls, commit only on a successful scan
and persist across supported Routine replacement. All 152 affected tests pass;
the full suite was not rerun. The matched SDK upload comparison reads five more
Task fields, reducing unavailable fields from 16 to 11. Both trials still fail
Task upload across 358 verified signed requests and 361 expanded leaves, with
actual Offline/cleanup, preserved source/model and no fatal SDK fault. Private
clock/schema/repository hypotheses remain unshipped. Full transfer and the
nonempty Routine source-retrieval boundary remain unfinished.
A separate SDK Program-mode NOP insertion and reconnect preserve nonzero Task
measurements across engine replacement; the next scan updates them normally.
All 183 signed requests complete with actual Offline/cleanup, unchanged original
files and no fatal SDK fault, using the normal protocol behavior.
The restarted normal demo passes SDK Go Online/Go Offline across 75 verified
signed requests, confirming actual Offline/cleanup, preserved source/model and
no fatal SDK fault. All 17 deployment checks pass; all 95 deployed modules and
served/packaged assets match the `.137` build. Webpage and executable versions
agree, and tags, logic, tasks, mode and edit configuration survive the restart.

Version `.136` supports [scheduled empty Programs](empty-programs.md) with
source-proven no-op execution, null main references, live Program references
and existing fault/edit guards. All 121 affected tests pass; the full suite was
not rerun. The isolated empty-Program upload advances from a 204-request Program
collection failure to later PLC file-mapping collection across 357 verified
signed requests. Both retain actual Offline/cleanup, unchanged source/model
and no fatal SDK fault. Private clock/schema experiments remain unshipped.
Full native transfer and the nonempty Routine upload boundary remain unfinished.
The corrected single-NOP Routine upload reproduces that boundary across 357
verified signed requests. Two source-matched downloads reach the result-response
gap across 176 requests each, retaining 907/909 temporary records. A private
empty-`0x6E` comparison advances to Task collection across 358 requests; that
substitute remains unshipped. All six retained comparisons confirm actual
Offline/cleanup, unchanged originals/model and no fatal SDK fault.
The restarted `.136` demo passes SDK Go Online/Go Offline across 75 verified
signed requests, confirming actual Offline/cleanup and unchanged source/model
without a fatal SDK fault. All 13 deployment checks pass, including the frozen
empty-Program implementation. All 94 deployed modules match the build; served
assets, packaged resources and webpage/executable versions match `.136`.
Tags, logic, tasks, mode and edit configuration are preserved across restart.

Version `.135` adds [separate offline upload merge targets](upload-merge-targets.md)
to the native acceptance probe. The SDK input is independently hashed while
backend checks retain the original emulator source pin. Both originals stay
preserved; only the private upload copy may change, with a matching SDK artifact
receipt required for success. Other operations keep their copy-preservation
checks. Missing-file evidence cannot suppress cleanup, and transfer comparisons
now include available Routine, Task, entry and controller state.
Three isolated `.134` trials retain 357/88/357 verified signed requests and
360/91/360 expanded leaves. The unrelated target is incompatible before Routine
upload. The original and same-project offline NOP targets reach the same
successful 22-field Routine reply, then fail Program upload without source reads.
The NOP target preserves source-key bytes, so no cache bypass is established.
All confirm actual Offline/cleanup, unchanged originals/model and no fatal SDK
fault; no physical-controller contact or live transfer authority is added.
All 92 affected tests and 12 deployment checks pass; the full suite was not
rerun. The restarted `.135` demo passes SDK Go Online/Go Offline across 75
verified signed requests, with actual Offline/cleanup, unchanged source/model
and no reported fatal SDK fault. Inputs, logic and edit settings match across
restart. All 94 deployed app modules, served assets and executable resources
match the build; the webpage and executable report `.135`.

Version `.134` adds [shared Routine metadata comparison diagnostics](routine-metadata-comparison.md)
to capture and checkpoint reports. Missing and failed values stay unknown;
complete profiles compare all fields except header references, original instance
IDs and opaque source-key metadata. All 809 saved replies form two comparable
groups and have null Code Addresses. Both isolated `.133` SDK trials match a
reference nonidentity profile but still fail Program upload before any `0x3A`
source request. The address-range change is exercised but not shipped. The
trials retain 357/358 verified signed requests and 360/361 expanded leaf requests,
with actual Offline/cleanup, unchanged source/model and no reported fatal SDK
fault. No physical-controller contact or live read/write authority is added.
All 162 affected tests and 12 deployment checks pass; the full suite was not
rerun. The restarted `.134` demo passes SDK Go Online/Go Offline across 75
verified signed requests, with actual Offline/cleanup, unchanged source/model
and no reported fatal SDK fault. Inputs, logic and edit settings match across
restart. All 94 deployed app modules, webpage, packaged assets and executable
version match `.134`.

Version `.133` adds [read-only Routine upload-source decoding](upload-routine-source.md).
All 806 supported containers in the saved upload retain their Standard/Safety
class and Original/TestEdits state. The 14,414 rung records include 15 adjacent
`IR`/`R` pairs with shared RegionIds; no active record is selected. Three other
containers retain an explicit unsupported compression-header error. Metadata
omits source text, names and native regions by default. Completed scoped
selector-`(1, 3)` reads can be inspected through the detached read assembler.
The online-edit/import XML profile remains strict, and its resolver/planner
reject the distinct upload result type. No live `0x3A` handler, source installation
or native transfer authority is added. The latest SDK upload remains blocked
before requesting source streams; full native transfer remains unfinished.
All 145 affected tests and 12 focused deployment checks pass; the full suite was
not rerun. The packaged decoder handles synthetic Standard, Safety and TestEdits
sources and preserves the separate edit guards. All 94 deployed app modules,
webpage, assets and executable version match `.133`. Native SDK Go Online/Go
Offline passes across 75 verified signed requests, with actual Offline/cleanup,
unchanged source/model and no reported fatal SDK fault. Inputs, logic and edit
settings match across restart. The previous `.132` upload failure is retained as
the transfer boundary; no new full upload trial or physical-controller contact
was initiated for this passive decoder change.

Version `.132` adds [signed read-stream decoding and bounded detached assembly](read-transport.md)
for Message Router `0x3A`. All 4,333 saved exchanges frame into 2,394 complete
streams totaling 1,100,885 bytes. Reports retain scope, offsets, lengths and
hashes without claiming an embedded CIP response or exposing bytes by default.
Known-key synthetic checks cover MAC tampering, counters and invalid assembly.
The live endpoint still rejects this service; no new stream execution or write
authority is added. A private revision-11 trial is actually read by Studio but
still fails Program upload after the successful 22-field Routine reply. The
normal endpoint retains its partial legacy revision. Full native transfer and
Routine reconstruction remain unfinished.
All 324 affected checks pass; the full suite was not rerun. The final isolated
SDK probe still fails Program upload after all 22 Routine fields return zero
statuses. Its trace retains 364 expanded leaf requests, 360 verified signed
requests and all 408 source-matched diagnostic fields; it reaches no `0x3A`
read. Actual Offline/cleanup and unchanged source/model are confirmed, with no
reported fatal SDK fault or physical-controller contact. The private Template
snapshot and clock hypotheses remain separate from the normal demo.
The restarted release passes 274 live checks and native SDK Go Online/Go Offline
across 75 verified signed requests, with actual Offline/cleanup, unchanged
source/model and no reported fatal SDK fault. Inputs, logic and edit settings
match across restart. All 93 deployed app modules, webpage, packaged assets and
executable version match `.132`.

Version `.131` adds [live Routine headers, main/subroutine flags, original opaque source metadata and unsigned state](routine-bulk-metadata.md)
for the guarded ordinary RLL profile. Field 8 is identified as Header Address,
correcting the earlier UID label. Its live reference matches the Program main
reference; original blob contents come only from the matching loaded ACD.
The source proof for zero Signature Types rejects signature markers and unknown
Routine attributes. No native memory service or signature verification is added.
All 227 affected checks pass; the full suite was not rerun.
The isolated SDK upload receives all 22 Routine fields with status zero, but
still reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` without further Routine requests.
The complete trace retains 360 expanded leaf requests, 357 verified signed
requests and all 408 source-matched diagnostic fields. The header reference
matches the earlier Program main reference, and opaque source metadata matches
the original owned ACD. Actual Offline/cleanup and unchanged source/model are
confirmed, with no reported fatal SDK fault or physical-controller contact.
The candidate retains its matching Template snapshot and private clock
hypotheses; these remain separate from the normal demo. Full transfer and
Routine reconstruction remain unfinished; successful field statuses do not
establish client interpretation or Routine acceptance.
The restarted release passes 273 live checks. The webpage, packaged assets,
executable version and all 92 deployed app modules match `.131`.
Native SDK Go Online/Go Offline also passes across 75 verified signed requests,
with actual Offline/cleanup, unchanged source/model and no reported fatal SDK
fault. Demo inputs, logic and edit configuration match across the restart.

Version `.130` adds [original Routine instance IDs and guarded ordinary RLL state](routine-state.md).
Matching original Program/AOI bindings supply Executable Instance; clean,
unmodified, idle ordinary Program RLL can also supply a null native Code Address,
absent edit buffers and unprotected/non-SFC one-byte state. Missing source,
uncertain faults, changed logic and pending native edit state withhold these
fields. Header Address, Source Key, Executable Flags and Signature Types remain unavailable.
The shared decoder frames all 809 saved bulk replies and checks 17,798 field
lengths/hashes without copying their values into the runtime.
The isolated native SDK upload receives 18 of 22 fields, up from one in `.129`,
but still reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`. Individual requirements for
the four unavailable fields remain unverified. The complete trace retains 360
expanded leaf requests, 357 verified signed requests and 408 source-matched
diagnostic fields. Actual Offline/cleanup and unchanged source/model are
confirmed, with no reported fatal SDK fault or physical-controller contact.
The candidate retains its matching Template snapshot and private clock
hypotheses; these remain separate from the normal demo. Full transfer,
reconstructed Routine logic and the complete native edit lifecycle remain
unfinished. All 210 affected checks pass; the full suite was not rerun.
The restarted release passes 265 live checks and native SDK Go Online/Go Offline
across 75 verified signed requests, with actual Offline/cleanup, unchanged
source/model and no reported fatal SDK fault. Inputs and logic match across the
restart. The webpage, packaged assets, executable version and all 92 deployed
app modules match `.130`.

Version `.129` adds [source-bound Routine Type words](routine-types.md) for the
unprotected format-54/body-371 ACD profile. Older manifests and other layouts
withhold Type; Program and AOI parent scopes remain distinct. An owned RLL/ST
project passes native Offline save/reopen validation. Shared offline framing
covers all 809 recorded Type replies, excluding separate class-revision reads.
The isolated SDK upload accepts Type in both a single-field and bulk request.
The bulk reply reports the other 21 requested Routine fields unavailable, and
SDK Program upload still fails; individual field requirements remain unverified.
Its complete trace retains 360 expanded leaf requests; 357 signed requests are
verified. Offline/cleanup and unchanged source/model are confirmed, with no
reported fatal SDK fault. Full transfer remains unfinished. All 182 affected
checks pass; the full suite was not rerun.
The restarted release passes 227 live readbacks and SDK Go Online/Go Offline
across 75 verified signed requests, with actual Offline/cleanup, unchanged
source/model and no reported fatal SDK fault. Inputs and logic match across the
restart. All 91 deployed app modules, webpage, packaged assets and executable
version match `.129`.

Version `.128` adds [empty Device Diagnostic Object discovery](device-diagnostic-objects.md)
from explicit original ACD collections and shared offline framing for populated
object fields. Nonempty sources remain unavailable to the runtime; all 132
fields across 44 saved reference objects frame without replaying their values.
The isolated SDK upload accepts the new list and reaches Program-scoped Routine
Type reads (`0x6D`, attribute 1), which remain unsupported. Its complete trace
retains 360 expanded leaf requests; 357 signed requests are verified. Actual
Offline/cleanup and source/model preservation are confirmed, with no reported
fatal SDK fault. Full transfer remains unfinished. All 243 affected checks pass;
the full suite was not rerun.
The restarted release passes 222 live readbacks and SDK Go Online/Go Offline
across 75 verified signed requests, with confirmed Offline/cleanup, unchanged
source/model and no reported fatal SDK fault. All 91 deployed app modules,
webpage, packaged assets and executable version match `.128`.

Version `.127` adds [empty device diagnostic profile discovery](device-diagnostic-profiles.md),
requiring explicit original ACD collection evidence and matching source hashes.
Nonempty, absent, unsupported and stale sources remain unavailable. Class
counts are proven zero; class revision is not inferred. The isolated SDK upload
accepts the new list and advances to Device Diagnostic Objects (`0x3B0`), with
status `0x0F`. Its complete trace retains 355 expanded leaf requests; 352 signed
requests are verified. Offline/cleanup and source/model preservation are
confirmed, with no reported fatal SDK fault. Full transfers remain unfinished.
All 230 affected checks pass; the full suite was not rerun.
The restarted release passes 213 live readbacks and SDK Go Online/Go Offline
across 75 verified signed requests, with confirmed Offline/cleanup, unchanged
source/model and no reported fatal SDK fault. All 90 deployed app modules,
webpage, packaged assets and executable version match `.127`.

Version `.126` adds [source-bound device diagnostic message definitions](device-diagnostic-messages.md).
The importer retains original ACD IDs, message strings and revisions; the
read-only endpoint exposes bounded instance lists and attributes. Missing or
stale bindings withhold the catalog. Shared offline framing covers the counted
strings without exposing values by default. The trace event limit increases to
2,000 while its existing byte budget remains unchanged.
The final isolated SDK upload reads all 408 fields across 136 definitions and
advances to diagnostic-profile discovery (`0x3B1`), which remains unsupported.
Its complete trace records 355 expanded leaf requests; the endpoint verifies
352 signed requests. Offline/cleanup and source/model preservation are confirmed,
with no reported fatal SDK fault. Full native transfers remain unfinished.
The restarted release passes SDK Go Online/Go Offline across 75 verified signed
requests, preserving Offline/cleanup and source/model with no fatal SDK fault.
All 221 focused tests and 204 live readbacks pass; the full suite was not rerun.
The deployed 89 app modules, webpage and executable match `.126`.

Version `.125` adds [Program-scoped empty catalog discovery](program-catalog-discovery.md)
for Digital/Analog Alarms, HMI Button Controls and Messages. Each catalog uses
its own complete-source absence check and matching native Program identity.
The offline transfer analyzer retains valid scoped requests unsupported by the
live decoder, preserving rejected responses and numeric parent paths.
The final isolated SDK upload accepts all four added scoped lists and reaches
device diagnostic message discovery, failing class `0x3B2` instead of Program
collection. Its 215 verified signed requests preserve Offline/cleanup and the
source/model, with no reported fatal SDK fault. Full transfer and reconstructed
Routine logic remain unverified.
The restarted release passes SDK Go Online/Go Offline with 75 verified signed
requests and confirmed Offline/cleanup, unchanged source/model and no fatal SDK
fault. All 245 focused checks and 63 live readbacks pass without a full-suite
rerun. Source, webpage and executable versions match `.125`.

Version `.124` adds original [Program and Task reference symbols](reference-symbols.md).
Source-bound data names and native IDs select supported Standard objects;
runtime references resolve to the current interpreter targets and immutable
Symbol descriptors. References have no tag-value or Data Table storage.
The isolated SDK upload reads both added references and all 22 Program fields,
then requests Program-scoped Data Table discovery. It still reports a Program
upload failure. Full native transfer and Studio GUI monitoring remain unfinished.
The restarted release passes SDK Go Online/Go Offline with 75 verified signed
requests; Offline/cleanup, unchanged source/model and no fatal SDK fault are
confirmed. All 292 focused software checks and 47 live readbacks pass without
rerunning the full suite. Source, webpage and executable versions match `.124`.

Version `.123` adds an identified [nonredundant Program synchronization model default](program-synchronization-default.md).
Explicit settings keep precedence; unknown, enabled-redundancy and unsupported
profiles stay unavailable. The isolated SDK upload reads all 22 requested
Program fields successfully, but full Program upload still fails. Successful
attribute replies remain separate from reconstruction and transfer acceptance.

Version `.122` adds [runtime Program and main-Routine references](runtime-object-references.md).
Opaque aligned addresses resolve to live interpreter objects, remain separate
from logical IDs and are revoked on object replacement. The isolated native
upload accepts both fields; one synchronization setting remains unavailable in
its Program list. Complete upload still fails. The released clock profile is
unchanged; native GUI monitoring and full transfers remain unfinished.

Version `.74`
ties native mode requests and webpage controls to the same scan worker.
Version `.75` adds transactional Run-entry prescan and first-scan initialization.
Version `.76` adds [member inspection of temporary native type definitions](template-layout-inspection.md)
as groundwork for validating storage layouts; encoded offsets and trailers remain opaque.
Version `.77` [checks staged members against the original ACD type metadata](source-type-verification.md)
and rejects source/layout mismatches. Native storage mapping remains unfinished.
Version `.78` adds a [source-bound temporary download image](download-image.md),
coherent [software system time](upload-inventory.md), and an
[online-edit diagnostic](native-online-edits.md) that requests acceptance
of a generated NOP rung on a private project copy. Download now starts a real
temporary image, and online edits can acquire a separate exclusive reservation.
Subsequent transfer and edit operations remain incomplete.
Version `.79` adds the [Program Disabled read used by online imports](edit-program-state.md),
three more source-backed Controller settings and [per-record download results](download-image.md#per-operation-preparation-results).
An [isolated protocol probe](research-session-probe.md) exercises the actual
challenge and signed transfer paths independently of the optional native SDK.
Version `.80` adds [source-bound Task settings and native Task IDs](task-metadata.md),
an [SDK-independent upload inventory reader](upload-inventory-client.md) and an
[offline download capture comparison](download-replay.md).
Version `.81` extends Task metadata with ordered native Program links and exact
source period/watchdog reads. The independent inventory reader checks those
Task-to-Program relationships without using the native SDK.
Version `.82` adds [Program-scoped native Routine inventory](executable-metadata.md),
including original ACD object IDs and a limited legacy description read.
The independent inventory reader preserves parent Programs when routine IDs overlap.
SDK testing has resumed: the rebuilt demo passes connection/Offline; its isolated
edit diagnostic returns an attribute-list error and confirms cleanup without a
reported fatal SDK exception.
Version `.83` adds the source-bound [overflow-reporting setting](controller-overflow-setting.md)
requested during native online import, and retains SDK import-log error codes
in diagnostic summaries. The isolated native import advances to a denied
controller operation. A separate local pending NOP import while online succeeds;
controller acceptance and active edits remain unavailable.
Version `.84` adds [Program preparation reservations](program-reservations.md)
and explicit typed SDK tag-read diagnostics. Accepted controller edits remain
unfinished.
Version `.85` models the observed Controller open/close preparation sequence
with Run inhibition and a source-checked zero UDI-stack proposal for complete
projects without AOIs. The independent inventory reader also reads this
modeled zero stack. Active edit storage and controller acceptance remain unfinished.
The `.85` native edit probe passes this preparation and reaches a compiled
Routine fragment, which is still rejected by the transfer receiver.
Version `.86` adds [compiled Routine fragment staging](edit-transfer.md)
under the edit reservation, with source-bound targets and bounded temporary
storage. Complete binaries remain separate from active routines; installation
and accepted controller edits are unfinished.
The native edit diagnostic now delivers all 11 compiled fragments before that
installation rejection; endpoint storage clears and active logic is unchanged.
Version `.87` receives the following [compressed Routine source](routine-source.md),
resolves supported native object references using original ACD identities, and
checks translated ladder logic in a detached execution plan. It retains both
containers temporarily; applying source and accepted edits remain unfinished.
Version `.88` acknowledges validated source storage and retains the following
[post-source record](edit-post-source.md). Its signed transfer parser keeps
the native session alive through the next unsupported operation, allowing
the edit diagnostic to complete Go Offline. Active edit completion remains unfinished.
Version `.89` adds [supported Program-mode routine edits](supported-routine-edits.md).
A native SDK rung import now replaces the translated routine in the execution
model; the inserted instruction executes on the next scan. The webpage exposes
edit access and an in-memory logic revision. Original ACD/L5X files are preserved.
The `.89` Windows milestone runs 1,263 tests successfully with two platform skips.
Version `.90` verifies two accepted rung imports in the same SDK project, both
while remaining online and with Offline/Online between imports. Both edits
remain active and execute on the next scan; the logic revision advances twice.
The [native diagnostic](development.md#native-sdk-acceptance-probe) checks
each intermediate routine and reconnection against the expected logic.
Version `.91` adds scoped metadata retention needed by native rung replacement
and verifies replacements in two routines with reconnects. **Save edited L5X**
now saves a separate [working copy of edited logic](edited-logic-l5x.md)
with original imported tag initial values. That copy reloads and executes in
the emulator.
Version `.92` verifies a replacement followed by an insertion in the same
routine, with reconnects. The optional native diagnostic imports the exported
L5X, saves a new edited ACD, reopens it and checks the re-exported logic and
initial values. That new ACD also passes a fresh SDK Go Online/Offline connection
to an emulator loaded from the saved project. Studio GUI acceptance remains
unverified.
Version `.93` resolves source-bound tag/member references inside native CPT
expressions. A CPT import followed by conditional arithmetic passes SDK
reconnects and executes with queued external inputs. The edited L5X reloads
and reproduces the tested results. See the
[expression reference profile](routine-source.md#cpt-expression-references).
Version `.94` adds source-bound CMP expressions and static array operands.
Native imports reconnect and execute comparisons, indexed reads and indexed
destinations; saved L5X copies reproduce the results. Unsupported decoded logic
is rejected by a signed edit operation while preserving native Offline cleanup.
Version `.95` adds checked integer-bit operands to native imports, including
array elements. Reconnects, scan-boundary external writes and saved L5X reloads
pass. Controller references that would bind to a shadowing Program tag are
rejected. Download diagnostics now distinguish a prepared image's unsupported
result encoding from a general write-policy rejection.
Version `.96` adds [checkpointed native transfer reports](native-transfer-diagnostics.md)
for upload/download investigations, plus an offline report reader. Reports
separate object errors, fragment acknowledgements and temporary preparation
state; they preserve the distinction between protocol observations and SDK success.
Version `.97` retains complete native transfer packets within a bounded trace
ring, allowing the offline reader to check large download fragments. Capture
limits and evictions are exposed in diagnostic state. It also adds
[source-bound indirect array indices](routine-source.md#indirect-array-indices)
to supported native imports. Indexed reads and CPT destinations pass reconnect,
execution, queued external input and saved L5X reload checks.
Version `.98` adds source-bound
[indirect integer-bit operands](routine-source.md#indirect-integer-bit-operands)
to native imports and the corresponding typed CMP condition syntax. Index
references remain live, with type checks and bounds faults at execution.
Version `.99` adds bounded [atomic-array Data Table storage](atomic-array-storage.md).
Native upload now reads the tested array's descriptors and values, advancing
beyond its previous missing-storage error. Full upload and SDK tag-address
discovery remain unfinished.
Version `.100` adds [structured Data Table storage](structured-storage.md)
using the existing symbolic UDT layouts, with real network readback and queued
external member writes. Native UDT upload stops at earlier Template metadata;
native tag monitoring and full upload/download remain unfinished.
Version `.101` adds [source-known Template family metadata and aligned definition reads](template-metadata.md).
Independent signed TCP checks pass. A fresh native Go Online/Go Offline test
passes after SDK service recovery; the previously faulting metadata overrides
remain excluded.
Version `.102` extends the [SDK-free inventory reader](upload-inventory-client.md)
with bounded Template definitions, multidimensional atomic arrays and raw UDT
value bytes. Malformed replies stop decoding and release the reader's connection.
The independent reader does not require the SDK.
Version `.103` adds an [isolated signed routine-edit probe](research-session-probe.md#supported-routine-replacement)
that checks commit ordering, reconnection, next-scan execution and edited L5X
reload alongside inventory and temporary-download checks, without the SDK.
Version `.104` adds [source-bound AOI definition discovery and metadata reads](aoi-metadata.md),
including original ACD IDs, clean model state, revisions and readable vendor
headers. Protected payloads remain opaque and do not gain a clean-state value.
Version `.105` adds [AOI-scoped Routine discovery](aoi-metadata.md#aoi-scoped-routines)
with original child IDs, sparse pagination and available source descriptions.
AOI and Program parent IDs remain separate throughout imports, inventory and
diagnostics. Protected Routine inventories remain unavailable.
Version `.106` adds [source identity checks for downloaded objects](source-object-identities.md).
Program/Routine IDs and known Symbol IDs must match their source scopes before
temporary objects are published; additional internal Symbols remain unresolved.
Version `.107` adds [source-bound auxiliary Symbol identities](source-object-identities.md#auxiliary-symbol-identities).
Original component records resolve Symbols omitted by TagInfo during download
checks, while their runtime tags, values and alias behavior remain unavailable.
Version `.108` adds [original Data Table identity checks](source-object-identities.md#data-table-identities).
Staged Table IDs must match the source inventory before temporary download
objects are published; native addresses and storage/value decoding remain unfinished.
Version `.109` adds [original Template ID checks](source-type-verification.md#original-template-identities).
Known IDs must match even when a transfer consistently renumbers nested types;
cached source metadata changes also reject temporary processing and result queries.
Version `.110` includes [source identity results in transfer diagnostics](native-transfer-diagnostics.md#source-verification-results).
A fresh native download matches all 242 Template IDs, 20 Symbol IDs and 16 Table
IDs in the original demo before reaching the unfinished result-response step.
The limited Program-mode accepted-rung SDK import also passes on an isolated
controller, with native Offline and source preservation confirmed.
Version `.111` adds [null Controller handler and aggregate reads](controller-handlers.md)
from a successful v35 reference upload. Configured handler references remain
unavailable; successful object replies still do not complete native upload.
Version `.112` improves [offline capture analysis](development.md#offline-cip-capture-inspection)
for complete upload recordings and decodes bounded Time Sync attribute lists,
including partial replies and vendor descriptions. Revision-only SDK experiments
still fail upload; their substituted revisions are not shipped.
Version `.113` adds optional [source-bound native Template snapshots](native-template-snapshots.md).
Supported structures can retain their original IDs, handles and complete saved
definitions while values remain in software memory. An isolated SDK case
advances to tag upload without a reported fatal fault; full transfers remain unfinished.
Version `.114` adds [source-checked empty Energy discovery](connectivity.md#empty-energy-discovery-for-ordinary-user-types)
for ordinary user types and the newer Base/Electrical discovery request. The
isolated structured-project SDK upload passes Controller tag collection and
reaches device/extended-device/memory collection, where it still fails.
Version `.115` adds [field-level collection diagnostics](native-transfer-diagnostics.md#collection-attribute-lists)
to native transfer reports and offline capture analysis. Valid field layouts,
unavailable attributes and undecoded layouts are reported separately. An isolated
complete-clock experiment still fails device collection and is not shipped.
Version `.116` adds [supplemental schema discovery and read-only Wall Clock Time](controller-schema-discovery.md).
The clock distinguishes legacy 1972 counters from UTC 1970 counters and checks
source settings before serving legacy local values. SDK schema queries succeed;
complete upload still fails during device collection.
Version `.117` adds [source-checked Program kind and original instance reads](edit-program-state.md#program-kind-and-original-instance)
and Program collection diagnostics. A disposable complete-clock experiment
reaches Program collection; its generated clock settings remain unshipped.
Version `.118` adds [Program Task owners, logical children and null fault references](program-hierarchy.md).
The isolated upload accepts these three fields, while full transfer remains unfinished.
Version `.119` adds [measured Program scan durations and source scheduling/synchronization flags](program-timing-and-flags.md).
Program timings track successful emulator scans and roll back on a failed scan;
programs used as folders cannot execute. The isolated upload comparison accepts
three more Program fields; full native transfer remains unfinished.

Version `.120` adds [Program output/edit diagnostics and model fault records](program-diagnostics.md).
The isolated upload comparison accepts four more fields, reducing unavailable
Program fields from 9 to 5. Untested-edit reads require idle native edit staging;
unknown fault history remains unavailable until reset. Full transfer remains
unfinished.

Version `.121` adds [Standard memory reads and bounded normal Program status](program-memory-status.md).
Program and Task Data Use remain distinct from execution status; normal status
requires source/native ownership and known-clean supported execution. Offline
diagnostics also frame Task collections without exposing values by default.
