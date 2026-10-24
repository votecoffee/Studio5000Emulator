# Native Routine upload checkpoint

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
