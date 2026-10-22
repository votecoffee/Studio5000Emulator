# Remote Run and Program

Version `0.6.0-connectivity.74` gives the emulator one shared controller mode.
Version `.75` adds [Run-entry prescan and first-scan initialization](run-entry.md).
The application owns continuous scanning. The webpage's **Run** and **Program**
buttons and supported native Studio requests use the same mode operation.
Closing a page, Go Offline, disconnecting a client or stopping EtherNet/IP
leaves a running simulation running. **Program**, reset, project replacement,
execution-scope replacement and application shutdown stop it. Restart starts
in Program. Program retains tag values; entering Run applies the bounded prescan
rules, which can reset non-retentive values or execute AOI initialization.

## Status and controls

`/api/state`, `observe` and `snapshot` expose a `controller` object separately
from the execution scope's existing `mode` (`project` or `routine`):

```json
{"mode":"Program","running":false,"keyswitch":"Remote","scan_interval_ms":10,"prescan_count":0,"first_scan_pending":true}
```

The authenticated local action `POST /api/controller-mode` accepts
`{"mode":"Run","dt":10}` or `{"mode":"Program"}`. Omitted `dt` retains the
current interval. Periodic project execution must use the imported task rate;
continuous tasks and routine harnesses default to 10 ms. Intervals must be
integers from 1 through 60000 ms. One worker serializes scans, tag changes and
mode changes under the application lock. It waits between scans without holding
that lock and does not issue catch-up bursts after a slow scan. Manual Step is
available in Program. Cached external Device I/O monitoring remains separate.

The native compatibility identity advertises a virtual **Remote** keyswitch.
Status attribute `5` is `0x3070` in Program and `0x3060` in Run; a scan fault
stops execution and reports `0x3450` (Faulted, recoverable major fault). Single,
list, all-attribute and discovery replies use the same status source. The
`native_session` API reports the current mode, keyswitch and the separate
`controller_mode_requests` capability. The legacy `read_only` setting still
describes tag/project writes; it does not prohibit this explicit mode control.

Rockwell's [ControllerDevice Status documentation](https://www.rockwellautomation.com/en-no/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-controllerdevice-object.html)
describes the mode, fault and keyswitch bits. Native requests were observed
using the public SDK against the emulator; vendor binaries are not inspected
or distributed.

## Native request boundary

| Operation | Target | Payload | Effect |
| --- | --- | --- | --- |
| Start (`0x06`) | Controller `0x8E`, instance `1` | Empty | Request Run |
| Stop (`0x07`) | Controller `0x8E`, instance `1` | Empty | Request Program |

Both require a bound native context, verified request MAC/counter, current
source-bound ACD correlation and that context's coordination lease. Paths must
have no attribute, symbolic or nested scope segments. Unsupported modes,
extra data, wrong targets and missing ownership are rejected. Replays and stale
project generations follow the existing session guards. The lease alone still
grants no mode-change authority: these two services are explicit exceptions.
Native tag setters, project transfer, online edits and Test mode remain denied.
The anonymous compatibility context does not authenticate an operator.

Execution blockers, a scan fault, import or a live programming inhibit prevent
Run. A scan fault retains the engine's existing rollback behavior and stops the
worker. Reset clears it. Setting Run Mode Inhibit also switches to Program;
release or expiry clears the inhibit without restarting scans. Program can be
requested while inhibited.

## Validation and limits

The optional [native SDK probe](development.md) has an explicit `--operation
modes` case. It verifies SDK Run advances actual scan count, SDK Program freezes
it, webpage API Run/Program reads back through the SDK, and final Program/Offline
cleanup. It preserves the ACD and retains the resulting emulated values and scan
history; use a private demonstration project. Other probe operations do not
request mode changes and still require unchanged modeled state.

These checks establish the tested SDK/model exchange. Studio GUI monitoring
and the complete native controller mode-transition contract remain unverified.
This is a software execution control, not a safety function or physical I/O
mode implementation.

The rebuilt `.153` mode probe passes across 108 verified requests with the v35
Controller/Time Sync schema selections. It verifies SDK Run/Program scan control,
webpage mode readback through the SDK, one prescan per Run entry, no repeated
prescan for an already active Run request and six expected audit updates.
Offline/cleanup is confirmed, the original ACD is unchanged and no SDK fault is
reported. The test intentionally advances the model; afterward the original
demo is reloaded into stopped Program mode with zero scans and audit updates.

The `.74` milestone below predates the expanded `.75` mode probe.
The rebuilt `.74` runtime passes all 291 live protocol checks. The 987-test
behavioral suite passes on Windows (985 passed, two platform skips) and Linux
(986 passed, one platform skip). The deployed native acceptance results are:

| Probe | Result | Verified signed requests |
| --- | --- | --- |
| Connection | Nine connection/Offline steps pass | 81 |
| Remote modes | Fourteen steps pass, including both control directions | 101 |
| Online tag reads | Still fail `RxDA_E_NO_ONLINE_ADDRESS` | 83 |
| Upload | Still fails `RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED` | 199 |
| Download | Still fails `RxCsE_DOWNLOAD_OF_DEVICES_FAILED` | 181 |

The mode probe observed 30 additional scans after SDK Run and a stable scan
count after SDK Program. Webpage API Run and Program became visible through
the SDK in approximately 0.7 and 0.5 seconds. The SDK caches this status between
its background polls; the probe waits up to eight seconds for readback rather
than assuming an immediate synchronous update. A first immediate-read attempt
exposed that delay and was retained as failed evidence before the bounded-poll
test passed. No runtime workaround or acknowledgement without execution was
added for that test.

The webpage also displayed **REMOTE RUN**, **Program** and disabled Step while
the shared worker ran. Closing that temporary test tab left scans advancing;
the final Program request stopped them. Every probe confirms Offline/TCP/lease
cleanup, and the ACD remains byte-identical. Transfer probes preserve modeled
state; the explicit mode test retains its executed scans and values. The live
application modules, served browser assets and rebuilt executable's embedded
browser assets were checked against source. FactoryTalk Linx and the SDK service
remain running. Final controller state is Remote Program.
