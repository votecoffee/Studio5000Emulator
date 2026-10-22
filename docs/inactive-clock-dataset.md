# Inactive Time Sync dataset

Version `.154` supplies the remaining twelve fields of the v35 Time Sync
collection when a complete controller source explicitly declares
`TimeSynchronize PTPEnable="false"`. This is initialized simulator state. It
does not start a PTP engine, communicate with a master or measure a network.

## Model and wire contract

The existing source parser must accept the declaration. Missing, ambiguous,
context-only or enabled PTP source does not receive this inactive substitute.
The imported enable and priority settings retain their source values.

| Attribute | Inactive software value |
| --- | --- |
| 5, 6, 7 | Initialized zero offset, maximum offset and path delay; unmeasured |
| 8, 9 | Empty grandmaster and parent structures, 24 and 16 bytes |
| 18 | Local inactive domain zero, without joining a PTP domain |
| 19 | Clear clock-role mask: no PTP role advertised |
| 20 | Four zero bytes for an unassigned manufacturer identity |
| 27 | Zero initialized steps, without a master path |
| 102 | Application clock identity and unassigned port zero |
| 103 | Same identity, clear type/manufacturer/profile, six counted product/revision strings |
| 104 | Same identity, unassigned port zero, empty protocol and address fields |

The inactive offset and empty master conventions are emulator design choices,
not a claim that IEEE 1588 mandates these defaults or that zero error was
measured. The API exposes `inactive_dataset.measurement_valid=false`, with
`master_assigned=false` and `parent_assigned=false`. Synchronization stays false
and every port array retains a zero count. Port zero does not create a port.

The local clock identity follows the existing
[application-lifetime identity contract](software-clock-identity.md). Invalid
application IDs withhold fields 102–104. Attribute 103 shares the product and
revision validation used by attributes 21/22, with USINT-counted UTF-8 fields
instead of their UDINT-counted descriptions. No hardware revision, firmware
revision, serial, assigned OUI or PTP profile is invented. The manufacturer
field is unassigned software state, not a claimed IEEE allocation.

Rockwell's [TimeSynchronize reference](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/input-output-instructions/access-the-timesynchronize-object.html)
defines the standard field meanings and clock-role bits. TI's
[Time Sync object documentation](https://software-dl.ti.com/processor-industrial-sw/esd/motor_control_sdk/am263px/10_02_00_11/ind_comms_sdk/docs/am263px/ethernetip_adapter/group___e_i___a_p_i___a_d_p___t_i_m_e_s_y_n_c.html)
documents the byte-sized domain and four-byte manufacturer field. LinuxPTP's
[default configuration](https://www.linuxptp.org/documentation/default/) uses an
unassigned zero manufacturer configuration; an assigned manufacturer should
use its own OUI. The installed plain v35 definitions establish the vendor
aggregate layouts, independently checked by the bounded offline decoder.

## Validation and limits

Focused checks cover the complete 32-field list, exact structure widths,
duplicate fields, one time sample, source gating, invalid identities/revisions,
API availability, read-only behavior and source/model/audit preservation.
Time reads remain host UTC and independent of scan time. The empty dataset
does not confer write authority or establish native upload completion.
