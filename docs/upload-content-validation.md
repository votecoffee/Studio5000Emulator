# Native uploaded-content validation

Version `26.1026.080644` adds an optional content check after an existing-project
SDK upload. A successful transfer alone does not establish that the SDK's
reconstructed offline project contains the expected values and logic, or that
it can be saved as an ACD.

## Usage

Use the original source ACD and exact complete L5X matching the owned emulator.
A separately saved matching download can be the preserved upload merge target:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --upload-target .local/Downloaded.ACD --verify-uploaded-content .local/Controller.L5X --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --retain-transfer-trace --output .local/upload-content-check
```

Substitute the owned endpoint's actual address and a new output directory.
The check requires stopped Program mode, unchanged ordinary source, complete
known values and the existing read-only native endpoint policies. It is not
available for new-project factory upload or another probe operation.

## Independent evidence

Before native calls, the tool checks the source hashes, complete leaf set,
declared types, current values and every Standard RLL routine. It repeats that
comparison after compilation to reject changes made while the probe builds.
The bounded plan permits at most 32 roots, 32 routines and 32 ordinary Programs; unsupported source,
unknown values, aliases, AOI contexts and changed logic reject the check.

After `UploadAsync`, the SDK remains Offline. The probe:

1. Reads every planned root through `GetTagValueAsync` with Offline mode and
   compares its bytes with the current emulator value encoded using the
   source-checked download layout.
2. Exports each routine through `PartialExportToXmlFileAsync` to a new private
   L5X. It checks the exact target, rung count and neutral source text.
3. Retains hashes and actual value receipts, including partial evidence when a
   later operation fails. Python independently parses each exported routine
   and compares its ladder nodes with the original source.
4. Exports each complete Program through `PartialExportToXmlFileAsync` to a
   separate native L5X. Python verifies its target, MainRoutine, disabled/class
   settings, complete routine set and parsed ladder, plus every declared local
   tag's type, dimensions, constant flag and current value. Controller objects
   included as context remain dependencies; this is a partial Program package.

An SDK success result with missing values, changed logic, incomplete receipts,
wrong targets, modified files or unavailable artifacts cannot pass the content
check. Export XML rejects DTDs/entities and has explicit size bounds.

The probe preserves original ACD/L5X files and the running model, confirms
native Offline cleanup, and never controls Windows services or repeats a native
operation automatically. Project names, values and exported logic remain in
ignored private storage.

The private `sdk.log` also receives flushed `native_step` JSON lines when a
step starts, succeeds or fails. These locate the last entered SDK call if the
process times out before it can write `sdk-result.json`. They do not establish
the outcome of an unfinished call or confirm native Offline cleanup.

## Acceptance boundary

The content check uses the SDK's reconstructed offline project. It does not
substitute original source files for native exports, save an ACD, request Run,
write controller tags or establish general Studio GUI compatibility.
Full uploaded ACD save/reopen remains a separate native acceptance step.

Six focused tests cover complete current-value and routine receipts, changed
source/state, missing or reordered values, altered export hashes and logic,
wrong targets, malformed XML and unsupported operation selection. Native
results are recorded separately from these software checks. The managed
request decoder also checks the actual cross-language request, including all
Program counts, without opening an SDK project before each content-check trial.
Three further tests cover Program package identity, changed settings/logic,
missing or extra components, altered hashes and scoped tag value/type changes.
The parser retains the distinction between a partial Program package and a
complete Controller export.

## Native checkpoint

On this version, source-equivalent download/save/reopen/Online succeeds across
430 verified requests. The upload merge baseline has MainRoutine replaced by
one NOP, while the running emulator retains nine MainRoutine rungs and one
Reporting rung. Nine temporary writes change five runtime tag roots.

Native upload succeeds across 980 verified requests. All 14 root values
(45 bytes) match independent Offline SDK reads. Both native routine exports
match all ten parsed source rungs, demonstrating replacement of the NOP
baseline. Originals, model and audit state are preserved, with actual SDK
Offline cleanup and no SDK fault. The complete 3,477-event journal replays
identically offline; replay does not reauthenticate MACs.

A separate guarded trial passes those same value and routine checks, then
faults during `SaveAsAsync:uploaded.ACD` with `LgxSrv_E_UNHANDLED_EXCEPTION`.
No uploaded ACD is created. Emulator endpoint cleanup and source/model/audit
preservation pass; SDK Offline cleanup cannot be confirmed for that faulted
session. This does not identify the faulty serialization field or establish
uploaded ACD persistence. No automatic save retry is made.

All temporary values are restored exactly without scanning. After the SDK
service is restarted externally, saved-download Go Online/Go Offline succeeds
again. The following revision's [installed DINT read profile](installed-memory-reads.md)
clears the typed online tag boundary; its separate upload regression times out
with an unknown native outcome. After a fresh saved-project connection confirms
SDK recovery, a new upload succeeds across 980 requests on that following
revision. All 14 values and both routines verify again, with native Offline
cleanup and no fault. Uploaded ACD persistence remains blocked.

The expanded Program check then succeeds across 983 verified requests. The
SDK exports one native Program package containing both routines; its settings
and all ten parsed rungs independently match the running source. All 14
Offline root values still match, and native Offline cleanup, source/model/audit
preservation and no SDK fault are confirmed. This verifies a native Program
export, not direct saving of the reconstructed uploaded project as an ACD.

## Offline Program rebuild checkpoint

A separate offline trial imports that native Program package into a preserved
ACD baseline whose MainRoutine contains one NOP. The SDK saves a new ACD;
a fresh SDK process then reopens it and exports a complete Controller L5X.
Independent checks verify both routines, all ten rungs, all 14 values (45
bytes), the Program settings and the original task entry. The originals remain
unchanged. The first combined trial exceeded its deadline during reopen;
the separately validated saved file establishes the successful reopen.

This demonstrates a component rebuild using the original Controller baseline.
It does not demonstrate direct saving of the uploaded SDK project. The rebuilt
ACD's correlation differs from the running installation. Repeating the offline
import with a saved, already matching baseline still clears its download UID.
Native Go Online then rejects the rebuilt file with
`RxCL_E_CHANGES_SINCE_IMAGE_COPY` across 69 verified requests. The SDK confirms
Offline cleanup without a fault, and the running model remains unchanged.
Automating this rebuild with valid online correlation remains further work. The probe currently
provides the native Program package for inspection or offline import.

## Checking a saved connection target

The native probe accepts a separate saved ACD while retaining the original
emulator source binding. It copies and preserves both files:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --connection-target .local/Saved.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation connection --output .local/saved-connection-check
```

`--connection-target` belongs only to a connection check and cannot combine
with `--upload-target`. This selects an input; it does not rewrite project
correlation, upload, download or enable native tag writes.
