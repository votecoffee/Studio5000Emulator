# Scheduled empty Programs

Version `.136` supports an explicitly empty ordinary Program as a no-op in
whole-project mode. Previously, a scheduled Program without a main Routine
produced a missing-Routine blocker even when its complete source contained no
routines at all.

## Source and execution

The complete v35 source must declare an ordinary Standard Program with one
canonical empty `Routines` container, `TestEdits="false"`, `UseAsFolder="false"`
and a canonical `Disabled` boolean. Main and fault Routine names must be absent
or empty. Protected, contextual, shadowed or ambiguous declarations cannot
establish this case.

An enabled empty Program can share the supported single Standard Continuous or
Periodic Task with executable Programs. A scan advances simulator time and scan
count while the empty Program executes no instructions and changes no tag
values. Normal Programs still execute their scheduled main routines. An empty
Task, a missing named main Routine, an inhibited Task or an unsupported Task
configuration remains blocked.

The empty Program retains zero main-Routine timing and execution counts because
no main Routine executes. It participates in the simulator's clean fault history
and source-checked idle Program state. An unclassified fault still withholds
normal fault/status metadata until reset. These are software-model counters,
not physical controller timing or imported fault history.

## Native metadata

The source-bound Program main reference is null. Its Program reference still
resolves to an actual current interpreter object, with the existing lifetime,
source and edit guards. Missing named routines do not become null references.
Routine discovery returns an empty list only through the existing complete
source and matching original native identity checks.

The eligible idle profile supplies the observed 22-field Program collection
reply, including known-untested state, clean fault records and zero UDI stack.
No Routine object, source blob, compiled code or native edit transaction is
created for the empty Program.

## Validation

Focused checks cover no-op scans and prescan, mixed empty/executable Programs,
source ambiguity, stale references, fault history and signed Program collection
and empty Routine discovery. All 121 affected tests pass; the full suite was
not rerun.

An isolated native upload of a separately saved and reopened empty-Program ACD
previously stopped at Program collection across 204 verified signed requests.
With this change it passes that collection and empty Routine discovery, reaching
the later PLC file-mapping collection request at class `0x6E`. Upload still fails
there across 357 verified signed requests. Both trials confirm actual Offline
and endpoint cleanup, unchanged originals/model and no fatal SDK fault. The
private clock/schema hypotheses needed to reach these stages remain unshipped.

Full native upload/download and source reconstruction remain unfinished. This
empty-source case does not resolve the existing nonempty Routine upload failure.

The corrected single-Routine comparison contains one `NOP()` rung, no removed
Routine references, and an independently saved/reopened ACD and Template snapshot.
Its upload still receives the complete Routine reply, then fails Program upload
before source retrieval across 357 verified signed requests. The Routine boundary
therefore also occurs with this minimal logic; its cause remains unresolved.

Two source-matched native download trials, using the empty Program and single
NOP Routine respectively, both reach the existing result-response gap across
176 verified signed requests. Their temporary images retain 907/909 records,
243 Templates and 18 Data Tables; no active image is committed. Both confirm
actual Offline/cleanup, unchanged source/model and no fatal SDK fault.

A separate private comparison exercises empty class-`0x6E` discovery and advances
the empty-Program upload to Task collection across 358 verified signed requests.
Sixteen requested Task fields remain unavailable and upload fails. This does
not establish a general empty repository or mapping contract, and the substitute
is not shipped. All six retained upload/download comparisons preserve their
originals and emulator model; no physical-controller contact was initiated.

The rebuilt and restarted `.136` demo passes SDK Go Online/Go Offline across
75 verified signed requests, with actual Offline/cleanup, unchanged source/model
and no reported fatal SDK fault. All 13 deployment checks pass, including
execution of the frozen empty-Program implementation and its source guards.
All 94 deployed app modules match the build; served assets, executable resources
and webpage/executable versions match `.136`. The demo's tags, routines, tasks,
mode and edit configuration match their state before restart.
