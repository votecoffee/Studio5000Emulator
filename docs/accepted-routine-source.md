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
