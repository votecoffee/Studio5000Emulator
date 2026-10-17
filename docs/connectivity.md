# EtherNet/IP connectivity

The endpoint is an experimental explicit-message target backed by the loaded
project's modeled memory. Studio Go Online, project correlation, upload/download,
online edits and native debugger services remain unimplemented or unverified.

## Start an endpoint

In the app, load a project and open **Connectivity**. Choose an identity profile
and port, then select **Start endpoint**. **Load network lab** opens a public
fixture with a 1,200-element DINT array, ControlWord, Command and read-only
Observed. Each modeled scan copies Command to Observed.
**Load structure lab** opens nested numeric UDTs for template discovery and
fragmented transfers. Each scan copies Command into Machine.Axis and copies
Machines[0].Axis.Command into the read-only Machine.History[0].Command.
**Load layout lab** exercises mixed-width numeric fields, nested alignment and
64-bit values. Each scan copies Records[0].Count into the read-only Observed tag.

The default address is `127.0.0.1:44818`, with TCP and UDP listeners and a modeled
backplane route of port 1, slot 0. The target never forwards traffic externally.
Writes are disabled until explicitly enabled before startup. Network writes and
the UI use the same memory; Step/Run controls modeled scan execution.

## Identity profiles

- `research` is the default: an experimental LogixLab identity using vendor
  value `0xFFFF`.
- `logix-v35-l85e` is an optional compatibility profile for a matching `1756-L85E`
  v35 source. It advertises vendor 1, device type 14, product code 168 and the
  loaded source's minor revision.

Both profiles use a research serial. A compatible identity response does not
establish an authentic Rockwell target or native controller equivalence.
Incompatible project imports are rejected while the compatibility profile is
active. Compatible replacements update identity data and invalidate old sessions.

## Supported services

| Surface | Implemented subset |
| --- | --- |
| Encapsulation | ListIdentity, ListServices, ListInterfaces, Register/Unregister Session |
| Explicit transport | SendRRData, slot-0 Unconnected Send, Class 3 SendUnitData |
| Connections | Standard/Large Forward Open and Forward Close; sequence/replay checks |
| Objects | Identity attributes, Message Router class inventory and controller name |
| Symbol metadata | Paginated `0x55`; single/list attribute reads for 1, 2, 8 and 10 |
| Templates | Class `0x6C` attributes 1, 2, 4 and 5; offset-based `0x4C` definition reads |
| Atomic access | BOOL and supported signed/unsigned integers and REAL; arrays and atomic members |
| Structured access | Bounded numeric UDT reads/writes, including nested structures and arrays |
| Transfers | `0x4C` read, `0x4D` write, `0x52` fragmented read, `0x53` fragmented write |
| Integer masks | `0x4E` Read Modify Write, applying OR then AND masks |
| Multiple service | Bounded Multiple Service Packets with independent child operations |

Symbol attributes provide name, type, dimensions and effective external access.
Constants, aliases and member restrictions are honored. Private tags, AOI locals
and Safety program tags are not exposed. Firmware-internal attributes 3, 5 and 6
remain unsupported, so full native tag-upload initialization is still pending.

Supported atomic wire types are BOOL, SINT, INT, DINT, LINT, USINT, UINT, UDINT,
ULINT and REAL. Whole STRING transfers and packed BOOL arrays remain unsupported.
Atomic STRING members can be addressed individually.

## Structured transfers

Explicit `User` UDTs in `NoFamily` may contain SINT, INT, DINT, LINT, USINT, UINT,
UDINT, ULINT and REAL members, nested supported UDTs and one-dimensional member
arrays. Numeric values use little-endian encoding. Root arrays may have up to
three dimensions. Symbol types link to template instances; templates describe
member types, offsets, names, structure size and the handle returned in reads.
See the [data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf),
chapter 2, for the protocol formats.

Numeric fields align to their byte width. Arrays align to at least four bytes
and include trailing alignment padding. Structures align to four bytes, or
eight when they contain a 64-bit member, including through nested types.
Structure sizes are rounded to that alignment. These rules follow
[Design Considerations, chapter 6](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm094_-en-p.pdf).

