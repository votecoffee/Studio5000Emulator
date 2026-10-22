# Stored Task configuration

Version `.139` extends the optional native Task catalog with selected original
settings from an observed v35 `Comps.Dat` format-18 body. These settings supplement
the existing [source Task metadata](task-metadata.md); they do not import runtime
history or change scheduling.

| Attribute | Stored setting | Wire encoding |
| --- | --- | --- |
| 2, Rate | Original positive microsecond value, including the latent Continuous setting | UINT32 |
| 4, Trigger | Original supported non-event trigger bytes | UINT16 length followed by five zero bytes |
| 5, Type | Original supported type word | UINT16 |
| 17, Timeout | Original zero timeout in the supported non-event profile | UINT32 |
| 21, Tag Mapping Count | Original zero count in the supported Standard profile | UINT16 |

A Continuous Task can retain a stored rate even when the native L5X export
omits `Rate`. The reader preserves that original value. It does not insert a
default or use the value as a Continuous execution period. Plain L5X still
supplies Rate only for an explicit Periodic declaration.

## Profile and binding

The reader accepts only the observed fixed 4506-byte format-18 Standard
Continuous/Periodic body. It checks the fixed Program-list capacity, used IDs,
zero unused slots, bounded positive times, priority, exact non-event trigger,
Boolean settings and zero timeout/data-use/mapping profile. Unknown or malformed
optional settings stay unavailable while the independently validated Task
identity remains usable.

The stored type words correlate with the offline comparisons: Continuous `4`
and Periodic `2`. The reader returns the original word after matching it to the
canonical source kind. It does not define Safety, Event or future type encodings.

Readback requires matching original ACD/L5X Project, Task and Program bindings.
The ordered native Program IDs must match the complete source schedule. Explicit
source type, rate, priority, watchdog, output-update and inhibit settings must
agree with the stored record. A missing or conflicting binding withholds all
five supplemental fields. Existing independent source fields retain their own
availability rules.

The immutable native manifest optionally carries a `configuration` map. Legacy
identity-only manifests remain supported. ACD import derives the optional map;
loading validates its shapes and values, reset/configuration preserve it, and a
plain source import clears it with the other native bindings.

Runtime counters, timestamps, pointers, addresses and extended stack properties
are excluded. The simulator's [Task measurements](task-runtime.md),
[execution status and slots](task-execution-state.md) remain independent. Native
setters remain denied. Start Time and the two unresolved Task fields remain
unavailable; this change does not complete native transfer.

## Validation

Controlled offline SDK imports, saves, reopens and exports compare a Continuous
project, Periodic 10 ms and 25 ms projects, and a Periodic variant with separate
priority, watchdog, output-update and inhibit settings. Their source differences
correlate with the selected stored fields while preserving the original project
and running demo. These operations confirm offline persistence, not controller
acceptance.

All 176 affected tests pass; the full suite was not rerun. Checks cover exact
encodings, rejected profiles and bounds, immutable legacy/extended manifests,
source and schedule mismatches, optional-data preservation, signed mixed reads
and write denial. They also verify that stored metadata excludes runtime state
and cannot manufacture a missing source rate.

The isolated SDK upload accepts all five added fields across 358 verified signed
requests and 361 expanded leaves. Compared with the exact-source `.138` control,
the unavailable Task fields fall from 8 to 3: Start Time and fields 22/23. Upload
still fails Task collection. Both trials use identical original project files,
Template snapshot and private clock/schema/repository hypotheses; those
hypotheses remain unshipped. Actual Offline/cleanup, unchanged source/model and
no fatal SDK fault are confirmed.

A separate normal-protocol SDK Program-mode NOP insertion and reconnect preserves
all five stored fields, Task status, slot and measured counters. The replacement
engine supplies a new live Task reference and executes the next scan normally.
All 183 verified requests succeed, with actual Offline/cleanup, unchanged
originals and no fatal SDK fault. The source-matched download retains the
result-response gap across 176 verified requests, 909 temporary records, 243
Templates and 18 Tables, without an active image commit. Test/Untest/Assemble
and full upload/download remain unfinished.

The restarted normal demo passes SDK Go Online/Go Offline across 75 verified
signed requests, with actual Offline/cleanup, preserved source/model and no
fatal SDK fault. All 21 deployment checks pass, including the frozen executable's
stored-record reader, source bindings and legacy manifests. All 96 deployed
modules and served assets match the build; webpage, executable resources and
Windows versions agree on `.139`. The prior model and edit configuration survive
restart.
