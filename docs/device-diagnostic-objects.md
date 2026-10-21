# Empty device diagnostic object discovery

Version `.128` adds source-bound empty Device Diagnostic Object (`0x3B0`)
discovery. This is independent of the
[Diagnostic Profile collection](device-diagnostic-profiles.md): an empty profile
catalog does not prove that Diagnostic Objects are absent.

## Original source evidence

The bounded Comps.Dat reader requires exactly one active controller-scoped
collection with component type 0, format 0 and a 74-byte body. Any active
Diagnostic Object definition, unsupported layout, duplicate collection or
scoped collection withholds the binding. Deleted records and allocation tails
are excluded. The object and profile readers share collection-bound checks,
while each requires its own class and explicit manifest field.

Both owned demo sources contain this explicit empty collection. A separate
nonempty offline example contains 44 stored 361-byte object records with IDs
matching the 44 IDs in a saved successful upload. That file has changed since
the capture, so the comparison is not an exact-byte native round trip. It
establishes a populated source shape that the empty reader must reject; it does
not authorize copying those objects into other projects or interpreting their
unverified storage fields.

The immutable `native_diagnostic_objects` manifest retains original ACD and
converted L5X hashes and an explicit empty `objects` list. Loading requires a
matching original Project identity and agrees with all supplied native source
bindings. Invalid manifests reject the load before model replacement. Reset
preserves the binding; loading a project without it clears it. Optional
extraction failure keeps ordinary L5X import available. Appliance imports
forward the same manifest through the shared application service.

## Runtime behavior

The controller-scoped Get Instance List (`0x4B`) returns an empty list for every
cursor only when the source binding is current. Signed read-only sessions use
the same handler. Class attributes 2 and 3 report maximum instance and count as
32-bit zeros. The class revision is not inferred from a storage-format value.
Unbound instances, malformed requests, parent scopes and configuration writes
remain denied; missing or stale evidence reports unavailable.

This does not implement populated Diagnostic Object runtime fields, generate
live diagnostic events or infer hardware status. The API reports availability,
counts and provenance without including source records in the webpage.

## Shared offline decoder

Saved capture and transfer reports can now frame nonzero `0x3B0` instances:
attribute 1 has four bytes, attribute 2 has one byte, and attribute 3 contains a
16-bit count followed by 16-bit condition entries, bounded at 4,096 entries.
These represent Profile ID, Enable and Conditions in the installed v35 layout.
The decoder preserves request order, duplicates, individual errors and partial
reply suffixes. Unknown successful fields, excessive counts, truncation and
trailing bytes fail framing. Values remain omitted by default; lengths and
hashes are retained. Framing a field does not implement it in the runtime.

All 132 fields across 44 saved reference objects frame successfully. Synthetic
checks also cover nonempty condition arrays and malformed replies. No captured
objects are replayed, and no physical-controller connection was initiated.

## Native validation and limits

The isolated `.128` SDK upload accepts the new empty list, then enumerates
Programs and Program-scoped Routines. The next unsuccessful read is Executable
class `0x6D`, attribute 1 (Type), under a Program. The SDK now reports
`RxCsE_UPLOAD_OF_PROGRAMS_FAILED`, replacing the prior diagnostic-object failure.
The complete trace retains 360 expanded leaf requests, including all 408
successful source-matched diagnostic message fields; the endpoint verifies
357 signed requests. Actual Offline, cleanup, unchanged source/model and no
reported fatal SDK fault are confirmed.

The diagnostic candidate uses its own matching Template snapshot and private
clock hypotheses. These remain separate from the normal demo. Full native
upload/download, reconstructed Routine logic, Studio GUI monitoring and the
complete Test/Untest/Assemble lifecycle remain unfinished or unverified.

All 243 affected software checks pass; the full suite was not rerun.
