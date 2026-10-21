# Device diagnostic message definitions

Version `.126` exposes original device diagnostic message definitions through
controller-scoped class `0x3B2`. The definitions come from the loaded project's
ACD. The application contains no bundled vendor message catalog.

These definitions describe message IDs, codes and revisions. They do not
generate faults or events, acknowledge alarms, supply active diagnostic status
or change the execution model.

## Source import

The optional ACD reader accepts the bounded Comps.Dat format-0 profile with
270-byte definition bodies, component type 256 and an explicit 74-byte
collection record. It retains each original logical instance ID and reads the
fixed definition data area: a 40-byte ID field, a 128-byte code field and a
UINT revision. Strings have explicit byte counts and checked unused padding.
The data-area extent and component-name/ID agreement are validated.

Compressed and uncompressed containers share bounds on stream size, expanded
size, record count and definition count. Duplicate identities, unknown layouts,
scoped definitions, invalid strings and malformed records withhold the binding.
Deleted records and records beyond the database's active extent do not become
current definitions. An absent or unsupported collection is not reported empty.

The immutable manifest carries ACD/L5X hashes and the complete definitions. ACD
conversion forwards it through the same application service used by the local
appliance. Missing original Project identity leaves diagnostic metadata
unavailable while preserving ordinary offline conversion. Explicit supplied
manifests require matching Project and other native bindings before the model
is replaced. Loading a project without a diagnostic manifest clears the prior
catalog; reset preserves the same source-bound definitions.

## Read-only protocol

| Target | Supported reads |
| --- | --- |
| Class instance `0` | Model revision `1`, maximum original instance and visible count |
| Original definition instance | Message ID (`1`), Message Code (`2`), Message Revision (`3`) |
| Instance list `0x4B` | Ordered original IDs, starting cursor, bounded partial pages |

String attributes use one-byte counts followed by unpadded ASCII bytes. The
revision uses a little-endian UINT. Single reads and attribute lists preserve
order, duplicates and per-field unsupported statuses. Unknown instances retain
errors. The list service requires an instance cursor and no attribute or payload.

Reads require the current source hash and matching original Project identity.
Missing or stale bindings return unavailable status. Program, symbolic and
mixed parent scopes remain unsupported. Configuration writes and other
unimplemented services retain errors, including under the signed read-only
session policy.

The API reports count and scope through `native_diagnostics`. It does not copy
the definition strings into ordinary status summaries or tag-value storage.

## Shared offline framing

Capture and transfer-checkpoint readers frame the three instance attributes
with the same bounded decoder. Successful fields retain byte counts and hashes;
payload values require the existing explicit opt-in. Invalid count fields,
truncation, unknown successful attributes and trailing data remain errors.
Instance-zero class metadata is not decoded using the definition layout.

## Evidence and limits

The installed plain v35 attribute definitions identify the counted-string and
UINT fields. Independently reading each owned ACD yields 136 definitions whose
three fields match all 136 corresponding replies in the saved successful v35
upload. The endpoint derives the fields from its own matching ACD; physical
capture values are not replayed. Vendor attribute files, native ACDs, message
catalogs and captures are not distributed in this repository.

The isolated SDK upload advances past diagnostic message collection and reports
a device diagnostic profile failure. The first attempt also exceeded the old
trace event limit, so its incomplete checkpoint report is retained as incomplete.
The expanded trace remains bounded and does not convert lost evidence into a
successful analysis.

The final `.126` attempt retains a complete trace and successfully reads all
three fields on all 136 definitions. Each returned field hash agrees with the
definition read from the matching ACD. It reports
`RxCsE_UPLOAD_DEVICE_DIAGNOSTIC_PROFILE_FAILED` after the next class `0x3B1`
list is rejected with status `0x0F`. Across 352 native verified signed requests,
Offline/cleanup and unchanged source/model are confirmed, with no reported fatal
SDK fault. The complete analyzer report contains 355 expanded leaf requests;
that count measures a different layer.

The isolated diagnostic uses an owned project, a matching Template snapshot and
unshipped clock/revision hypotheses. The released clock behavior stays unchanged.
This does not establish a completed native upload/download, reconstructed
Routine logic, Studio GUI monitoring or the full Test/Untest/Assemble lifecycle.

The restarted released `.126` demo passes SDK Go Online/Go Offline across 75
verified signed requests, with Offline/cleanup, unchanged source/model and no
reported fatal SDK fault. All 221 focused software checks and 204 live readback
checks pass, including all deployed diagnostic definitions. The full suite was
not rerun. The deployed 89 app modules, webpage, packaged assets and Windows
executable version match the source.
