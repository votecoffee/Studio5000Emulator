# Native Routine upload checkpoint

Version `26.1024.095632` completes an existing-project native SDK upload with
one ordinary RLL routine containing one `NOP` rung. The SDK reads the actual
Routine source stream and finishes `UploadAsync` across 973 verified requests.
Download, save, close, reopen and Go Online also succeed across 430 requests.
Source/model preservation, actual Offline cleanup and no SDK fault are confirmed.

## Current boundary

| Owned fixture | Routine source read | Native SDK upload |
| --- | --- | --- |
| One NOP rung | One complete 440-byte source container; no tag operands | Succeeds, 973 verified requests |
| One `XIC`/`OTE` rung, two BOOL tags | One complete 460-byte source container; two IOI operands | Fails reconstruction, 333 verified requests |
| Two-routine conveyor demo | First complete 688-byte source container; nine rungs and 27 IOI operands | Fails reconstruction, 367 verified requests |

Both failures report `RxE_CORRUPT_RECON_DATA` while building the first routine.
The minimal BOOL fixture completes download/save/reopen/Online across 431
requests; the demo completes that sequence across 429. These results focus the
next investigation on tag-operand reconstruction. They do not prove a particular
descriptor, address, instruction or auxiliary field is the cause.

All three transfer journals are complete and replay identically offline.
Their download/upload event counts are 1,739/3,451 for NOP, 1,738/1,360 for the
minimal BOOL fixture and 1,735/1,496 for the demo. Offline replay does not
independently reauthenticate MACs. Native inputs, loaded values, logic and audit
state are preserved by upload, and every SDK session confirms Offline cleanup
without a reported SDK fault.

## Implemented source path

The client discovers the original [scoped Routine reference Symbols](routine-reference-symbols.md),
reads Routine data, queries the guarded [Label inventory](routine-label-discovery.md),
and requests the empty `(1, 4)` component followed by `(1, 3)` source.
[Downloaded Routine readback](downloaded-routine-read.md) validates the installed
source and adds the upload profile's explicit Standard class. Rung XML and
compressed auxiliary bytes are preserved, and no native machine code executes.

The emulator must first receive an unchanged source-equivalent download.
Resetting, reloading or restarting clears that memory-only installation.
This checkpoint uses existing matching ACD targets; uploaded ACD saving,
new-project reconstruction, general ladder upload and Studio GUI acceptance
remain unverified or unfinished.

## Validation

At this milestone, 2,101 Windows software tests pass with two platform checks
skipped, and all 357 Python files parse. Source, EXE, served browser assets and
119 appliance modules match the app version. Software checks and SDK acceptance
remain separate from native controller equivalence.

The original demo is restored with a new source-equivalent download across 430
verified requests. A separate SDK process reopens the saved ACD and goes Online
across 73, then confirms Offline cleanup. Original source and model remain
unchanged, with no SDK fault. The installation remains memory-only.
