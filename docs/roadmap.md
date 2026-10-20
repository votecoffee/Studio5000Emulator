# Milestones

These are planned capabilities, not claims of current controller compatibility.
The current host-only appliance provides an isolated EtherNet/IP endpoint;
native Studio connection and programming services remain unfinished.

## Native Linx and Studio connection

Current milestone: `.92` verifies replacement followed by insertion in the same
routine and [native SDK import/save/reopen of an edited ACD](edited-logic-l5x.md#optional-native-acd-save-diagnostic).
The saved ACD also passes a fresh SDK connection against an isolated emulator
loaded from its new source pair, and its saved edits execute. The post-edit SDK
tag-read diagnostic still fails online address discovery. Version `.91` verifies
[rung replacement across routines](supported-routine-edits.md#rung-replacement-across-routines),
and `.90` checks consecutive inserts while continuously online.
Next: broader operand/routine coverage,
Studio GUI acceptance and the native Test/Untest/Assemble lifecycle. Source-aware
upload/download completion and native tag-address discovery remain separate gaps.

Version `.77` adds [source-bound member verification](source-type-verification.md).
Staged type sizes, member locations, types and references must agree with the
original ACD metadata; mismatches reject temporary processing atomically. The
demo matches all 242 types and 13,312 members. Storage mapping, trailers and the
complete device-operation/commit contract remain unfinished.

Version `.76` adds [native Template member inspection](template-layout-inspection.md).
The demo download's 242 temporary Templates decode into 13,312 members; native
offset encodings and trailers remain opaque, and no storage mapping or execution
is enabled. Next: verify those encodings, member extents and nested types, then
source binding, the complete device-operation contract and atomic commit.

Version `.75` adds transactional [Run-entry initialization](run-entry.md).
Version `.74` ties signed Remote Run/Program requests and webpage controls to
the same server-owned scan worker, with native mode readback.

Version `.73` adds [temporary object graphs and reference checks](object-staging.md).
The remaining Symbol, Table, Program, Routine and coordination models cover
all 904 records in the tested batch, with no active execution. Next: compiled
definitions, the full device-operation contract, the further empty transport request
(`0x4D` on `0x412`), remaining transfer stages and atomic active-model commit.

Version `.69` adds [bounded temporary device-transfer fragments](transport-fragments.md).
The SDK stages a complete device payload and advances to service `0x06`,
which remains denied. Next: establish the full payload and operation contract,
then verified device preparation, further transfer stages, source-aware project
validation, atomic commit and rollback.
Library data, full native transfer, tag monitoring and online edits remain unfinished.

Version `.68` adds [temporary Resilient Transport setup](resilient-transport.md).
The SDK reached a segmented device-data request, which was denied in that revision.

Version `.67` adds [typed values for staged definitions](metadata-values.md).
The SDK reached Resilient Transport setup, which was denied in that revision.

Version `.66` adds [temporary metadata definitions](metadata-staging.md).
The SDK accepts definition names and reaches a metadata-value write, which
remains denied. Next: establish the metadata-value format and validation before
staging values, followed by library data, source-aware project validation, atomic
commit and rollback. Full native transfer, tag monitoring and online edits remain
unfinished.

Version `.65` adds [temporary library descriptors and the observed
signed transfer envelope](library-staging.md). The SDK now reaches Metadata
Definition creation. Library-data writes and metadata creation remain denied.
Next: validated metadata staging and a verified library-data contract, then
source-aware validation, atomic commit and rollback. Full native transfer,
tag monitoring and online edits remain unfinished.

Version `.64` adds [owner-scoped preparation](programming-preparation.md)
and acknowledgement of unchanged disabled redundancy. The SDK now reaches
library Create on class `0x37D`, which remains denied. Next: define bounded
library staging, validation and atomic commit or rollback before accepting
project changes. Full native transfer, tag monitoring and online edits remain
unfinished.

Version `.63` makes download-preparation checks repeatable through the
[public SDK probe](development.md#native-sdk-acceptance-probe), with admission and
cleanup checks for clients, lease, inhibit and programming authority. Full native
transfer, compiled tag-address discovery and online edits remain unfinished.

Version `.62` supplies native [software clock descriptions](clock-descriptions.md)
for upload inventory, including the actual app version. Fifteen Time Sync fields
remain unavailable, and full upload is unfinished.

Version `.61` supports owner-scoped Run Mode Inhibit with scan and
input-queue guards, readback and cleanup. The SDK accepts the write and reaches
Controller service `0x60`. Its initial response/status trials did not progress
beyond polling. See [Run Mode Inhibit](run-mode-inhibit.md). Version `.64`
extends that preparation state; transfer and monitoring remain unfinished.

Version `.60` adds a session-owned coordination lease and a
source-backed Local link-address read. Native download preparation advances
to a Run Mode Inhibit write, which was denied in that revision.
See [programming coordination](programming-coordination.md). Next: implement
the inhibit/state lifecycle, validated transfer staging and atomic commit or
rollback before admitting project changes. Full native transfer and monitoring
remain unfinished.

Version `.59` recognizes nested I/O Connection class paths and
supports a source-checked class-revision read. The SDK accepts that discovery
request; upload still fails controller collection. See
[I/O Connection discovery](io-connection-discovery.md).
Native tag-address discovery and programming remain unfinished.
The `.59` download trace rejected a nested Controller / Semaphore path.
Version `.60` supplies bounded coordination for that path; it grants no
project-transfer authority.

Version `.58` adds source-checked empty Data Logging discovery,
acknowledgements that retain an existing source Timeline UID, and visible native
policy rejections. See [native session policy](native-session-policy.md).
Complete native upload, tag-address discovery and programming remain unfinished.

Version `.57` adds source-checked empty I/O Map, tag-alarm and
Add-On Instruction definition discovery to the native read policy, plus
embedded-server status. The SDK accepts those reads; upload still fails
controller collection. See [native inventory discovery](native-inventory.md).

Version `.56` adds driver-backed Ethernet Link counter structures for
the tested Linux `e1000e` interface. Normal-source SDK upload now accepts that
list and reaches the incomplete Time Sync object. Full upload/download and
native tag/rung monitoring remain unfinished.

Version `.55` provides a repeatable, read-only native SDK acceptance
probe with private ACD copies, per-step results, runtime/source hashes and protocol
traces. Its rebuilt endpoint passes the SDK connection sequence; tag address
discovery and complete native upload/download remain unfinished. `.54` supplies
source-checked empty I/O and SFC force status for supported projects.

Version `.52` preserves source-bound Program IDs even for programs
without local tags. Read-only Program discovery supplies instance lists, class
counts and names; numeric program paths address their empty child catalogs.
Compiled address discovery and full native upload remain unfinished.

Version `.51` adds Symbol and Template class revision/count reads.
Maximum IDs and counts match each exposed catalog, including scoped Symbols
and nested Templates; private or unreferenced Templates are excluded from
enumeration. Native tag address discovery and full upload remain unfinished.

Version `.50` removes the fixed 480-byte cap from connected replies.
Class 3 messaging uses the negotiated T-to-O budget, up to 4,000 bytes including
its sequence word. Signed single/batch replies retain their bounds and write
denials. Native upload still needs earlier metadata gaps resolved.

Version `.49` adds a read-only local UTC clock to Time Sync, with
coherent microsecond/nanosecond list reads, explicit unsynchronized status and
zero PTP ports. Master offsets, clock descriptions and PTP networking remain
unfinished, alongside earlier Ethernet counter and handler-reference gaps.

Version `.48` adds Extended Device software-model metadata: unassigned
location, English locale, no trusted slots and no authorized system operator.
Source project name/description remain independent. Native upload still needs
Ethernet counters, handler references and remaining controller/clock metadata.

Version `.47` adds read-only Time Sync configuration from complete
L5X source. The PTP enable flag and priorities are available when explicitly
exported; missing settings, synchronization, clock measurements and port metadata
remain unavailable. Full native upload and SDK tag monitoring are unfinished.

Version `.46` adds source-checked empty PCCC mapping descriptors.
An isolated SDK diagnostic accepts them and reaches Time Sync (`0x43`), whose
metadata remains incomplete. Earlier missing Ethernet/controller fields still
prevent normal upload. Complete native upload and SDK tag monitoring are unfinished.

Version `.45` adds TCP/IP configuration status and verified Linux
DHCP/DNS flags. An isolated SDK diagnostic accepts that list and then requests
the unimplemented PCCC mapping object (`0x67`); earlier missing fields still prevent
normal upload. Complete native upload and SDK tag monitoring are unfinished.

Version `.44` adds field-level unsupported-read diagnostics to the
Connectivity panel, API and trace export. Native upload still fails controller
collection; missing fields are reported without assigning a root cause. Complete
native upload and SDK tag monitoring are unfinished.

Version `.43` adds controller compatibility settings and read-only
Linux Ethernet status. The deployed native test preserves scalar tag discovery and
returns these fields, but still fails controller collection. Handler-reference
encoding, Ethernet counters and remaining controller/device metadata need further
work. Complete native upload and SDK tag monitoring are unfinished.

Version `.42` adds backed ordinary scalar Symbol descriptors. The
deployed native upload test accepts all 12 supported demo descriptors and advances
to controller/device collection; Ethernet Link and Controller metadata
remain incomplete. Complete native upload and SDK tag monitoring are unfinished.

Version `.41` adds bounded empty energy inventory and source-checked
empty Message discovery. The native candidate passes those catalogs and reaches
Symbol address/configuration descriptors (`0x6B`); missing fields still prevent
tag upload and native tag monitoring. Energy support is limited to ordinary-tag,
software-controller-only projects; energy and MSG runtime behavior are unfinished.
`.40` adds source-checked empty HMIBC discovery and an explicit
unsupported reply to the exact native Base Energy probe. The native candidate
passes HMIBC discovery, then falls back to Base Energy Get Instance List (`0x4B`),
which remains unsupported. Button and energy runtime behavior remain unfinished.
`.39` adds source-checked empty Digital/Analog Alarm discovery
for projects without instruction alarm objects. The native candidate accepts both
lists and reaches HMI Button Control (`0x36E`) discovery. Nonempty alarm catalogs
and alarm execution remain unsupported. `.38` adds source-checked empty Axis Group, Axis and Coordinate
System discovery. An isolated native candidate accepts all three lists and
advances to Digital Alarm (`0x331`) discovery. Nonempty motion catalogs and motion execution remain unsupported.
`.37` adds backed model addresses and read-only full scalar
Data Table transfers. A native candidate accepts the demo's 12 supported scalar
values and reaches Axis Group instance discovery. Native tag/rung monitoring and
complete upload remain unfinished. `.36` keeps Windows appliance commands and the SSH tunnel
from opening console windows. `.35` fixes navigation to the Device I/O panel and clarifies
the unverified native GUI boundary in the webpage banner. `.34` adds scoped Data Table discovery and supported tag
descriptors. That native upload reached its first Data Table attribute list;
address and data-use fields were unavailable. `.33` adds bounded symbol/template instance lists and empty
extended-property discovery needed during upload initialization. `.31` preserves
source-bound ACD symbol IDs and routes native controller/program instance paths.
The `.30` implementation completes a
read-only native SDK Go Online/Online state/Program mode/Go Offline sequence and
stays Online across repeated polls. The
next acceptance stage is native tag address discovery: SDK tag reads currently
fail `RxDA_E_NO_ONLINE_ADDRESS`. Implement and verify that correlation layer
before claiming native tag/rung monitoring or complete Studio GUI compatibility.
See the [verified scope and limits](connectivity.md#native-sdk-online-connection).
The version-specific notes below record earlier investigation milestones.

- Preserve verified direct-IP discovery and device location. Linux broadcast
  discovery has datagram coverage; validate Linx range browsing separately with
  bounded packet captures.
- Implement the source-backed port/topology metadata and controller services
  required for native path selection and project correlation.
- Resolve the vendor object/service gaps observed by the
  [native connection probe](connectivity.md#observed-native-connection-gaps),
  with supported payload layouts and separate checks for each connection phase.
  The `.18` probe passes controller and File Manager class-revision queries;
  `.20` adds the observed Extended Device `0x64` / `0x4B` public-key challenge.
  Confirmation and authenticated Message Router services remain unsupported.
  `.21` adds offline `0x36`/`0x37` structural decoding and known-key request MAC
  verification, with no live dispatch. `.22` adds reply signing/verification;
  native `0x37` denial tests distinguish valid MACs from a damaged-MAC control.
  Resolve confirmation proof and session lifecycle before connecting that codec
  to live dispatch. Native `0x36` request/reply MAC controls now pass as well;
  temporary registration wire replies exposed the next vendor context request
  without implementing its semantics. See the
  [native sequence investigation](connectivity.md#native-signed-sequence-investigation).
  Version `.26` adds the read-only virtual Identity hardware/build fields
  requested after context binding. The isolated SDK accepts that list reply;
  later revisions address the class `0x8E` attribute `13` source metadata;
  cache/session semantics remain unresolved. Keep modeled values separate from native device
  provenance and security permissions.
  Subsequent isolated wire-shape trials reach class `0x349` service `0x53`
  and object-inventory discovery; they still fail before native Go Online.
  Version `.27` preserves scoped object paths and requested attribute IDs in
  offline capture reports to support further analysis without dispatching
  unknown vendor operations.
  Version `.28` adds source-backed SecurityCode and controller name/description
  reads, plus limited class discovery. The isolated SDK accepts these responses
  and reaches Safety Controller locked-state/signature queries. Resolve those
  requests with evidence while preserving the distinction between source
  metadata and live safety behavior. Native Go Online still fails.
  Version `.24` adds bounded offline `0x38` batch decoding and ordered child
  reply correlation, checked against 157 reference exchanges. Validate their
  MACs with a known key before adding authenticated batch dispatch.
  A passive reference capture now establishes the matching request and varying
  successful replies, followed by `0x64` / `0x4C` and Message Router services
  `0x36`–`0x38`; their vendor semantics still need implementation evidence.
- Demonstrate a read-only native Go Online session with a matching private ACD.
- Add upload, download and online editing as separate, explicitly tested stages.
  Upload must reconstruct types, tags, programs/routines and controller settings
  before it can produce a usable native project. Download needs a programming
  session and validated, atomic model replacement. Online editing additionally
  needs edit ownership, change history, test/assemble and rollback semantics.
  Current native attempts fail; `.34` discovery does not complete these stages.

Independent CIP client success and a Linx identity icon do not complete this
milestone. Keep exact native failure phases and protocol receipts locally.

## VMware-independent host-only networking

Status: planned. Provide a managed private network and isolated execution backend
without requiring VMware Workstation. Prefer existing free, maintained components
before developing a network driver or TCP/IP stack.

Acceptance criteria:

- Each emulated PLC gets an independent IP and TCP/UDP port 44818 while host Linx
  continues running.
- Windows Studio/Linx can reach the PLC by IP; verify unicast discovery, then
  supported range/broadcast browsing and device location separately.
- Preserve the existing model, browser UI, Windows ACD conversion and tray
  lifecycle across networking backends.
- Support repeatable start, shutdown and cleanup without changing physical
  interface configuration or interrupting existing automation communications.
- Define and review any required administrator setup, routing or adapter changes.
- Record exact component versions, licenses and local configuration receipts;
  keep machine-specific addresses, keys and captures out of the public tree.

Candidate architectures include a Linux container backend under WSL2, a portable
QEMU appliance with a private virtual adapter, and Windows network-compartment
integration. A new adapter or VLAN alone does not supply an independent network
stack. Avoid recreating a general network-lab platform inside the emulator.

### Existing tools

Assessment date: 2026-10-17. Suitability judgments below are project design
assessments; no integration with these products has been implemented or tested.

| Tool | Cost/licensing evidence | Fit for this project |
| --- | --- | --- |
| GNS3 | Free download; open-source components use GPLv3 | Useful optional lab integration for multiple PLCs, clients and routed networks. More orchestration than a single PLC endpoint needs. |
| EVE-NG | Legacy Community Edition is free but listed as end-of-life; the current release is freemium for limited personal/non-commercial use, with paid full features | A possible external lab environment, but not the preferred dependency for a maintained, freely usable backend. |
| Containerlab | Free, open source under BSD-3-Clause | Preferred evaluation candidate among these three for repeatable container topologies and independent PLC instances. Windows uses a Linux backend, normally WSL2. |

Primary sources:

- [GNS3 downloads](https://gns3.com/) and [GNS3 GUI source/license](https://github.com/GNS3/gns3-gui).
- [GNS3 Windows/local-server guidance](https://docs.gns3.com/docs/getting-started/setup-wizard-local-server).
- [EVE-NG downloads and edition lifecycle](https://www.eve-ng.net/index.php/download/) and [published edition terms](https://www.eve-ng.net/index.php/documentation/eula/).
- [Containerlab source and BSD license](https://github.com/srl-labs/containerlab) and [Windows/WSL setup](https://containerlab.dev/windows/).

Start by evaluating a plain Linux container endpoint and host reachability.
Containerlab can add topology management when it provides useful capabilities;
it is not itself a Windows virtual-network driver. EVE-NG and GNS3 similarly do
not remove the need for an execution backend with its own network stack.

## External device simulation

`.32` adds committed cached snapshots, a bounded transactional input queue and
an optional separate-process MQTT bridge. Device input batches apply between
scans with acknowledgements, access checks and source-generation guards.
See [Device I/O](device-io.md) for verified scope and setup.

Next: typed OPC UA subscriptions/writes, DDS integration where needed, an
independent SQL historian, device-owned input namespaces and optional simulation
clock synchronization. Keep protocol adapters and storage work outside the scan
path, and distinguish sampled current state from a lossless transition log.

## Execution coverage

Continue expanding instruction and data-type models, task scheduling, strings,
packed Boolean data and predefined structures. Preserve unsupported-feature
reporting and the separation between modeled behavior and native validation.
