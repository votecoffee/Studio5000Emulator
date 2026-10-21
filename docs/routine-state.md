# Routine identities and guarded RLL state

Version `.130` extends source-bound Executable (`0x6D`) metadata. Ordered bulk
and single-attribute reads use the same checks, including signed sessions.
The separate [original Type word](routine-types.md) remains unchanged.

## Runtime fields

| Attribute | Value | Availability |
| --- | --- | --- |
| 9, Executable Instance | Original four-byte child ID | Current native Routine binding and matching original Project identity; numeric Program or AOI parent |
| 2, Code Address | Four-byte null address | Guarded ordinary Program RLL |
| 10 through 21, native edit addresses and sizes | Four-byte zeros | Guarded ordinary Program RLL; no staged native edit buffers |
| 23, Source Protection Type | One-byte zero | Guarded, readable and unprotected ordinary Program RLL |
| 26 and 27, Pause/Resume and SFC end-pause state | One-byte zeros | Guarded ordinary Program RLL; no SFC execution |

Guarded state requires complete ordinary v35 source, explicit `TestEdits=false`,
normal RLL rungs and the validated native Type storage profile. The simulator
must have no execution blockers, current fault, uncertain fault history, active
call frames, changed logic or pending native edit preparation/transfer. A
reservation withholds state for its Program; a global edit phase withholds it
for all Programs. Unrelated Program reservations do not hide known idle state.
Clearing a fault message does not clear uncertain history; reset does.

Code Address is null because the interpreter has no native machine-code entry
point. This is separate from its active interpreted RLL body and from the
model's opaque runtime object references. Null edit addresses do not represent
native compiled logic or establish Test/Untest/Assemble support.

AOI routines expose original instance IDs, without these Program state fields.
Legacy bindings without Type can still expose original IDs but cannot supply
guarded state. Missing, stale or foreign Project evidence withholds both new
identity and state fields. Unsupported children keep their scoped errors.
Setters acquire no additional authority.

UID (8), Source Key (22), Executable Flags (24) and Signature Types (28) remain
unavailable. In particular, zero signatures are not inferred from readable
source, and captured flags or keys are not copied into another project.

## Offline framing

The shared decoder frames all 22 fields in the observed bulk order, requiring
one numeric Program or AOI parent and exact consumption of the reply. It
retains order, duplicates, individual failures, partial suffixes and value
lengths/hashes. Raw values remain omitted by default. Source Key is a bounded
16-bit-counted byte string of at most 66 bytes; field 8 remains opaque with a
four-byte width. This does not establish its UID semantics.

All 809 saved successful bulk replies frame completely: 17,798 fields. Original
Executable Instance equals the requested child ID in every reply. Code Address,
the edit-buffer fields and the three modeled one-byte states are zero in these
replies. This supports the narrow model; it does not establish those values for
other controller states. Runtime values use the loaded source and simulator
state rather than replaying captured values.

## Validation boundary

Software checks cover both parent scopes, source/identity changes, old manifests,
fault history, modified logic, native edit coordination, malformed framing and
denied writes. Source-reader checks also exercise the original demo and a
separate owned diagnostic project without changing either file.

Full native upload/download, Routine logic reconstruction, Studio GUI monitoring
and the complete native Test/Untest/Assemble lifecycle remain unfinished or
unverified. Native probe results are recorded in the
[connectivity history](connectivity-history.md).
