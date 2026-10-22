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

All 177 affected checks pass, covering initialization versus failed samples,
Task/source/mode guards, ambiguous and nonempty AOI catalogs, unknown fault
history, signed mixed and duplicate reads, write denial and preserved state.
Live signed reads verify reply MACs and all 22 Task fields without running a
scan. The native Run/Program case verifies 107 requests and 118 actual scans;
the measured Start Time replaces zero, both stack sizes remain zero, and reload
returns to the initialized state with the original demo restored.

The empty-routine native upload verifies 361 signed requests on the unmodified
public runtime. It accepts all 22 Task fields, then passes empty Security
Authority Binding and trend discovery. It stops at a later Controller attribute
list with unavailable fields 11/12/33/34 and the SDK diagnostic
`RxCsE_ASA_ATTRIBUTE_LIST_ERROR`. The raw transfer interval is complete and has
no reported collection framing errors. Its bounded collection summary truncates
earlier rows; the final-request view retains the full Task list. This is native
acceptance of the Task collection in the no-AOI fixture, not a complete upload.

The normal demo upload retains its separate Program/Routine failure after 349
verified requests. SDK Go Online/Offline passes across 74 requests. All four
native cases confirm actual Offline/cleanup, unchanged original files and no
reported SDK fault. Read-only cases preserve the model; the mode test executes
logic intentionally before the original zero-scan/audit demo is restored.
Webpage, executable and appliance versions match `.158`. No uploaded-file save
was attempted. Complete native upload/download, a saved uploaded ACD, and the
complete Test/Untest/Assemble lifecycle remain separate acceptance goals.
