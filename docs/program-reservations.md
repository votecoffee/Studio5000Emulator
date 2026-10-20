# Program preparation reservations

Version `.84` preserves Program parent scope for Semaphore `0x74` paths and
models a bounded reservation on an existing source-bound ordinary Program.
The observed native online-import path is Program `0x68/<id>` followed by
Semaphore `0x74/1`. Its `0x4B` acquire request has one selector byte, `0`;
`0x4C` release has no payload. This is separate from Controller-scoped
coordination and from selector-1 Program coordination inside temporary
download batches.

Acquire and release require the live owner of the Controller's selector-1 edit
reservation, matching original ACD and L5X bindings, a known Standard Program
and stopped Program mode. Unsupported selectors, scopes, extra data and
unknown Programs are rejected. Unsigned clients cannot reserve a Program.

The model retains at most 128 Program reservations. Repeating an acquire or
release for the same Program and owner is idempotent. Reservations block a
new Run request until released, without changing the Controller Run Mode
Inhibit attribute. They neither run a partial scan nor change Program source,
tag values, scheduling or active routines. Release does not start execution.
Controller release, disconnect, context expiry, source replacement and endpoint
shutdown discard all subordinate reservations.

`native_programming_lease.edit_preparation.program_reservations` exposes only
the aggregate count. The SDK probe requires zero reservations before a case
and during cleanup. Detailed Program IDs remain in private protocol evidence.

## Controller preparation and zero stack

Version `.85` models the observed Controller `0x8E/1` services `0x55` and `0x57`
as opening and closing a software preparation phase. Both require an empty
payload, stopped Program mode, the current source identity and the live owner
of selector 1. Opening is idempotent and blocks Run even when no Programs are
held. Closing fails while a subordinate Program remains reserved; otherwise it
clears preparation and releases the phase's Run inhibition. Controller release,
disconnect, expiry, source replacement and endpoint shutdown also clear it.

The installed v35 Program attribute description identifies attribute 27 as the
UDI Stack Size, a BITS32 value. The emulator exposes a modeled zero only for a
complete, unprotected source with an explicit empty AOI-definition section, no
runtime AOIs or execution blockers, and complete executable inventory for the
Program. Other cases leave the attribute unavailable. An exact one-attribute
set-list proposal of zero additionally requires the open phase, matching
original ACD/L5X bindings and the requesting owner's Program reservation.
Nonzero values, unknown attributes and unsupported scopes are rejected. The
proposal records temporary preparation; it allocates no memory and changes no
active stack, tags, routines or source. Program release removes its proposal.

The state reports `phase_open`, aggregate `program_stack_preparations`,
`stack_bytes_allocated: 0` and `active_stack_changed: false`. Probe preflight
and cleanup require all preparation to be idle. The independent inventory
reader distinguishes an available zero from an unavailable attribute.

Version `.86` adds a separate [compiled Routine fragment receiver](edit-transfer.md)
inside this preparation phase. It shares ownership, source and Program holds;
release also clears its temporary binary. Download preparation keeps its own
receiver, and a completed edit binary cannot be installed or accepted yet.

## Native evidence and limits

The `.84` private experiment supplied a hypothetical empty success reply for
Controller `0x55`. It exposed the Program reservation and zero attribute-27
proposal, which the ordinary `.84` app denied. The SDK released its reservations
and confirmed Offline cleanup without a reported fatal SDK fault. Version `.85`
replaces that hypothesis with the preparation state described above. The
observed request order and local attribute description guide this bounded
software model; they do not prove the complete firmware contract for these
services, native stack allocation, compiled edit storage, accepted edits,
testing or assembly.

The isolated `.85` native `AcceptEdits` probe uses unchanged public application
sources. Studio accepts phase open, Program reservation and the zero-stack
proposal, releases and reacquires the Program, then sends a `0x39` first
fragment containing Program-scoped Executable `0x6D` service `0x5C` and opaque
ELF bytes. It declares 4,304 total bytes and carries 456 bytes in that fragment.
The receiver only supports fragments under download preparation and rejects
this edit transfer. The attempt verifies 103 signed requests and fails with
`RxCsE_ASA_NO_PERMISSION`. Its Go Offline call also fails with `RxE_COMM_NOTOPEN`,
so native Offline cleanup remains unconfirmed for this case. Project close
succeeds, endpoint temporary state clears without explicit socket cleanup,
source/model state is unchanged and no fatal SDK exception is reported.
Fresh connection/Offline and mode cases subsequently succeed independently;
they do not retroactively confirm this edit case's native cleanup.

Focused tests cover real signed TCP reservations, parent IDs of different
widths, source and ownership mismatch, capacity, malformed payloads, unchanged
execution state, Run inhibition and cleanup. The independent research client
also checks phase open/close, Program acquire/release and zero-stack proposal
and readback against the original imported source pair.

Version `.89` retains a fully validated code/source/post-source candidate
through Program release, under the owning Controller lease. The following
supported completion may [replace the Program-mode routine](supported-routine-edits.md).
Incomplete candidates still clear at Program release; phase close, expiry,
disconnect or source replacement discard any uncommitted candidate. Reservation
cleanup does not undo a replacement that already completed.
