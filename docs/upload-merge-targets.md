# Separate offline upload merge targets

Version `.135` lets the native SDK diagnostic upload into a private copy of a
separate offline ACD. This supports testing different local merge baselines
while preserving the controller model's original source binding. It does not
change the emulator's native upload services.

## Usage

The installed SDK's `UploadAsync` operates while Offline and merges into an
existing project. The [native acceptance probe](development.md#native-sdk-acceptance-probe)
normally copies the emulator's matching ACD before calling it. Upload cases
can now select a different baseline:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --upload-target .local/OfflineCopy.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload
```

Use the actual owned emulator address in place of the example. `--project`
remains the original ACD matching the running emulator. `--upload-target`
selects an existing ACD of 8 through 100,000,000 bytes. It is accepted only for
upload diagnostics; connection, download, mode and edit cases reject it.

The selected baseline is copied into the new private output directory as
`input.ACD`. The SDK opens that copy. Neither supplied original is opened for
SDK writes. Omitting the option retains the original baseline selection.

## Independent source and file checks

Before and after the native call, the probe checks the emulator's instance,
source ACD/L5X hashes, address, mode, idle lease and disabled write policies.
The native helper receives a separate controller-source hash; its backend and
trace checks use that hash even when the local SDK input differs. A target ACD
cannot silently replace the emulator's source pin.

Both original ACDs must retain their original hashes. An upload can change its
private working copy because that is the SDK's merge destination. Reports keep
the original-source result separate from `working_copy_unchanged`, the final
working-copy hash and the SDK's own hash receipt. A successful upload result
requires the receipt to match the retained file and the pinned controller source.
Missing or inaccessible files cannot suppress endpoint cleanup. Changes to a
working copy remain forbidden for the other probe operations.

The summary's `source_unchanged` covers preserved originals; upload changes to
the private copy have separate fields. The native helper's legacy
`sourceUnchanged` field still describes its working input; the explicit
`workingProjectUnchanged` and `workingProjectSha256` fields make that scope clear.
File hashes establish retained bytes, not native project reconstruction or
execution equivalence. Independent save/reopen/readback remains a separate check.

Upload/download model comparisons also include available Routine, Task, entry
and controller state, alongside tags, scan/time and existing value fields.
Reports list `model_fields_checked`. Native Offline and endpoint cleanup remain
separate confirmations. No SDK command is automatically retried and no Windows
service is controlled.

## Native trials

Three isolated `.134` trials use the same owned emulator source and native
helper implementation:

| Offline SDK baseline | Verified signed requests | Expanded leaf requests | Native result |
| --- | --- | --- | --- |
| Original matching source | 357 | 360 | Program upload fails after the complete Routine reply |
| Separate demo ACD | 88 | 91 | Images incompatible, before Routine upload |
| Same project with one offline NOP insertion | 357 | 360 | Same Routine boundary and Program upload failure |

The NOP baseline was imported, saved and reopened Offline. It preserves Routine
paths and source-key bytes; only Copy UID changes among the tracked project
correlation fields. Its different logic is verified from the reopened export.
It does not demonstrate a source-key cache miss or rule out cache involvement.

All three native trials leave both originals and the emulator model unchanged,
confirm actual Offline/cleanup, and report no fatal SDK fault. None reaches
`0x3A` source retrieval. No physical controller was contacted. Full native
upload/download, source reconstruction and complete native online edits remain
unfinished.
