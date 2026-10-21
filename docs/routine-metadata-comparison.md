# Routine metadata comparison diagnostics

Version `.134` adds a shared description of the observed 22-field Executable
bulk reply to the [capture inspector and transfer analyzer](native-transfer-diagnostics.md).
It helps distinguish a changed field or missing reply from a native client
failure that occurs after successfully reading the fields.

## Reported evidence

`tools.routine_metadata_profile.describe()` accepts the exact observed request
order and a nonzero Routine path instance. It delegates framing to the shared
collection decoder, including partial prefixes, per-field errors, count/order
checks and exact response extents. The callers require one valid Program or AOI
parent and a Routine instance; unrelated scopes and other attribute requests do
not acquire a bulk profile.

The resulting `routine_bulk_profile` reports:

- Successful, failed and unreturned field numbers, and whether all 22 returned
  successfully.
- Whether Code Address is zero, Header Address is nonzero, and the returned
  Executable Instance matches the request path.
- How many edit-buffer fields contain zero bytes; the all-zero result stays
  unknown until all 12 fields are available.
- The source-key byte count and whether its framing matches the observed
  66-byte format, without returning blob contents.
- Literal zero checks for the protection, executable-flags and signature fields.
  These are byte observations, not native lifecycle or signature verification.

Partial and failed fields stay unknown. Missing data does not become zero.
An observed source-key format does not verify its meaning, decryptability or
association with a project.

## Comparable fields

Complete replies also receive `nonidentity_fields_sha256`, calculated over
ordered field numbers, widths and value hashes. It excludes only Header Address
(8), Executable Instance (9) and opaque source-key metadata (22), which differ
between objects. Type, Code Address, edit-buffer fields, flags and other fields
remain in the comparison. The fingerprint is unavailable for incomplete replies.

A matching fingerprint establishes equality of that subset. It does not compare
the excluded fields, authenticate a capture, bind code to a project or establish
native client acceptance. Original IDs, addresses, names, source-key contents
and payload bytes remain omitted from the profile. Existing explicit private
payload options retain their separate behavior.

## Reference and native trials

All 809 saved successful Routine bulk replies produce complete profiles. They
form two nonidentity groups, with 121 and 688 replies respectively. Every reply
has a null Code Address, a nonzero Header Address, an Executable Instance matching
its request path, zero edit-buffer fields and the observed source-key format.
The saved capture's MAC integrity remains unverified.

Two isolated `.133` SDK trials use the same owned source, matching Template
snapshot and diagnostic clock settings. The control uses the existing virtual
reference allocator; the other changes only its starting address range. The
native traces confirm that the header references differ and that both complete
Routine replies match an observed nonidentity reference profile. Both trials
still fail with `RxCsE_UPLOAD_OF_PROGRAMS_FAILED` before any `0x3A` source request.
They retain 357/358 verified signed requests and 360/361 expanded leaf requests.

Actual Offline/cleanup, unchanged source/model and no reported fatal SDK fault
are confirmed for both trials. The address-range hypothesis is not shipped;
no physical controller was contacted. A separate nonzero Code Address trial was
not run because all saved successful examples use zero.

The current failure remains before source retrieval. Full native upload/download,
source reconstruction and the complete native edit lifecycle remain unfinished.
These diagnostics improve comparison evidence and do not change live dispatch.

All 162 affected software tests pass, including profile privacy, incomplete and
failed fields, identity-independent comparison, changed state fields, malformed
frames and both scoped capture/checkpoint readers. The full suite was not rerun.

The restarted `.134` release passes 12 focused deployment checks. All 94 app
modules match the build, and the webpage, packaged assets and Windows executable
versions match. Native SDK Go Online/Go Offline passes across 75 verified signed
requests, with actual Offline/cleanup, unchanged source/model and no reported
fatal SDK fault. Inputs, logic and edit settings match across the restart.
