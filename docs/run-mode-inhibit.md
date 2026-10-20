# Native Run Mode Inhibit

Version `0.6.0-connectivity.61` implements a temporary software scan inhibit for
the owner of a [native coordination lease](programming-coordination.md). The v35
SDK writes Controller attribute `7` during download preparation. This revision
accepts that bounded write and advances to the next unsupported Controller
service, `0x60`. Complete download remains unfinished.

## Supported contract

The target is Controller class `0x8E`, instance `1`, with no attribute or
symbolic segment in the path. A registered, bound native context, valid signed
MAC/counter, current source-bound ACD correlation and ownership of the lease
are required.

| Operation | Payload or value | Behavior |
| --- | --- | --- |
| Set Attributes List (`0x04`) | Exactly one entry: attribute `7`, UINT `0` or `1` | Clear or set the owning lease's temporary inhibit |
| Get Attribute Single (`0x0E`) | Attribute `7` | Read the current UINT mask |
| Get Attributes List (`0x03`) | Attribute `7` among requested fields | Read the same mask with per-field status |

Set Attributes List returns one successful attribute result. Unknown mask bits,
truncated or trailing data, mixed lists, unsigned setters and unrecognized setter
forms retain errors. Another context cannot change the owner's inhibit.

The default mask is zero. Source replacement, reset, endpoint shutdown, context
replacement/invalidation, disconnect, lease release and native-context expiry
remove the temporary mask. Repeated acquisition by the same owner preserves
it. No source XML, tag value, Change Log identifier or controller mode changes.
Native tag setters and project transfer remain disabled; the native read-only
setting permits this specific coordination operation.

## Simulation behavior

The shared application scan entry point rejects scans while inhibited, before
draining queued Device I/O inputs or changing scan time or model memory. Cached
external monitoring remains available. Queued inputs retain their normal expiry
rules and can apply at a later scan after the inhibit clears.

The webpage shows **SCANS INHIBITED**, disables Step/Run, stops its run loop and
explains that the owning client must clear/release or disconnect. Connectivity
reports `run_mode_inhibit`, `scan_inhibited` and the owner-scoped rejection reason.
The API exposes no operator identity, keys or context tokens.

This is a software scan guard, not a hardware run-inhibit input or a safety
function. The native compatibility profile still reports Program mode. It does
not authorize native Run mode, online edits or project replacement.

## Validation and next gap

Seven added tests cover exact single/list readback, mask and framing errors,
source and ownership guards, signed batches, independent clients, retained
write denials, queued device inputs, reset, bad MACs and cleanup. The 845-test
suite passes on Windows and Linux, with two Windows skips and one Linux skip.

An isolated final-source native download probe verifies 104 signed requests. It
accepts the Run Mode Inhibit write, fails `RxCsE_ASA_NO_PERMISSION` at Controller
service `0x60`, then releases the lease and confirms Offline cleanup. Source
bytes, modeled values and scan count are preserved.

Private substitutions for `0x60` and Download In Progress (attribute `26`) left
the SDK polling until bounded timeouts. Those substitutions and an unverified
begin/abort prototype are not shipped. The service response and status contract
remain unresolved; neither zero nor a nonzero trial establishes completion.
Resolve that contract before adding validated transfer staging, atomic commit
and rollback. The installed plain v35 Controller definition identifies attribute
`7` as a UINT Run Mode Inhibit; vendor definitions and private traces are not
distributed.
