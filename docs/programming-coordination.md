# Native programming coordination

Version `.64` adds [owner-scoped preparation](programming-preparation.md) to
this lease. Transfer, commit and online edits remain unsupported.

Version `.61` adds [Run Mode Inhibit](run-mode-inhibit.md), a temporary scan
guard owned by this lease. The notes below record the `.60` coordination
milestone and its then-current limits.

Version `0.6.0-connectivity.60` adds a software coordination lease for the
Semaphore requests sent by the v35 native SDK during download preparation.
It also exposes the supported Local controller's source-backed link address.
These operations advance preparation; project transfer remains unimplemented.

## Semaphore namespace and services

The live path parser preserves Controller `0x8E`, instance `1` / Semaphore
`0x74`, instance `1` as a child object with `controller_instance: 1`. Arbitrary
child classes, missing instances, mixed scopes and deeper nesting retain errors.
Global Semaphore class instance `0` and its Controller-scoped equivalent expose
software revision `1` as a UINT through single and list reads. Other class
fields and firmware ownership attributes are not implemented.

The coordination operations require a registered, bound native context, valid
signed framing/MAC/counter, and the exact child path without symbols or an
attribute segment:

| Service | Request payload | Software behavior |
| --- | --- | --- |
| `0x4B` | Exactly one zero byte | Acquire the exclusive coordination lease |
| `0x4C` | Empty | Release the caller's lease; repeated cleanup is harmless |

Acquisition also requires ACD correlation whose L5X hash matches the loaded
source. Success returns an empty CIP service payload. An existing owner's
repeated acquisition succeeds. Another live context receives `0x0C` on
acquisition and `0x0F` if it attempts to release the owner's lease.

Ownership uses the native context object, not an IP, operator name or reusable
session number. It ends on explicit release, TCP close/unregister, context
replacement or invalidation, project replacement, endpoint shutdown, or expiry
of the owning native context. Signed activity retains the existing native idle
deadline. A stale context cannot reserve the lease against another client.

This is an emulator coordination policy checked against the SDK's request and
cleanup behavior. No successful physical download reference establishes all
firmware Semaphore semantics. The lease grants no tag-write, project-transfer
or online-edit permission. Supported Remote Run/Program requests use the
separate [controller-mode checks](controller-mode.md).

Version `.84` adds subordinate [Program preparation reservations](program-reservations.md)
under the Controller's edit-purpose lease. They preserve the Program parent,
require the bound owner and original source pair, and block Run until released.
They retain zero active edits and are discarded with their owning lease.

## Local controller link address

The I/O Map root namespace, class `0x69`, instance `1`, exposes only attribute
`10` as a four-byte UDINT when original complete source contains the supported
matching Local L85E controller module and an unambiguous ICP port:

- Parent module `Local`, parent port `1`.
- One direct `Ports` section and one port with ID `1`.
- Port type `ICP`, address `0`, upstream `false`.
- The existing no-external-I/O, force-data and protected/ambiguous-source checks.

The supported endpoint's backplane route is slot zero. Missing, ambiguous or
unsupported route data withholds the field; another slot is not silently
substituted. Plain empty `Modules` source does not supply a Local address.
Reloading source recomputes availability. The field is a logical link address,
not a tag address or physical-controller memory pointer.

Unknown root fields receive per-attribute `0x14`; unrelated instances remain
unknown. Full module inventory, status, Map storage/linking, I/O connections and
I/O execution remain unsupported. The external-module catalog is unchanged.

## Diagnostics and validation

`native_programming_lease` reports availability, occupied/free state, remaining
native-context lifetime and explicit unsupported authorities. It contains no
operator identity, keys or context tokens. Connectivity displays the transfer
lock state and states that project transfer is unsupported. Numeric Controller
parent scope is retained in attribute gaps and native rejection summaries.

Thirteen added tests cover source route guards and exact widths, unsigned and
malformed requests, independent signed clients, competing ownership, signed
batches, retained project-write denials, expiry, disconnects, bad MACs, source
replacement and endpoint shutdown. The 838-test suite passes on Windows and
Linux, with two Windows skips and one Linux skip.

An isolated normal-source native download probe verifies 103 signed requests.
It acquires the lease, accepts the Local link-address read, reaches a Set
Attributes List request for Controller Run Mode Inhibit (attribute `7`), and
then fails `RxCsE_ASA_NO_PERMISSION` under the existing read-only policy. The
SDK releases its lease and confirms Offline cleanup. Model values, scan count
and original ACD bytes are preserved. This advances past the earlier
`RxCsE_ASA_INVALID_IOI_SEGMENT_TYPE` and intermediate unknown-destination errors;
it does not complete a download.

The rebuilt and restarted `.60` appliance passes 259 wire checks. The packaged
version and web assets, deployed source hashes and served webpage match source.
The deployed SDK connection probe passes all nine steps with 81 verified signed
requests. Two tag reads still fail before sending tag-read packets, with
`RxDA_E_NO_ONLINE_ADDRESS` across 83 verified requests. Upload still fails
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED` across 197 verified requests;
it retains 12 scalar reads and 12 Symbol descriptors.

The fresh deployed download probe repeats the 103-request preparation sequence,
including successful acquisition, link-address read and release around the
denied Run Mode Inhibit write. Its final state is Offline, client connections
close, and the lease is free. All four probes preserve source bytes, modeled
values, scan count and scan time. Both application write gates remain disabled;
Windows services are not reconfigured.

The installed plain v35 Controller, I/O Map and Semaphore definitions identify
the attribute names and widths. Vendor definitions, SDK binaries, ACDs and
private traces are not distributed. The next programming phase needs modeled
Run Mode Inhibit handling, transfer staging/validation and atomic commit or
rollback, with explicit limits on mode changes and online edits.
