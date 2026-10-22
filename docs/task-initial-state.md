# Initialized Task metadata

Version `.158` defines initial Start Time and no-AOI stack allocation for the
existing single Standard Continuous/Periodic interpreter Task. These are
explicit emulator policies; they do not recover a physical controller's history
or its internal stack allocator.

| Task attribute | Emulator policy | Encoding |
| --- | --- | --- |
| 13, Start Time | Zero before the first successful execution; then the committed simulator WALLCLOCKTIME sample | INT64 microseconds |
| 22, Pending AOI Stack Size | Zero allocation when complete source proves there are no AOI declarations | UINT32 |
| 23, AOI Stack Size | Zero allocation under the same no-AOI condition | UINT32 |

The installed v35 Task attribute schema identifies fields 22 and 23 as pending
and active AOI stack sizes. It supplies their four-byte widths but does not
document an initial timestamp or a no-pending sentinel. This implementation uses
zero allocation for both sizes in its no-AOI interpreter profile. It does not
adopt the earlier private hypothesis that returned `FFFFFFFF` for field 22.

The [Task object reference](https://www.rockwellautomation.com/en-il/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
defines StartTime as the WALLCLOCKTIME at the last Task start. Before any
successful execution, this emulator reports an initialized zero, separately
identified as unmeasured in `task_measurements.start_time_measured`. After a
successful scan with an invalid clock sample, Start Time remains unavailable;
zero never masks a failed measurement. Reset initializes a new record. Existing
failed-scan rollback and supported Routine-replacement preservation still apply.

Both stack fields require the existing current-source, registered Task and
supported execution-profile guards, known clean simulator fault history, and
the complete [AOI catalog's](aoi-metadata.md) empty declaration proof.
Missing, protected, ambiguous or nonempty AOI declarations retain unavailable
stack fields. Unexpected runtime AOI definitions, active definitions or instance
frames also withhold them. No populated AOI stack sizing or native stack-memory
service is implemented. `task_aoi_stack` exposes this policy and availability.

Single and ordered signed reads preserve duplicate and mixed unavailable
fields without executing logic, sampling Start Time again or modifying source,
tags or audit state. Native setters remain denied.

## Validation

Focused software and live native results are recorded with this revision's
release evidence. Complete native upload/download, a saved uploaded ACD, and
the complete Test/Untest/Assemble lifecycle remain separate acceptance goals.
