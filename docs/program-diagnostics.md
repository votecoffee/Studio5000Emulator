# Program output, edit and fault diagnostics

Version `.120` adds bounded read-only Program diagnostics to the native profile:

| Attribute | Read | Conditions |
| --- | --- | --- |
| `7` Output List | Null four-byte ACADDR | Complete ordinary source proves no external I/O, produced/consumed or aliased tags, Program parameters or connections |
| `11` Edits Mode | Two-byte zero, not testing edits | Explicit `TestEdits=false`, visible ordinary RLL routines containing normal rungs, and no relevant native edit reservation, phase or transfer |
| `20` Local Major Fault | Empty 44-byte record | Supported scheduled whole-project execution with no emulator fault since reset |
| `21` Local Minor Fault | Empty 44-byte record | Same as `20` |

The source SHA and original native Program binding must match. Single and list
reads share the same values; setters remain denied. A null output-list reference
does not invent a compiled address or implement I/O connections. Unknown,
protected, contextual or noncanonical declarations remain unavailable. Output
parameters, connections, aliases and produced/consumed data withhold the null
list even when no external I/O module is present.

## Edit state

Rockwell's [Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
defines `TestEdits=false` as not testing edits. The diagnostic also checks for
normal RLL rungs and absence of alternate edit content. It does not default a
missing flag, infer untested state from opaque logic, or treat pending/tested
edits as ordinary rungs.

A relevant Program reservation, open edit phase or staged transfer makes this
read unavailable. Cleanup or expiry can restore it when the source still
qualifies. Existing supported direct Program-mode routine replacements leave
no test-edit alternative; this diagnostic does not implement Test, Untest or
Assemble operations, or add a tested-edit mode.

## Fault history

A fresh supported engine starts with no simulator fault history. Its empty
records contain zero timestamp, type, code and info fields. Prescan, scan-worker
and execution faults invalidate this known-clean state. Simulator failures have
no established native fault code mapping, so both records become unavailable.
The endpoint never invents a native code or turns an unknown fault into an
empty record.

That uncertainty survives a subsequent successful scan, clearing the displayed
fault string, and supported in-memory routine replacement. Loading or resetting
the engine establishes a new history. Blocked execution, disabled/unscheduled
Programs and isolated routine harnesses do not expose these whole-Program
records. Physical controller fault history is not imported.

The endpoint exposes aggregate `program_diagnostics` and `program_faults`
availability summaries. Reads do not advance scans or alter tags. Empty native
records describe this model's known-clean history; they do not establish full
native fault handling or equivalence to a physical controller.
