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

### New-project upload

The native probe can instead call the SDK's `UploadToNewProjectAsync` factory:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --upload-new-project
```

This explicit option does not open the copied `input.ACD` in the SDK. The original
ACD still pins the owned emulator's source. The factory receives a new
`uploaded.ACD` path inside the new private output directory. Existing outputs
are rejected. `--upload-target` and `--save-uploaded-acd` cannot be combined with
this option; the factory creates its output as part of its own operation.

Reports distinguish factory completion, retained output bytes and their hash,
SDK Offline confirmation, endpoint cleanup and native ACD reopen verification.
A matching output hash does not prove ACD validity or reconstructed logic.
The unused `input.ACD` must remain unchanged. The default upload continues to
use `UploadAsync` and its private merge copy.

The SDK process has a bounded deadline. A timeout records an unknown native
outcome, with SDK fault and Offline status left unconfirmed. Endpoint cleanup
is checked independently; no SDK operation is automatically repeated and no
Windows service is controlled. Trace analysis selects the actual factory method
when a completed SDK report is available.

On `26.1022.213142`, the first factory trial times out after 120 seconds, with no
observed CIP requests and no output ACD. Source/model preservation and endpoint
cleanup are confirmed. There is no completed native SDK report, so the factory
outcome remains unknown. The subsequent established Go Online/Offline comparison
passes across 74 verified requests without a reported fault. This trial does not
resolve Routine source retrieval or prove a valid new uploaded project.

### Merge-target preservation

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

All 92 affected tests pass, including target restrictions, independent source
pins, preserved originals, changed private upload copies, missing files, SDK
receipt mismatches and model-change detection. The full suite was not rerun.

The restarted `.135` demo passes SDK Go Online/Go Offline across 75 verified
signed requests, with actual Offline and endpoint cleanup confirmed. The
original source, runtime tags, routines, tasks, mode and edit settings remain
preserved. No fatal SDK fault is reported. All 12 deployment checks pass;
all 94 deployed app modules, served assets and executable resources match the
build, and the webpage and executable report `.135`.

The later `26.1024.005421` controls use a saved matching download as their common
source. An unrelated routine-free baseline is rejected as incompatible after
87 requests, before Routine upload. A compatible copy retains Project UID,
Routine paths and source-key bytes while replacing MainRoutine Offline with one
NOP and preserving Reporting and all 14 saved tag values. Upload into that copy
still fails Program collection after 348 verified requests. Its complete
recording confirms the first Routine's 22 fields succeed and no source read
follows. Both controls preserve originals/model/installation, confirm actual
Offline cleanup and report no SDK fault. Neither establishes a source-key cache
miss or identifies the underlying failure cause.
