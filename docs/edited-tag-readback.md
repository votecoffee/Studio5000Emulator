# Tag readback after routine edits

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
That still needs current source-key metadata, change-log and component support.
See [edited Routine source and state](accepted-routine-source.md) for that scope.

Focused checks cover current values after repeated edits, committed identities
and Control, stale views, altered layout/access/source/headers/handles, missing
bindings, and read-only constant verification. Model/protocol checks remain
separate from native SDK and Studio GUI acceptance.
