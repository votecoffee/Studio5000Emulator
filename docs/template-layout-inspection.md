# Native Template member inspection

Version `0.6.0-connectivity.76` decodes the member entries and names in temporary
[Template definitions](template-staging.md). This is structural inspection;
native storage mapping, device execution, tag monitoring and full download
remain unfinished.

## Supported structure

Rockwell's [Logix 5000 Data Access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
pages 55–58, describes eight-byte member entries followed by NUL-terminated type
and member names. Each entry contains two UINTs and one UDINT: member information,
the type word and the offset word. The decoder preserves those words exactly.
It does not mask an encoded offset into a presumed byte address.

The type name precedes an optional semicolon suffix. That suffix is opaque.
All bytes after the last member name are counted as an opaque trailer, including
zero bytes. They are not silently discarded as padding. Download definitions
can contain information beyond the documented read format.

Limits are 65,536 definition bytes, 4,096 members, 254 bytes per name and 1,024
Templates. Existing staging also caps total definition storage at 1 MiB. Names
must be ASCII identifiers, allowing colons for native system names. Member
names must be unique without regard to case. A missing terminator, invalid or
duplicate name, truncated member table or exceeded limit rejects that definition's
inspection. An incomplete definition never contributes partial member counts.

Immutable decoded definitions remain inside temporary staging. Invalid inspection
does not turn an otherwise opaque staged definition into a valid layout, nor
does it authorize execution. Existing staging validation still controls batch
acceptance. No definitions enter the active type catalog.

## Diagnostics and cleanup

`template_staging.layout_inspection` reports:

- Status `idle`, `decoded`, `partial` or `invalid`.
- Counts of decoded/unavailable Templates and decoded members.
- Opaque trailer bytes and member offsets whose high nibble is nonzero.
- Fixed, aggregate error reasons without names, IDs, offsets or definition bytes.
- False storage-mapping, signature-verification, definition-exposure and execution flags.

`decoded` means the supported structure was parsed; it does not certify type
words, array sizes, member extents, offset encodings, nested references, CRCs,
signatures or instruction semantics. Summary reads use cached counts rather
than repeatedly traversing every member. Repeated summaries are independent
copies. Transport, preparation, lease and source cleanup discard the inspection
along with its definitions. Native SDK probe admission and cleanup require an
advertised inspection to be idle and empty with all authority flags false.

The signed device-operation path emits a payload-free
`native_template_layout_inspection` event, then retains its existing execution
denial. It neither acknowledges installation nor assigns native tag addresses.

The offline payload inspector supports the same optional analysis:

```powershell
py -3.13 -X utf8 source/tools/inspect_device_payload.py --payload .local/device-payload.bin --expanded-bytes 371787 --templates --out .local/template-report.json
```

Use the actual expanded size for the inspected payload. Reports use exclusive
creation and cannot overwrite the payload. The default analysis without
`--templates` remains structural batch inspection only. Neither mode connects
to a controller or verifies a captured signature.

## Evidence and remaining work

Offline inspection of the preserved demo download decodes 242 Templates and
13,312 members without a name/table error. It counts 26,990 opaque trailer bytes
and 5,337 member offset words with a nonzero high nibble. These are observations
of one captured download, not an authenticated native storage specification.
Synthetic tests exercise bounds, names, exact word preservation, partial failure,
privacy, staging cleanup, signed execution denial and probe admission.

Next work must establish those encodings and trailers, validate member extents
and nested types, bind source names and native IDs, and implement a verified
device-operation and atomic commit contract. The native SDK still fails online
tag-address resolution before emitting value reads. Full upload/download and
online edits remain unsupported; Studio GUI monitoring remains unverified.
