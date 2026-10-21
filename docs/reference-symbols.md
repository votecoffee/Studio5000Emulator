# Program and Task reference symbols

Version `.124` exposes selected original ACD reference Symbols through the
root Symbol (`0x6B`) catalog. These describe supported interpreter Programs and
Tasks. They are separate from readable and writable tag values.

## Source binding

The ACD auxiliary-symbol reader retains an optional explicit data name from
root, format-63, component-256 records with the known fixed layout. Only
`Program:<name>` and `Task:<name>` names are recognized. The original native
Symbol ID is retained; no ID or target is inferred from its hash-style name.

Public references require matching ACD/L5X hashes, native Project identity,
native Program and Task bindings, and complete source configuration. Eligible
targets are ordinary Standard nonfolder Programs and Standard Continuous or
Periodic Tasks. Safety, folder, event and opaque kinds stay unavailable.
All eligible targets must have their own reference. Unknown targets, duplicate
references and root tag-ID/name collisions fail validation. Legacy auxiliary
manifests without explicit data names retain their previous behavior.

The reference catalog and its descriptors are immutable. Discovery checks
current source bindings, original IDs and target kinds. Stale or replaced
bindings withhold discovery. Loading a project without these bindings clears
the catalog. Other auxiliary records remain private comparison metadata.

## Symbol attributes and object backing

| Attribute | Supported value |
| --- | --- |
| `1` | Original explicit Program/Task data name |
| `2` | `0x1068` for Program, `0x1070` for Task |
| `3` | Reference to the current interpreter target |
| `5` | Separate reference to the immutable Symbol descriptor |
| `6`, `7`, `8` | Null/zero storage size and dimensions |
| `9` | Standard memory class |
| `10`, `11` | Zero access/constant metadata for these references |
| `12` | `0xFFFF` no-Data-Table sentinel, encoded as a DWORD |
| `14` | Null signature |

The values in `3` and `5` resolve within the emulator's
[runtime object address space](runtime-object-references.md). They are aligned
DWORD references with distinct target and descriptor identities. The Program
target address equals that Program's attribute `16`. Reset or engine replacement
revokes prior references. Physical addresses and compiled controller code are
never imported.

Instance lists, attribute lists, single reads and cursor-based enumeration
include these Symbols at their original IDs. Program-scoped ordinary tag
catalogs retain their scope. The references have no Data Table entries, tag
storage, fabricated Template definitions or tag read/write behavior. Metadata
does not grant execution or memory-access authority.

The API reports the bound counts and scope under `native_reference_symbols`.

## Evidence and limits

Offline analysis of a saved successful v35 upload found 20 Program and two Task
reference Symbols using these type codes. Every Program target address matched
the corresponding Program-address set. All 22 used the no-Data-Table sentinel
and the observed null/zero storage fields. The implementation derives addresses
from current interpreter objects; captured physical addresses are not replayed.

The final isolated `.124` SDK upload reads the two source reference Symbols and
all 22 requested Program fields, then requests Program-scoped Data Table
discovery. The `.123` comparison did not make that scoped request. Full upload
still reports `RxCsE_UPLOAD_OF_PROGRAMS_FAILED`, across 206 verified signed
requests. The empty scoped table reply succeeds; that does not identify the
remaining reconstruction failure. Offline, cleanup and unchanged source/model
are confirmed, with no reported fatal SDK fault.

The isolated diagnostic uses an owned project, its source-bound Template
snapshot and unshipped clock/revision hypotheses. The release retains its prior
clock behavior. This experiment does not establish full native upload/download,
SDK tag-address discovery, Test/Untest/Assemble acceptance or Studio GUI
monitoring.

Focused checks cover source parsing, metadata framing, real object resolution,
reset, stale bindings, unsupported kinds, scope, enumeration and denied value
access. The independent signed TCP inventory reader preserves both reference
descriptors without attempting value reads or adding storage tables.

The restarted released `.124` demo passes SDK Go Online/Go Offline across 75
verified signed requests, with Offline/cleanup, unchanged source/model and no
reported fatal SDK fault. All 292 affected software checks and 47 live readback
checks pass. The full suite was not rerun. The deployed 88 app modules, webpage,
packaged assets and Windows executable version match the source.

Two unrelated fixed-array storage assertions and a null Template-code decoder
assertion were corrected after reproducing their failures on `.123`. Existing
array storage and null-code decoding behavior is unchanged. The decoder check
now verifies that a nonnull code reference stops before definition reads.
