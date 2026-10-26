# Installed scalar word online reads

Version `26.1026.085243` supports the observed signed UserMemory request for an
exact scalar DINT value retained by a completed source-equivalent download.
It joins a saved download address to the current interpreter value, rather
than returning the staged initial bytes.

Version `26.1026.112241` adds exact ordinary scalar BOOL allocations. The
count-one reply contains four bytes: the current BOOL in its low byte and
three explicit zero bytes. Separate native SDK sessions verify `true` and
`false` through `GetTagValueBOOLAsync`, each across 74 verified requests with
actual Offline cleanup and no fault. Recorded replies independently match
`01000000` and `00000000` at the same installed address. This is a bounded
model word profile, not arbitrary memory or BOOL-array bit storage.

The SDK's typed online tag request uses class `0x72`, instance `0`, service
`0x4C`, with a little-endian 32-bit address and a 16-bit count of `1`. This
profile returns exactly four DINT or padded BOOL bytes. Other counts, interior addresses,
descriptor addresses, auxiliary tables and other data types remain unavailable.
This does not establish a general memory-read dialect.

## Binding and access

The request must arrive through a bound signed native compatibility session.
Unsigned access, UserMemory setters and allocation services remain blocked.
The address must identify exactly one installed ordinary, nonconstant scalar
DINT or BOOL. Source identity, type/catalog bindings, the preparation/effect ledgers,
declared tag shape and current external access are checked before reading.

Values are encoded from current model memory under the existing endpoint
serialization. Reads do not execute scans, change mode or update the audit
value. No host memory, physical controller memory, arbitrary pointer traversal
or general address range is exposed.

Reset, reload, restart, changed source, inconsistent effects and routine edits
revoke this installed-source view. Ordinary research-mode Data Table services
retain their existing behavior.

## Evidence and validation

The preceding native SDK connection goes Online and Offline normally, but its
`GetTagValueDINTAsync` request is rejected by the read-only policy. The captured
address belongs to the committed download's DINT value allocation. The
installed v35 schema identifies the class as UserMemory; it does not authorize
general memory services.

Four signed TCP checks cover current positive/negative DINT values, unchanged
model/scan state, unsigned denial, unknown or interior addresses, invalid paths
and counts, write denials, changed source/effects, private/constant tags and
reset revocation.

## DINT native checkpoint: `26.1026.085243`

On that version, source-equivalent download/save/reopen/Go Online succeeds
across 430 verified requests. Two separate SDK sessions then reopen that saved
ACD and successfully call `GetTagValueDINTAsync` while Online. They return the
current model values `87` and `-123`, although the saved ACD value is `50`.
Each session verifies 75 requests, confirms Offline cleanup and reports no
SDK fault. Independent inspection of each session's recorded request interval
matches both four-byte replies to the exact installed address. Offline
inspection does not independently reauthenticate the recorded MACs.

No scans execute, and the reads preserve source, logic, values and audit state.
The temporary values are restored to `50` afterward. Other tag types,
array/member monitoring, native writes and Studio GUI monitoring remain
unverified or unsupported.

A subsequent upload regression times out after 866 verified requests. Its
complete recording contains no call to the new UserMemory read service and no
new native rejection, but it does not establish the cause of the timeout or a
completed upload. The SDK service remains running; the SDK call outcome and
native Offline cleanup are unknown. The emulator endpoint is idle and its
source/model/audit state is preserved. That call's outcome remains unknown.
A later fresh saved-project connection succeeds across 73 requests with
confirmed SDK Offline cleanup. A new upload succeeds across 980, independently
verifying all 14 values and both routines, again with normal cleanup and no
fault. This confirms recovery without establishing the timeout's cause.

The milestone passes 2,120 software tests with two platform checks skipped;
all 363 Python files parse. Source, executable, browser assets and all 120
deployed modules match the release. These checks do not establish controller
equivalence or uploaded ACD persistence.
