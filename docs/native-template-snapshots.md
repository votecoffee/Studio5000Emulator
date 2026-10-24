# Source-bound native Template snapshots

Version `0.6.0-connectivity.113` can optionally serve saved native definitions
for user structures that the software model already supports. The normal L5X
execution model continues to run the logic and hold tag values. This feature
supplies read-only type metadata; it does not install or execute compiled code.

Native Template definitions contain more than the member table and names.
Their type-name headers can include additional bytes, and the data after the
last member name is not necessarily zero padding. The snapshot retains these
bytes without assigning checksum, signature or reconstruction semantics.

## Preparing a snapshot

Use an existing native device payload previously sent to your owned emulator,
its original ACD and the matching complete L5X export. The offline builder does
not invoke the SDK or connect to a controller:

```powershell
py -3.13 -X utf8 source/tools/build_native_templates.py --payload .local/device-payload.bin --expanded-bytes 100000 --source-acd .local/Controller.ACD --source-l5x .local/Controller.L5X --out .local/native-templates.json
```

Supply the actual expanded byte count recorded with that payload. The builder
checks all staged type identities and member layouts against the ACD metadata,
then checks the supported software layouts against those source types. It
requires a new output file and verifies that all input hashes remain unchanged.
Definitions and application names make the output private; keep it under
ignored `.local/` storage. Captures and vendor definitions are not bundled.

The application service accepts the JSON as the optional `native_templates`
field of an L5X `load` request, alongside the matching `native_types` manifest
and existing project/symbol bindings. No snapshot is inferred when that field
is absent. A mismatched source pair, unsupported software layout, changed
member access, unknown nested type or inconsistent allocation rejects the load
before replacing the active engine. Reset preserves the loaded binding;
loading another project without a snapshot clears it.

## Read behavior

Version `26.1023.235144` accepts ordinary identifiers for hidden packed-bit
hosts. A BIT still requires an explicit target naming a preceding scalar
hidden SINT, with a unique bit in the range 0–7. Generated `ZZZZ…` names are
accepted through the same checks. Host bytes have no independent application
value and cannot be read or written directly. Snapshot binding still compares
the original member names, offsets, bits, type IDs and access permissions;
accepting a host name does not relax those source checks.

The snapshot applies only in native compatibility mode. The public tag and
nested-type visibility rules still select which definitions can be browsed;
private and unsupported types do not become public merely because their bytes
exist in the snapshot. Ordinary research-mode layouts retain their model IDs.

| Field | Source or behavior |
| --- | --- |
| Template ID, handle, memory words | Saved definition, checked against original type identity and exact allocation |
| Member count and structure size | Saved metadata, checked against original and software layouts |
| Family and reconstruction byte | Saved values; supported user structures require an explicit `NoFamily` source declaration |
| Multiply Code reference | Four-byte null: the software model has no generated Multiply Code routine |
| Definition read | Exact saved extent, including opaque header/trailer bytes; no added three-byte padding |
| Symbol type and structured-read handle | Same bound Template ID and handle as the definition inventory |
| Values | Existing software memory, encoded using the checked software member layout |

Nested member type references use the same bound IDs. Reads check that the
original type layouts, ID map and source hashes still match the loaded binding.
Setters and compiled-code installation are not enabled by a snapshot.

The independent [upload inventory reader](upload-inventory-client.md) recognizes
the explicitly enabled saved-definition profile. It retains opaque trailers
instead of demanding three final zero bytes, and decodes only the exact null
Multiply Code reference. Other code references remain unsupported. Snapshot
descriptions expose counts, hashes and limits without repeating definitions or
application type names in polling state.

## Validation and limits

Version `26.1023.235144` binds the original definitions of an owned nested UDT
fixture with an ordinary packed-host name. Complete symbolic and Data Table
reads match 100 source-value bytes across scalar, nested and array UDT tags.
The SDK also receives those exact three tables before its upload stops at
unavailable Energy discovery. This verifies type/value reads without establishing
complete native upload or saved uploaded ACD acceptance.

A completed reference upload supplied 830 contiguous Template definitions.
All 830 parsed structurally. Across 42 type names also present in an owned demo
download, handles, member counts, sizes, families, reconstruction metadata and
type-name headers matched; the opaque trailers differed. This establishes no
general rule for generating or substituting trailer bytes.

The `.113` runtime with the owned demo's saved snapshot reaches
`RxCsE_UPLOAD_OF_TAGS_FAILED` across 182 verified signed SDK requests. Native
Offline, cleanup and source/model preservation pass, without a reported fatal
SDK fault. This is progress in type inventory, not a completed project upload
or proof of the individual cause of earlier failures.

With the same saved snapshot, `.114` adds [source-checked empty Energy discovery](connectivity.md#empty-energy-discovery-for-ordinary-user-types).
The structured-project SDK case passes Controller tag collection and reaches
device/extended-device/memory collection, then fails with
`RxCsE_UPLOAD_OF_CONTROLLER_COLLECTION_FAILED` across 199 verified signed
requests. Native Offline, cleanup and source/model preservation pass without
a reported fatal SDK fault. Complete project upload remains unfinished.

Snapshots are bounded to 1,024 definitions, 65,536 bytes per definition and
1 MiB total. Exposed software definitions also retain the 32,768-byte model
bound. Only existing supported numeric, nested and packed-bit user layouts can
bind. Built-in/native-only types, compiled addresses, signature validation and
the complete upload/download/edit lifecycle remain unfinished.
