# Routine source containers and object references

Version `.87` extends [compiled edit staging](edit-transfer.md) with the source
container sent after the compiled ELF. Both belong to the same reserved,
source-bound RLL routine. Receipt of a complete ELF now acknowledges temporary
storage and permits the source transfer. The final source fragment still
returns an installation error; the active project is unchanged.

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
owner, Program, source-change, expiry and endpoint cleanup clear both buffers.

## Scope

This establishes a source path toward the custom execution model. It does not
prove ELF/source equivalence, resolve native relocations, apply source, accept
controller edits or implement Test/Untest/Assemble. Those operations remain
unsupported. Native results and conditional capture experiments are recorded
separately from software-model tests.

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
