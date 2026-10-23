# Supported Program-mode routine edits

Version `.89` applies a translated Routine source candidate to the custom
execution model. The tested path is a native SDK `AcceptEdits` rung import into
an existing Standard RLL routine, with the controller stopped in Program mode.
Native Test, Untest, Assemble, Run-mode edits, native binary execution and full
firmware edit semantics remain unsupported. Studio GUI editing is unverified.

## Usage

Load the ACD-backed complete v35 project and select whole-project execution.
In **Connectivity**, enable **Allow supported Studio edits** before connecting
the native client. Access defaults off and can change only while stopped and
disconnected. This control is separate from direct tag-write access.

The webpage reports a logic revision after application. Changes stay in memory.
Reset restores imported tag values while retaining the edited logic; reload the
original ACD or L5X to restore its routines. No original or input-copy file is
overwritten. Activating an edit does not automatically save a project file.

Version `.91` adds **Save edited L5X** for a separate
[working copy](edited-logic-l5x.md). Stop the emulator and finish the native edit
transaction before saving. The copy contains edited routines and original
imported tag initial values. Reloading it starts a new L5X artifact without
inheriting the original ACD's native correlation manifests. Version `.92` adds
an optional [native ACD save/reopen diagnostic](edited-logic-l5x.md#optional-native-acd-save-diagnostic).

## Transaction and activation

The existing [paired transfer](routine-source.md) validates bounded code/source
containers, object references and a detached execution plan. The following
[post-source record](edit-post-source.md) remains opaque retained metadata.
An incomplete candidate is discarded at Program release. A complete, validated
candidate instead survives that release under the same owning Controller
reservation and absolute deadline.

The observed Controller `0x59` profile with four zero payload bytes completes
this software transaction. It requires enabled edit access, the live edit owner,
an open preparation phase, no remaining Program holds, the released complete
candidate and unchanged original catalogs/runtime revision. Other payloads,
owners, scopes or states cannot activate it.

Resolution and execution planning run again against current bindings. A detached
engine receives independent copies of current values, scan/time history, timer
bookkeeping, first-scan/prescan state and traces. Preview prescan validates it
without applying its writes. Only then does the application replace its engine
under the existing scan lock. Failure leaves the active engine intact.

The replacement does not run a scan, initialize values or alter scheduling.
The normal next Run/Step executes it. An exact repeated completion within the
same transaction returns its existing receipt without another replacement.
Phase close, reservation release, timeout and disconnect clear temporary
buffers/receipts; they do not undo an already committed model edit.

The initial profile replaces one ordinary RLL routine per preparation phase in
an executable whole project without AOIs. Missing/protected context, unsupported
instructions or operands, unresolved object paths and blocked/faulted projects
remain errors. Multi-routine transactions and persistent project export are
separate work.

## Identity and reporting

The original L5X hash remains the base artifact/catalog binding. It is not a
hash of edited logic. `routine_edits` reports access, an incrementing runtime
revision, a separate logic digest and `memory_only` persistence. Device I/O
snapshots include the logic revision while retaining their existing tag layout
and project generation. The model never assigns the opaque post-source word
as an executable identity or claims ELF/source equivalence.

## Native result

After SDK service recovery, the isolated `.110` accepted-NOP import passes with
120 verified signed requests. The helper confirms the resulting routine edit,
native Offline, unchanged original ACD and clean endpoint shutdown without a
reported fatal fault. The main demo remains unchanged. This is the limited
Program-mode routine replacement profile; native Test/Untest/Assemble and the
Studio GUI workflow remain unverified.

The isolated `.89` SDK import of `MOV(123,SpeedSetpoint);` succeeds across 119
verified signed requests. The active routine contains the inserted rung plus
its original nine rungs. Application preserves tag values, scan/time history,
controller state, scheduling and the other routine. The logic revision becomes
1 and its content digest changes.

One subsequent emulator scan changes `SpeedSetpoint` from 50 to 123, demonstrating
execution of the imported instruction. Native Offline/readback and endpoint
cleanup succeed; no fatal SDK fault is reported and the original ACD is
unchanged. The running main instance is separate from this isolated test.

An earlier private empty-success `0x59` hypothesis completed the SDK import
without changing model logic. That diagnostic is not activation evidence; the
result above verifies the actual routine replacement and its execution.

### SDK FinalizeEdits in Program mode

The native probe accepts `--edit-import-option FinalizeEdits` together with
`--apply-supported-edits`. It retains the existing stopped Program-mode,
source/instance, ordinary RLL and explicit write-access requirements. The default
remains `AcceptEdits`; disabled-edit diagnostics do not enable finalization.

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation edits --apply-supported-edits --edit-import-option FinalizeEdits --edit-code 'NOP();' --reconnect-edits
```

Use the actual owned emulator address and loaded Program/Routine names. The
installed SDK describes additional assembly behavior for finalization in Run
mode. This probe requires Program mode and does not request that behavior,
native Test or Untest. The option name alone does not establish the complete
online-edit lifecycle.

On `26.1022.213142`, a native NOP finalization and reconnect pass across 187
verified requests, with one expected logic revision and audit update. A second
case finalizes `MOV(123,SpeedSetpoint);` and `MOV(456,Parts.PRE);` in the same open
SDK project, reconnecting after each import. Both pass across 298 requests and
advance the revision/audit twice without changing tag values or scanning during
the imports. One subsequent simulator scan applies the setpoint and counter
preset. Actual Offline/cleanup, preserved originals and no reported SDK fault
are confirmed. The original stopped zero-scan/audit demo is restored.

### Consecutive edits and reconnect

Version `.90` tests two inserts using the same open SDK project. One isolated
case goes Offline/Online after each import and succeeds across 315 verified
signed requests. A separate case remains online between imports and succeeds
across 159. Both reach revision 2, retaining the two new rungs and the original
nine, with unchanged values and scan/time history at each application. Each
case confirms final Offline and endpoint cleanup without a fatal SDK fault.

The continuously connected case inserts `MOV(123,SpeedSetpoint);` and then
`MOV(456,Parts.PRE);`. One subsequent emulator scan changes the setpoint from
50 to 123 and the counter preset from 5 to 456. This also exercises a supported
native member reference. Both cases produce the same runtime logic digest.
The original ACD and the separate main demo remain unchanged.

Reconnect here means the same open, updated SDK project going Offline/Online.
Reopening an original ACD with stale logic, upload/download and Studio GUI
editing remain separate unverified paths. Version `.92` separately tests a new
saved ACD as described below. The native diagnostic
requires revision 0 before opening its fresh ACD copy, preventing a new test
from unintentionally replacing prior in-memory edits with stale project logic.

### Rung replacement across routines

Version `.91` checks explicit zero-based insertion positions and replacement
counts against each routine's predicted preceding source. A second SDK import
can select a different loaded program/routine. This remains two separate,
sequential transactions; it is not an atomic multi-routine transaction.

The native case replaces rung 1 in `MainRoutine` with
`MOV(123,SpeedSetpoint);` and the sole rung in `Reporting` with
`MOV(456,Parts.PRE);`. Both imports and Offline/Online cycles succeed across 307
verified signed requests. Rung counts remain nine and one, unaffected rungs are
preserved, and logic revision advances to 2 without executing scans or changing
values at activation. A subsequent scan executes both changes. An exported L5X
working copy reloads into a separate emulator instance with original initial
values and executes both instructions again. Original ACD data and the separate
main demo remain unchanged. Native Studio import of that L5X remains unverified.

Replacement additionally sends the [removed-rung metadata profile](edit-post-source.md#replacement-metadata).
Unknown metadata forms remain rejected; retained records never write active
metadata or relax execution validation.

### Replacement followed by insertion

Version `.92` tests replacing rung 1 and then inserting a rung at position 2 in
`MainRoutine`, with Offline/Online after each transaction. The resulting routine
has ten rungs and logic revision 2. A scan executes both imported instructions.
One diagnostic then saves and reopens a new native ACD, rebinds an isolated
emulator to the saved project and confirms a fresh native SDK connection and
execution. See the [save diagnostic](edited-logic-l5x.md#optional-native-acd-save-diagnostic).

A separate repeat adds a post-edit DINT SDK read. Both imports and reconnects
succeed across 316 verified requests, but the read still fails with
`RxDA_E_NO_ONLINE_ADDRESS`. That diagnostic is reported as failed despite
confirmed applied edits, clean native Offline and endpoint cleanup. Executing
the edits in the emulator does not establish native tag-monitoring support.

### CPT and conditional arithmetic

Version `.93` adds [CPT expression reference translation](routine-source.md#cpt-expression-references).
The native SDK appends a CPT calculation at position 9 and conditional ADD at
position 10 of the demo's `MainRoutine`. Both imports and reconnects succeed
across 314 verified signed requests. The original nine rungs remain present;
activation advances logic revision to 2 without executing scans or changing
values/history.

With `SpeedSetpoint=50` and `StartPB=false`, a scan sets `SpeedCommand=107`.
Queued external inputs remain invisible until the next scan, when setpoint 60
and StartPB true produce 137. Setpoint 75 and StartPB false then produce 157.
Each input transaction has an applied acknowledgement for its scan boundary.
The saved L5X retains original initial values, reloads and reproduces 107/137.
Native Offline and endpoint cleanup succeed, no fatal SDK fault is reported,
and the original ACD/main demo remain unchanged. Studio GUI acceptance and
native tag monitoring remain unverified.

### Comparisons and array operands

Version `.94` translates source-bound references in CMP expressions and
[static array operands](routine-source.md#static-array-operands). One demo case
appends `CMP(SpeedSetpoint>55)MOV(111,SpeedCommand);` and
`CMP((SpeedSetpoint+5)>=65)ADD(SpeedCommand,9,SpeedCommand);`. Both imports and
reconnects pass across 314 verified signed requests. Setpoints 50, 60 and 56
produce commands 0, 120 and 111 respectively. The saved L5X reproduces all three.

A separate native demo declares a four-element DINT array `Samples` with initial values
10, 20, 30 and 40. Native imports append `MOV(Samples[2],SpeedCommand);` and
`CMP(Samples[0]>0)CPT(Samples[1],Samples[0]+SpeedCommand);`. Both imports and
reconnects pass across 315 requests. The first scan sets the command to 30 and
element 1 to 40. Queued external writes setting elements 0/2 to 100/7 produce
command 7 and element 1 equal to 107. Setting them to 0/9 produces command 9
while the false CMP retains element 1 at 107. Receipts confirm each write batch
at its scan boundary, and an exported L5X reproduces the cases from original
initial values. No fatal SDK fault is reported; Offline and cleanup succeed.

Before each translator extension, the corresponding unsupported import is
rejected without altering active logic or values. The
[signed rejection path](edit-post-source.md) now preserves native Offline and
endpoint cleanup. All private candidates are separate from the original main
demo. These checks do not establish native tag-address discovery, firmware
execution equivalence, Studio GUI acceptance or Test/Untest/Assemble support.

### Integer-bit operands

Version `.95` extends the translator with checked
[integer-bit references](routine-source.md#integer-bit-operands). A native case
appends `XIC(Samples[2].0)MOV(123,SpeedCommand);`, then
`OTL(Samples[1].31);`, to the separate four-element DINT demo. Both imports and
Offline/Online reconnects succeed across 315 verified requests. Activation
advances the logic revision to 2 without scanning or changing tag values.

The first scan leaves the command at 0 because element 2 is 30, and latches
element 1's sign bit, changing 20 to -2147483628. Queued external inputs of
7/31 for elements 1/2 produce -2147483641 and command 123. Inputs of
2147483647/32 produce -1 and command 0. Each input batch remains invisible
until its acknowledged scan boundary. A separate edited L5X retains original
initial values and reloads to reproduce all three cases.

Before adding bit translation, the same first import is rejected with the
active model unchanged; native Offline and endpoint cleanup succeed. The
successful case also confirms Offline/cleanup without a fatal SDK fault.
Original source files and the main demo are preserved. Software tests
additionally reject controller IOIs that would become shadowing Program-local
names. Native tag monitoring and the full edit lifecycle remain unfinished.

### Indirect array operands

Version `.97` extends the source-bound translator with
[indirect indices](routine-source.md#indirect-array-indices). Native imports
append `MOV(2,SpeedCommand)MOV(Samples[SpeedCommand],SpeedSetpoint);` and
`CPT(Samples[SpeedCommand],Samples[SpeedCommand]+5);` to the separate array demo.
Both imports and reconnects pass across 315 verified signed requests. The first
scan reads element 2 as 30, then writes 35. Queued external inputs of 200 and
-3 produce read/write pairs 200/205 and -3/2 at acknowledged scan boundaries.
The edited L5X retains original initial values and reproduces these scans.

The unsupported form was first captured from a rejected native import; that
case preserves the model and confirms native Offline/cleanup. The successful
case also confirms Offline/cleanup without a fatal SDK fault. Index references
stay live during execution, and out-of-range access has software tests for
scan rollback. Broader native index/type coverage and the complete edit
lifecycle remain unfinished.

### Indirect integer-bit operands

Version `.98` adds [source-bound bit indices](routine-source.md#indirect-integer-bit-operands).
The native case appends `MOV(0,SpeedCommand)OTL(Samples[1].[SpeedCommand]);`, then
`MOV(31,SpeedCommand)OTL(Samples[2].[SpeedCommand])XIC(Samples[2].[SpeedCommand])MOV(777,SpeedSetpoint);`.
Both imports and reconnects pass across 315 verified signed requests. The first
scan latches element 1's low bit and element 2's sign bit, producing
21/-2147483618; the selected sign bit also enables the setpoint write to 777.
Queued external inputs produce 3/-1 and 2147483647/-2147483648. The saved L5X
reproduces these cases from original initial values.

The previously unsupported source form was first captured from a rejected
import that preserves the model and confirms native Offline/cleanup. The
successful case also confirms Offline/cleanup without a fatal SDK fault.
Software checks cover live index changes, CMP conditions, invalid index types
and bounds faults with scan rollback. Full upload/download, Studio GUI
monitoring and Test/Untest/Assemble remain separate unfinished milestones.
