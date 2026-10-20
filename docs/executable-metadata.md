# Source-backed Executable metadata

`source/logixlab/executable_configuration.py` captures ordinary Program Routine
declarations and an explicitly limited legacy Executable description read.
It supplies no native instance IDs: the source-bound native Routine inventory
must independently bind each Program/Routine name before a Router exposes it.

```python
configuration = ExecutableConfiguration.from_source(root, controller, source_sha256)
programs = configuration.program_names
routines = configuration.routine_names("MainProgram", source_sha256=source_sha256)
attributes = configuration.attributes("MainProgram", "MainRoutine",
                                      source_sha256=source_sha256)
```

The input must be a complete, unambiguous v35 controller export. Program and
Routine names retain their original spelling and source order; matching is
case insensitive within the proper Program namespace. Ambiguous names,
case/namespace aliases, nested or repeated declaration containers and context
exports withhold the global inventory. Snapshots and their nested maps are
immutable, and a different source hash withholds all readback.

Only ordinary Programs and Routines with visible, matching `RLLContent`,
`STContent`, `FBDContent` or `SFCContent` are eligible. Protection markers,
unknown classes/languages, missing bodies and multiple bodies withhold the
whole containing Program's Routine inventory. The module does not expose a
partial list as a complete catalog. Routine language names describe source;
they do not supply numeric wire Type codes or execution support.

An explicit empty canonical `Routines` container returns `()` from
`routine_names`; a missing or unavailable container returns `None`.
`program_names` includes only eligible Programs. Protected AOI routines do
not become ordinary Program Routine declarations.

The installed plain v35 `cip109r01v01.adf` through `cip109r08v01.adf` define
Executable attribute 7 as a 16-bit length followed by a description string
with a capacity of 128. This model supports the established ASCII subset:

| Source | Read result |
| --- | --- |
| One plain explicit `Routine/Description`, at most 128 ASCII bytes | Attribute 7: UINT16 byte count followed by exact text bytes |
| An explicit empty description | Attribute 7: `0000` |
| Missing, duplicate, localized, structured, non-ASCII or oversized description | Attribute 7 unavailable |

XML text, including whitespace, is preserved. Descriptions are never trimmed,
padded or truncated. Description availability is independent of the Routine
name inventory: an ordinary Routine with no description still has a known
source declaration, but does not acquire an invented empty description.

This contract is intentionally a **legacy subset**. Installed Executable ADF
revisions 9 and 10 omit Description 7 and Executable UID 4. The model does not
claim their full object layout. Type 1 has a declared 16-bit width but no
established source-to-wire enum here; UID 4 has no established source mapping.
The later Name field is marked for GSV use with native attribute number zero,
so its ADF slot 25 is not treated as a wire Name attribute. Compiled addresses,
headers, word counts and edit-buffer records remain unavailable.

The installed v35 source-protection help (`20072.htm`) documents `SourceKey`,
`EncodedSourceKey` and `SourceProtectionType` on L5X Routines. Presence of these
or other protection/encoded-content markers withholds the Program inventory;
the reader does not interpret keys or bypass protection.

## Program-scoped native identities

`NativeRoutines` reads the original ACD's bounded `Comps.Dat` records and binds
complete eligible source Program/Routine names to their logical object paths.
Only the observed component type 256, header version 0 and Executable body
format 54 are supported. Each path must retain Program class `0x68`, the actual
parent Program ID, Executable class `0x6D`, its nonzero child ID and zero trailing
words. The Program catalog must match both original ACD and exported L5X hashes.
Free records, database tails, ambiguous historical records, conflicting paths,
unsupported versions and malformed bounds cannot supply identities.

Rows, name lookups and `(parent, child)` lookups are immutable. Identical child
IDs in different Programs remain distinct objects. Loading checks the complete
eligible Routine name set and every parent against the matching native Program
catalog before replacing the active project. Plain L5X replacement clears the
optional native Routine binding; reset/configuration preserve an existing one.
Unsupported Routine extraction does not discard otherwise usable offline logic.

## Wire inventory

Executable instance reads and Instance List (`0x4B`) require a numeric parent
Program path. The cursor is the nested child instance, with the existing bounded
UDINT list/pagination contract. Nested class instance 0 reports model revision
1, maximum child ID and visible count using the shared class metadata widths.
The global Executable class exposes only its partial legacy revision; it does
not flatten Program catalogs or provide aggregate counts.

Missing, stale or mismatched source bindings return unavailable status `0x0C`.
Unknown Programs or child instances retain `0x05`; unsupported fields retain
`0x14`. Missing metadata cannot become an empty successful catalog. Signed
research sessions use the same reads and deny modifications. Class/instance
GetAll, compiled type/UID/address reads and native edit authority remain absent.

The independent inventory reader enumerates Executables beneath each discovered
Program, preserves parent scope and reads exact available legacy descriptions.
It retains unavailable field statuses and does not infer routine names from
descriptions. Its reports distinguish complete exposed inventory, partial
inventory and unavailable bindings; none is a complete native project upload.

These are source metadata and model read contracts. They do not establish
native Studio upload, online editing, firmware compilation or runtime
equivalence. Focused tests cover framing, bounds, source ambiguity,
protection, namespace isolation, missing values and immutable source guards.
