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

## Native evidence and limits

The ordinary app still denies unresolved Controller services `0x55` and `0x57`.
A private experiment supplied a hypothetical empty success reply for `0x55`;
that reply is absent from the app. With that experimental precondition, the SDK
issued the Program acquire, accepted its real reservation response, then issued
a Program attribute-27 write. The app denied the write. The SDK released the
Program and Controller reservations and confirmed Offline cleanup, with the
source/model unchanged and no reported fatal SDK fault.

The installed v35 Program attribute description identifies attribute 27 as the
UDI Stack Size, a BITS32 value. Its active write and stack-allocation contract
remain unimplemented. The trace establishes the requested path and request
ordering; it does not establish the Controller `0x55`/`0x57` contract, active
stack changes, compiled edit storage, accepted edits, testing or assembly.

Focused tests cover real signed TCP reservations, parent IDs of different
widths, source and ownership mismatch, capacity, malformed payloads, unchanged
execution state, Run inhibition and cleanup. The independent research client
also checks Program acquire/release against the original imported source pair.
