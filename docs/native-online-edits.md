# Native online-edit diagnostics

The optional public SDK probe has an `edits` operation that inserts one generated
`NOP();` rung into a loaded RLL routine on a private ACD copy. It exercises the
native import path while LogixLab continues to advertise disabled online-edit
authority. Active controller edits, finalizing and assembling edits remain
unsupported.

The observed controller-scoped semaphore acquire (`0x4B`, controller `0x8E/1`,
semaphore `0x74/1`) has a one-byte request selector. Selector `0` reserves the
existing programming coordination lease. Selector `1`, observed during the
native online import, reserves a separate edit purpose on that same exclusive
lease. The reservation retains its bound native owner and source generation.
It stages zero changes and grants no accepted, tested, assembled or committed
edit state. Changing purpose requires release; a second native context cannot
share either reservation. Download preparation and Run Mode Inhibit require
selector `0`. Release, disconnect, expiry and source replacement clear the edit
reservation.

Run against an idle, source-bound emulator in Program mode, with protocol and
Device I/O writes disabled. Use the endpoint's actual local webpage URL and
Linx path. The documentation address below is an example:

```powershell
py -3.13 -X utf8 source/tools/probe_native_sdk.py --project .local/Controller.ACD --url http://127.0.0.1:8786 --path 'Emulator\192.0.2.8\Backplane\0' --operation edits --edit-program MainProgram --edit-routine MainRoutine
```

The default `AcceptEdits` option requests that the SDK accept and send imported
logic to the controller. The current endpoint is expected to reject unsupported
operations. This attempt records the SDK's actual error and paired protocol
requests instead of returning invented successful programming acknowledgements.
It never requests Run mode, replaces existing rungs, finalizes or assembles edits.

For an independent comparison on a fresh private copy, repeat with
`--edit-import-option LeaveEdits`. The installed SDK documents `LeaveEdits` as
offline pending changes, even when the project is online. A successful call with
that option establishes a local pending import; it does not establish that the
controller accepted an edit. Each invocation uses a separate output directory
and ACD copy. `FinalizeEdits` is deliberately unavailable.

Before the native call, the probe validates the selected ordinary RLL routine,
source hashes, emulator instance, disabled edit authority and empty programming
state. Afterward it requires unchanged routines, tasks, entry points, controller
state, running values and scan history. It goes Offline, disposes the private
SDK project and requires the endpoint's clients, lease and temporary staging to
clear. It never saves the edited ACD over the input and never manages Windows
services.

Private reports include the generated rung hash, SDK step start/end timestamps,
newly rejected structural requests and import-interval protocol evidence. The
helper captures emulator traces immediately before and after the import, with
source and instance checks on both sides of each checkpoint. The report uses
the exact last retained event to identify newly appended frames. It preserves
trace order independently of the host and guest wall clocks. Missing checkpoints
or a lost marker are reported explicitly.

The
`first_failed_request` field identifies the first complete nonzero CIP response
observed during the import, when available. It is diagnostic evidence rather
than a claim that every returned CIP error causes the SDK failure. An empty
interval is reported explicitly. Parsing these saved frames checks their
structure and correlation; it does not authenticate their MACs or establish
native runtime equivalence.

Version `.78` native testing advanced past the selector-1 reservation: acquire
and later release both succeeded, with the source and active model preserved.
The next failed read requested attribute 19 of the source-correlated Program
object (`0x68`); that attribute was unavailable. Later Controller reads also
returned unsupported fields. The SDK then reported `LgxSrv_E_FATAL_ERROR`,
despite an import log containing zero warnings and zero errors. These reads do
not establish the fatal error's cause. No active edit-write or commit was
observed, and the remaining native edit boundary is unresolved. Testing stopped
after this fatal result. The SDK service subsequently stopped, and the probe's
bounded cleanup did not complete: its report remains `incomplete`, with native
cleanup unconfirmed. Explicitly stopping the isolated emulator endpoint cleared
the lingering connection before its original address and the normal endpoint
were restored. Both application instances and source/model state were retained.
No automatic SDK-service restart or repeated edit attempt followed. Further SDK
testing requires a healthy SDK service.

Version `.79` supplies the source-bound [Program Disable field](edit-program-state.md).
An isolated native repeat read it successfully and verified 98 signed requests.
The first unavailable import read then targeted class `0x70`, instance `1`,
attribute `19`. Later Controller reads remained partial or unsupported, and the
SDK repeated `LgxSrv_E_FATAL_ERROR`. No active edit-write or commit was observed.
The report remains `incomplete`, with native cleanup unconfirmed. Explicit
emulator socket cleanup restored the main listener, and the original ACD and
modeled state were preserved. Native SDK testing was paused after this result;
source work and isolated protocol testing can continue without the SDK.

