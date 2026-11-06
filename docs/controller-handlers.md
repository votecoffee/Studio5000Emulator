# Controller fault handlers

## Simulated I/O fault capture

A complete v35 ControlLogix 5580 export can assign one enabled, unscheduled
Standard Program through Controller `MajorFaultProgram`. Its single ladder
main routine executes once when a simulated Type 3 Code 16 or Code 23 fault
latches. The routine runs outside normal task scheduling and prescan. Its
tag writes and trace are visible at the current scan and simulated time.
If the routine fails, its writes and partial trace roll back. The original
I/O major fault remains latched, and its `handler` record reports the
routine, status and any error.

The first profile accepts contacts, coils, compares, MOV, CLR, ADD, SUB,
MUL, DIV, AFI, NOP and the listed GSV reads. The handler can read named Module
EntryStatus, FaultCode and FaultInfo. To capture the active fault record,
declare a writable DINT array and use its first element.

```text
GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);
```

The read writes 11 DINT words. Words 0 and 1 hold the low and high halves
of the emulator UTC timestamp in microseconds. Word 2 holds Type in its
low half and Code in its high half. The eight fault-specific Info words
are unknown. The browser and HTTP fault record retain the injected module
code and information independently. The read is available inside the
executing handler. Direct structure destinations, SSV fault clearing,
Program-specific fault routines, additional fault types and native
handler references remain open. Restore the simulated connection and
clear the fault through the existing recovery control to resume.
[Rockwell Major, Minor, and I/O Faults manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)
[Rockwell Program object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)

## Null native Controller handler references

Version `.111` adds reference-backed reads for absent Controller Power Loss
(attribute 1) and Fault Routine (attribute 6) handlers in native compatibility
mode. A successful v35 reference upload establishes four-byte values for both
fields, including an all-zero null. Nonzero physical references are not copied
or interpreted by the emulator.

## Source and scope

A null is available only when the complete controller export proves that the
corresponding handler is absent. Configured names, UID-only declarations,
context exports, missing source sections and ambiguous case/namespace variants
keep that field unavailable. Ordinary endpoint attributes remain unchanged.
Single reads and ordered lists share the same four-byte value; duplicate list
entries preserve their widths and positions. Setters remain denied.

Connectivity describes `handler_reference_encoding: null_uint32_only`, a
four-byte width and `configured_handler_references: false`. The native reference profile only serves proven null references.

## Aggregate profile

The Controller instance `Get Attributes All` read supports one observed
16-byte profile when both handlers are proven absent:

| Field | Bytes | Model source |
| --- | --- | --- |
| Communications time slice | 2 | Existing source value or declared compatibility default |
| Fault Routine reference | 4 | Proven absent handler |
| Power Loss reference | 4 | Proven absent handler |
| Run Mode Inhibit | 2 | Current programming lease state |
| Connection ID | 2 | Existing anonymous model slot value |
| Opaque zero trailer | 2 | Observed profile constant; meaning remains unresolved |

The trailer does not establish another controller attribute or runtime state.
The aggregate requires an instance path without an attribute and an empty
request body. Incomplete source or a configured handler returns an error.
Changing the owning lease's inhibit state changes the aggregate's inhibit
field; clearing the lease clears it. These reads do not change tags or scans.

The independent inventory reader retains the aggregate bytes and identifies
only an exact successful four-byte zero as `NULL_UINT32`. Other handler replies
stay unresolved. It does not convert opaque references into native addresses.

## Validation boundary

The reference upload includes successful handler and aggregate responses.
Nonzero configured native references remain unavailable. Synthetic source checks, independent signed TCP reads and inventory
tests cover null widths, duplicate lists, withheld configured/context data,
malformed scope/payload, live inhibit readback and unchanged tag/scan state.

The isolated SDK upload receives successful null-handler list reads. A second
case receives the 16-byte aggregate successfully, without the earlier fallback
list. Both still report `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED`.
Successful object replies do not establish successful SDK collection or identify
its remaining cause. Native Offline, endpoint cleanup and source/model
preservation pass without a reported fatal fault. A separate native Go Online/
Go Offline case passes.

Full upload/download, configured handler references, native tag addresses and
Test/Untest/Assemble remain unfinished. The previous Template metadata fault
hypothesis is not retried. Private captures, projects and native references are
not distributed with the repository.
