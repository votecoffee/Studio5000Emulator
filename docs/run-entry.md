# Run-entry prescan

Version `0.6.0-connectivity.75` applies the execution model's prescan rules to
every Program-to-Run transition, through either native requests or webpage
controls. It rearms `S:FS` for the first successful normal scan. Repeated Run
requests, including an interval change while already running, do not repeat
initialization. The scan worker discards its old wait deadline after a stop,
restart or interval change.

## Loading and stepping

The application loads saved values in Program. Coverage checks perform a
prescan preview and discard its effects; an AOI's Prescan routine does not
initialize the loaded instance until execution starts. Run commits that
initialization once before reporting success. The first manual Step also
initializes once; subsequent Steps continue the same modeled execution.
Switching from those Steps to Run performs a new Run-entry initialization.
Reset and project/scope replacement return to saved values in Program.

The standalone Python `Engine` retains eager initialization by default for
existing deterministic harnesses. The application uses `defer_prescan=True`.
Both paths share the same transactional prescan implementation.

## Modeled behavior

| State | Run-entry behavior |
| --- | --- |
| `S:FS` | True until the next successful normal scan finishes |
| OTE destinations | Cleared |
| ONS/OSR storage | Set; OSR output cleared |
| OSF storage/output | Cleared |
| CTU/CTD edge storage | Set; accumulator and other retained state preserved |
| TON/TOF | EN, TT, DN cleared; ACC cleared; PRE retained |
| RTO | EN and TT cleared; ACC, DN and PRE retained |
| OTL/OTU destinations and ordinary data | Retained unless another prescan operation writes them |
| ST non-retentive `[:=]` destinations | Cleared at lexical sites, including conditional code |
| AOIs | Existing bounded logic prescan and enabled Prescan routine, including parameter copies |

Whole-project scope includes uncalled routines in scheduled, enabled programs.
An isolated harness retains its existing selected/called-routine scope. Timer
visit history and the old logic trace clear without advancing simulated time
or the normal scan count. Existing normal-scan change history is retained.
Prescan does not consume queued Device I/O inputs; those apply at normal scan
boundaries. Snapshots can therefore change at Run entry before scan count moves.

Tag values, AOI bindings/instance metadata, call context, timer history, the
first-scan flag, trace and instruction budget restore on initialization failure.
The application remains stopped and reports Faulted. Native Start returns a
state-conflict error, with the same faulted identity readback; it cannot report
Run for a failed initialization. Reset is required before another Run request.
Each prescan has a fresh instruction budget.

The `controller` API adds `prescan_count` and `first_scan_pending` to the
[shared mode state](controller-mode.md). Loading a project starts the count at
zero; only successful, committed initialization increments it. Preview and
failed initialization do not increment it.

## Verification boundaries

Synthetic fixtures exercise first-scan rearming, timer and counter retention,
edge suppression, lexical ST behavior, uncalled-routine/harness scope, AOI
parameter copies and arithmetic failures, and native Start/Stop error paths.
The optional native `--operation modes` probe now requests two SDK Run/Program
cycles, checks one initialization per Run, verifies webpage mode readback and
checks that a repeated webpage Run preserves the initialization count.

These are bounded software rules. Native prescan ordering, repeated subroutine
calls, loop iteration parity, every extended instruction's initialization,
physical output behavior and Studio GUI monitoring remain unverified. This
feature does not establish full controller or safety equivalence.

Rockwell documents Program-to-Run prescan in its
[ladder rung-condition reference](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/ladder-diagram-rung-condition.html),
the first-scan flag in
[Math status flags](https://www.rockwellautomation.com/en-ro/docs/studio-5000-logix-designer/37-02/contents-ditamap/math-status-flags.html),
and AOI scan modes in the
[Add-On Instructions manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm010_-en-p.pdf).
These references describe the intended semantics; they are separate from the
model and SDK verification described above.

## Deployed verification

The rebuilt `.75` application and served browser assets match source. Its
1,002-test suite passes on Windows (1,000 passed, two platform skips) and Linux
(1,001 passed, one platform skip). All 291 live protocol checks pass.

The deployed 17-step native mode probe verifies 119 signed requests. Its two
SDK Run cycles advance 30 and 34 scans, with committed prescan counts of one
and two. Program stops scans between cycles. Webpage Run produces count three;
a repeated Run retains three, and its Program change reads back through the SDK.
Loading the demo in Program was separately checked against saved source values,
with zero normal scans and zero committed prescans.

Go Online/Offline still passes the nine-step connection probe. Native tag reads,
upload and download retain their known failures, with source/model preservation
and final Offline/TCP/lease cleanup. One upload probe exposed a transport that
closed at the endpoint's normal 30-second idle timeout. The probe now allows a
bounded 40-second cleanup wait while retaining every source, instance, lease,
inhibit and temporary-state check; the repeated upload probe confirms cleanup.
The initial incomplete report remains private evidence.

The original ACD remains byte-identical, and FactoryTalk Linx and the SDK service
remain running. The application is left stopped in Remote Program, with the
three committed initializations retained in its diagnostic count. Studio GUI
monitoring and native instruction equivalence remain unverified.
