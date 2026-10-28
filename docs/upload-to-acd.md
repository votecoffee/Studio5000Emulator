# Upload and save an Offline ACD

The Windows `upload_to_acd.py` command performs a native SDK upload, verifies
its complete bounded content, then rebuilds and reopens an editable Offline
ACD. It runs both stages serially and keeps their results separate.

The saved file contains the uploaded Program packages and current tag values
with the original source's Controller metadata. Program import clears download
correlation: **the resulting ACD requires a download before going Online**.
General Studio GUI upload/save and direct saving of the reconstructed SDK
project remain unfinished.

## Requirements

- Windows, .NET 8 and the installed Logix Designer SDK service already running.
- A stopped, source-bound emulator in Program mode, with disabled network
  writes, Device I/O writes and routine editing, and no connected native client.
- The original source ACD and exact complete Controller L5X, preserved in private
  storage; an unchanged source-equivalent download must already be installed.
- Complete ordinary RLL Programs and Task schedules, at least one controller
  tag, known current values, and the existing upload checker bounds of 32 roots,
  32 routines and 32 Programs. Aliases and AOIs are outside this workflow.

An optional matching saved-download baseline enables an actual Online/Offline
check before upload. It must meet the existing
[baseline requirements](upload-tag-definitions.md#ordinary-upload-with-a-checked-online-baseline).
Without one, upload uses a preserved copy of the original source ACD.

## Run

Use the owned emulator's actual address and Linx path:

```powershell
py -3.13 -X utf8 source/tools/upload_to_acd.py --project .local/Controller.ACD --source .local/Controller.L5X --upload-target .local/MatchingDownloaded.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --output .local/upload-and-save
```

Omit `--upload-target` when no matching saved-download ACD is available. The
output directory must be new. `--sdk-feed` optionally selects the installed
SDK NuGet feed. All native helper processes run hidden. The command never
controls Windows services, changes controller mode or enables write authority.

## Fresh ACD from uploaded L5X

Add `--from-uploaded-l5x` to create the saved ACD by importing a complete L5X
assembled from the verified uploaded controller tags and complete Program
packages. This mode retains Controller, Task and type context from the original
source L5X. The source ACD is used for provenance/native type checks; the native
save helper receives `input.L5X` and opens no source ACD. It checks current values,
saves a fresh ACD, closes and reopens it, and exports its complete Controller.

The default method imports the uploaded Programs into an original ACD copy.
Both methods preserve originals and require a download before going Online.
Neither reconstructs unknown Controller metadata or uploads online-edited logic.

## Outputs and verification

`summary.json` reports the overall result, separate upload/rebuild statuses,
original-input preservation, final model preservation and the saved ACD hash.
On success, the ACD is `rebuilt/rebuilt.ACD`; `rebuilt/rebuilt.L5X` is its complete
native reopened export. `upload/` retains the original upload receipts, actual
routine/Program/controller-tag exports and the full compressed transfer journal.
`rebuilt/` retains the independent native rebuild/save/reopen receipt.
The L5X method also retains its exact complete `rebuilt/input.L5X`; its hash and
actual native import step must match. It cannot fall back to an ACD-copy receipt.

The upload's success flag alone cannot start the rebuild. Its actual native
values, every routine, complete Program packages and requested controller-tag
definitions are independently revalidated first. Saved content checks compare
declarations separately from decorated values, including logical BOOL array
bits versus packed Table words. The final native reopen must preserve values,
logic, Task order/settings and explicit UDT schemas, and clear correlation.

Failed, faulted or uncertain uploads stop before rebuilding. A failed or unknown
save retains its outputs and the separately successful upload evidence. Neither
stage is automatically retried; the existing 120-second upload and 300-second
native rebuild deadlines are unchanged. The command never calls `SaveAsAsync`
on the reconstructed upload object.

For separate stages or retained upload artifacts, use the existing
[Offline ACD rebuild command](uploaded-acd-rebuild.md). A matching baseline can
instead produce a [value snapshot retaining Online correlation](upload-value-snapshots.md).

## Native checkpoint

The ConveyorDemo command completes its upload across 1,052 verified requests,
then saves and reopens the rebuilt ACD. Independent checks match all fourteen
roots, 45 value bytes, two routines and ten rungs, including three deliberately
changed live values. The actual controller-tag export, complete Program package,
Task configuration and cleared download correlation verify. Upload and rebuild
confirm Offline cleanup; source files and the running model remain unchanged
by the workflow. The test restores the original live values afterward.

The fresh L5X method also saves and reopens an ACD from that retained verified
upload, preserving the three changed values, all fourteen roots, both routines,
ten rungs and source Task/type context. Its native input is the complete assembled
L5X; no original ACD copy is opened. Cleared correlation and final Offline cleanup
verify independently. Loading that reconstructed source into the emulator then
completes native download/save/reopen/Online across 428 verified requests. Its
next upload completes across 1,054 requests and the single-command L5X method
again saves and reopens a complete ACD with all fourteen values and ten rungs
preserved. Actual upload and rebuild Offline cleanup pass. That newly uploaded
file again has cleared correlation and requires a download before going Online.

This is a source-bound Windows tool result. The app remains `26.1026.153720`;
general Studio upload/save and uploading online-edited routines remain unfinished.
