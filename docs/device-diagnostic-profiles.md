# Empty device diagnostic profile discovery

Version `.127` adds source-bound empty Device Diagnostic Profile (`0x3B1`)
discovery. An explicit collection in the original ACD establishes availability;
absence from an L5X export does not. This is separate from the nonempty
[diagnostic message definitions](device-diagnostic-messages.md).

## Source and lifetime

The optional reader checks the bounded Comps.Dat database, active record extent,
component headers and logical paths. It requires exactly one controller-scoped,
format-0, component-type-0 collection with a 74-byte body and no active profile
definitions. Deleted records and allocation tails are excluded. Missing,
duplicate, scoped, nonempty or unknown layouts withhold this binding while
ordinary L5X conversion remains available.

The immutable manifest includes both original ACD and converted L5X hashes and
an explicit empty `profiles` list. It requires a matching original Project
identity and agrees with the other supplied native bindings. Invalid supplied
manifests reject the load before replacing the current model. Reset preserves
the binding; loading a project without it clears it. Older manifests do not
implicitly acquire an empty profile catalog.

The importer, application service and appliance import path use the same
binding. The connectivity API reports availability and count under
`native_diagnostic_profiles`, without copying source records into the webpage.

## Protocol behavior

- Controller-scoped Get Instance List (`0x4B`) returns an empty list for every
  cursor when the binding is current, including signed read-only sessions.
- Class attributes 2 and 3 report the proven maximum instance and instance
  count of zero, as 32-bit values.
- Class revision remains unavailable. Storage format and installed description
  filenames do not establish a runtime revision.
- Unbound instances, parent scopes, malformed payloads and configuration writes
  remain denied. Missing or stale source evidence returns an unavailable state.

This does not implement nonempty profile definitions or Device Diagnostic
Objects (`0x3B0`). The latter may include runtime hardware objects; an empty
source collection alone does not establish their runtime inventory.

## Validation and limits

Both owned test ACDs contain the explicit empty profile collection. A saved
successful v35 upload also contains a successful empty `0x3B1` list. The
emulator derives availability from its matching source rather than replaying
captured definitions. No physical-controller connection was initiated.

The isolated `.127` SDK upload accepts the new list and advances from
`RxCsE_UPLOAD_DEVICE_DIAGNOSTIC_PROFILE_FAILED` to
`RxCsE_UPLOAD_DEVICE_DIAGNOSTIC_OBJECTS_FAILED`. Its next rejected operation is
the `0x3B0` instance list, status `0x0F`. A complete trace retains 355 expanded
leaf requests, including all 408 successful source-matched diagnostic message
fields. The endpoint verifies 352 signed requests. Actual Offline and cleanup,
unchanged source and model, and no reported fatal SDK fault are confirmed.

The diagnostic project uses its own matching Template snapshot and private
clock hypotheses. These are not installed on the normal demo. Full native
upload/download, Routine reconstruction, Studio GUI monitoring and the complete
Test/Untest/Assemble lifecycle remain unfinished or unverified.

All 230 affected software checks pass; the full suite was not rerun.
