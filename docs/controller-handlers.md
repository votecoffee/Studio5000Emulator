# Controller fault handlers

## Simulated I/O fault capture

A complete v35 ControlLogix 5580 export can assign one enabled, unscheduled
Standard Program through Controller `MajorFaultProgram`. Its ladder main
routine executes once when a simulated Type 3 Code 16 or Code 23 fault
latches. The routine runs outside normal task scheduling and prescan. Its
tag writes and trace are recorded at the current scan and simulated time.
The next prescan or scan replaces the trace. If the routine fails, its
writes and partial trace roll back. The original
I/O major fault remains latched, and its `handler` record reports the
routine, status and any error.

The handler profile accepts contacts, coils, compares, MOV, CLR, ADD, SUB,
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
executing handler. Program-specific fault routines, additional fault types
and native handler references remain open.
The existing recovery control can clear a fault after the simulated
connection is restored.
[Rockwell Major, Minor, and I/O Faults manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)
[Rockwell Program object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)

## Call ladder diagnostic subroutines

The handler main can use JSR to call ladder routines in its own Program.
Calls use the normal JSR/SBR/RET rules for typed parameter copies, with a
25-call limit and an instruction budget shared by the handler. Recursive
calls, calls to the main routine and unsupported instructions in called
routines block project execution during validation.

Called routines can read or clear the active MajorFaultRecord just like the
main. Their tag writes, including input and return copies, and a pending
fault clear commit together when the main finishes. An error anywhere in
the call chain discards those writes and its trace. Handler routines stay
outside normal task scheduling, prescan and the isolated routine harness.

[Rockwell JSR, SBR and RET reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm003_-en-p.pdf)

## Read and clear a structured fault record

A user-defined record can declare either a scalar LINT timestamp or two
scalar DINT words in low/high order. Declare scalar INT Type and Code
next, then a one-dimensional DINT[8] Info array. The member names may
vary. Use the record's first timestamp member as the GSV destination or
SSV source. The selected record can be a scalar tag or an element of
an array. The simulator validates the entire declared layout, including
visible members and array extent, before writing any fields.

For a record whose first member is `Timestamp`, these rungs capture
the fault and clear only Type 3 Code 16.

```text
GSV(Program,THIS,MajorFaultRecord,FaultRecord.Timestamp);
EQU(FaultRecord.Type,3)EQU(FaultRecord.Code,16)CLR(FaultRecord.Type)CLR(FaultRecord.Code)SSV(Program,THIS,MajorFaultRecord,FaultRecord.Timestamp);
```

The split timestamp form uses its low word as the operand. Info words
remain unknown in either layout. Both INT fields must contain known zeros
to request a clear. The existing handler commit and rollback rules apply.
[Rockwell fault-record structure and operand guidance](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)
[Rockwell LINT timestamp layout](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-program-object.html)

## Clear an active fault in ladder logic

In the same controller handler, use SSV with THIS or the current handler
Program. For an 11-word DINT source, the packed Type and Code word must be
known zero. For example, after reading the active fault, this rung clears
only Type 3 Code 16.

```text
EQU(FaultWords[2],1048579)CLR(FaultWords[2])SSV(Program,THIS,MajorFaultRecord,FaultWords[0]);
```

The clear commits only after the handler completes. A later failure rolls
back the pending clear and handler writes. A reached SSV with an unknown
or nonzero Type/Code word fails the handler. A GSV in the handler after a
valid SSV sees zero Type and Code. The remaining record words stay read-only.

A cleared 3/16 continues Run at the next scan without another prescan. A
cleared 3/23 lets the current Run request proceed through prescan. The
simulated connection still reports the applied fault, so another
Program-to-Run request can raise a new 3/23. The browser and
`controller.last_cleared_module_fault` report the latest programmatic clear
for the current simulation, with the original type, code and diagnostics.
[Rockwell programmatic fault clearing example](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm014_-en-p.pdf)

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
