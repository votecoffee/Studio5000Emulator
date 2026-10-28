# Guarded Routine bulk metadata

Version `.134` adds [offline comparison diagnostics](routine-metadata-comparison.md)
for this reply shape. Matching nonidentity fields does not establish native
interpretation or source association; the isolated address-range trial does not
resolve the current upload failure.

Version `.131` extends the [ordinary RLL state model](routine-state.md) to the
four fields withheld in `.130`. Single and ordered bulk reads share the same
source, identity, fault-history, unchanged-logic and native-edit guards. This
completes the observed 22-field metadata shape for the narrow eligible profile;
it does not supply compiled Routine logic.

Version `26.1028.105723` extends these guards to [source-verified edited
routines](accepted-routine-source.md#current-state-metadata-after-edits), retaining
class revision 11 for the verified v35 inventory. Changed routines withhold the
original source-key field; their live state and header references remain available.

## Header references and flags

Executable attribute 8 is **Header Address**, as defined by the installed v35
Executable description. Earlier development notes labeled it UID while its
meaning was unresolved. Header Address is separate from Code Address (2) and
the older Executable UID field. The shared offline decoder already retained
its four-byte width.

The emulator uses its existing live Routine object registry for this address.
The main Routine's address is the same reference exposed by its Program's
main-Routine field. Other routines have distinct references; reused child IDs
under different Programs do not share objects. Repeated reads are stable while
the object lives. Reset or replacement revokes the old reference. A foreign
project, missing object or exhausted address space cannot produce a guessed
address. These references grant no native memory or code-execution service.

Executable Flags (24) uses the observed ordinary RLL relationship: main Routine
`0`, other Program routines `2`. No other flag bits are modeled. All 20 saved
Program main references match the corresponding Routine header and zero flags;
the other 688 saved Program routines have flags `2`. These checks establish the
narrow relationship, not the meanings of every flag or other Routine kinds.

## Original source-key metadata

The native reader retains the opaque 66-byte blob from the validated
unprotected format-54/body-371 storage profile when its count and format prefix
match. It does not decrypt or generate a source key. Another layout, count or
format withholds this field while retaining independently known identities.
All 809 saved replies have the same bounded count and format prefix, with
per-routine blob contents. Captured contents are not replayed into projects.

The optional manifest field `source_key_hex` carries original bytes between
the importer and emulator. It requires the validated Type profile, exact length,
lowercase hexadecimal and supported prefix. Absent fields in older manifests
stay absent. Routine objects are immutable, omit the blob from their ordinary
representation, and report availability counts without blob contents. The
status API does not return these bytes. The read-only field (22) requires the
matching original Project identity, untouched Routine source and guarded Program
RLL state. AOI bindings
can retain the metadata but do not gain this Program-specific read behavior.

## Unsigned model state

Signature Types (28) is zero only for a canonical complete ordinary RLL source
without signature markers. Unknown Routine attributes and signature elements,
attributes or namespace variants withhold that proof. Source-hash checks and
the other runtime guards still apply. Reset retains the source proof; changed
logic and uncertain faults withhold the field until the normal reset/reload
conditions are met.

This represents the emulator's unsigned ordinary RLL model. It does not verify,
generate, import or bypass native safety or source-protection signatures.
Readable source alone does not enable the field outside the canonical profile.
The new reads grant no setter or Test/Untest/Assemble authority.

## Validation boundary

Focused checks exercise original blob preservation, compressed/raw ACD members,
old and malformed manifests, both parent namespaces, hidden values, source
changes, live object lifetime, native edit reservations and unsigned-source
ambiguity. The original demo and separate owned diagnostic project retain their
original bytes. Native acceptance results are recorded in the
[connectivity history](connectivity-history.md).

All 227 affected checks pass; the full suite was not rerun. The isolated native
SDK upload receives the complete 22-field reply with zero statuses, including
the header reference matching its earlier Program main reference and blob bytes
matching the original ACD. It still reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`
without further Routine requests. Actual Offline/cleanup and unchanged
source/model are confirmed, with no reported fatal SDK fault. Successful field
statuses do not establish native client interpretation or Routine acceptance.
The restarted release passes 273 live checks. The webpage, packaged assets,
executable version and all 92 deployed app modules match `.131`.
Native SDK Go Online/Go Offline passes across 75 verified signed requests, with
actual Offline/cleanup, unchanged source/model and no reported fatal SDK fault.
Demo inputs, logic and edit configuration match across the restart.

Full native upload/download, reconstructed Routine logic, Studio GUI monitoring
and the complete native edit lifecycle remain unfinished or unverified.
