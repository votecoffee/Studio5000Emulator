# Native online-edit diagnostics

The optional public SDK probe has an `edits` operation that inserts one generated
`NOP();` rung into a loaded RLL routine on a private ACD copy. It exercises the
native import path while LogixLab continues to advertise disabled online-edit
authority. Active controller edits, finalizing and assembling edits remain
unsupported.

Run against an idle, source-bound emulator in Program mode, with protocol and
Device I/O writes disabled. Use the endpoint's actual local webpage URL and
Linx path. The documentation address below is an example:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation edits --edit-program MainProgram --edit-routine MainRoutine
```

The default `AcceptEdits` option requests that the SDK accept and send imported
logic to the controller. The current endpoint is expected to reject unsupported
operations. This attempt records the SDK's actual error and paired protocol
requests instead of returning invented successful programming acknowledgements.
It never requests Run mode, replaces existing rungs, finalizes or assembles edits.

For an independent comparison on a fresh private copy, repeat with
`--edit-import-option LeaveEdits`. The installed SDK documents `LeaveEdits` as
offline pending changes, even when the project is online. A successful call with
that option establishes a local pending import; it does not establish that the
controller accepted an edit. Each invocation uses a separate output directory
and ACD copy. `FinalizeEdits` is deliberately unavailable.

Before the native call, the probe validates the selected ordinary RLL routine,
source hashes, emulator instance, disabled edit authority and empty programming
state. Afterward it requires unchanged routines, tasks, entry points, controller
state, running values and scan history. It goes Offline, disposes the private
SDK project and requires the endpoint's clients, lease and temporary staging to
clear. It never saves the edited ACD over the input and never manages Windows
services.

Private reports include the generated rung hash, SDK step start/end timestamps,
newly rejected structural requests and import-interval protocol evidence. The
`first_failed_request` field identifies the first complete nonzero CIP response
observed during the import, when available. It is diagnostic evidence rather
than a claim that every returned CIP error causes the SDK failure. An empty
interval is reported explicitly. Parsing these saved frames checks their
structure and correlation; it does not authenticate their MACs or establish
native runtime equivalence.
