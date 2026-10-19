# Milestones

These are planned capabilities, not claims of current controller compatibility.
The current host-only appliance provides an isolated EtherNet/IP endpoint;
native Studio connection and programming services remain unfinished.

## Native Linx and Studio connection

Current milestone: `.36` keeps Windows appliance commands and the SSH tunnel
from opening console windows. `.35` fixes navigation to the Device I/O panel and clarifies
the unverified native GUI boundary in the webpage banner. `.34` adds scoped Data Table discovery and supported tag
descriptors. Native upload now reaches its first Data Table attribute list;
address and data-use fields remain unavailable. `.33` adds bounded symbol/template instance lists and empty
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
