# Original ACD metadata values

Version `.149` reads the supported original v35 `Comments.Dat` records and
serves their immutable metadata through signed class `0x349`, service `0x53`.
The source catalog includes definition properties, localized diagnostic text,
comments, numeric arrays and object references. This extends
[definition discovery](metadata-definitions.md) and the
[fragmented query decoder](metadata-upload-query.md).

## Source contract

The bounded reader requires matching original ACD/L5X hashes and Metadata
Definitions. Stored `ValueType` declarations identify each definition's value
kind; missing, duplicate or conflicting declarations withhold the catalog.
Active record bounds, supported header/qualifier forms, exact value sizes,
UTF-8/UTF-16 text, numeric widths, reference names and locale profiles are checked
before installation. Deleted records and allocation tails supply no values.
An unsupported optional catalog leaves the converted L5X available and reports
a separate import diagnostic. L5X alone cannot manufacture this binding.

Supported source forms are string values, SINT/INT/DINT arrays and reference
arrays. The stored reference entries contain their original name and target
words. Ten observed locale profiles include the invariant/default form and
the localized diagnostic records. Qualifiers preserve their source text; their
stored lookup word is not treated as an authentication or checksum proof.
Unsupported forms remain unavailable.

Two owned source projects decode to 1,670 and 1,660 records. Each includes 1,638
shared built-in records that match a saved successful controller upload after
decoding, including localized text, numeric values and target/definition/locale
keys. This comparison excludes project-specific records and wire record IDs.
Public tests use synthetic databases; ACD files, captured values and validation
artifacts stay outside tracked files.

## Read behavior

The two data selections are all-object metadata and Controller metadata. The
previous exact empty Controller-attribute-26 compatibility selection remains.
Nonempty replies follow the observed first/intermediate/final framing and echo
the requested byte cursor. Chunk sizes respect the negotiated response budget.
Each signed session owns one cursor, pinned to its loaded catalog, source and
generation. Another session cannot resume it. Invalid cursors, changed source
and closed/expired sessions cannot expose a previous transfer's remaining data.
The bytes are prepared once at load; reads do not scan logic or mutate tags.

The returned record IDs belong to this simulator catalog and remain stable
while it is loaded. They do not claim to be original controller MUIDs or the
opaque words in Program service `0x50`. Stored target words remain source
identifiers; this feature does not resolve them into executable addresses.

Reads require the existing signed anonymous compatibility context. Unsigned
queries and active metadata writes remain unsupported. The programming lease's
[temporary staged values](metadata-values.md) are separate and never merge into
this read-only catalog. Reset retains the original catalog; loading a project
without the manifest clears it. Supported runtime logic changes withhold its
nonempty reads, because the original metadata cannot describe edited logic.
The existing empty compatibility selection remains usable for reconnect.

The API's `connectivity.metadata_values` reports counts, source hashes and
capability limits. It omits names, qualifiers, references and values.

## Limits

All 183 affected checks pass. The rebuilt appliance returns the original demo's
221,937 metadata bytes and 1,670 records across 505 signed replies, matching the
source catalog exactly. Controller and empty compatibility reads also pass.
Cross-session cursor reuse, changed selections and active metadata writes reject
without changing source, tags, scans or audit values. The packaged executable
runs the same source reader. All 102 source/build/guest module hashes and served
webpage/executable/appliance versions match.

Native SDK Go Online/Offline passes across 75 verified requests. A supported
Program-mode import and reconnect passes across 188 verified requests, with the
expected single simulator audit update. The upload trial receives the nonempty
Controller metadata reply and proceeds to later requests; it still fails the
Controller collection stage at the unresolved Time Sync response. All three
cases confirm native Offline and endpoint cleanup, preserve original source
files and report no SDK fault. After the edit, direct checks confirm that
nonempty original metadata is withheld while the empty reconnect selection
remains available. The original demo is restored afterward.

Serving these metadata records does not complete native upload. Program `0x50`,
the remaining Controller fields and other source/response contracts remain
independent upload gaps. Download still needs the class `0x412` result response.
Metadata values are original source data, not live tag values or new controller
execution semantics. Full transfers and the complete edit lifecycle remain
unfinished.
