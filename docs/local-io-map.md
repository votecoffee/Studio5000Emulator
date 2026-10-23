# Local I/O Map metadata

Version `26.1023.091827` exposes three read-only fields for the canonical Local
L85E I/O Map instance, class `0x69`, instance 1.

| Field | Wire type | Model backing |
| --- | --- | --- |
| 9, Link Port | UINT | Local module's `ParentModPortId`, validated as port 1 |
| 10, Link Address | UDINT | Its canonical ICP port's `Address`, validated as slot 0 |
| 13, Map Address | UDINT | Reference to the current interpreter's I/O Map object |

The installed v35 attribute definitions independently name these fields and
their types in I/O Map schema revisions 1, 9 and 17. A successful reference
download contains the same two/four/four-byte response layout. The app returns
its own backed reference rather than importing a captured controller address.
The definitions and private capture are not distributed with the repository.

## Source and lifetime

The existing complete-source check must establish one self-parented Local
`1756-L85E` controller module, its unique ICP port 1, downstream routing and
slot-zero address. Context, ambiguous/namespaced/protected declarations,
external modules, module tags and force declarations retain unavailable data.
An empty `Modules` section alone does not establish a Local map object.

Map Address resolves only to that current interpreter object and source hash.
Replacing the object or reloading the project revokes the old reference. New
allocations never reuse an address in the process. Address exhaustion leaves
field 13 unavailable while preserving the source-backed link fields; it does
not return a null successful address. Link fields and Map Address do not
install an I/O connection, import physical health or enable memory access.

## Protocol behavior

Get Attribute Single and ordered/duplicate Get Attribute List reads retain the
declared widths and stable reference. The three-field download query uses
attributes 9, 10 and 13. Unknown fields retain per-attribute errors, and setters
remain denied. Class-level field 9 is the separate empty force-status contract;
it does not supply the instance's Link Port.

The implementation shares the interpreter object registry with Program,
Routine and Task references. Its routing layer only reads those model values.
Complete native download, upload and Run-mode edits remain separate milestones.
