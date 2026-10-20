# Routine source containers and object references

Version `.87` extends [compiled edit staging](edit-transfer.md) with the source
container sent after the compiled ELF. Both belong to the same reserved,
source-bound RLL routine. Receipt of a complete ELF acknowledges temporary
storage and permits the source transfer. In `.87`, the final source fragment
returns an installation error. Version `.88` instead acknowledges validated
source storage and supports the following [post-source record](edit-post-source.md).
The active project remains unchanged.

The observed source setup consists of DWORDs `1`, `3`, followed by a container
whose first DWORD describes its remaining length. Relative source/auxiliary
offsets, extents, reserved words and alignment are checked before allocation.
The source section contains an explicit expanded length and compressed XML;
the auxiliary section contains another bounded compressed stream. Compressed
stream ends, expanded lengths and zero padding must match exactly. This profile
uses UTF-8 XML bytes despite its UTF-16 declaration. Other encodings/profiles
remain unsupported.

The decoder accepts the observed complete v35 `RLLContent` document, normal
rungs with unique region IDs and one `TextIOI` element per rung. Context exports,
protected/extra nodes, DTDs, entities, unexpected text, invalid targets and
excessive rung/source sizes are rejected. The auxiliary data and region-ID
lifecycle remain uninterpreted. A source target must match the reserved Routine.

## Translating supported references

`TextIOI` identifies objects numerically. Supported six-word paths resolve
controller and Program symbols through the original `NativeSymbols` catalog,
and same-Program JSR targets through `NativeRoutines`. Ordinary member paths in
the observed `0x6C`/`0x84FE` profile additionally require a matching DataType ID
and checked member order from `NativeTypes`.

DataType IDs come from active Comps.Dat format-177 records with a plain DataType
path. They are correlated by name with TagInfo's explicit type/member metadata;
they are never assigned from source order. This member-path profile uses
one-based ordinals over TagInfo's checked zero-based member Index, including
hidden members. Direct access to hidden members, unknown markers/IDs, indirect
forms, unsupported array paths and stale/mismatched source catalogs fail
translation. Old type manifests without IDs remain readable and cannot resolve
these member paths.

Translation produces neutral ladder text for inspection. A detached project
copy passes through the existing parser, execution planner and preview prescan.
It validates supported instructions and operands without running scans,
replacing active routines, changing values or assigning controller addresses.
Reference resolution is reported separately from successful plan validation.

`edit_transfer.source_description` reports decoding, rung/reference counts,
content hashes, reference/plan status and redacted failure reasons. It exposes
neither source text nor auxiliary bytes. The code and source buffers share the
262,144-byte cap, 128-fragment cap and absolute 30-second deadline. Existing
owner, source-change, expiry and endpoint cleanup clear both buffers. In `.89`,
a fully validated candidate with its post-source record survives Program
release until Controller completion or phase cleanup; incomplete pairs are
discarded at Program release.

## CPT expression references

Version `.93` extends reference translation to CPT's second operand. Complete
source-bound scalar/member chains can appear inside the existing bounded
expression grammar, including arithmetic and parentheses. Each chain resolves
through the same Symbol and DataType catalogs as a direct operand. The parser's
reference list must match those resolved chains, including repeated occurrences;
unencoded names and member/index suffixes cannot add references implicitly.

Expressions are limited to 4,096 characters and the parser's existing token,
nesting, function and numeric-type limits. Unknown IDs, malformed markers,
quoted expression strings, unsupported functions and hidden members are rejected.
The detached execution-plan check still validates destination/operand types and
supported arithmetic. Version `.94` adds CMP's first operand with comparison and
Boolean syntax; its detached plan must produce a typed Boolean condition.
Other instruction expression positions remain outside this profile. No compiled address is
assigned and the opaque native ELF is not executed.

The native test appends `CPT(SpeedCommand,(SpeedSetpoint*2)+7);`, then
`XIC(StartPB)ADD(SpeedCommand,10,SpeedCommand);`, with Offline/Online after each
import. Both imports succeed across 314 verified signed requests. A scan
produces 107; queued device inputs then produce 137 and 157. The exported L5X
reloads with original initial values and reproduces the first two cases.
Native Offline and endpoint cleanup are confirmed without a reported fatal SDK
fault. See [supported edit validation](supported-routine-edits.md#cpt-and-conditional-arithmetic).

## Static array operands

Version `.94` accepts a decimal subscript suffix on a resolved Symbol/member
chain. Each index is checked against the original imported value's array shape,
with exact rank required when subscripting. The same complete references can
appear in direct operands, CPT calculations and CMP conditions. Unknown IDs,
out-of-range or negative indices, repeated subscript groups, unresolved members
and arithmetic/indirect index expressions remain rejected. Existing hidden
member, type-ID and source-binding checks still apply.

Software tests cover one- and two-dimensional numeric arrays, wrong ranks and
bounds, scalar-as-array errors and rejected indirect forms. Native SDK evidence
covers a one-dimensional DINT array in a separately generated demo. Its two
imports use an indexed MOV source, indexed CMP/CPT sources and an indexed CPT
destination; reconnects pass across 315 verified signed requests. Scans and
queued external array writes exercise both true and false CMP outcomes, and
an edited L5X reload reproduces them. Broader native array/type coverage remains
unverified. See [comparison and array validation](supported-routine-edits.md#comparisons-and-array-operands).

## Scope

The decoder/translator establishes a source path toward the custom execution
model. It does not prove ELF/source equivalence or resolve native relocations.
Version `.89` adds a separate, explicitly enabled [Program-mode activation](supported-routine-edits.md).
Native Test/Untest/Assemble remain unsupported. Native results and conditional
capture experiments are recorded separately from software-model tests.

## Native result

The final isolated `.87` SDK import uses unchanged public application sources.
It retains the 4,304-byte compiled container and a 692-byte source container,
decoding 1,790 XML bytes and 81 auxiliary bytes. The source container's size
varies with compressed content; it is not fixed at the earlier 688-byte sample.
All 27 object-reference occurrences resolve to 10 neutral ladder rungs using
242 original DataType IDs. A detached execution-plan check succeeds. Independent
offline reconstruction matches the receiver's hashes; the new first rung is
NOP and the other nine parsed rungs match the original source exactly.

The import still fails at the explicit installation boundary across 115
verified requests. Native Go Offline reports `RxE_COMM_NOTOPEN`, so native
cleanup remains unconfirmed for this case. Project close and endpoint cleanup
succeed without explicit socket cleanup; source/model are unchanged and no
fatal SDK fault is reported. This result establishes translation and candidate
validation, not accepted controller edits or an active routine replacement.
