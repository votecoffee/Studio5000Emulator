# Source-bound Routine names

Version `.161` implements Executable attribute 25, Name, for a known Routine
under its original Program or AOI parent. The installed v35 Executable layout
defines a four-byte byte count followed by up to 40 ASCII bytes. The source
spelling is preserved without truncation, padding or case normalization.

The read requires the matching complete L5X Routine inventory, original native
child/parent IDs and ACD/L5X project identity. Missing, foreign or stale bindings
remain unavailable. Protected AOI children and unknown parents/children are not
exposed. Unscoped Routine instances cannot resolve through a different parent.
Name is known source metadata, so reading it does not assert clean execution,
unchanged logic, source-key interpretation or support for native online edits.
The existing code/edit-state guards remain independent. Writes remain denied.

Single and ordered bulk reads share the same value. The offline collection
decoder also accepts this bounded counted string for Program- and AOI-scoped
Routine lists. It rejects truncation, excess counts and trailing bytes, and
omits name bytes from normal reports.

## Upload and download investigation

A native SDK upload of an owned project containing one NOP Routine on `.160`
still fails Program upload after 357 verified requests, despite the complete
successful 22-field Routine metadata reply. It does not reach Routine source
retrieval. Actual Offline/cleanup, source/model preservation and no reported
SDK fault are confirmed, and the original demo is restored. The tested file
differs from the demo beyond its Routine count, so this is not a controlled
single-variable explanation of the failure.

The saved successful reference's three unsupported source containers use a
different compression-flag variant and do not decode as the supported zlib
stream. They remain errors. This does not establish encryption or any new
source-key semantics. Native Routine upload, a valid saved uploaded ACD, the
download result encoding and full native edit lifecycle remain unfinished.
The new Name read does not resolve that earlier upload failure.

## Validation

All 153 affected checks pass, including signed single/duplicate/mixed reads,
parent and source isolation, AOI protection, exact count/ASCII bounds, reply
budgets, write denial and preservation of execution/audit state. Known names
remain readable when code-state fields are withheld after a fault or logic
revision. The previous milestone's full suite is not rerun for this addition.

Live signed reads verify both demo Routine names before and after supported
Program-mode replacement, including mixed/duplicate reads, denied writes and
invalid scopes. Names remain available after the import while code-state fields
remain guarded. AOI Name coverage is from software tests, without a native AOI
transfer claim. SDK Go Online/Offline verifies 74 requests; supported import and
reconnect verify 188 with one expected revision/audit update. Both native cases
confirm Offline/cleanup, original-file preservation and no reported SDK fault.
The original demo is restored to stopped Program mode with zero scan/revision/
audit state. Source/build/appliance modules match, and browser, executable and
appliance versions all report `.161`.
