# SDK-free upload inventory reader

`source/tools/upload_inventory.py` exercises the emulator's read contracts
without Studio 5000 or the Logix Designer SDK. It accepts an already-loaded,
owned, in-process `Endpoint` bound to loopback with native read mode enabled
and network writes disabled. It accepts no remote address and imports no ACD.

```python
from tools.upload_inventory import collect_inventory, Limits

report = collect_inventory(owned_endpoint, read_values=True,
                           limits=Limits(instances=4096, programs=128,
                                         tasks=32, routines=4096,
                                         pages=128, requests=16384))
```

The existing independent `AnonymousClient` performs a fresh TCP challenge and
checks signed replies with its ephemeral key. Its optional `cryptography`
dependency is required. The inventory reader does not patch the endpoint,
share server keys, acquire a programming lease or request Run/Program changes.

The reader:

- Compares source/catalog revision before and after the inventory and checks
  the same application instance, source bytes and generation for every request.
- Reads Controller configuration and retains unsupported aggregate and handler
  responses as evidence. It does not invent a `POINTER` decoder.
- Enumerates Program, Task, scoped Executable, Symbol and Data Table catalogs with bounded sparse-ID
  pagination, independent class counts and exact attribute-list framing.
- Reads Task priority, output-update/inhibit flags and explicitly available
  rate/watchdog values in wire microseconds. Task attribute 16 remains an
  individual unavailable row: a native CIP Task path ID is not assumed to be
  the Task GSV Instance slot.
- Decodes Task attribute 1 as a UINT16 count followed by ordered UDINT Program
  IDs, bounded to the installed plain v35 Task ADF's 1,028 entries. Zero IDs,
  repeats, truncation, trailing bytes and excessive counts fail decoding.
- Resolves each scheduled Program reference against the separately discovered
  source-bound Program catalog, preserving schedule order and sparse IDs.
- Reads Program attribute 27 as a UDINT. A source-supported zero UDI-stack
  requirement remains distinct from an unavailable stack attribute.
- Keeps controller and Program namespaces distinct and checks Symbol/Data Table
  links, types, dimensions, value addresses and scalar element sizes.
- Reads supported scalar bytes through Data Table service `0x4F` with selector
  zero and the complete atomic width. The values come from wire replies.

Unavailable catalogs retain `instances: null` and their status, separately
from a successful empty catalog. Attribute failures remain individual rows;
duplicates, byte alignment and response order are preserved. Missing storage,
aliases, constants, arrays and unsupported types do not acquire zero values.
Unknown scalar values retain their read failure. Nonfinite floating-point
encodings retain raw bytes and an explicit label rather than invalid JSON.

Task catalogs require a matching `NativeTasks` source binding. Task schedules
also require matching source-bound Program identities and an explicit complete
schedule. Missing bindings or schedules retain unavailable status and `null`
data. An explicit empty schedule decodes to `[]`; it is not inferred from an
unsupported attribute. The reader never derives native IDs from source order.

`scheduling_consistency` reports `consistent`, `inconsistent` or `unavailable`,
with a corresponding `true`, `false` or `null` result. Each Task row retains its
ordered schedule and resolved Program names where available. Unknown Program
IDs and references shared by multiple Tasks are explicit consistency errors;
unavailable Program inventory leaves references unresolved. Unscheduled
Programs are listed only when both inventories and every schedule are known.
This checks source-bound readback relationships, not runtime scheduling or
firmware acceptance.

Each discovered Program row also retains an `executable_catalog` and its
`executables`. Executable class `0x6D` is queried only beneath that Program's
actual `0x68` ID, including class metadata and every sparse-ID pagination cursor.
The same Routine ID in two Programs remains two distinct scoped objects. There
is no flattened global Routine catalog, synthetic ID or inferred Routine name.

The reader decodes only legacy Executable attribute 7, Description, as an exact
UINT16 length followed by at most 128 ASCII bytes without NUL or padding. An
explicit empty description is `""`; an unavailable description remains a failed
attribute with a `null` value. Revision-1 legacy description support does not
claim that the latest Executable ADF exposes that field. Type, compiled-address
and UID probes retain unavailable statuses. An unexpected success for a field
without an established decoder fails the inventory instead of guessing its size.

`executable_inventory` reports aggregate availability, discovered scoped count
and unavailable Program IDs. A missing or mismatched Routine binding preserves
its unavailable catalog and `executables: null`; it never becomes a successful
empty list. The Routine budget counts every scoped entry, including repeated
child IDs under different parents, and is checked before reading their metadata.

`read_values=False` collects metadata without issuing scalar reads. Values read
with the default option are individually observed values, not one simultaneous
snapshot; the reader does not freeze ongoing simulation. It closes only its
own connection. Request, instance, Program, Task, scoped Routine and page budgets stop unexpectedly
large or non-progressing inventories.

Reports include project names, tag names, observed values and raw read traffic.
Keep saved reports in ignored local storage. Model descriptor addresses and
logical fixture IDs are not native firmware addresses or compiled handles.

This is a model inventory, not an ACD export or a complete project upload.
`project_upload_complete` is always false and native Studio acceptance remains
unassessed. Focused tests cover malformed framing, duplicate/ordered fields,
sparse pagination, scoped values, unsupported storage, source replacement,
request budgets, denied targets, schedule resolution and actual owned TCP reads.
