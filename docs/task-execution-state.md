# Task execution status and slots

Version `.138` adds read-only Task status and a registered execution slot to the
existing [Task measurements and references](task-runtime.md).

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
not grant native setters or memory services. Unknown Task type, trigger,
start-time, timeout and stack encodings remain unavailable.

## Validation

All 158 affected tests pass; the full suite was not rerun. Checks cover successful
scans, fault-history withholding and reset, source/mode and object-lifetime
guards, slot bounds and identity, signed mixed reads, write denial and programming
scan inhibit. Routine replacement retains unknown fault history while registering
the replacement Engine's actual Task object.
