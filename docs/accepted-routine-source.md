# Accepted edited Routine source readback

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

Selector `(1, 4)`, opaque component `(1, 9)`, unrecorded routines and complete
edited-project upload remain unavailable after edits. This does not implement
native compiled-code execution, Test/Untest/Assemble, updated vendor metadata or
the complete online-edit upload lifecycle. [General upload/save](upload-to-acd.md)
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

## Native checkpoint

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