Reserved alignment padding is canonical zero data in this software model.
Reads emit zero padding; writes reject nonzero bytes in reserved padding before
changing application values. A zero-only padding fragment is a no-op. This is
a model policy, not a claim about native controller padding contents. Unknown
application values still reject reads, independently of the padding policy.

The model limits each layout and requested transfer to 32 KiB, nesting to eight
levels, each type to 256 members and member arrays to 4,096 elements. Hidden,
private, overlaid, packed, inferred-only, predefined and AOI layouts are excluded.
BOOL/STRING fields inside whole UDT transfers and LREAL remain unsupported.
Eligible atomic members remain accessible separately.

Template IDs and CRC-derived handles belong to this software model and are not
native compiled type identifiers. Only templates reachable through externally
accessible tags are exposed. Unknown member values reject the requested read;
unknown backing data is never replaced with zeroes.
Reset and import invalidate sessions; project replacement rebuilds the catalog.

Structured `0x4D` and `0x53` writes require the `A0 02` type marker and the matching
template handle before the element count. Fragment offsets address bytes in the
requested record region. Writes validate root access and every touched member,
including aliases, constants and read-only nested members. A whole-record write
touches every member; a fragment may update writable fields while leaving a
read-only field untouched. Complete atoms can establish unknown leaf values;
split atoms require known bytes for the remainder of that atom.

The independent structure probe uses the client's template parser and value
codec over a negotiated 256-byte Class 3 connection to exercise fragmentation.
Its tag-cache adapter uses supported symbol attributes. This does not establish
native firmware-address tag upload, native UDT layout parity or Studio Go Online.

## Write semantics

Each write request validates its payload and rolls back that request on failure.
Accepted fragments take effect immediately; a later failed fragment does not
undo prior fragments. Scans may run between separate requests. Fragments can
split an atomic element, but untouched bytes within that atom must already be
known. This applies to both atomic and supported numeric UDT transfers. A failed
member or nonfinite REAL rejects the entire request, including earlier members
or records in that request.

Integer masks may cover 1, 2, 4 or 8 low bytes of a sufficiently wide integer.
Upper bytes are preserved; OR is applied before AND. BOOL, REAL and aggregate
mask writes are unsupported.

Multiple Service Packet children are independent operations. Later child failure
does not roll back earlier writes, and an oversized combined response can fail
after earlier children executed.

## Bounds and traces

The target permits up to 16 TCP clients and 8 Class 3 connections per session.
Request payloads are bounded to 32 KiB. CIP replies are bounded to 480 bytes and
the negotiated connection size. Nested messages and dispatch work are bounded.
Reset, scope changes and project replacement require clients to reconnect.

The trace retains up to 1,000 events with peer/session, path, service, status,
error and bounded request/reply hex samples. Samples have a truncation flag.
Trace exports may contain project tag names and data; keep them in `.local/`.

## Native SDK diagnostic

`source/research/NativeStudioProbe` uses the optional official Logix Designer SDK
client to open a private ACD copy and attempt a mode query or GoOnline. The target
must be configured and visible in FactoryTalk Linx. The diagnostic accepts only
loopback slot-0 paths and never downloads, saves, changes mode or writes tags.

From the repository root, with native tooling available and the local endpoint
running:

```powershell
dotnet run --project source/research/NativeStudioProbe -- --acd .local/projects/demo.ACD --comm-path 'Ethernet\127.0.0.1\Backplane\0' --operation mode --out .local/probes/mode.json
```

Use `--operation go-online` for the broader connection attempt. Retain receipts
and before/after protocol traces locally. A native failure before any endpoint
traffic does not identify the next missing CIP service. A successful identity
query is still distinct from successful project correlation or online monitoring.

## References

- [Rockwell Logix data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf)
- [Rockwell Logix Designer SDK guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf)
- [pycomm3 client implementation](https://github.com/ottowayi/pycomm3)
