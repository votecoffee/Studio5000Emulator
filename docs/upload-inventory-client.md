# SDK-free upload inventory reader

`source/tools/upload_inventory.py` exercises the emulator's read contracts
without Studio 5000 or the Logix Designer SDK. It accepts an already-loaded,
owned, in-process `Endpoint` bound to loopback with native read mode enabled
and network writes disabled. It accepts no remote address and imports no ACD.

```python
from tools.upload_inventory import collect_inventory, Limits

report = collect_inventory(owned_endpoint, read_values=True,
                           limits=Limits(instances=4096, programs=128,
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
- Enumerates Program, Symbol and Data Table catalogs with bounded sparse-ID
  pagination, independent class counts and exact attribute-list framing.
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

`read_values=False` collects metadata without issuing scalar reads. Values read
with the default option are individually observed values, not one simultaneous
snapshot; the reader does not freeze ongoing simulation. It closes only its
own connection. Request, instance, Program and page budgets stop unexpectedly
large or non-progressing inventories.

Reports include project names, tag names, observed values and raw read traffic.
Keep saved reports in ignored local storage. Model descriptor addresses and
logical fixture IDs are not native firmware addresses or compiled handles.

This is a model inventory, not an ACD export or a complete project upload.
`project_upload_complete` is always false and native Studio acceptance remains
unassessed. Focused tests cover malformed framing, duplicate/ordered fields,
sparse pagination, scoped values, unsupported storage, source replacement,
request budgets, denied targets and actual owned TCP reads.
