# Native download preparation

Version `.65` extends this preparation with
[temporary library descriptors](library-staging.md). The notes below record
the `.64` milestone and its then-current library Create boundary.

Version `0.6.0-connectivity.64` adds an owner-scoped preparation state to the
native coordination lease. The tested v35 SDK advances past Controller setup
and reaches a library-object Create request. Project transfer, commit and
online edits remain unsupported.

## Software contract

These requests require a checked signed envelope and a bound native context.
Preparation changes additionally require the live lease owner, matching source
generation and ACD/L5X correlation. Controller paths address class `0x8E`,
instance `1`, with no parent object or symbolic scope.

| Request | Supported behavior |
| --- | --- |
| Service `0x60`, empty payload | Require Run Mode Inhibit mask `1`; enter preparation and return an empty success reply |
| Get Single/List attribute `26` | Return UDINT `2` while prepared, otherwise `0` |
| Set Attributes List, attribute `9`, BOOL `0` | Acknowledge the existing disabled redundancy setting only when complete source explicitly establishes that setting and the owner is prepared |
| Service `0x62`, empty payload | End preparation; retain the existing scan inhibit |
| Clear Run Mode Inhibit | Clear preparation and permit subsequent scans |

Begin/end requests are idempotent for the owner. Another bound client can read
status but cannot change preparation or acknowledge configuration. The
attribute `9` acknowledgement never changes redundancy configuration; unknown,
enabled or changed settings are rejected. Other programming setters, service
`0x61` and library Create remain denied.

Status `2` is the software state that advanced the tested SDK. This observation
does not establish the complete physical controller transaction contract.
No project or library bytes are accepted by these operations.

## Lifecycle and diagnostics

Lease release, disconnect, expiry, invalidation, reset, project reload and
endpoint stop clear preparation and its scan inhibit. Ending preparation alone
does not resume scans; the owning client must clear the inhibit or end its
lease. The existing [scan and input-queue guard](run-mode-inhibit.md) continues
to apply. Source configuration, Timeline UID, tag values, scan count, model time
and controller mode remain unchanged.

`native_programming_lease` exposes `preparation_state` (`idle`/`ready`) and
`preparation_status` (`0`/`2`). Transfer, online-edit, tag-write and mode-change
authorities remain false. Accepted operations increment
`native_preparation_begin`, `native_preparation_end` and
`native_configuration_retained`. Rejection diagnostics describe missing
ownership, scan inhibit, preparation or source configuration. The Connectivity
summary shows **native preparation ready** while the existing **SCANS
INHIBITED** controls remain active.

## Validation and next gap

Eight added behavioral tests cover ownership, source binding, exact framing,
single/list status, signed batches, unchanged configuration, scan inhibition,
independent clients and cleanup. All 861 tests pass on Windows and Linux, with
two Windows skips and one Linux skip.

An isolated final-source SDK download attempt verifies 107 signed requests.
It accepts service `0x60`, observes status `2`, retains the source redundancy
setting, then fails `RxCsE_DOWNLOAD_OF_LIBRARYOBJS_FAILED` at Create (`0x08`) on class
`0x37D`. Cleanup accepts service `0x62`, reads status `0`, releases the lease
and returns Offline. Original/copy hashes, modeled values and scan count are
preserved. Private ACDs, native library payloads and traces are not distributed.

The rebuilt and deployed `.64` runtime reproduces that 107-request download
sequence and passes 273 wire checks. Packaged/served browser assets and deployed
modules match source. The public SDK probe completes all nine connection/Offline
steps with 81 verified requests. Tag reads still fail online-address discovery
across 83 requests; upload still fails controller collection across 201 requests
after accepting twelve scalar reads and their Symbol descriptors. These are
observed request counts for the recorded runs.

All four public probes confirm SDK Offline and endpoint cleanup, unchanged
source hashes and modeled state. The final endpoint has zero clients, a free
lease, idle preparation, zero scan inhibit and scan count zero. FactoryTalk Linx
and the Logix Designer SDK service remained running. Complete native transfer,
Studio GUI monitoring and online edits remain unsupported or unverified.

The next step is to define and validate bounded library-object staging,
validation, commit and rollback before accepting that Create request. Native
upload, compiled tag-address discovery, Studio GUI monitoring and online edits
remain separate unfinished acceptance stages.
