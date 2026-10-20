# Compiled Routine fragment staging

Version `.86` adds temporary storage for the observed online-import fragment
dialect, separate from Resilient Transport download preparation. It receives
bytes for an existing Program-scoped Executable `0x6D` service `0x5C`.

Every fragment requires a live owner of the Controller selector-1 reservation,
an open [edit-preparation phase](program-reservations.md), stopped Program mode,
a reserved Standard Program and matching original ACD/L5X Program/Routine
identities. The current profile is limited to an ordinary RLL routine in a
complete, unprotected source without AOIs or execution blockers. It does not
create native routine identities or accept other compiled routine formats.

The first fragment has the numeric operation path followed by four setup
DWORDs: `3`, `1`, an opaque value and `0`. Its remaining bytes begin the known
20-byte container header and an ELF candidate. The announced total and later
offsets cover that container. Header lengths and ELF magic are checked before
allocation; unknown header flags remain opaque. These checks do not establish
ELF validity, native instruction semantics, resolved relocations or execution.

The receiver retains a single contiguous assembly, at most 262,144 bytes and
128 fragments, with an absolute 30-second lifetime. Holes, overlap, target
changes, invalid final sizes and malformed owned chains discard the buffer.
Another client cannot append to or discard the owner's assembly. Program
release, phase close, Controller release, disconnect, expired context, source
replacement and endpoint shutdown clear all compiled bytes.

`native_programming_lease.edit_transfer` reports byte/fragment counts, bounds,
completion and the complete container's SHA-256. It exposes no payload bytes
or target identities. Installation, accepted edits, native execution and commit
remain false. SDK preflight and cleanup require idle empty storage.

Partial fragments receive the observed signed acknowledgement after their
bytes have actually been retained. When the final fragment completes storage,
the endpoint records the complete container and **rejects installation**. An
assembled binary is insufficient to implement its embedded Executable write.
The active source, tags, routines, scheduling and scan state remain unchanged.

Focused tests cover signed TCP assembly, source and ownership checks, capacity,
offsets, timeout and cleanup. An independent client also stages synthetic
partial ELF candidates against the original imported source bindings and
checks that Program release removes them. Native SDK results are recorded
separately; buffering code does not establish accepted online edits.
