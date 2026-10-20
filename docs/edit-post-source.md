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

## Controller completion

The following observed Controller `0x59` request carries four zero bytes. In
`.88`, its active-edit contract is unresolved and the public app rejects it. Temporary
receipt does not acknowledge accepted edits, source activation, Test, Untest
or Assemble. The source ACD remains preserved. Native results are recorded
separately from the synthetic codec, TCP and staging checks.

The final isolated `.88` native case retains 5,016 bytes across the code/source
containers and this record. It verifies 120 signed requests, resolves all 27
source references into 10 rungs and validates their detached plan. It fails at
Controller `0x59` with `RxCsE_ASA_NO_PERMISSION`. Native Go Offline/readback,
project close and endpoint cleanup succeed. Active source/model remain
unchanged and no fatal SDK fault is reported. This result advances temporary
transfer compatibility; it does not establish accepted controller edits.

Version `.89` adds an explicitly enabled [Program-mode replacement](supported-routine-edits.md)
for this observed completion profile. Completed candidates survive Program
release until completion or cleanup; incomplete candidates are still discarded.
This software transaction does not implement the native Test/Untest/Assemble lifecycle.

## Replacement metadata

Version `.91` retains the observed signed `0x4F` request on Metadata Definition
class `0x349`, instance 1, sent after the paired code/source and post-source
record when a documented rung is replaced. Its 38-byte profile consists of
version `0x301`, body size 30, UINT Program/Executable class-and-instance pairs,
a nonzero region identifier, a zero selector, marker `0x7F`, three zero DWORDs
and trailing marker 4. The region identifier and marker semantics remain
opaque; this receiver does not apply active metadata writes.

It requires explicitly enabled supported edits, stopped Program mode, the
live edit owner, open preparation, a reserved Program and a complete validated
candidate for the same Program/Routine. The region must be absent from the new
source. Unknown fields, scopes, lengths and profiles are rejected. Repeated
identical records are idempotent. At most 1,024 records fit within the shared
256 KiB candidate limit and its original absolute deadline. Commit, cancellation,
disconnect and expiry clear retained records with the rest of the transaction.
Descriptions expose counts and hashes rather than identifiers or payloads.

The isolated two-routine native replacement case retains one record per edit
and succeeds, including both reconnects and final Offline, without a reported
fatal SDK fault. This establishes the tested transfer path and translated
logic replacement; complete native documentation semantics remain unverified.
