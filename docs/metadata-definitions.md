# Metadata Definition discovery

Version `.147` reads Metadata Definition (`0x349`) names and logical instance
IDs from the original ACD's `Comps.Dat`. An explicit collection and a complete,
unambiguous set of active format-0 definition records are required. Each stored
Name must match the component name. Deleted records and database allocation
tails do not supply definitions. Unsupported formats, scoped records, duplicate
IDs/names or malformed fields withhold the catalog.

The supported stored profile has one counted ASCII Name field in a 216-byte
body. Names are identifiers up to 62 characters. This does not claim support
for every native metadata record layout. Conversion keeps its L5X output when
this separate catalog cannot be read, and records the binding error.

## Read-only CIP surface

With matching original ACD/L5X hashes and project identity, the emulator exposes:

- Class revision, maximum original instance ID and actual instance count.
- Cursor-based instance discovery, including bounded partial replies.
- The original Name attribute, with its counted ASCII encoding.

The original IDs are not renumbered. A mismatched or stale binding is rejected;
loading another project without this manifest clears the binding. Status reports
show the source-bound catalog count. Existing L5X-only compatibility behavior
remains available without claiming an original ACD catalog.

The catalog is independent of temporary download definition staging. Reads do
not create definitions, write values, alter tags or grant transfer authority.

## Validation

The original demo ACD and a separate native-saved empty-program fixture each
yield 23 definitions with maximum ID 43. The source files remain unchanged.
One hundred fifty-three focused checks cover the reader, binding, converter,
appliance forwarding and affected SDK/session paths. Twenty-six live CIP checks
read all original names/IDs and class counts. The rebuilt executable runs the
same reader, and the native SDK Go Online/Offline case passes with the catalog
loaded. This does not establish SDK use of every definition or metadata values.

## Remaining upload work

Definition names and IDs do not establish metadata values, MUID encoding,
locales, qualifiers or the [Program `0x50` query response](program-upload-query.md).
Version `.149` adds a separate [original metadata value catalog](native-metadata-values.md)
with supported locale/qualifier forms and signed stream reads. Its record IDs
are simulator-local. Program `0x50`, full native upload/download and the separate
download result-response format remain unfinished.
