# Empty simulator component tracking

Version `.160` adds an explicit empty component-tracking profile for ordinary
v35 L85E source. Native Controller attributes 33 and 34 each return 32 zero
bytes for the modeled active and test groups, which both contain no members.
These are emulator-owned empty-group values. They do not import, compute or
verify the original controller's signatures.

## Source and model limits

Rockwell's [System Security reference, Component Change Detection](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/secure-rm001_-en-p.pdf)
describes tracking selected components and combining their signatures. The
[Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
defines `TrackingGroups` declarations on trackable components. The installed
v35 Controller schema identifies attributes 33/34 and their 32-byte widths.
An observed successful v35 reference returns zero arrays for both fields;
that observation does not establish a nonempty signature algorithm.

An offline SDK import/save/reopen/export test did not retain a routine's
`TrackingGroups="1"` marker. The test confirms that absence in the converted
L5X cannot prove native ACD membership. This app therefore explicitly selects
an empty **simulator** group when supported source has no affirmative tracking
declarations. Its API reports `native_membership_imported=false`,
`native_signatures_imported=false` and
`absence_proves_native_membership=false`. Do not use these values to verify an
ACD's native tracking state or code integrity.

The profile requires complete unprotected v35 L85E source, no AOI definitions
or external I/O map, ordinary Programs with explicit `TestEdits=false`, and no
signature/protection/ambiguous tracking declarations. Explicit canonical
`TrackingGroups="0"` on a recognized trackable component is accepted. Nonzero,
malformed, case, namespace, shadow and unknown tracking declarations leave
the fields unavailable. Nonempty tracking groups remain unsupported.

Native reads additionally require matching L5X identity binding, project-mode
execution, clean simulator fault history, no blocked execution or active call
frames, and no programming scan inhibit. The research profile retains its
unavailable statuses. The API's `controller_component_tracking` reports the
selected policy separately from current read availability.

Scans, tag values and untracked supported Routine replacements do not change
an empty group's values. Reset/load reevaluates the policy. No membership writes,
nonempty hash calculation, signature verification or Tracked State Value Get
MSG service is implemented. Attribute writes remain denied.

## Validation

All 187 affected checks pass, including mixed/duplicate signed reads, policy and
binding guards, fault/reset behavior, write denial and Routine replacement
preservation. Native upload acceptance is assessed separately from these checks.

The milestone regression runs 1,832 tests: 1,830 pass, with two Linux-only
listener checks skipped on Windows. Two older assertions were updated to check
the established Program source-binding guard and aligned Template read extent.

Live signed reads on the rebuilt `.160` appliance return all 21 fields of the
tested Controller list successfully, including both empty tracking values.
Single, duplicate and mixed reads and write denials preserve source, execution
and audit state. Source, executable, served browser assets and appliance module
hashes match; all three application surfaces report `.160`.

Native SDK Go Online/Offline succeeds across 74 verified requests. An owned
same-project fixture with an empty Routine catalog now completes `UploadAsync`
across 971 verified requests on the unmodified public runtime. Its source/model
are preserved, actual Offline/cleanup is confirmed, and no SDK fault is reported.
The saved trace does not retain the full successful transfer checkpoint, so
complete transfer framing analysis is unavailable for that case. This proves
the tested API operation only: it does not establish reconstruction into a new
project, a valid saved uploaded ACD, or normal Routine upload. No upload save
was attempted.

The normal demo still reports Program/Routine upload failure after 348 verified
requests, with no endpoint attribute gaps in that transfer interval. Download
verifies 175 requests and prepares 904 temporary records, retaining 242 Templates
and allocating 16 tables, then fails at the result query without an active image
commit. Supported Program-mode Routine import and reconnect succeed across 188
requests, preserve the empty tracking policy and record one expected revision/
audit update. These cases also confirm actual Offline/cleanup, original-file
preservation and no reported SDK fault. The original demo is restored afterward
to stopped Program mode with zero scan, revision and audit state. The full
Test/Untest/Assemble lifecycle remains unfinished.
