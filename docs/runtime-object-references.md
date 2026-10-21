# Runtime object references

Version `.122` supplies two Program `0x68` reads from a small interpreter object
address space. They are opaque, aligned DWORD references in the emulator process:

| Attribute | Backing object |
| --- | --- |
| `5`, Main Executable | The current Program's main RLL Routine |
| `16`, Program Address | The current interpreter Program |

The values resolve internally to actual objects. Logical native instance IDs
remain separate. Addresses are stable across reads of the same object and are
never reused within the process. Replacing an object revokes its old reference;
new engines, including reset and routine replacement, have separate registries.
Resolution checks the exact Project object, target object and reference kind.
Exhaustion withholds values without wrapping.

Reads require complete ordinary v35 source, an executable whole-project model,
matching original ACD/Program/Routine identities, visible RLL routines, an actual
main routine, explicit untested edits and idle native edit preparation. Missing,
opaque, foreign, blocked or unsupported inventories withhold the references.
Native writes remain denied.

The API's `runtime_references` description identifies this scope. These values
are emulator object references. No physical heap addresses, native compiled
code, arbitrary memory access or new execution services are imported or exposed.

## Evidence and remaining work

Offline analysis of the saved successful upload found 20 Programs with nonzero
Main Executable and Program Address values. None equaled its logical Program
ID. Neither value appeared in subsequent decoded leaf requests in that capture.
This observation supports keeping object references separate from logical IDs;
it does not establish all address-consuming services or their contracts.

The isolated `.122` SDK upload accepts both new fields in its 22-field Program
read. Only `29`, Synchronize Data, remains unavailable there, compared with three
unavailable fields in `.121`. The owned native export omits that setting;
the emulator continues to require its explicit source value. Successful field
reads do not establish full Program reconstruction or identify every transfer
blocker. The attempt still reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` across 202
verified signed requests, with Offline, cleanup and unchanged source/model
confirmed, and no reported fatal SDK fault.

This diagnostic uses an isolated owned project, a source-bound Template snapshot
and unshipped clock/revision hypotheses. The released profile retains its prior
clock behavior. Its unchanged public-profile upload failure is not rerun in this
iteration. Release connection acceptance is checked separately. Full native
upload/download, complete online-edit acceptance and Studio GUI monitoring
remain unfinished.
