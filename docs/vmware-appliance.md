# VMware host-only appliance

This optional mode runs the emulator in a small diskless Alpine Linux VM on an
existing VMware host-only network. Its TCP/UDP port 44818 belongs to the guest's
network stack, so a host application can retain its own wildcard listener.
Studio 5000 and FactoryTalk Linx stay on Windows.

This resolves host port ownership. The appliance enables the experimental
[anonymous native read-only session](connectivity.md#experimental-native-read-only-session).
The native SDK completes Go Online, reads Online/Program state and goes Offline
for the tested demo. Studio GUI monitoring, upload/download and online edits
remain unverified. See the [connection scope](connectivity.md#native-sdk-online-connection).

## Prepare

Requirements:

- Windows with Python 3.13, OpenSSH client and VMware Workstation `vmrun`.
- An existing VMware host-only network with DHCP, normally `VMnet1`.
- Optional image-building dependency: `pycdlib==1.14.0`.
- Internet access during preparation to download official Alpine media/packages.

From the repository root:

```powershell
py -3.13 -m pip install --target .local/vmware/build-deps pycdlib==1.14.0
py -3.13 -X utf8 source/tools/vmware_appliance.py prepare
```

The builder checks the pinned Alpine virtual ISO's SHA-256, adds the application
and offline packages, and generates guest/client SSH keys. Alpine retains its
normal signed package verification. A private manifest records package versions,
download URLs and hashes. Operating-system packages retain their own licenses.

The default generated directory is `.local/vmware/appliance`. Images, keys, logs,
imports and receipts stay there or in the neighboring private download cache.
Do not publish generated images or keys. No guest disk, Windows license or
Studio installation is required. The guest uses 768 MB RAM and two virtual CPUs.

`--network VMnetN` selects another existing host-only network; NAT and bridged
networks are rejected. The builder does not create adapters, assign host IPs,
change DHCP configuration, open firewall ports or stop/reconfigure Linx.

## Start and connect

Run `START-VM.cmd`, or:

```powershell
py -3.13 -X utf8 source/tools/vmware_appliance.py start
```

The launcher starts the VM in the background, discovers its DHCP address, verifies
its SSH host key and opens the browser through a localhost-only SSH tunnel.
The web service remains on guest loopback; the forwarded Windows address is
`http://127.0.0.1:8786`. The header shows the exact running version, PLC endpoint IP and VMware appliance
status. The Windows launcher supplies the tray controls.

Read the current guest address with:

```powershell
py -3.13 -X utf8 source/tools/vmware_appliance.py status
```

Add that **guest IP only** to the FactoryTalk Linx Ethernet driver's device/browse
list. Linx uses port 44818 automatically. A host-only network connects the guest
to its Windows host without placing it on the physical LAN. See
[VMware networking types](https://knowledge.broadcom.com/external/article?legacyId=1006480).

The Linux appliance also supports directed and limited broadcast discovery on
its selected Ethernet interface. The **Connectivity** tab reports whether these
listeners are available. Keep the direct guest-IP entry as the established Linx
workflow; Linx range browsing still needs separate native validation. See the
[broadcast discovery contract](connectivity.md#broadcast-discovery).

The appliance starts the read-only ConveyorDemo endpoint with the experimental
L85E v35 identity. **Allow tag writes** remains an explicit opt-in.

## Ping and IP scanners

The appliance answers IPv4 ICMP echo requests at the **guest IP** shown in the
webpage header and `status` output. Startup explicitly enables unicast echo
replies in the guest network stack. Ping has no TCP or UDP port setting and
continues to work while the VM is powered on, even if the CIP endpoint is stopped.

Run the IP scanner on the Windows host and select the existing host-only adapter
and its subnet. Enable ICMP echo discovery, or probe TCP port 44818 while the
endpoint is running. The browser's `127.0.0.1:8786` address is the local UI tunnel;
use the guest IP as the scanner target. An HTTP-only scan will not find the UI
at the guest IP because the guest web service binds to loopback.

The host-only network is separate from the physical LAN. Scanning it from
another physical computer requires separately configured routing; this launcher
does not add routes or change the Windows firewall. For an app running directly
on Windows, ICMP replies come from Windows and depend on that host's firewall
configuration. The Python CIP endpoint does not create an ICMP listener.

Ping confirms IP reachability. EtherNet/IP identity discovery and Studio Go
Online remain separate checks.

## Import projects

Complete L5X exports can be opened directly in the browser. For ACD files, use
the Windows tray's **Import ACD / L5X...** menu. Conversion runs on Windows using
the configured native `l5xgit` tool, then sends the resulting L5X to the guest.
The original ACD is preserved and rehashed. Native conversion still requires a
compatible Studio 5000/SDK installation.

The same operation is available from the CLI:

```powershell
py -3.13 -X utf8 source/tools/vmware_appliance.py import --project .local/projects/demo.ACD --converter .local/tools/l5xgit.exe
```

`--converter` is optional when `LOGIXLAB_CONVERTER`, `PATH`, or the normal Windows
LogixLab import settings provide its location. Conversion copies, logs and
provenance stay under the appliance's private `imports/` directory. The guest
accepts an import only if it satisfies the active identity profile's source
requirements.

## Stop, restart and update

**End session** stops the guest app; its Windows manager then powers off the VM.
The Windows tray's **Quit LogixLab** also shuts it down. Closing the browser
leaves the appliance running. CLI shutdown:

```powershell
py -3.13 -X utf8 source/tools/vmware_appliance.py stop
```

This is a diskless appliance. Runtime memory, guest imports and guest settings
are temporary; a cold start loads ConveyorDemo again. Export snapshots before
ending a session when needed. The manager keeps recent observed state privately,
and explicit launcher shutdown attempts a final snapshot before stopping the app.
These receipts do not automatically restore the model.

To activate a new app revision, stop the appliance and rebuild its image:

```powershell
py -3.13 -X utf8 source/tools/vmware_appliance.py prepare --rebuild
START-VM.cmd
```

Rebuild refuses a running appliance and retains its keys and MAC address. The
launcher rejects a source/image version mismatch. The guest's DHCP address can
change; check `status` before updating a saved Linx browse entry.

## Diagnostics

Private files include `serial.log`, `vmware.log`, `ssh.log`, `appliance.json`,
`session.json`, `last-state.json`, and any captured import/snapshot receipts.
`appliance.json` identifies the exact VM; the manager refuses manifests pointing
at another VM. Application instance IDs prevent a reused UI port from directing
imports or quit requests to a different app session.

The protocol endpoint is available only on the host-only guest adapter. The guest
has no NAT adapter or physical bridge. SSH uses a generated key and pinned host
identity with password authentication disabled; the app runs as an unprivileged
guest account.
