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

In `.86`, partial fragments receive the observed signed acknowledgement after their
bytes have actually been retained. When the final fragment completes storage,
the endpoint records the complete container and **rejects installation**. An
assembled binary is insufficient to implement its embedded Executable write.
The active source, tags, routines, scheduling and scan state remain unchanged.

Focused tests cover signed TCP assembly, source and ownership checks, capacity,
offsets, timeout and cleanup. An independent client also stages synthetic
partial ELF candidates against the original imported source bindings and
checks that Program release removes them. Native SDK results are recorded
separately; buffering code does not establish accepted online edits.

## Native result

The isolated `.86` SDK `AcceptEdits` case uses unchanged public application
sources. Studio sends 11 contiguous fragments; the receiver retains all 4,304
container bytes and rejects installation at the final fragment. Independent
offline reassembly of the captured fragments matches the receiver's complete
SHA-256. The contained 4,284-byte file is a little-endian ARM ELF32 relocatable
object with 14 sections and 42 symbols. These observations do not resolve its
runtime imports, data references or instruction behavior.

The case verifies 111 signed requests and reports `RxCsE_ASA_NO_PERMISSION`.
Go Offline returns `RxE_COMM_NOTOPEN`, so native Offline cleanup is unconfirmed
for this case. Project close succeeds; endpoint state and compiled bytes clear
without explicit socket cleanup. The source ACD and active model are unchanged,
and no fatal SDK exception is reported. A subsequent connection/Offline check
against the prior `.85` main runtime succeeds; this is a separate recovery
check, not `.86` runtime acceptance or confirmation of the failed edit cleanup.

Installing a compiled routine requires implementing its native storage and
runtime contracts or a verified translation to the emulator's execution model.
A fragment acknowledgement and valid ELF layout alone cannot supply that step.

A separate private receipt-only experiment acknowledges the completed ELF
container without installing it. Studio then starts another fragment transfer
to the same Routine: a declared 688 bytes with a different initial setup
(`1`, `3`, followed by other fields). The public receiver rejects that setup;
the experiment also fails import and leaves native Offline cleanup unconfirmed,
with project close and endpoint cleanup complete and no reported fatal SDK
fault. Its modified final reply is absent from the public app. This conditional
trace identifies a further container contract to investigate; it establishes
neither accepted edits nor a working installation path.

Version `.87` extends this receiver to paired code and [Routine source](routine-source.md)
containers. The code receipt acknowledges retained bytes; the source component
then decodes and translates supported object references, with a detached plan
check. Installation is rejected after the source component. Both components
remain under the same owner, target, combined byte/fragment limits and absolute
deadline; neither changes active execution.

Version `.88` acknowledges validated source storage and retains the observed
[post-source record](edit-post-source.md), under the same ownership, target,
combined capacity and deadline. The next Controller operation is
still denied. Source activation and accepted controller edits remain unfinished.
