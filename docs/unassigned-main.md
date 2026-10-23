# Programs without an assigned main Routine

Version `.162` supports a source-checked ordinary Program containing stored RLL
routines without an assigned main Routine. Earlier releases accepted only an
empty Routine catalog in this case and otherwise reported a missing-Routine
blocker. No stored routine is selected automatically, including one whose name
is `MainRoutine`.

## Source and execution

Rockwell's [Import/Export Project Components manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm019_-en-p.pdf)
describes existing Programs without a main Routine and the effect of assigning
one during import. A private offline v35 SDK export/import/save/reopen test also
retains stored RLL source with no main assigned. These establish the source
configuration; physical controller execution has not been tested here.

The simulator's whole-project scheduler executes no main Routine for this
Program. Scans and Task measurements advance, while main-Routine execution and
timing counters stay zero. Normal prescan still visits its supported stored
routines. Mixed schedules continue executing other Programs' assigned mains.
The isolated Routine harness can execute a stored routine explicitly.

The profile requires complete ordinary v35 source, explicit canonical
`TestEdits=false`, `UseAsFolder=false` and a valid `Disabled` boolean. Main and
fault assignments must be absent or empty. The Routine inventory must be complete,
readable, ordinary untested RLL with no signature or unknown Routine metadata.
Hidden, contextual or ambiguous declarations remain unavailable. A nonempty
main name that does not resolve remains a blocker. Unsupported stored logic is
still checked and blocked, including instructions whose prescan is unsupported.

## Metadata and limits

The source-bound Program main reference is null; its Program reference still
identifies an actual current interpreter object. Stored routines retain separate
backed header references and the existing ordinary subroutine flag value `2`.
Original native parent/child bindings, source hashes, fault history and edit
guards remain required. A changed or incomplete current Routine inventory cannot
advertise the null-main reference. No compiled Routine code is installed.

API counts distinguish truly empty Programs from Programs with no assigned main:
`empty_programs_available` stays zero for a populated catalog, while
`unassigned_main_programs_available` reports the eligible source or schedule.
This adds no main-assignment setter, fault-handler execution, Safety behavior or
native Test/Untest/Assemble authority.

## Validation

All 248 affected checks pass, covering unused source, mixed schedules, prescan,
explicit harness execution, zero main timings, invalid/incomplete source,
reference lifetime and signed Program/Routine metadata. The full suite is not
rerun for this addition. Native transfer acceptance is assessed separately.
