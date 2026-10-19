# EtherNet/IP connectivity

The endpoint is an experimental explicit-message target backed by the loaded
project's modeled memory. Studio Go Online, project correlation, upload/download,
online edits and native debugger services remain unimplemented or unverified.

## Start an endpoint

In the app, load a project and open **Connectivity**. Choose an identity profile,
bind IP and port, then select **Start endpoint**. **Load network lab** opens a public
fixture with a 1,200-element DINT array, ControlWord, Command and read-only
Observed. Each modeled scan copies Command to Observed.
**Load structure lab** opens nested numeric UDTs for template discovery and
fragmented transfers. Each scan copies Command into Machine.Axis and copies
Machines[0].Axis.Command into the read-only Machine.History[0].Command.
**Load layout lab** exercises mixed-width numeric fields, nested alignment and
64-bit values. Each scan copies Records[0].Count into the read-only Observed tag.
**Load flag lab** opens 28-byte records with multiple packed Boolean hosts,
nested groups and a 12-record array. Each scan copies Records[0].Ready and
Records[0].Count into the read-only Observed and ObservedCount tags.

The default address is `127.0.0.1:44818`, with TCP and UDP listeners and a modeled
backplane route of port 1, slot 0. The target never forwards traffic externally.
Writes are disabled until explicitly enabled before startup. Network writes and
the UI use the same memory; Step/Run controls modeled scan execution.

## Linx coexistence and addresses

Use **Bind IP** or `--eip-bind` to select a specific IPv4 address belonging to
the emulator's PC. TCP, UDP and the ListIdentity socket address all use that
address. The HTTP UI stays on loopback. Wildcard, multicast, limited-broadcast and
hostname bindings are rejected. A reachable non-loopback address makes the
experimental protocol endpoint accessible to other devices; tag writes remain
opt-in. The app does not assign IP addresses, change firewall rules or configure
Linx.

Two applications can use port 44818 on different local addresses when both
bind specifically. A wildcard listener on `0.0.0.0:44818` can prevent a second
application from binding even a different loopback address. Changing only the
emulator's IP does not resolve that case. A temporary nonstandard port supports
protocol testing, but does not establish normal Studio discovery or Go Online.

