# SDK-free upload inventory reader

`source/tools/upload_inventory.py` exercises the emulator's read contracts
without Studio 5000 or the Logix Designer SDK. It accepts an already-loaded,
owned, in-process `Endpoint` bound to loopback with native read mode enabled
and network writes disabled. It accepts no remote address and imports no ACD.

Version `.113` also reads explicitly loaded [native Template snapshots](native-template-snapshots.md)
for supported user structures. Their saved headers/trailers remain opaque;
the reader does not require three zero alignment bytes in that profile.
It recognizes only the exact four-byte null Multiply Code reference.

```python
from tools.upload_inventory import collect_inventory, Limits

report = collect_inventory(owned_endpoint, read_values=True,
                           limits=Limits(instances=4096, programs=128,
                                         tasks=32, routines=4096, templates=1024, aois=1024,
                                         pages=128, requests=16384))
```

The existing independent `AnonymousClient` performs a fresh TCP challenge and
checks signed replies with its ephemeral key. Its optional `cryptography`
dependency is required. The inventory reader does not patch the endpoint,
share server keys, acquire a programming lease or request Run/Program changes.

The reader:

- Compares source/catalog revision before and after the inventory and checks
  the same application instance, source bytes and generation for every request.
- Reads Controller configuration, preserves aggregate replies and recognizes
  only the observed four-byte null handler value. Configured references remain
  opaque; unsupported responses retain their errors.
- Enumerates AOI Definition, Template, Program, Task, scoped Executable, Symbol and Data Table catalogs with bounded sparse-ID
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
  links, types, dimensions, value addresses and element sizes.
- Retrieves bounded Template definitions through service `0x4C`, preserving
  member descriptors, raw offsets, definition bytes and their SHA-256 hashes.
- Reads supported scalar and atomic-array bytes through Data Table service
  `0x4F` with selector zero and the complete value width. Arrays decode in
  row-major order with up to three dimensions checked against the Symbol rank.
- Links structured values to observed Template IDs and retains their complete
  wire bytes. It does not interpret UDT member offsets or decode typed UDT values.
- Reads available AOI state, revision and vendor headers through class `0x338`.
  Missing bindings and protected-state fields stay unavailable; definition names
  absent from the wire are not inferred, and compiled AOI upload is unsupported.

Unavailable catalogs retain `instances: null` and their status, separately
from a successful empty catalog. Attribute failures remain individual rows;
duplicates, byte alignment and response order are preserved. Missing storage,
aliases, constants and unsupported types do not acquire zero values.
Unknown values retain their read failure. Packed BOOL arrays remain unsupported.
Nonfinite floating-point encodings retain raw bytes and an explicit label rather
than invalid JSON; array reports also identify each affected element's coordinates.

Template instance metadata includes attributes 1, 2, 4, 5, 6, 7 and 8. Missing
fields retain their individual errors. Attribute 7, Multiply Code, has no
established decoder; an unexpected successful value stops the inventory before
definition parsing. Unknown fields never become invented null pointers.

Definition reads cover the advertised aligned allocation, `4 * words - 20`,
including three reserved zero bytes after the compact definition. Short final
replies, empty progress, oversized chunks, contradictory partial status and
nonzero reserved bytes fail decoding. Each definition and value is bounded to
32 KiB, and all declared Template allocations together are bounded to 1 MiB.
Definitions also require checked member counts, names and framing. Raw member
offsets remain uninterpreted; `structured_values_decoded` is always false.
Structured Symbols with a known but absent Template are consistency errors;
unavailable Template catalogs remain unavailable.

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
`executables`. Executable class `0x6D` is queried beneath that Program's
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

Version `.105` also queries Executable catalogs under discovered AOI Definition
`0x338` parents. Each AOI row retains its `executable_catalog` and `executables`;
`aoi_executable_inventory` reports the discovered child count and unavailable
AOI IDs. Every request records `aoi_instance` separately from `program_instance`.
Identical IDs under those parent classes stay distinct. Protected or missing
source/bindings retain failed catalogs and `executables: null`. The aggregate
Routine budget covers both AOI and Program entries. This adds discovery and
legacy descriptions, with `aoi_definition_upload` still false.

`read_values=False` collects metadata and Template definitions without issuing
Data Table value reads. Values read
with the default option are individually observed values, not one simultaneous
snapshot; the reader does not freeze ongoing simulation. It closes only its
own connection and waits briefly for its server-side cleanup on success and
decode errors. Request, instance, Program, Task, scoped Routine, Template, AOI and
page budgets stop unexpectedly large or non-progressing inventories. A complete
value that exceeds the negotiated reply size retains its read error; the reader
does not invent fragmented Data Table semantics.

Reports include project names, tag names, observed values and raw read traffic.
Keep saved reports in ignored local storage. Model descriptor addresses and
logical fixture IDs are not native firmware addresses or compiled handles.

This is a model inventory, not an ACD export or a complete project upload.
`project_upload_complete` is always false and native Studio acceptance remains
unassessed. Focused tests cover malformed framing, duplicate/ordered fields,
sparse pagination, scoped values, unsupported storage, source replacement,
request budgets, denied targets, schedule resolution, Template pagination,
multidimensional arrays, raw UDT bytes and actual owned TCP reads.
