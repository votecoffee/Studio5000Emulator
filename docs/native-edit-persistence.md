# Native accepted-edit persistence

The SDK acceptance tool can save one accepted native rung edit directly from
its existing project, reopen the resulting ACD and verify Go Online. The
emulator keeps the same active edited logic throughout this check.

## Run the check

Start with a stopped Program-mode emulator containing the original matching
ACD/L5X source, a completed source-equivalent download and its saved
`downloaded.ACD`. Enable **Allow supported Studio edits** before connecting.
Use the emulator's actual Linx driver and IP address in place of the example:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py `
  --project .local/controller.ACD `
  --connection-target .local/download/downloaded.ACD `
  --url http://127.0.0.1:8786 `
  --path 'YourDriver\192.0.2.8\Backplane\0' `
  --operation edits --apply-supported-edits `
  --edit-program MainProgram --edit-routine MainRoutine `
  --edit-code 'NOP();' --edit-replace-count 1 --reconnect-edits `
  --save-native-edits-acd .local/controller.L5X `
  --output .local/native-edit-save
```

Choose the intended routine and edit before running. The supported profile is
one `AcceptEdits` import in an unchanged ordinary RLL project, with a matching
download baseline and an Offline/Online check before saving. Multiple edits,
other import options and the neutral `--save-edited-acd` path cannot be combined
with this option. The original L5X is read only for independent verification;
it is never imported into the SDK by this save path.

## Evidence and outputs

The tool creates new `native-edited.ACD` and `native-edited.L5X` files. It saves
after going Offline, closes the SDK project, reopens the saved ACD, exports its
actual L5X, goes Online and confirms Program mode, then returns Offline.
Original input and baseline files are preserved.

`native_edited_acd_verification` requires successful ordered native steps,
actual Offline cleanup, no SDK fault, exact output hashes and unchanged working
input. Exported tag types, dimensions, Constant flags, complete values, routine
logic, Program settings and entry routines must match the active model. Saved Change Index,
Generation, Download UID, Project UID and Timeline UID remain anchored to the
matching baseline. Native Save As can change Copy UID; that change is recorded
separately and does not waive the other checks. The local empty journal profile
does not establish that the edited controller has no history.

The tested demo passes the accepted replacement/save/reopen/Online sequence
across 261 verified requests. Independent exported-content checks cover all 14
tag roots, 45 value bytes, both routines and ten rungs. A separate fresh SDK
session opens the saved ACD and goes Online across
74 requests, with a typed DINT read and confirmed Offline cleanup.
Both native cases report no SDK fault and execute no scans.

The app's core behavior and version remain unchanged by this acceptance-tool
addition. The saved file is correlated to that live installation; a new download
or emulator reload can revoke it. Studio GUI Save/Save As, arbitrary projects
and the full Test/Untest/Assemble lifecycle remain unverified.

## Upload boundary

This saves the client's accepted native project. It does not call `UploadAsync`
or reconstruct an unknown controller project. Complete edited-project upload
still stops at the guarded Change Log search; its opaque record layout remains
unresolved. Known-faulting reconstructed-upload save trials remain separate.
