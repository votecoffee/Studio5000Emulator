# Rebuild a verified upload as an Offline ACD

The Windows rebuild command saves native uploaded Program packages and current
tag values into a fresh copy of the original bound ACD. It then reopens the
saved file and exports a complete Controller L5X for independent validation.
It can consume a retained successful upload without a saved-download baseline
or an active emulator connection.

This provides an editable Offline ACD using the source's Controller metadata.
Program import clears download correlation, so the result requires a download
before going Online. The separate [value snapshot](upload-value-snapshots.md)
retains Online correlation when a matching saved-download baseline is available.
Direct saving of the reconstructed SDK upload remains unfinished.

## Requirements

- Windows, .NET 8 and the installed Logix Designer SDK with its service running.
- The original bound source ACD and exact complete Controller L5X.
- A successful existing-project upload from
  [`probe_native_sdk.py`](../source/tools/probe_native_sdk.py), with
  `--verify-uploaded-content`, actual Offline cleanup and no SDK fault.
- Complete unchanged ordinary RLL Programs, known current values and explicit
  Task schedules within the upload checker bounds (32 roots and 32 Programs).

The original source's metadata and unsupported Controller configuration are
retained. This workflow does not reconstruct an arbitrary project from an
unknown controller or incorporate online logic edits.

## Run

First collect a native upload with content checks:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --verify-uploaded-content .local/Controller.L5X --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --output .local/verified-upload
```

Then rebuild its retained artifacts into a fresh private output directory:

```powershell
py -3.13 -X utf8 source/tools/rebuild_uploaded_acd.py --project .local/Controller.ACD --source .local/Controller.L5X --upload-result .local/verified-upload --output .local/rebuilt-upload
```

Use the owned emulator's actual endpoint for the upload. The second command
has no network address or communications-path argument. It never goes Online,
changes controller mode or manages Windows services. Native helper processes
run hidden, with a 300-second call deadline and no automatic retry.

Outputs include `rebuilt.ACD`, its complete reopened `rebuilt.L5X`, native
step receipts and an independent `summary.json`. Original files and the
successful upload remain preserved; a partial or unknown result is retained
for inspection and is not reported as successful.

## Validation

Before any native project opens, Python rechecks the pinned source, recorded
plan, every uploaded root value, all routine exports and each complete Program
package. Copied inputs are checked again after building; the managed helper
also validates hashes and target paths without opening an SDK project.

The helper imports Programs in their original Task schedule order, restores
all mutable uploaded root values and checks constants without assigning them.
It saves, closes and reopens the new ACD, verifies Offline state and exports
the complete Controller. Independent validation checks every value, root type,
dimension and constant flag; all parsed ladder; Program settings; Task order,
priority, watchdog and output-update/inhibit settings; explicit UDT member
schemas; and cleared download correlation.
Successful native reopen, final Offline cleanup and preserved originals are
also required. The result always reports `requires_download: true` and
`online_verified: false`.

## Native checkpoint

Using retained verified uploads, the command saves and reopens both the
ConveyorDemo profile (14 roots, 45 value bytes, two routines and ten rungs) and
the expanded two-Program profile (29 roots, 202 bytes, four routines and
thirteen rungs). The latter includes ten constants, nested UDTs, UDT arrays
and distinct Program-local values. All saved values, flags, logic, schedules
and explicit type schemas match. Native Offline cleanup succeeds without an
SDK fault; originals remain unchanged.

An initial two-Program rebuild saved and reopened, but its independent check
rejected the changed Task execution order. Importing in the source's schedule
order fixes that case; a regression check covers names whose alphabetical
order differs from their execution order. Seventy focused upload checks pass.
These are Windows tool results; app `26.1026.131441` remains unchanged. General
Studio GUI upload/save and direct reconstructed-project saving are unfinished.

## Round-trip boundary

The rebuilt ConveyorDemo ACD has also completed native download/save/reopen/
Online across 430 verified requests, after loading and binding that rebuilt
source in the emulator. It retains the original input and changes only the
installed download correlation. Native Offline cleanup succeeds without an
SDK fault. This does not enable arbitrary project replacement over the network.

That checkpoint's subsequent upload stops during tag collection, and its
rebuilt two-Program download stops at a typed header check. Version
`26.1026.143655` resolves those two boundaries using
[installed Table identities](installed-table-identities.md): both rebuilt
downloads pass with complete saved-content checks, and the demo upload's
values, routines and Program package verify. The next failures are a final
typed Online BOOL getter for the demo and a two-Program snapshot reopen timeout.
Version `26.1026.153720` then completes the rebuilt demo's native download and
next upload snapshot, including save/reopen/Online, all fourteen values and ten
rungs, and twelve typed Online scalar getters. Both cases clean up Offline
without an SDK fault. The expanded rebuilt profile remains a separate checkpoint;
this bounded source-equivalent result does not enable general Studio upload-save.

The optional [download content check](download-content-validation.md) verifies
the complete saved Controller separately from connection and correlation.
