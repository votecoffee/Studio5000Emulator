# Installed scalar word online reads

Version `26.1028.112823` extends this profile to [validated tag readback after
routine-only edits](edited-tag-readback.md). Current tag values, committed Table
identities and original Symbol Control remain readable with per-request layout,
source and binding checks. Historical Routine components remain separate.

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

Version `26.1026.122552` separately supports source-bound scalar DINT constants
through ordinary Data Table descriptors and read service `0x4F`. This requires
a completed unchanged source-equivalent installation, verified header/effect
bindings and a current value identical to its prepared source bytes. The
constant flag remains set; tag writes and UserMemory reads of constants remain
blocked. Generic uninstalled constants retain unavailable storage fields.

The two-Program native snapshot completes across 1,188 verified requests,
including an actual constant Table read of `1000` and independent saved-value/
flag checks. Typed Online getters also verify mutable BOOLs and DINTs with
duplicate names in different Programs. Their model value addresses remain
distinct. Native Offline cleanup and no SDK fault are confirmed.

Version `26.1026.124956` extends the constant Table path to bounded complete
BOOL/numeric roots, including numeric arrays and supported packed BOOL arrays.
The shared installation check verifies the original source, namespace, header
effects and prepared values. Readback then checks the exact scoped Symbol/Table
binding, storage type and full byte count before comparing every current byte
with its source value. This supports different scalar widths without treating
them as four-byte UserMemory words.

Constants retain their flags and write restrictions. At that checkpoint,
UserMemory constant reads, constant structures, aliases, arbitrary ranges and
host memory remain outside the profile. Whole roots must fit the negotiated Table reply budget; oversized
responses fail rather than returning partial values. Generic uninstalled
constant storage remains unavailable.

Version `26.1026.131441` also admits explicit user-defined structure roots and
structure arrays. The installed native Template snapshot must bind the source
member layouts, identities and storage size. The full encoded value, including
reserved padding and packed bits, must match its prepared source bytes. Each
visible member read rechecks external access. Unsupported built-in structures,
unknown layouts and arbitrary memory remain unavailable; constant writes and
UserMemory constant reads stay blocked.

## Constant upload checkpoint: `26.1026.124956`

A source-authored two-Program project contains 26 roots (102 bytes), seven
constants and thirteen rungs. The constants include BOOL, INT, DINT, REAL,
LINT, a DINT array and a packed BOOL array. Native download/save/reopen/Online
passes across 436 verified requests. Upload snapshot/save/reopen/Online then
passes across 1,206 requests while five mutable local values differ from the
saved source.

Independent recorded-response inspection checks all seven constant Table
descriptors and 35 value bytes, including the eight-byte LINT and packed BOOL
word. All saved constant values and flags match. Both native Program exports
and the complete saved L5X preserve all values and thirteen rungs. Eleven
mutable BOOLs and five DINTs pass typed Online checks. Temporary mutable
values are restored without scanning; native Offline cleanup and no SDK fault
are confirmed.

The complete 1,759/4,494-event download/snapshot recordings replay identically
offline. Replay does not independently reauthenticate MACs. The snapshot still
requires an unchanged source-equivalent installation and matching saved baseline;
general Studio GUI upload/save remains unfinished. The revision passes 343
affected software checks and 367 Python syntax checks.

## Constant structure checkpoint: `26.1026.131441`

The expanded two-Program profile adds a nested UDT and a UDT array, with three
constant roots occupying 100 bytes. It completes download/save/reopen/Online
across 435 verified requests and upload snapshot/save/reopen/Online across
1,221. All 29 roots (202 bytes), four routines and thirteen rungs match the
uploaded SDK values, native Program packages and saved full L5X. The installed
download binds its actual Template definitions against the original sources.

Independent recorded-response checks verify all ten constant descriptors and
135 value bytes, including 16/52/32-byte structured roots. All constant flags
and values survive saving; packed bits, member arrays and reserved padding
match the source encodings. Five mutable local changes are captured separately,
then restored without scanning. Eleven BOOL and five DINT Online getters pass.
Native Offline cleanup and no SDK fault are confirmed.

Complete 1,755/4,550-event download/snapshot recordings replay identically
offline, without independent MAC reauthentication. The revision passes 374
affected checks and 367 Python syntax checks. General GUI upload/save and
unbound project reconstruction remain unfinished.

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
