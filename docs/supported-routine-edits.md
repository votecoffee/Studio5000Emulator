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
