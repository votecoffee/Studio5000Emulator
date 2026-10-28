# Accepted edited Routine source readback

Version `26.1028.132722` also [retains the bounded selector-9 profile and
empty selector-4 stream](routine-profile-readback.md) through supported source
replacement. The SDK now reads both routines' source and components; complete
edited upload next stops at the guarded all-object metadata query.

Version `26.1028.121233` [preserves pinned Source Key metadata after verified
plain RLL edits](routine-source-key-retention.md). Native offline edit/save/reopen
checks show the original opaque configuration stays unchanged. Earlier versioned
checkpoints below retain their original scope.

Version `26.1028.094227` retains the exact native source container when a
supported Program-mode RLL edit commits. Previously the temporary transfer was
cleared after updating interpreter logic, leaving no current native source for
later readback. Original downloaded components remain historical snapshots.

Each retained record binds the complete source bytes, SHA-256, native Program/
Routine scope, original source identity and accepted revision. A later edit to
the same routine replaces its record without changing the preceding Engine.
An internal replacement without native source revokes that routine's record.
Reset/reload does not carry these records into a different source project.

The existing signed Routine read service can return selector `(1, 3)` for a
recorded edited routine on an installed download. It checks the live source and
catalog bindings, current Standard RLL routine and every resolved TextIOI rung
before returning data. Native RegionIds, TextIOI and compressed auxiliary bytes
are preserved. The served view adds the explicit Standard upload class using
the existing bounded container conversion. Each continuation rechecks the model;
a new edit revokes an in-progress stream.

Version `26.1028.103821` also preserves validated original source containers
when a download installs. After an edit, untouched routines can still return
selector `(1, 3)` from this immutable source-only snapshot. Each read verifies
the original catalogs, exact bytes, native scope and every active ladder rung.
Empty routines retain their exact empty container; no rung is invented. Editing
a previously untouched routine switches it to its accepted edit source. A missing
edit record never falls back to the original download. This snapshot contains
no executable components and does not make original vendor metadata current.

Edited routines without recorded source and complete edited-project upload
remain unavailable. The bounded profile retention above does not implement
native compiled-code execution, Test/Untest/Assemble, updated general vendor
metadata or the complete online-edit upload lifecycle. [General upload/save](upload-to-acd.md)
continues to require unchanged source.

Storage is bounded to 128 retained routines and 8 MiB per project, within the
existing per-transfer bounds. Allocation/validation occurs on the detached edit
candidate before changing the active Engine. A failure preserves the original
logic, values and retained history. The `routine_edits.native_source_readback`
state reports counts, byte extent and supported selector, without source payloads.

Focused checks cover actual signed edit commit retention, fragmented source
readback, native RegionIds/auxiliary preservation, same-routine replacement,
stale-stream rejection, missing or altered bindings and atomic storage failure.
Software/protocol checks remain separate from Studio GUI acceptance.

The SDK edit probe can use `--connection-target` to open a preserved matching
saved-download ACD after a download, while `--project` continues to pin the
emulator's original source. Edit targets require an unchanged source-equivalent
installation and unedited saved correlation; admission is checked again after
building. The original ACD and saved target are preserved on private copies.

## Native checkpoint for 26.1028.094227

The v35 SDK applies two ordinary Program-mode edits in separate ConveyorDemo
routines using a saved-download target and reconnects after each, across 291
verified requests. Both exact source containers remain after native Offline
cleanup. A separate read-only peer reads both sources over the signed transport,
verifies every response MAC and compares the complete returned source with the
SDK's actual transmitted containers. Native RegionIds and auxiliary data match;
independent IOI resolution matches every active ladder rung. Values and scan state
remain unchanged by editing/readback. This establishes accepted source readback,
not SDK full-project upload after edits.

The same deployed version also passes native download/save/reopen/Online across
429 requests and unchanged-source upload/fresh-L5X ACD save/reopen across 1,053.
All fourteen tag values, both routines and ten rungs verify. Host SDK/Linx services
remain running; the original demo is restored after the edit check.

## Native checkpoint for 26.1028.103821

The updated version passes native download/save/reopen/Online across 433 verified
requests, including all fourteen tag values, both routines and ten rungs. One
Program-mode SDK edit and reconnect passes across 185 requests. A separate signed
peer reads both routine sources before and after the edit and verifies every
response MAC. The changed routine matches the exact SDK edit container; the
untouched routine matches its pre-edit source bytes. Both independently resolve
to every active ladder rung, preserving RegionIds and auxiliary data. Each source
uses two signed frames, and reads leave values, scan state and edit state intact.
These are source-read checks, not a complete SDK upload of the edited project.

## Current state metadata after edits

Version `26.1028.105723` keeps Executable class revision 11 for the supported v35
Standard RLL inventory after an edit when every current routine source verifies.
The same source checks gate clean idle-state attributes, live interpreter header
references and empty Label discovery. Source checks bind the current Engine and
native scope on every metadata request; earlier successful reads grant no cache.
Reservations, pending transfers, active execution, fault history and unsupported
source continue to withhold state. A missing or corrupted edit source revokes its
state and prevents complete typed inventory recognition.

The edited routine does not expose its original opaque source-key attribute 22.
An untouched routine retains that attribute only with verified original source.
This does not synthesize a replacement key, compiled components or change-log
records, or implement Test/Untest/Assemble. Complete upload after edits remains
unfinished. Focused signed checks cover the two scopes, source corruption, stale
Engine proof, reservations, faults, live references and empty Label discovery.

The deployed version passes native download/save/reopen/Online across 428
verified requests and one Program-mode SDK edit/reconnect across 186. A separate
read-only peer verifies signed bulk metadata and source reads before and after
the edit. Both routines retain class revision 11, clean idle-state fields and
empty Label discovery; the main header reference matches its Program reference.
Only the changed routine withholds source-key attribute 22, and the untouched
key matches its pre-edit value. Every reply MAC verifies; both source containers
match active logic. These checks leave tag values and scan state unchanged.
Complete SDK upload after edits is not established by this metadata checkpoint.
