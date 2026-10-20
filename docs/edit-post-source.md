# Post-source edit storage

Version `.88` acknowledges the final Routine source fragment only after its
supported object references resolve and its detached execution plan validates.
Code, source and subsequent records remain temporary, owned storage. The active
routine and execution state are unchanged.

## Signed transfer control

The next observed request uses Message Router service `0x39`, container format
`0x301` and control word `8`. It embeds an ordinary Executable `0x5C` request.
The codec now parses this control separately from fragmented transfers and the
existing control-1 dialect. Both exact controls retain their value when framing
and checking signed inner replies. Other controls remain unsupported.

MAC verification and the shared monotonically increasing session counter apply
before dispatch. The control word alone grants no write permission. An unknown
operation returns an authenticated inner error and leaves the context usable
for subsequent cleanup. Previously this structurally unrecognized control
invalidated the context before its embedded operation could be inspected.

## Retained record

The supported storage profile is one 20-byte record containing four DWORDs
`2`, `5`, `0`, `1`, followed by one nonzero opaque DWORD. Its final value varies
between native imports; it is not assigned as an emulator or controller ID.
The emulator does not interpret this record as relocation, region, identity,
checksum or commit metadata.

Receipt requires the matching Program-scoped Routine target, control 8, a live
edit owner, an open preparation phase, the Program reservation, stopped Program
mode and the already validated code/source pair. Original source catalogs are
rechecked before retention. Another wrapper, target, owner, incomplete source,
changed correlation or unsupported profile cannot stage the record.

An exact duplicate receipt is idempotent; conflicting bytes cannot replace the
stored record. It shares the existing combined byte cap and absolute assembly
deadline. Program/Controller release, source replacement, expired context,
disconnect and endpoint shutdown clear it with the source and code. Status
reports byte count, SHA-256 and an uninterpreted flag, without its payload or
opaque value. SDK probe admission requires empty record storage.

## Remaining boundary

The following observed Controller `0x59` request carries four zero bytes. Its
active-edit contract is unresolved and the public app rejects it. Temporary
receipt does not acknowledge accepted edits, source activation, Test, Untest
or Assemble. The source ACD remains preserved. Native results are recorded
separately from the synthetic codec, TCP and staging checks.
