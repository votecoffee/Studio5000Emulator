# Tag readback after routine edits

Version `26.1028.121233` [preserves pinned Source Key metadata after verified
plain RLL edits](routine-source-key-retention.md). Native offline edit/save/reopen
checks show the original opaque configuration stays unchanged. Earlier versioned
checkpoints below retain their original scope.

Version `26.1028.112823` preserves validated ordinary tag bindings when a
source-equivalent download installs. Previously a routine edit disabled the
installed Table map, making discovery fall back to Symbol IDs. Installed-address
reads also required unchanged Routine headers, even when tag storage was intact.

The installed tag view retains committed Table identities, source Symbol scope,
value handles, type codes and original Symbol headers. Current values come from
interpreter memory, using the existing scalar, array and structure storage
layouts. Original saved values establish installation provenance; they are not
replayed as current running values. Symbol and Table IDs remain separate.

A routine-only edit creates a new immutable binding view for its exact Project
and revision. Earlier views retain their original association. Every read checks
the current source identity, native catalogs, shared tag/type/Program/Task
configuration, initial source values and committed tag headers and table handles.
Changes revoke the view. Merely setting a runtime revision does not authorize
readback, and missing bindings never fall back to unrelated Symbol IDs.

Supported native reads include Data Table discovery and complete value reads,
ordinary Symbol Control metadata, and the existing exact DINT/BOOL installed
UserMemory word reads. Constants retain their verified source value and read-only
profile; an altered constant is not returned as valid source data. Private tags
and disabled network writes retain their access restrictions. Reads do not
advance scans or change tag values.

This view is independent of historical Routine components. It can expose current
tag values even if edited native source readback is unavailable or the interpreter
has faulted. It does not make original compiled code or Routine metadata current,
add a setter, persist an edited project or establish full SDK upload after edits.
That still needs change-log and component support; Source Key handling follows
the versioned pinned-configuration profile described above.
See [edited Routine source and state](accepted-routine-source.md) for that scope.

Focused checks cover current values after repeated edits, committed identities
and Control, stale views, altered layout/access/source/headers/handles, missing
bindings, and read-only constant verification. Model/protocol checks remain
separate from native SDK and Studio GUI acceptance.

## Native checkpoint

The deployed version completes native download/save/reopen/Online across 429
verified requests. A Program-mode SDK edit and reconnect completes across 189
requests, including successful post-edit DINT getters for SpeedSetpoint (50),
SpeedCommand (0) and DisplayedPartCount (0), with actual Offline cleanup and no
SDK fault.

A separate read-only peer verifies every response MAC while reading all fourteen
tag roots (45 value bytes), Table links, addresses and Control words before and
after the edit. The values and descriptors match exactly, including the demo
BOOL, DINT, TIMER and COUNTER roots. Both routine source streams and current
metadata still verify independently. These reads leave values and scan state
unchanged. The demo uses equal Symbol/Table IDs; native post-edit coverage of
a differing-ID profile remains separate work. Full SDK upload after edits and
Studio GUI monitoring are not established by these checks.
