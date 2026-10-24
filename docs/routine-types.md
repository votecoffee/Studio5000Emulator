# Original Routine Type words

Version `26.1023.212737` reports Executable class revision 11 for the native v35
L85E profile with a complete, unchanged ordinary RLL inventory, original Type
words and unprotected source keys. Both global and Program-scoped class reads
use that layout revision; global reads still withhold flattened instance counts.
Generic, partial, stale, edited and other source profiles keep the legacy
revision-1 layout. This class field is separate from instance attribute 1 (Type)
and does not grant programming authority or establish complete upload support.

Version `.129` exposes source-bound Executable (`0x6D`) instance attribute 1,
Type. The value comes from the original ACD. It is not generated from the
Routine's RLL, ST, FBD or SFC language name, and an L5X-only import does not
invent it.

## Source and manifests

The bounded native Routine reader already correlates original Program or AOI
parents, child IDs and readable names. It now retains the two-byte word at
offset 90 for the unprotected format-54, 371-byte body profile, after checking
its fixed storage headers. Other body layouts may still supply identities but
withhold Type. Program component type 256 and AOI component type 259 remain
separate namespaces.

The immutable Routine manifest adds an optional `type_word`. An absent field
remains unavailable, including in older manifests; no default is applied.
Supplied words must be integers from 0 through 65,535. Boolean, null, unknown
fields and invalid ranges reject the manifest. Existing original ACD/L5X hash,
parent, readable-source coverage and atomic load checks remain in force.

The importer and appliance already forward these native Routine manifests.
Reset preserves the binding; replacing the project without it clears it. The
API reports available Type counts through `native_routines` and
`native_aoi_routines`. The separate L5X Executable description model retains its
legacy attribute-7 scope.

## Read behavior

The read-only endpoint exposes Type only with current native Routine bindings
and a matching original Project identity. Program and AOI parents are required
for instance reads. Reused numeric child IDs cannot share another parent's
value. Class-instance revision and instance Type remain separate fields.

Both single and ordered attribute-list reads work through signed sessions.
Unknown or stale Type evidence stays unavailable; legacy descriptions do not
acquire a guessed Type. Setters and programming operations receive no additional
authority. Type words do not establish native machine code, debugger support,
protection semantics or the complete online-edit lifecycle.

## Offline framing

The shared capture and transfer decoders now frame two-byte Type values and
legacy counted descriptions for Executable instances. They require exactly one
numeric Program or AOI parent. Unscoped class reads and unsupported parent paths
are excluded from this instance schema. Reports retain the parent, field order,
duplicates, individual errors and partial suffixes; values remain omitted by
default. Truncated, oversized, unknown successful or trailing fields fail
framing rather than selecting guessed widths.

All 809 saved reference instance Type replies frame successfully. Seven
separate class-revision reads are excluded; their values are not Routine Types.
Captured values are not replayed into loaded projects.

## Validation and limits

A separate owned project containing RLL and ST routines was imported, saved as
ACD, closed, reopened and re-exported through the native SDK while Offline.
The RLL examples retain `0x07FF`; the ST example retains `0x07FC` at the same
source field. These are measured examples, not a language-to-Type mapping or an
interpretation of the word's bits. All seven Routine words across three owned
sources pass reader checks. The original demo and running model are preserved,
with no reported fatal SDK fault or physical-controller contact.

The isolated `.129` SDK upload accepts the first Type read and advances to a
22-field Routine metadata request. Type also succeeds in that request; the
other 21 fields, including Code Address, remain unavailable. The SDK still
reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`. Its complete trace retains 360
expanded leaf requests and all 408 source-matched diagnostic message fields;
the endpoint verifies 357 signed requests. Actual Offline, cleanup and unchanged
source/model are confirmed, with no reported fatal SDK fault.

The diagnostic candidate uses its own matching Template snapshot and private
clock hypotheses. These remain separate from the normal demo. Full native
upload/download, reconstructed Routine logic, Studio GUI monitoring and the
complete Test/Untest/Assemble lifecycle remain unfinished or unverified.

All 182 affected software checks pass; the full suite was not rerun.
The restarted normal demo passes 227 live readbacks and native SDK Go Online/Go
Offline across 75 verified signed requests, with actual Offline, cleanup and
unchanged source/model confirmed and no reported fatal SDK fault. The demo's
inputs and logic also match the saved state across the restart. All 91 deployed
app modules, served webpage, packaged assets and executable version match `.129`.
