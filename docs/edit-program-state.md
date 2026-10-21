# Program state used by native edit preparation

Native online import reads Program attribute `19` (`0x13`) after acquiring its
temporary edit reservation. The installed v35 Program attribute descriptions
define this field as **Program Disable**, encoded as one `BITS8` value. The
source L5X `Program@Disabled` supplies the corresponding explicit `true` or
`false` value.

`ProgramConfiguration` retains this field from a complete controller export.
It requires v35 source, unambiguous ordinary program names, the canonical XML
scope and a matching source SHA-256. Missing or malformed `Disabled` values
remain unavailable. They never become an assumed enabled program. Values are
immutable after parsing; loading another source creates another snapshot.

The Router must first resolve the source-bound native Program ID and apply its
existing Standard-program eligibility checks. Only then may it merge the
configuration attributes into that program's read response. Some native
ordinary-program exports omit `Class`; the configuration reader preserves
their explicit `Disabled` value without creating a Class readback. Explicit
Safety or unknown classes remain unavailable.

The field encodes enabled source (`Disabled="false"`) as `00` and disabled
source as `01`. A successful single-attribute read therefore contains one data
byte. Attribute-list reads retain the ordinary count, attribute ID and
per-attribute status fields before that byte. Unknown attributes still receive
their ordinary unavailable status.

This metadata does not change execution state or accept an online edit. A `.79`
native import successfully read the Program field. Its next unavailable read
was class `0x70`, instance `1`, attribute `19`; later Controller reads also
returned unsupported fields. The SDK again reported `LgxSrv_E_FATAL_ERROR`.
These packets do not establish which missing field caused the SDK failure.
Source and model remained unchanged, but native cleanup was unconfirmed; the
isolated emulator connection was explicitly closed and the main endpoint
restored. Native SDK tests were paused at that revision. Program readback can be checked with the
[independent protocol client](research-session-probe.md). Compiled routine
identity, edit storage, acceptance, testing, assembly and commit remain separate
work.

## Program kind and original instance

Version `.117` adds Program attribute `30`, **Program Type**, as one byte: `01`
for a proven ordinary user Program. This is separate from the safety/standard
class and from the Disable setting. The installed v35 Program definition
identifies the field; 20 successful type-only reference replies independently
establish the ordinary kind byte. The [Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
defines `Type="Normal"`, `EquipmentPhase` and `Sequence` in its Program section.

The reader requires complete v35 source, a canonical `Programs/Program`,
Standard or omitted Class, and Normal or omitted Type. Only recognized Program
attributes and ordinary child containers supply the kind. Context, duplicate,
nested, namespaced, unknown/opaque and phase/sequence declarations remain
unavailable. Kind availability is independent of an explicit Disable value.
The source SHA-256 and native Program identity must still match every read.

Attribute `22`, **Program Instance**, returns that resolved original native ID
as a four-byte value. It does not allocate another ID or provide a compiled
address. All 20 full Program lists in the successful reference recording match
this field to their requested instance. Single and list reads agree; writes
remain denied. Other parent scopes cannot resolve a global Program implicitly.

The shared [collection decoder](native-transfer-diagnostics.md#collection-attribute-lists)
also handles Program lists at nonzero source-selected instances. It frames the
established scalar widths, opaque four-byte address fields, 44-byte fault
structures, counted names and bounded child lists without interpreting them
as executable state or exposing values by default. All 40 reference Program
lists, including 20 full 22-field lists, frame without layout errors.

A disposable complete-clock comparison advances beyond Controller collection
and reaches the previously unsupported Program Type read. Adding the kind read
returns `01` and advances that comparison to the full Program list, which still
contains unavailable fields and fails `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` across
201 verified signed requests. Generated Time Sync/Wall Clock settings and
substituted class revisions used to isolate this path are not shipped. A fresh
unpatched public-source candidate still fails Controller collection across 196
verified requests. All four comparisons confirm Offline, cleanup and unchanged
source/model without a reported fatal SDK fault. These results do not establish
a complete upload, download or full online-edit lifecycle.

The restarted `.117` runtime separately passes SDK Go Online/Go Offline with
75 verified signed requests, clean Offline/cleanup and unchanged source/model.
The 192 focused software tests and 18 live reads pass; the full suite is not
rerun for this iteration.

Version `.118` adds the separately source-checked [Task owner, child list and null fault reference](program-hierarchy.md)
reads observed in the full Program collection. These remain metadata reads;
the full native online-edit lifecycle is unfinished.

Version `.119` adds [committed Program scan timings and explicit source flags](program-timing-and-flags.md).
Supported routine replacements preserve the recorded timing history. This does
not add native timing/flag setters or the complete Test/Untest/Assemble lifecycle.

## Earlier native checks

Version `.80` adds the separately source-bound [Task Inhibit read](task-metadata.md)
identified in that retained trace. Task and Program settings use their own exact
field widths and identities. This change has focused protocol validation only;
native SDK testing remained paused at that revision.

SDK testing resumed in `.82`. With the Task read and later Controller
[overflow-reporting setting](controller-overflow-setting.md), the `.83` native
import advances to a denied Controller service `0x55` and confirms Offline and
endpoint cleanup. Active edit acceptance, testing, assembly and commit remain
unfinished.
