# Source-equivalent upload value snapshots

The native probe can save the current uploaded tag values into a fresh ACD
when the installed project still has its original supported logic. It uses
the native SDK to upload and check the values/source, then updates a separate
matching saved baseline through Offline tag setters. The saved ACD is reopened,
exported for independent content checks and verified Online.

This profile retains the baseline's Controller metadata and compiled project.
It does not import Programs or patch native identity/journal bytes. Direct
saving of the SDK's fully reconstructed uploaded project remains unfinished.

When a saved-download baseline is unavailable, the separate
[Offline ACD rebuild](uploaded-acd-rebuild.md) imports verified native Program
packages into the original source copy. Its saved result requires a download
before going Online.

## Requirements

- A stopped Program-mode emulator with an unchanged source-equivalent download.
- The original bound ACD and its exact complete Controller L5X.
- An unedited ACD saved after that download, with the bound source's original
  project/copy/timeline identity and its new nonzero download UID.
- Complete known current values and supported Standard RLL source within the
  [uploaded-content check](upload-content-validation.md) bounds.
- Windows and the installed native Logix Designer SDK service.

The snapshot option requires `--operation upload`, `--upload-target` and
`--verify-uploaded-content`. It cannot combine with direct `--save-uploaded-acd`
or new-project factory upload. The SDK first checks that the baseline actually
goes Online, then returns Offline before uploading.

## Run

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --upload-target .local/Downloaded.ACD --verify-uploaded-content .local/Controller.L5X --snapshot-uploaded-acd --retain-transfer-trace --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation upload --output .local/upload-snapshot-check
```

Use the owned emulator's actual address and a fresh private output directory.
The matching baseline can be produced with `--save-downloaded-acd` after a
supported source-equivalent download. Reset, reload or restart revokes that
memory-only installation; a previously saved baseline then needs revalidation.

The result includes `snapshot.ACD`, the SDK's complete reopened `snapshot.L5X`,
native Program/routine exports and private receipts. The original files and
the separate snapshot input copy are preserved. The native call deadline is
300 seconds; a timeout remains an unknown outcome and is not retried.

## Checks and limitations

Upload must independently verify all planned root values and routine/Program
exports. On a fresh baseline copy the SDK exports and checks every routine
again before writing any values. Only Offline tag values are set; constants
are checked without assigning them. ACD save, close and reopen follow.

The reopened file must go Online and report Program mode. Supported ordinary
scalar DINTs and BOOLs also receive typed Online reads that must match the uploaded
values. Python independently checks every saved root's type, dimensions,
constant flag and bytes, the complete parsed logic and Program/task entries,
artifact hashes and exact retained correlation. A final model/source/cleanup
check remains required. Partial evidence or an SDK success alone cannot pass.

Routine edits, other project replacement and unknown values are outside this
profile. General Studio GUI upload/save remains separate from this Windows
probe workflow. General tag monitoring and controller equivalence remain
unverified.

## Native checkpoint

With running app `26.1026.085243`, the conveyor profile completes upload,
value snapshot save/reopen and Go Online across 1,129 verified requests.
Nine temporary writes change five roots, covering BOOL, DINT, TIMER and
COUNTER data. All 14 roots (45 bytes), both routines and ten rungs verify
in the uploaded SDK project and the saved, reopened ACD. The complete
correlation header remains unchanged; native Offline cleanup and no SDK
fault are confirmed. All temporary model values are restored without scanning.

After those temporary values are restored, a separate SDK process reopens the
saved snapshot and goes Online across 74 verified requests. Its typed DINT
read returns the restored live value `50`, while the file retains the captured
value `87`. Native Offline cleanup and no fault are confirmed again.

The retained complete trace contains 4,127 events and replays identically
offline; replay does not reauthenticate MACs. Software checks and native
acceptance are recorded separately. The snapshot/checking paths pass 88
focused tests; the milestone passes 2,130 tests with two platform checks
skipped, and all 365 Python files parse.

An additional routine-free profile contains 17 roots, including nested UDTs,
an array of structures, REAL/INT/DINT values and named packed bit members.
Fourteen temporary member/array changes alter three UDT roots (100 bytes).
Upload/save/reopen/Online succeeds across 1,125 verified requests; all 17 roots
(145 bytes) match both the uploaded SDK values and the saved full L5X. Every
temporary model value is restored without scanning, with native Offline cleanup
and no fault. Download/save/reopen/Online separately succeeds across 423 requests.
Complete 1,711/4,110-event recordings replay identically offline.

On app `26.1026.112241`, the restored conveyor demo completes download/save/
reopen/Online across 431 requests and upload snapshot/save/reopen/Online across
1,139. The snapshot now checks nine scalar BOOLs and three DINTs through typed
Online getters. A fresh SDK process reopens the saved snapshot, goes Online
and reads the live DINT across 74 requests. Source/model preservation, correlation, Offline
cleanup and no SDK fault pass. This revision passes 194 affected software checks;
the preceding full milestone remains separately recorded above.

App `26.1026.122552` extends native acceptance to a two-Program profile with
six local roots, duplicate names across Programs, a DINT constant and an
array. Download/save/reopen/Online succeeds across 434 requests; snapshot
upload/save/reopen/Online succeeds across 1,188. Five deliberately changed
local values survive upload and native save/reopen. All twenty roots (71
bytes), four routines and thirteen rungs verify, including both Program
packages. Eleven BOOLs and five DINTs receive typed Online checks; the constant
remains `1000` with its flag preserved. Values are restored without scanning,
with actual Offline cleanup and no fault. See the complete
[scoped transfer checkpoint](scoped-download-tables.md#native-snapshot-checkpoint-261026122552).

On `26.1026.124956`, the expanded two-Program profile passes with 26 roots
(102 bytes) and seven BOOL/numeric/array constants. Download/save/reopen/Online
completes across 436 requests; snapshot upload/save/reopen/Online across 1,206.
Every constant's value and flag survives, including LINT and packed BOOL-array
storage, while independently changed mutable local values are captured. All
thirteen rungs and both Program packages verify with normal Offline cleanup
and no SDK fault. See the
[constant upload checkpoint](installed-memory-reads.md#constant-upload-checkpoint-261026124956).

Version `26.1026.131441` also preserves nested UDT constants and UDT arrays.
The expanded profile verifies all 29 roots (202 bytes), ten constants and
thirteen rungs through download/save/reopen/Online (435 requests) and snapshot
upload/save/reopen/Online (1,221). Complete structure bytes and saved flags
match, with actual Offline cleanup, restored mutable values and no SDK fault.
See the [constant structure checkpoint](installed-memory-reads.md#constant-structure-checkpoint-261026131441).

Version `26.1026.153720` extends acceptance to actual native Program-rebuilt
inputs: both the fourteen-root demo and twenty-nine-root two-Program fixture
complete download, subsequent upload snapshot, native save/reopen and Online
value checks. All twelve and sixteen supported scalar getters respectively
pass without SDK faults. See the current
[rebuilt transfer checkpoint](installed-table-identities.md#read-path-validation-cost).