FactoryTalk Linx documents **Ethernet driver properties → Advanced → IP Address**
for limiting its listener to one address. Its **Listen on EtherNet/IP encapsulated
ports** setting controls incoming TCP/UDP 44818 services. Existing unsolicited
messages can depend on that listener. Coordinate any Linx configuration change
with the applications using it; the emulator never stops or reconfigures that
service. See the official
[Ethernet Advanced settings](https://www.rockwellautomation.com/en-us/docs/factorytalk-services-platform/6-60/factorytalk-services-platform-help-ditamap/factorytalk-linx-help/config-stand-alone-apps/add-a-driver/ethernet-ppt-advanced-sets.html).
The optional [VMware host-only appliance](vmware-appliance.md) supplies an isolated
guest network stack when the host's Linx listener must remain unchanged. Its
launcher provides a localhost browser tunnel and Windows tray controls.

## Broadcast discovery

Linux endpoints on an Ethernet interface with an IPv4 subnet prefix shorter than
`/31` also listen at that subnet's directed-broadcast address and
`255.255.255.255`. These are separate, specific UDP bindings; the TCP and unicast
UDP listeners remain on the selected PLC address. Windows and loopback endpoints
continue to use unicast discovery.

Linux `IP_PKTINFO` metadata must identify the selected interface, its local IP
and the matching broadcast destination. Missing, ambiguous or truncated metadata
is rejected. Only empty ListIdentity, ListServices and ListInterfaces requests
with zero session/status/options are answered; other broadcast datagrams are
ignored. Replies are unicast to the sender, with the selected PLC IP and interface
explicitly supplied to the kernel. This does not require a raw socket or network
configuration privileges.

If either additional socket cannot bind, both are closed and the endpoint
continues with unicast discovery. **Connectivity** shows broadcast availability
and the reason when unavailable. The API exposes this under `discovery`; traces
include `broadcast_discovery`, `broadcast_ignored` and send-error events. No host
adapter, Linx, firewall or routing configuration is changed.

Broadcast reception and FactoryTalk Linx range browsing are separate acceptance
checks. A successful broadcast reply does not establish range browsing, path
selection or Studio Go Online. The discovery exchange follows ODVA's
[IPv4 ListIdentity description](https://www.odva.org/wp-content/uploads/2022/06/2012_ODVA_Conference_XuYuBrooksBatke_FINAL.pdf)
and Linux's [IPv4 socket interface](https://man7.org/linux/man-pages/man7/ip.7.html).
The interface/destination control message follows
[IP_PKTINFO](https://man7.org/linux/man-pages/man2/IP_PKTINFO.2const.html).

Validation on 2026-10-19 with `0.6.0-connectivity.17` passed 445 behavioral tests
on each of Windows and Linux. An unprivileged Linux datagram probe completed nine
discovery exchanges across unicast, subnet broadcast and limited broadcast,
with matching payloads and the selected PLC reply source. Six malformed
broadcast requests received no reply. A Windows `pycomm3` 1.2.16 client then
discovered the running host-only appliance with one subnet-broadcast query.
Exact addresses, packet traces and receipts remain local. These checks do not
establish Linx range browsing or change the native Go Online result below.

## Virtual chassis

The modeled port-1/slot-0 route is an EtherNet/IP routing response; it does not
register this application in Rockwell's native virtual chassis. That requires
a separate virtual-backplane provider integration. Rockwell historically offered
a toolkit for third-party network or specialty modules in SoftLogix, including
the L30 and L60 variants; it was not exclusively limited to Rockwell modules.
See the official [SoftLogix product overview](https://www.rockwellautomation.com/en-tr/products/hardware/programmable-controllers/softlogix-controllers.html).
That history does not establish a supported way to register a custom v35 CPU in
the installed chassis. This project has no such provider yet. Changing an IP
or adding an EDS file cannot supply that integration or the remaining native
Studio project/debugger services.

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
| Network metadata | Port/node addresses `0xF4`, TCP/IP configuration `0xF5`, Ethernet MAC `0xF6` |
| Device locator | Identity instance 1, `0x4B` Flash_LEDs; timed webpage indicator |
| Catalog refresh | Controller class `0xAC`: class revision/inventory and instance 1 comparison attributes |
| File Manager | Class `0x31A`, instance 0: revision and zero storage-instance count |
| Symbol metadata | Paginated `0x55`; single/list attribute reads for 1, 2, 8 and 10 |
| Templates | Class `0x6C` attributes 1, 2, 4 and 5; offset-based `0x4C` definition reads |
| Atomic access | BOOL and supported signed/unsigned integers and REAL; arrays and atomic members |
| Structured access | Bounded numeric and explicit packed-BIT UDTs, including nested structures and arrays |
| Transfers | `0x4C` read, `0x4D` write, `0x52` fragmented read, `0x53` fragmented write |
| Integer masks | `0x4E` Read Modify Write, applying OR then AND masks |
| Multiple service | Bounded Multiple Service Packets with independent child operations |

Nonzero encapsulation-status packets from a peer are recorded as `peer_error`
and are not answered. This prevents an error-response loop during client
interoperability; the session remains available for later valid requests.

Symbol attributes provide name, type, dimensions and effective external access.
Constants, aliases and member restrictions are honored. Private tags, AOI locals
and Safety program tags are not exposed. Firmware-internal attributes 3, 5 and 6
remain unsupported, so full native tag-upload initialization is still pending.

Supported atomic wire types are BOOL, SINT, INT, DINT, LINT, USINT, UINT, UDINT,
ULINT and REAL. Whole STRING transfers and packed BOOL arrays remain unsupported.
Atomic STRING members can be addressed individually.

## Device locator

Identity class `0x01`, instance 1 supports the `0x4B` Flash_LEDs service. The
request contains exactly one USINT duration: zero stops identification, and
9 through 255 starts it for that many real seconds. Values 1 through 8 are
invalid. A later valid request replaces the remaining time. Success returns an
empty service response. The timing contract follows the
[ODVA CIP Object Tests, section 4.1 test 6.8](https://ticket.hilscher.com/secure/attachment/260555/CIP_PCTS.pdf).

The webpage displays a global **DEVICE LOCATOR ACTIVE** banner with a countdown
and a repeating red/green/off color cycle. It remains visible while switching
tabs and automatically clears on expiry, cancellation or endpoint shutdown.
Page refresh reads the current request from the endpoint. Browser reduced-motion
preferences show a steady indicator. Idle pages poll at two-second intervals;
local countdowns continue between responses.

Identification works with tag writes disabled. It does not change application
memory, scan execution, project generation, device identity or catalog tokens.
Its monotonic timer runs independently of modeled scan time. Protocol traces
record requests and durations. Application resets preserve identification of
the same endpoint; stopping or replacing the endpoint clears it.

FactoryTalk Linx discovery and device-location support are separate from native
project selection, Go Online and upload/download. Extended identity and vendor
metadata remain incomplete. Manufacturing dates, warranty identifiers and other
physical-device data are not inferred from an ACD or invented to fill empty
fields in a device-information view.

## Port and TCP/IP interface metadata

The Port Object (`0xF4`) describes two modeled interfaces: local slot-zero
backplane routing on port 1 and the selected EtherNet/IP endpoint on port 2.
Class attributes 1, 2, 3, 8 and 9 support single/list reads and class
Get_Attributes_All. The entry port is 2; the port-info array includes the reserved
zero entry. Instance attributes 1 through 5 and 7 support single/list reads and
instance Get_Attributes_All. Attribute 7 describes local slot zero on port 1,
and the selected IPv4 address as a padded extended-link segment on port 2. Port 2's
link path points to TCP/IP Interface instance 1. Port 1 has an empty link-object
path because no physical backplane object is implemented. Unknown ports are
rejected rather than advertised as additional hardware.

The TCP/IP Interface Object (`0xF5`) supports class attributes 1 through 3 and
class Get_Attributes_All. Instance 1 exposes attribute 5 (IPv4 configuration) and
6 (hostname). Attribute 4 returns the path to Ethernet Link instance 1 when its
MAC address is known, or a zero-length path when physical-link metadata is
unavailable. IPv4 values are CIP little-endian UDINTs; domain/hostname values use
length-prefixed, even-padded CIP strings. The configuration uses the selected
local address, actual subnet mask, default gateway, IPv4 DNS servers and domain.

Configuration is captured lazily on the first IPv4/physical-link query and retained for
that endpoint. Linux queries interface ioctls, its route table and resolver file;
Windows calls the read-only IP Helper API directly. It does not launch a shell
on a CIP request. Restart the endpoint to refresh
the snapshot after an OS configuration change. If the selected configuration
cannot be read or validated, the request returns a CIP error; no subnet, gateway
or MAC address is guessed. Snapshot availability and errors are exposed in the
connectivity state. Ethernet Link (`0xF6`) supports class attributes 1 through 3,
class Get_Attributes_All, and single/list reads of instance 1 attribute 3. The MAC
is six octets in adapter order, read from that exact OS interface. Unknown,
non-Ethernet, zero or multicast addresses are not replaced with invented MACs;
the request returns an explicit CIP error. Loopback normally has no Ethernet MAC.

Network configuration writes, TCP/IP instance Get_Attributes_All, the remaining
TCP/IP attributes, Ethernet Link speed/flags/counters and physical-backplane services
remain unsupported. Enabling tag writes does not enable network reconfiguration.
These responses do not establish native Studio path selection or Go Online.

The layouts follow the published
[Port/TCP-IP object tables](https://productinfo.se.com/pm5500/595e2aa946e0fb0001f715da/PM5500%20user%20manual/English/PM5500SeriesUserManualv02_0000044889.ditamap/$/R_Communications_EthernetIP_MessagingExplicitExchanges_PM5500_0000178841)
and the [Rockwell port-object description](https://www.sprecherschuh.com/content/dam/sprecher-schuh/downloads/tech-docs/CEP7-UM014B-EN-P_12-11.pdf).
This is an original, bounded implementation; no upstream stack code is bundled.
Windows adapter layouts follow Microsoft's
[IP Helper documentation](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getadaptersaddresses).

## Catalog refresh

Controller class `0xAC`, instance 0 supports Get Attribute Single and Get Attribute
List for the common class attributes 1 (object revision), 2 (maximum instance)
and 3 (instance count), each a UINT. The modeled object revision is 1, with one
implemented instance numbered 1. This revision describes the model's object
interface, independently of the source comparison tokens or advertised firmware
identity. Class-level Get Attributes All and configuration writes are unsupported.
The common attribute definitions follow the
[OpENer class implementation](https://github.com/EIPStackGroup/OpENer/blob/d8820ef41ce30dda06d213438ba81c81de33ffe2/source/src/cip/cipcommon.c#L329).
No upstream code is bundled.

Controller class `0xAC`, instance 1 supports Get Attribute Single and Get Attribute
List for attributes 1, 2, 3, 4 and 10. Their wire widths are 2, 2, 4, 4 and 4 bytes
(INT/INT/DINT/DINT/DINT). This comparison interface is described in
[Data Access, chapter 2](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf).

The model derives opaque comparison tokens from the imported source bytes and
model version. Compare all five attributes together. Values stay stable during
scans, tag writes, resets and scope changes. Importing identical source bytes
preserves tokens; different source bytes conservatively change them, including
changes to comments or initial values. These are not native firmware signatures.
The connectivity API exposes the combined token as `catalog_revision.token`
while the endpoint is enabled.

Imports, resets and scope changes still require clients to reconnect and refresh
their cached symbols/templates. Old sessions are rejected. A metadata check and
tag reads may share a Multiple Service Packet. For writes, check the revision
before and after writing; a grouped metadata check is not a conditional write
guard because Multiple Service children execute independently.

Only the read-only comparison attributes are implemented. Native project
correlation, mode changes and Studio Go Online remain pending.

## File Manager discovery

File Manager class `0x31A`, instance 0 supports Get Attribute Single and Get
Attribute List for attribute 1 (object revision, UINT) and attribute 3 (instance
count, UDINT). The modeled object revision is 1 and the count is zero: this
implementation has no emulated removable-storage devices. The four-byte count is
specific to this object's layout; it must not use the two-byte count from the
controller metadata class. Message Router inventory includes this implemented
class, and connectivity state exposes its limited scope under `file_manager`.

The layout was checked against the installed Studio v35 File Manager Attribute
Description Files. These reference files are neither modified nor bundled;
the implementation is original. Reference paths and hashes stay in local
validation receipts.

Attribute 2, instance attributes, capacity, file contents and file operations
remain unsupported. Requests for a storage instance return path-unknown
(`0x05`); unsupported class attributes return attribute-unsupported (`0x14`),
including per-attribute statuses in mixed lists. Class Get Attributes All and
mutating services remain rejected. Enabling tag writes does not enable storage
operations. This discovery subset does not implement SD-card project loading,
upload/download or native Studio correlation.

## Structured transfers

Explicit `User` UDTs in `NoFamily` may contain SINT, INT, DINT, LINT, USINT, UINT,
UDINT, ULINT and REAL members, explicitly mapped BIT flags, nested supported
UDTs and one-dimensional member arrays. Numeric values use little-endian
encoding. Root arrays may have up to three dimensions. Symbol types link to
template instances; templates describe
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
levels, each type to 256 members and member arrays to 4,096 elements. Private,
inferred-only, predefined and AOI layouts are excluded. Hidden storage is allowed
only for the validated BIT hosts described below. Unmapped BOOL declarations,
BOOL/BIT arrays, STRING fields, LREAL and other overlays remain unsupported in
whole UDT transfers. Eligible atomic members remain accessible separately.

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

### Packed Boolean flags

Visible scalar `BIT` members must explicitly name a preceding hidden scalar
`SINT` host through `Target`, with unique `BitNumber` values from 0 through 7.
Host names must start with `ZZZZZZZZZZ`. Multiple hosts, sparse bit positions,
nested UDTs and arrays of these UDTs are supported. Templates describe both the
host and each visible flag, using the shared byte offset and the flag's bit
number. This follows the UDT mapping described in the
[data access manual, chapter 2](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf).

The model stores visible flag values, with unused host bits reserved as zero.
Reads assemble the host bytes from known flag values; unknown visible flags
reject the read. Unused bits are not native backing-memory values. Writes reject
nonzero reserved bits, and never create or expose a separate hidden host value.
Arbitrary hidden members and overlapping, missing, forward or non-SINT mappings
are rejected.

A structured write that touches a host byte checks write permission for every
visible flag mapped to that byte, even when the requested value is unchanged.
An atomic symbolic write to one flag checks that flag alone. Host-byte fragments
can establish previously unknown flags without reading unrelated fields. Hidden
hosts cannot be read or written directly. The existing per-request rollback and
fragment rules apply.

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

### Observed native connection gaps

On 2026-10-19, an isolated RockwellMCPServer 0.8.2 instance used the native SDK
with a matching private v35 ConveyorDemo ACD and the host-only appliance running
`0.6.0-connectivity.15`. The project opened offline, setting and reading its
configured Linx Ethernet/backplane/slot-zero path succeeded, and the Go Online
attempt reached the endpoint. It returned
`RxE_COMM_ASA_SERVICE_NOT_SUPPORTED - Unimplemented service`.

The baseline endpoint trace contains these unsupported requests:

| Object path | Request | Response in `.15` |
| --- | --- | --- |
| Class `0xAC`, instance 0 | Get Attribute List for attribute 1 | Unknown metadata instance (`0x05`) |
| File Manager class `0x31A`, instance 0 | Get Attribute List and Get Attribute Single for attribute 1 | Unsupported service (`0x08`) |
| Extended Device class `0x64`, instance 1 | Vendor service `0x4B` | Unsupported service (`0x08`) |

The same native operation was repeated against `0.6.0-connectivity.16` after
adding controller class metadata. Its class `0xAC`, instance 0 revision request
received a successful reply with object revision 1. The `0x31A` requests and
class `0x64` service `0x4B` still returned unsupported-service errors. Go Online
still failed with `RxE_COMM_ASA_SERVICE_NOT_SUPPORTED`. Both native attempts used
the same preserved ACD content; the original and private input hashes remained
unchanged. Independent client checks and 433 behavioral tests on each of Windows
and Linux passed for `.16`.

The `.18` retest added the File Manager class-discovery subset. Its native
class-revision request received a successful UINT revision-1 reply; the earlier
Get Attribute Single fallback was no longer sent. Of the 11 CIP events recorded
during this attempt, the sole unsupported request was Extended Device class
`0x64`, instance 1, service `0x4B`. Go Online still failed with
`RxE_COMM_ASA_SERVICE_NOT_SUPPORTED`. The ACD inputs, shared native-service
configuration and installed attribute-reference files retained their original
hashes. Independent client checks and 452 behavioral tests on each of Windows
and Linux passed for `.18`.

These are observed gaps, not a complete list of requirements for native online
operation. The trace does not establish the vendor payload layouts or which
response prevents later phases. Service `0x4B` on class `0x64` is a different
object request from the implemented Identity Object device locator. Unknown
requests retain explicit errors until their behavior is established.

This probe did not demonstrate the Studio GUI's Set Project Path, upload,
download or online monitor. ACD inputs, exact target configuration, job receipts
and packet samples remain in ignored local storage. The diagnostic CLI above
retains its loopback restriction; the appliance test used the separately
configured, target-allowlisted RockwellMCPServer instance.

The ASA naming in the native error refers to CIP in the
[FactoryTalk Linx SDK reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/lnxsdk-rm001_-en-e.pdf),
chapter 4. The remaining vendor request's response layout and later connection
stages still require separate evidence.

## References

- [Rockwell Logix data access manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm020_-en-p.pdf)
- [Rockwell Logix Designer SDK guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf)
- [pycomm3 client implementation](https://github.com/ottowayi/pycomm3)
