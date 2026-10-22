# Software clock descriptions

Version `0.6.0-connectivity.62` adds read-only Time Sync descriptions for the
local software clock. These fields identify the emulator during native inventory
reads, including the SDK's upload preparation. Full native upload remains
unfinished.

## Wire contract

Time Sync class `0x43`, instance `1`, supports Get Attribute Single (`0x0E`)
and Get Attributes List (`0x03`) for these attributes:

| Attribute | Meaning | Value |
| --- | --- | --- |
| `21` | Product description | `Studio5000Emulator;LogixLab;` |
| `22` | Revision data | `;;` followed by the running app's full version |
| `23` | User description | Empty, unassigned text |

Each value starts with a little-endian UDINT UTF-8 byte count, followed by
exactly that many bytes. There is no terminator or fixed-width padding. Product
and revision fields use semicolons to separate their three components. Serial,
hardware and firmware components are blank because this is a software model.
Limits are 64, 32 and 128 Unicode symbols, respectively. An invalid or overlong
revision is unavailable instead of silently truncated.

The layouts follow the Time Sync instance table in Rockwell's
[Dynamix 1444 manual, Table 292](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/1444-um001_-en-p.pdf).
The revision format and blank components are also described by TI's
[Time Sync revision-data API](https://software-dl.ti.com/processor-industrial-sw/esd/ind_comms_sdk/am243x/11_00_00_08/docs/am243x/ethernetip_adapter/group___e_i___a_p_i___a_d_p___t_i_m_e_s_y_n_c_gaa10f1e08f8a39a2597bf816e8e57f105.html).
Installed plain v35 attribute definitions independently identify the field IDs,
widths and text limits; vendor files are not distributed.

## Behavior and limits

Descriptions do not sample or adjust host time, execute scans, or modify source
settings, tag values or queued device inputs. They are available independently
of an exported TimeSynchronize declaration. Revision data uses the same app
version as the executable and webpage. Connectivity `time_sync.software_clock`
metadata exposes the software version and description attributes.

Version `.152` adds separate [local software-clock identity reads](software-clock-identity.md).
The original `.62` scope below remains historical.

No manufacturer OUI, hardware serial number, hardware revision or firmware
revision is assigned. The compatibility profile's controller identity is
separate. Clock identity, PTP node type, grandmaster/parent measurements and
vendor clock/port description structures remain unavailable. The clock remains
unsynchronized with zero PTP ports. Time Sync setters retain their errors.

## Validation

Tests cover byte-counted single reads, reordered and duplicate list fields,
per-field errors, accurate gap reporting, version and Unicode boundaries,
unchanged modeled state, and retained setter denials. The SDK's 32-field Time
Sync request is checked against the exact expected response, including errors
for the fifteen remaining unsupported fields.
The 848-test suite passes on Windows and Linux with two and one expected
platform skips, respectively.

The packaged and deployed `.62` runtime and served browser assets match the
committed source. All 268 wire checks pass, including exact single and reversed
list description replies and a retained setter denial. The public native SDK
completes its nine-step connection/Offline sequence with 81 verified signed
requests. Its upload request receives all three descriptions with successful
per-field statuses, alongside errors for the fifteen remaining unsupported Time
Sync fields. Upload still fails controller collection across 197 requests; tag
reads still fail online-address discovery across 83 requests without sending
tag-read packets. These probes preserve source bytes and modeled state.

A fresh native download probe verifies 104 signed requests, accepts Run Mode
Inhibit and fails `RxCsE_ASA_NO_PERMISSION` at Controller service `0x60`. Every
probe confirms Offline cleanup. The final endpoint has no TCP clients, a free
lease, zero inhibit mask and scan count zero. Original ACD bytes, modeled values
and model time remain unchanged. FactoryTalk Linx and the Logix Designer SDK
service remained running.

Native upload and download acceptance, Studio GUI monitoring and online edits
remain separate milestones. Controller service `0x60` still rejects download
preparation; an operation-identifier substitution also left the SDK polling and
is not shipped. See [Run Mode Inhibit](run-mode-inhibit.md).
