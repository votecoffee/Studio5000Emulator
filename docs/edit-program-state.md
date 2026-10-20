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

Version `.80` adds the separately source-bound [Task Inhibit read](task-metadata.md)
identified in that retained trace. Task and Program settings use their own exact
field widths and identities. This change has focused protocol validation only;
native SDK testing remained paused at that revision.

SDK testing resumed in `.82`. With the Task read and later Controller
[overflow-reporting setting](controller-overflow-setting.md), the `.83` native
import advances to a denied Controller service `0x55` and confirms Offline and
endpoint cleanup. Active edit acceptance, testing, assembly and commit remain
unfinished.
