# Verify the saved downloaded project

The Windows SDK probe can independently check a complete Controller L5X
exported after saving and reopening a downloaded ACD. This supplements the
existing correlation and Go Online checks with validation of actual saved
values, logic, Program settings, Task schedules and explicit UDT schemas.

## Run

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --verify-downloaded-content .local/Controller.L5X --save-downloaded-acd --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation download --retain-transfer-trace --output .local/checked-download
```

Use the owned emulator's actual endpoint, original bound ACD, exact complete
Controller L5X and a fresh private output directory. The check requires a
stopped, unchanged supported source with complete known values. The source
must already be loaded and bound in the emulator; this does not enable
replacement with an arbitrary different project over the network.

`--verify-downloaded-content` requires `--operation download` and
`--save-downloaded-acd`. The probe derives a complete bounded plan before
building, repeats it before the native call and rejects changed inputs.

After successful installation, the native helper saves `downloaded.ACD`, closes
and reopens it, confirms Offline state and exports a complete `downloaded.L5X`.
It then verifies Go Online with the reopened ACD and performs normal cleanup.
The result retains both artifact hashes and the native export receipt.

Python separately verifies every root's value bytes, type, dimensions and
constant flag; all supported parsed ladder; complete Program inventory and
settings; Task order, rate, priority, watchdog and output-update/inhibit settings;
and explicit UDT member schemas. Artifact hashes, actual native reopen/Online
evidence and the existing saved-correlation check must also pass.
`downloaded_content_verification.verified` is false for missing, partial or
altered evidence, and such a result fails the overall probe.

The command never controls Windows services or retries a native call
automatically. Processes run hidden. An incomplete native call remains an
unknown outcome; software checks do not establish controller execution parity.

## Native checkpoint

The demo completes download/save/reopen/Online across 429 verified requests.
Independent checks match all 14 roots (45 value bytes), both routines and ten
rungs in the actual reopened full export, including source Task settings and
type schemas. Correlation, source/model preservation and actual Offline cleanup
pass without an SDK fault. The complete 1,735-event recording replays identically
offline; replay does not independently authenticate MACs. One diagnostic cursor
read times out and is retried without repeating a native transfer operation.

The affected Windows tools pass 91 focused checks and 371 Python syntax checks.
App `26.1026.131441` is unchanged; this adds a Windows probe option. Broader
project replacement, direct Studio GUI acceptance and the complete rebuilt
project cycle remain separate acceptance steps.
