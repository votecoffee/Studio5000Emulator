# Saving edited logic as L5X

Version `.91` adds **Save edited L5X** next to **Export snapshot**. After supported
native routine edits have finished, stop the emulator and select this control.
The browser downloads a separate `<controller>-edited-r<revision>.L5X` working
copy. The control is enabled only after an edit and while stopped with no active
native programming reservation.

The copy contains the active neutral source and model comments of edited
Standard RLL routines. Other project XML, routine attributes, unedited routines,
tag definitions, imported tag initial values and scheduling are retained from
the original complete L5X. The source file is read and checked against its
original SHA-256; a changed or missing source prevents export. Original ACD/L5X
files are never overwritten. Live values and scan history remain available in
the separate JSON snapshot feature.

Use **Open L5X** to reload the working copy in the emulator. It has a new source
hash, its own revision-0 baseline, and no inherited native ACD correlation
manifests. Changes persist in the saved L5X; there is no automatic save. This is
an emulator working-copy path. Version `.92` separately demonstrates native SDK
import and edited ACD save/reopen for the tested demo, as described below.
Studio GUI acceptance and firmware upload/download round trips remain unverified.

The session-authenticated `export-edited-l5x` action returns UTF-8 XML content,
a safe suggested filename, output/base hashes, runtime revision/digest and the
edited routine list. It reports `tag_values: original_import` and
`native_acd_correlation: false`. It does not write a server-side output file or
change the active model. A busy import, running emulator or active programming
reservation prevents saving.

The isolated native test replaces rungs in `MainRoutine` and `Reporting`, saves
the resulting revision-2 project, and reloads it into a separate emulator.
Both routines retain their edited instruction ASTs. The reloaded initial values
are 50 and 5; one scan again produces 123 and 456. XML comparison confirms that
tag data and Task/Module/DataType sections are preserved. The original ACD and
separate main demo remain unchanged.

## Optional native ACD save diagnostic

The [native SDK probe](development.md#native-sdk-acceptance-probe) accepts
`--save-edited-acd` with explicitly authorized supported edits. After final
Go Offline, it exports the active logic, closes its original SDK project,
imports the exported L5X through the SDK and saves a new `edited.ACD`. It closes
that project, reopens the new ACD offline and exports `reopened.L5X`. All three
outputs must be new files in the private diagnostic folder. The original ACD
and its input copy are not saved or overwritten.

Verification checks output hashes, all routine instruction ASTs against the
active model, executable entries, initial tag leaf types/values and program/task
names. This is a separate native receipt; the browser export by itself continues
to report native import as unverified. Native tooling is needed only for this
optional conversion diagnostic.

The `.92` demo case replaces rung 1 with `MOV(123,SpeedSetpoint);`, then inserts
`MOV(456,Parts.PRE);` at position 2 in the same routine. Both imports and
reconnects succeed across 313 verified signed requests. Native import,
ACD save/reopen and L5X re-export pass. Loading the new source pair with freshly
extracted ACD correlation manifests into an isolated emulator allows a fresh
SDK Go Online/Offline connection across 79 requests. Its first emulator scan
again changes 50/5 to 123/456. No fatal SDK fault is reported; native Offline and
endpoint cleanup are confirmed. The original main demo remains unchanged.

The regenerated ACD has its own identities. Reconnecting it requires an emulator
loaded from that new ACD/L5X pair; it must not inherit stale correlation manifests
from the original project. Saving a working copy does not implement native PLC
upload, download, online tag addressing or Test/Untest/Assemble.
