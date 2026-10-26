# Native Routine upload checkpoint

Version `26.1026.085243` adds [native Online scalar DINT reads](installed-memory-reads.md).
Download/save/reopen/Online succeeds again, and two saved-project SDK sessions
read positive and negative current values. Its subsequent upload regression
times out after 866 verified requests without a new native rejection. The
recording is complete, but that call's completion and Offline cleanup are
unknown. A later fresh saved-project connection confirms actual SDK Offline
cleanup across 73 verified requests. A new upload then succeeds across 980,
verifying all 14 tag values and both routines with normal cleanup and no fault.
This does not identify the earlier timeout's cause. Uploaded ACD persistence
and reliable general upload remain unfinished.

An expanded content check then exports a native Program package across 983
verified requests. Its two routines, ten rungs and Program settings match;
all 14 Offline tag values still verify. A separate offline Program import into
the altered baseline saves and reopens a new ACD with all values and logic
preserved. This [component rebuild](upload-content-validation.md#offline-program-rebuild-checkpoint)
retains baseline Controller metadata and has different online correlation;
it does not establish direct uploaded-project saving or Go Online for that file.

Version `26.1026.080644` adds [independent native content validation](upload-content-validation.md).
Upload into a compatible NOP-altered baseline succeeds across 980 verified
requests. The SDK's Offline reads match all 14 current tag roots (45 bytes),
and its two native routine exports match all ten source rungs. Full ACD save
still faults the tested SDK after these checks; persistence remains blocked.

Version `26.1024.111516` completes existing-project native SDK upload of the
two-routine conveyor demo across **981 verified requests**. Both complete
Routine source streams are read: 688 and 476 bytes, containing ten rungs and
30 IOI operands. Download, save, close, reopen and Go Online also succeed
across 430 requests. Actual Offline cleanup and no SDK fault are confirmed.

## Demonstrated profiles

| Owned fixture | App version | Native SDK upload |
| --- | --- | --- |
| One NOP rung | `26.1024.095632` | Succeeds, 973 verified requests |
| One `XIC`/`OTE` rung, two BOOL tags | `26.1024.104524` | Succeeds, 936 verified requests |
| Two-routine conveyor demo, including TIMER and COUNTER | `26.1024.111516` | Succeeds, 981 verified requests |
| Routine-free BOOL[64] regression profile | `26.1024.111516` | Succeeds, 968 verified requests; all eight packed value bytes match |

The two-BOOL fixture previously failed `RxE_CORRUPT_RECON_DATA` after reading
its 460-byte source. Returning the original [Symbol Control words](installed-symbol-control.md)
from committed headers clears that failure. The demo still failed while its
TIMER/COUNTER tags were omitted from discovery. Binding their exact
[source-checked definitions and current values](builtin-template-reads.md)
allows the demo upload to finish.

The complete demo download/upload journals contain 1,739/3,488 events and
replay identically offline. Offline replay does not independently
reauthenticate MACs. Upload preserves the original input, loaded values,
logic, installed correlation and audit state. Independent CIP reads verify
the two original control words, Template IDs and all 24 TIMER/COUNTER bytes
through both symbolic and Data Table paths.

A second demo upload succeeds across 982 verified requests after nine
temporary value changes across five tags. Its actual Table responses match
all 33 current-value bytes for BOOL, DINT, TIMER and COUNTER tags, including
timer/counter status bits. All five values differ from the saved initial
source. The complete 3,488-event recording replays identically offline;
source/model/audit preservation, actual Offline cleanup and no SDK fault pass.
Every temporary value is then restored exactly without scanning the model.

## Implemented source path

The client discovers the original [scoped Routine reference Symbols](routine-reference-symbols.md),
reads Routine data, queries the guarded [Label inventory](routine-label-discovery.md),
and requests the empty `(1, 4)` component followed by `(1, 3)` source.
[Downloaded Routine readback](downloaded-routine-read.md) validates the installed
source and adds the upload profile's explicit Standard class. Rung XML and
compressed auxiliary bytes are preserved, and no native machine code executes.

The emulator must first receive an unchanged source-equivalent download.
Resetting, reloading or restarting clears that memory-only installation.
These checkpoints use matching existing ACD targets. Saving/reopening an
uploaded ACD, new-project reconstruction, arbitrary ladder projects and
Studio 5000 GUI upload acceptance remain unverified or unfinished.

## Validation

This revision passes 238 affected software checks and 359 Python syntax
checks. Source, EXE, served browser assets and 119 appliance modules match the
app version. Software checks and SDK acceptance remain separate from native
controller equivalence. This milestone passes 2,110 Windows
tests with two platform checks skipped; milestone checks are recorded
separately from small iterations.

The original demo is restored with a fresh source-equivalent download across
432 verified requests. A separate SDK process reopens that saved ACD and goes
Online across 73, then confirms Offline cleanup. Its complete controller
header matches independent CIP readback. The final model is stopped in
Program with original values, zero scans and no active programming lease.
Routine editing is enabled again; external network tag writes stay disabled.
The installation remains memory-only.
