# Task execution status and slots

Version `.138` adds read-only Task status and a registered execution slot to the
existing [Task measurements and references](task-runtime.md).
Version `.139` separately adds [original stored configuration](stored-task-configuration.md).

| Task attribute | Current software model | Encoding |
| --- | --- | --- |
| 3, Status | No event trigger, timeout trigger or overlapping Task dispatch | UINT32 bitfield, currently zero |
| 9, Overlap Count | No overlapping dispatch in the single serial Task runner | UINT32, currently zero |
| 16, Task Instance | Slot allocated by the current interpreter Task registry | UINT32, 0 through 31 |

## Execution status

The existing executor runs one complete Standard Continuous/Periodic Task at a
time. It has no event or timeout scheduler and does not queue a second execution
while a Task is running. Status and overlap count describe those actual model
constraints. They are separate from controller Run/Program mode.

These values require the current complete source, a canonical executable Task,
an unchanged Task registration and known clean simulator history. A simulator
fault withholds both fields. Clearing its message or completing a later scan
does not restore a known native status: the uncertainty remains until reset.
Supported Routine replacement preserves that history.

The installed v35 Task descriptions establish the four-byte fields; the
[Task object reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
describes status bits and the execution-instance range. This implementation
does not add periodic deadline scheduling, preemption, missed-trigger accounting
or watchdog enforcement. Source Rate remains configuration metadata. These
counters do not predict physical controller timing or fault behavior.

The endpoint's `task_execution_status` reports availability, the serial model's
limits and uncertain fault history without exporting private runtime objects.

## Execution slots

The interpreter registry allocates Task slots in declaration order, independently
of native logical CIP IDs and opaque DWORD object references. The current
single-Task execution profile uses slot 0. This is a simulator allocation, not
an imported or recovered physical-controller slot.

Each allocation resolves to its actual current Task object. Foreign projects,
invalid slot types/ranges, duplicate Task names, more than 32 registrations,
renaming, replacement, removal and reordering invalidate lookup. A new Engine
registers its own objects, including after reset or supported Routine replacement.
The internal 32-slot bound does not expand the supported single-Task executor.

The wire field requires the same current ACD/L5X Project and Task bindings as
Task Address. Programming scan inhibit withholds both fields until cleanup.
Read services share one registry, preserve mixed attribute-list framing and do
not grant native setters or memory services. Stored type, trigger and timeout
reads have the separate `.139` profile above. Start-time and unresolved stack
encodings remain unavailable.

## Validation

All 158 affected tests pass; the full suite was not rerun. Checks cover successful
scans, fault-history withholding and reset, source/mode and object-lifetime
guards, slot bounds and identity, signed mixed reads, write denial and programming
scan inhibit. Routine replacement retains unknown fault history while registering
the replacement Engine's actual Task object.

The isolated SDK upload accepts all three added fields across 358 verified
signed requests and 361 expanded leaf requests. The unavailable Task fields fall
from 11 to 8 compared with the retained `.137` trial using identical original
project files, Template snapshot and private clock/schema/repository hypotheses.
The `.137` code hashes match the frozen control; that control was reused instead
of repeating an unchanged test. Upload still fails Task collection. The private
hypotheses remain unshipped.

A separate SDK Program-mode NOP insertion and reconnect uses normal protocol
behavior. Task status, slot and timing values survive replacement, the object
reference changes, and the next scan executes normally. All 183 verified signed
requests complete successfully. A source-matched download reaches the same
result-response gap across 176 verified signed requests, with 909 temporary
records, 243 Templates and 18 Tables prepared and no active image commit.
All three trials confirm actual Offline/cleanup, preserved originals and no
fatal SDK fault. The transfer trials preserve the active model; the edit trial
changes only its authorized Routine. Full upload/download and the complete
Test/Untest/Assemble lifecycle remain unfinished.

The restarted normal demo passes SDK Go Online/Go Offline across 75 verified
signed requests, with actual Offline/cleanup, preserved source/model and no
fatal SDK fault. All 19 deployment checks pass, including the frozen executable's
status, slot, fault-history and reset checks. All 95 deployed modules and served
assets match the build; webpage, executable resources and Windows versions
agree on `.138`. Tags, logic, tasks, mode and edit configuration survive restart.