Version `.82` resumed SDK testing on the rebuilt runtime with source-bound Task
and Program-scoped Routine metadata. An isolated `AcceptEdits` attempt verifies
95 signed requests. The SDK returns `XMLSrv_E_IMPORT_ABORTED_NO_CHANGES` with
`RxCsE_ASA_ATTRIBUTE_LIST_ERROR` in its import log. The paired import trace
contains a Controller `0x8E/1` attribute-list read of attribute `31`, returned
unavailable (`0x14`, overall list status `0x0A`). That missing field is a concrete
next investigation point; the trace does not establish that supplying it would
complete an edit.

This attempt reports no fatal SDK exception. Native Go Offline and its readback
succeed, the project closes, and the endpoint's clients, lease and temporary
state clear. Source and model remain unchanged; no active edit-write or commit
is observed. The isolated application is stopped and the main listener restored.
This result does not establish that the earlier SDK fault is fixed. The helper
now stops further ordinary SDK calls after an observed fatal/server-faulted
exception and records native Offline confirmation separately from endpoint
cleanup.

Version `.83` supplies the source-bound [overflow-reporting setting](controller-overflow-setting.md).
An isolated native import successfully reads Controller attribute 31 and
advances to signed Controller `0x8E/1` service `0x55`, with no request payload.
The read-only endpoint denies that unresolved operation (`0x0F`); the SDK reports
`RxCsE_ASA_NO_PERMISSION`. This request is distinct from Symbol object `0x55`
enumeration. The repeat verifies 99 signed requests, reports no fatal SDK fault,
and confirms native Offline and endpoint cleanup with unchanged source/model.
Handler references and Controller Get Attributes All remain incomplete too.
No active edit acceptance, testing, assembly or commit is established.

On the rebuilt `.83` main instance, the separate `LeaveEdits` comparison
succeeds across 93 verified signed requests and confirms native Offline plus
endpoint cleanup. This is a local pending NOP import on the probe's private
ACD copy while online; it does not establish accepted controller edits. The
source ACD and emulated routines, task configuration, values and scan state
remain unchanged. The SDK project is closed without saving over the input.

Version `.84` adds [Program preparation reservations](program-reservations.md).
A private empty-success hypothesis for Controller `0x55` exposed the subsequent
Program Semaphore acquire and release. After implementing those backed
reservations, the isolated repeat advances to a denied Program attribute-27
UDI Stack Size write. It verifies 103 signed requests, confirms native Offline
and endpoint cleanup, and preserves source/model state with no reported fatal
SDK fault. The hypothetical Controller reply is absent from the `.84` public app;
this is conditional diagnostic evidence, not accepted-edit support.

Version `.85` adds a software [preparation phase](program-reservations.md#controller-preparation-and-zero-stack)
for the observed Controller open/close sequence. It retains ownership and Run
inhibition until closing, with no active edit state. A zero Program UDI-stack
proposal additionally requires a reserved Program and a complete source without
AOIs. Nonzero or unproven stack requirements remain unsupported. This advances
the preparation model; compiled routine storage, accepted controller edits,
Test/Untest and Assemble remain separate unfinished work.

The `.85` native attempt accepts this preparation and reaches an edit transfer:
a signed first fragment starts Program-scoped Executable `0x6D` service `0x5C`
with opaque ELF bytes. The current fragment receiver requires download
preparation and rejects the edit reservation. Controller acceptance still
fails. The case verifies 103 signed requests and reports
`RxCsE_ASA_NO_PERMISSION`; Go Offline returns `RxE_COMM_NOTOPEN`, leaving native
cleanup unconfirmed. Project close succeeds, endpoint cleanup completes and
source/model are unchanged, with no reported fatal SDK fault. Fresh main
connection/Offline and Run/Program cases subsequently pass.

The probe now reports plain outer CIP wrapper rejections separately from signed
inner operation failures, including fragment format, position and byte count.
These short rejection responses contain no MAC and are explicitly labeled
unauthenticated. Offline reanalysis of the retained trace does not rerun the SDK
or change the original result. The first denied fragment is the next transfer
implementation point; the compiled bytes have not been installed or executed.

Version `.86` adds a separate [compiled Routine receiver](edit-transfer.md).
The native attempt now delivers all 11 fragments of its 4,304-byte container;
the endpoint rejects installation after retaining the complete binary. Offline
reassembly matches its recorded SHA-256. The case verifies 111 signed requests,
preserves source/model state and clears endpoint storage. Native Go Offline
still returns `RxE_COMM_NOTOPEN`; project close succeeds and no fatal SDK
exception is reported. Native cleanup remains unconfirmed for the edit case.
Controller acceptance, active routine replacement, Test/Untest and Assemble
remain unfinished.
