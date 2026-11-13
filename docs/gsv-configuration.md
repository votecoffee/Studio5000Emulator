# Configuration and identity GSV

The explicit v35 ControlLogix 5580 profile supports source-configuration reads
in ladder and Structured Text. Existing [audit-value GSV](controller-gsv.md)
keeps its original 64-bit destination contract. [Wall-clock GSV](wall-clock-gsv.md)
adds separate host UTC CurrentValue/DateTime and qualified LocalDateTime reads;
these are runtime clock samples rather than source-configuration attributes.
[TimeSynchronize counters](wall-clock-gsv.md#timesynchronize-clock-reads) expose
the same software UTC in microseconds and nanoseconds.
[Scan-time GSV](scan-time-gsv.md) separately reads committed Program/Task
LastScanTime and MaxScanTime through the existing interpreter counters.

```text
GSV(Task,FastTask,Rate,FastRate);
GSV(Task,FastTask,Priority,FastPriority);
GSV(Task,FastTask,Name,TaskName);
GSV(Controller,,TimeSlice,CommTimeSlice);
```

In a whole-project ladder scan, a handler that clears an out-of-bounds
operand can skip the GSV write or SSV setting change and continue the rung.
See [GSV and SSV array recovery](controller-handlers.md#recover-gsv-and-ssv-array-faults).

[SSV WallClockTime settings](wall-clock-set.md) add CurrentValue from a scalar
DT/LINT or two DINT cells, plus DateTime and UTC-qualified LocalDateTime from
seven DINT cells or leading user-record members. Clock changes commit with a successful
advance and are visible to GSV and the software clock services.

## Attributes and types

| Class | Attribute | Destination type | Scope |
| --- | --- | --- | --- |
| Program | Name | STRING or explicit user string | Named ordinary nonfolder Program or current Program |
| Routine | Name | STRING or explicit user string | Named Routine in the current Program or current executing Routine |
| Task | Name | STRING or explicit user string | Existing named Standard Continuous/Periodic or qualified Event task |
| Task | Instance | DINT | Current emulator registry slot from 0 through 31 |
| Task | Rate | DINT | Effective Periodic rate, or [defined Event timeout](event-tasks.md#runtime-timeout-settings), in microseconds |
| Task | EnableTimeOut | DINT | Current Event timeout enable, 0 or 1 |
| Task | Watchdog | DINT | Effective setting in project execution, explicit positive source setting in a harness, in microseconds |
| Task | Priority | INT | Effective Periodic/Event priority in project execution, explicit source priority in a harness |
| Task | InhibitTask | DINT | Explicit source flag, 0/1 |
| Task | DisableUpdateOutputs | DINT | Explicit source flag, 0/1 |
| Controller | Name | STRING or explicit user string | Explicit unambiguous source name |
| ControllerDevice | DeviceName | SINT[33] window | Counted catalog name from ProcessorType |
| ControllerDevice | ProductCode, ProductRev, Type, Vendor | INT | v35 5580 model identity |
| ControllerDevice | Status | INT | Controller mode sampled at scan entry |
| Module | LEDStatus | INT or DINT low word | Complete controller-only map or complete simulated module inventory with a determinable aggregate |
| Module | ForceStatus | INT or DINT low word | Complete controller-only I/O map |
| Module | Mode | GSV to INT or DINT low word, SSV from INT | Named local or qualified Ethernet module with explicit Inhibited and MajorFault settings |
| Module | EntryStatus | INT or DINT low word | Explicit Inhibited setting on the target and a modeled inhibit, waiting condition or simulated connection |
| Module | FaultCode | INT or DINT low word | Effective simulated connection |
| Module | FaultInfo | DINT | Effective simulated connection |
| Message | ConnectionPath | 82 contiguous SINT elements | [Named configured MESSAGE tag in whole-project ladder](ladder-message.md#supported-configuration-and-timing) |
| Message | UnconnectedTimeout | DINT or TIME32 | [Named configured MESSAGE tag in whole-project ladder](ladder-message.md#supported-configuration-and-timing) |
| Message | ConnectionRate | DINT or TIME32 | [Named connected MESSAGE tag in whole-project ladder](ladder-message.md#supported-configuration-and-timing) |
| Message | TimeoutMultiplier | SINT | [Named connected MESSAGE tag in whole-project ladder](ladder-message.md#supported-configuration-and-timing) |
| Module | Path | SINT window in a one-dimensional array | Source-proven local backplane, IPv4 Ethernet, or remote ControlLogix backplane route |
| Controller | TimeSlice | INT | Explicit source setting, 10..90 |
| Controller | ShareUnusedTimeSlice | INT | Explicit source setting, 0/1 |
| Controller | CanUseRPIFromProducer | DINT | Explicit Controller setting, 0/1 |
| Controller | RedundancyEnabled | SINT | Explicit RedundancyInfo Enabled flag, 0/1 |
| Controller | KeepTestEditsOnSwitchover | SINT | Explicit RedundancyInfo retention flag, 0/1 |
| Controller | InhibitAutomaticFirmwareUpdate | BOOL | Explicit Controller setting, 0/1 |

Class, attribute and object lookup are case insensitive. Returned names retain
source spelling. Task references use literal configured names or
[THIS in ordinary scheduled Program routines](current-instance-gsv.md).
Controller, ControllerDevice and collection-wide Module status reads use an
empty instance operand. Mode, EntryStatus and Path require a module name. Numeric
object references and AOI/harness THIS contexts remain outside the profile.

Structural preflight validates destinations without reading saved dynamic
indices. ST FOR effects cover complete static cells/strings and conservatively
widen changing/alias/AOI outputs across enclosing arrays.

Metadata must come from a complete loaded source snapshot. Task times use the
existing exact source milliseconds-to-microseconds conversion. For example,
10 ms reads as 10000 and 500 ms as 500000. Missing, malformed, zero-watchdog or
unqualified settings fail explicitly; compatibility defaults do not become GSV
source values. Continuous rate/priority remain unqualified. Event settings
require the [qualified Event project context](event-tasks.md). Event Rate is
available when source enables the timeout with an explicit rate or when SSV
defines one. A defined period remains readable while the timeout is disabled.

## TimeSynchronize status and settings

Ladder and ST can read these attributes with an empty TimeSynchronize instance.
They use the same explicit source settings and software clock state as CIP:

| Attribute | Exact destination type | Software value |
| --- | --- | --- |
| PTPEnable | DINT | Explicit source PTPEnable, as 0 or 1 |
| Priority1 / Priority2 | SINT | Explicit source priority byte, stored as signed SINT |
| IsSynchronized | DINT | 0: the software clock has no synchronized master |
| NumberOfPorts | INT | 0: the software clock has no PTP ports |

Priority values above 127 retain their unsigned byte pattern: 128 reads as -128
and 255 as -1 in a decimal SINT watch. Use hexadecimal, or interpret the byte
as unsigned, to view the configured priority. PTPEnable is configuration intent;
even when the source requests PTP, IsSynchronized remains zero in this model.
These reads do not sample UTC or require a working host clock.

The existing complete v35 5580 configuration-source rules apply. Missing,
ambiguous or invalid source enable/priority settings are unavailable and block
those reads, including false calls. IsSynchronized and NumberOfPorts remain
known software state when no TimeSynchronize source element exists. Typed
destinations, scoped aliases, selected elements and existing AOI bindings use
structural preflight, lazy live indices, full writes and whole-advance rollback.
ST FOR protection tracks the complete destination. This adds no SSV settings,
PTP messages, master measurements or native status/fault/lifecycle equivalence.

In **System lab**, set SyncStatusIndex=1 and enable ReadSyncStatus. The source
explicitly disables PTP and sets priorities 128/255. Ladder reads enable/status/
ports as zero and priorities as -128/-1. SyncStatusWords[1] receives status zero;
guard cells retain 101/999. ST reads match when ReadConfig is enabled and FastTask
runs. SyncStatusDivisor=0 faults after the reads; restore 1 to retry. Disable the
gate before returning its index to 99. Current-time reads retain their separate
[clock profile](wall-clock-gsv.md#timesynchronize-clock-reads).

The source basis is installed v35 accessing_the_time_sync_object and the
[Rockwell TimeSynchronize reference](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/input-output-instructions/access-the-timesynchronize-object.html).

## Object identity reads

Program Name and Routine Name use the current loaded source catalogs. Both
require an ordinary scheduled caller. Program THIS selects its owning Program.
Routine THIS follows the executing routine through JSR and nested Event calls.
A named Routine resolves within the caller's Program. String writes update LEN
and the active DATA bytes and retain the unused backing bytes.

Task Instance reads the zero-based Task slot in the current emulator registry.
Slots follow the loaded Task inventory. A changed registry makes the attribute
unavailable until reload. These values are separate from native CIP instance
IDs. Task Instance requires project execution.

```text
GSV(Program,FastProgram,Name,StObjectProgramName);
GSV(Routine,THIS,Name,ObjectRoutineName);
GSV(Task,THIS,Instance,ObjectTaskSlot);
```

Open **System lab**, enable ReadObjectIdentity and step. The ladder routine
ReadCurrentInstances reads BackgroundProgram, ReadCurrentInstances and slot
0. The ST routine ReadSettings reads FastProgram by name, ReadSettings via THIS
and SlowTask slot 2. ST also uses the existing ReadConfig gate.

The operand types follow the installed v35 Program, Task and Routine help
topics 14638, 14646 and 14651. Native instance identity and execution parity
remain separate.

## Controller source flags

Ladder and ST can read four explicit settings from the loaded project with an
empty Controller instance operand. The RPI setting uses DINT, redundancy and
test-edit retention use SINT, and firmware-update inhibition uses a BOOL cell.
Missing, ambiguous or invalid flags are unavailable. RedundancyInfo must be
canonical. The BOOL read requires a saved value of 0 or 1 and a declared BOOL
destination.

Enable ReadControllerFlags in **System lab** and step 25 ms. Ladder reads
UseProducerRpi (1) and RedundancyFlag (0). ST reads RetainTestEdits (1) and
FirmwareUpdateInhibit (true) with ReadConfig enabled. The flags are read-only.
Native RPI negotiation, redundancy switchover and firmware services are outside
the software model. The 5580 data-table padding attribute is outside this
instruction profile. [Rockwell Controller reference](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/instruction-set/input-output-instructions/access-the-controller-object.html)
[5580 migration guidance](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm100_-en-p.pdf)

## Controller device identity

ControllerDevice reads the loaded v35 ControlLogix 5580 model's catalog name,
product code, firmware revision, device type (14), and vendor (1). The complete
source must declare the processor and major revision explicitly. ProductRev
also requires an explicit byte-sized MinorRev. Its low byte is the major
revision and its high byte is the minor revision. The destination is a signed
INT, so show it in hexadecimal to see the packed word.

DeviceName writes the ASCII character count, the catalog name, and zero
padding into 33 writable SINT elements. A larger array or an indexed start
works when the complete window fits in the selected array. Bytes outside
the window retain their values. The catalog name comes from the project
processor, independent of the endpoint's advertised identity profile.

In **System lab**, enable ReadControllerDevice and step 25 ms. Ladder writes
DeviceNameBytes, product code 168, and revision 16#0B23. ST writes device type
14 and vendor 1. ST also uses the existing ReadConfig gate. Physical serial
numbers and native ControllerDevice execution remain unqualified. These reads
follow installed v35 help topic 14635.
[Rockwell ControllerDevice reference](https://www.rockwellautomation.com/en-pr/docs/studio-5000-logix-designer/38-02/contents-ditamap/instruction-set/input-output-instructions/access-the-controllerdevice-object.html)

### Controller device status

ControllerDevice Status uses the same INT word as the emulator's Logix
EtherNet/IP Identity status. The virtual keyswitch remains Remote. Every
routine in an advance sees the mode sampled at its entry.

| Scan entry | Status word |
| --- | --- |
| Manual Step in Remote Program | 16#3070 |
| Background scan in Remote Run | 16#3060 |
| Manual retry entered while the emulator still reports a software fault | 16#3450 |

A failed advance rolls back the destination. If a manual retry succeeds, the
next step samples Remote Program. Switching back to Program updates the
endpoint immediately. The GSV destination retains its last value until a scan
reaches the instruction.

Enable ReadControllerDevice in **System lab**. Compare DeviceStatus in ladder
and StDeviceStatus in ST after Step, Run, and another Step in Program.
The software model covers these modes and the existing emulator fault word.
Native fault classifications, debug, and transition flags remain unqualified.

## Controller-only Module status

Ladder and ST can read LEDStatus and ForceStatus with an empty Module instance
operand. A complete v35 5580 project with a visible controller-only I/O map
returns zero for both. LEDStatus reports no I/O modules. ForceStatus reports
that I/O forces are neither installed nor enabled.

An INT destination gets the complete value. A DINT destination gets the low
16 bits and retains its upper word. That DINT must have a known value when
the instruction executes. A skipped call retains its destination.

Enable ReadModuleStatus in **System lab** and step 25 ms. Ladder sets
IoLedStatus to zero. ST clears the low word of IoForceStatus, changing
16#1234FFFF to 16#12340000, with ReadConfig enabled.

Projects with configured external modules, produced or consumed tags, force
declarations or opaque I/O source are outside this profile. Hardware LED
behavior and force control remain unqualified.
[Rockwell I/O status](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf)
[Rockwell force status](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm004_-en-p.pdf)

## Simulated Module LEDStatus

Use `GSV(Module,,LEDStatus,Destination)` in ladder or ST. A qualified
external inventory includes every declared module, with explicit routes
and Inhibited settings. The aggregate uses effective states, including
any Mode changes made earlier in the same scan.

| Value | Modeled condition |
| --- | --- |
| 0 | Controller-only inventory with zero configured modules |
| 1 | No module is Running |
| 2 | At least one module is Running and at least one is Faulted, Inhibited or Waiting |
| 3 | Every module is Running |

An unknown connection state can still yield 2 if both sides of the
condition are known. Otherwise an ambiguous read faults and rolls back
the scan. Incomplete or opaque module inventories fail preflight. A
false rung skips the read and keeps its destination. The INT value can
also be read into the low word of a known DINT.

In **Module status lab**, set PointAdapter to `faulted` using the
[simulated connection input](#simulated-module-connection), enable
ReadLed, and step. ModuleLed reads 1 because the other modules are
inhibited or waiting. Set PointAdapter to `running` and step to see 2.
These values are simulated GSV results. The native I/O Map and physical
indicator behavior remain separate.
[Rockwell Module object and LEDStatus values](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/input-output-instructions/access-the-module-object.html)

## Named Module status

In a complete v35 5580 project, a Program routine can use ladder or ST to
read settings for an unambiguous named module under Local or on a
qualified Ethernet or remote chassis route. The initial Mode uses the
explicit L5X boolean fields MajorFault for bit 0 and Inhibited for bit 2.
EntryStatus returns 16#6000 when the named module is inhibited. An
uninhibited module returns 16#7000 when a validated parent or ancestor
on its route is inhibited or explicitly simulated as faulted. With
neither condition, the read uses the simulated connection state for the
target. If the target lacks an explicit state, the read faults the advance.

Both reads support INT and the low word of a known DINT, with the upper
word preserved. Destination indices are resolved only when a call executes.
An invalid reached destination rolls back the scan.

In scheduled project logic, SSV Mode takes an exact scalar INT tag and
replaces both defined bits. The supported words are 0, 1, 4 and 5. Values
with other bits set fault the advance. A false rung or skipped ST call
leaves the mode alone and defers source selection. Later GSV calls in the
same advance see the change. The override commits with tag values, so a
later fault restores the previously committed mode. Run entry and
routine replacement retain it. Reset, project reload and changing
execution scope restore the L5X settings.

Open **Module status lab** from Examples, set ReadModule to true, and step.
StateWord becomes 16#6000, ModeWord changes from 16#1234FFFF to 16#12340005,
and StMode reads 5. A masked ladder comparison sets ModuleInhibited.
Set ModeCommand to 1 and enable ApplyMode. On the next step, the readback
changes to 1 and ModuleInhibited clears. StateWord retains its last value
because the read is skipped. Set ModeCommand to 4, disable ApplyMode and
enable ApplyModeST to restore the inhibit through ST.

The same ReadModule scan reads RemoteInput as 16#7000 because RemoteRack
starts inhibited. Set RackModeCommand to 0 and enable ApplyRackMode to
clear the parent inhibit. The sample gates the EntryStatus call with the
parent's Mode bit 2. RemoteWaiting clears and RemoteStatus retains its
last value while the call is skipped. Set RackModeCommand to 4 to see
Waiting again. The remote route bytes are available in either mode.
[ModuleStatusLab.L5X](../source/samples/ModuleStatusLab.L5X)

AOI module references, cyclic data and live connection diagnostics remain
open. Bit 0 controls whether a [simulated connection loss](#required-module-loss-during-run)
trips the controller.
[Rockwell Module object](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/instruction-set/input-output-instructions/access-the-module-object.html)
[Rockwell module states](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/status.html)
[Rockwell L5X import/export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)

## Simulated module connection

In the **Device I/O** tab, use **Simulated Module Connections** to set
Running, Faulted or Clear input for a module with a qualified route and
a declared Inhibited setting. The panel displays the applied input and
effective state separately. An inhibited module can have a Running input
while its effective state remains Inhibited. Step or run the logic to
read the result into tags with GSV.

Automation can use the local session's token-protected POST
`/api/module-connection`. Send the current
`project_generation` from `/api/state`. The command is serialized
between scans and rejects stale project generations. It applies to the
active simulation. Routine edits retain the input. Reset, a new project,
an execution-scope change or a native download installation clears it.

A `running` input gives EntryStatus 16#4000 and zero for both diagnostic
fields. A `faulted` input gives EntryStatus 16#1000 and requires a
nonzero 16-bit `fault_code` and a signed DINT `fault_info`. FaultCode
preserves the code's bit pattern in an INT or the low word of a DINT.
A `clear` input removes the explicit state. Own inhibit and a waiting
condition take precedence over simulated connection inputs. FaultCode
and FaultInfo require an effective running or faulted input. Reaching
them without one faults the advance. Input persists independently of a
failed scan, and the scan's tag and Mode writes roll back.

Open **Module status lab**, then **Device I/O**. Select PointAdapter
and Faulted. Enter 516 for Fault code and -42 for Fault info, then
select Apply connection. The equivalent local session command is below.

```javascript
await api('module-connection', {
  project_generation: state.project_generation,
  module: 'PointAdapter', state: 'faulted', fault_code: 0x0204, fault_info: -42
})
```

Enable ReadConnection and step. PointStatus reads 16#1000, PointFaultCode
reads 16#0204, and PointFaultInfo reads -42. Apply Running for the same
module and step to see Running and zero diagnostics. The local
simulation input covers these steady states. Automatic reconnection
and real module communication remain open.

## Required module loss during Run

In whole-project Remote Run, changing a module's effective connection
from Running to Faulted trips a latched Type 3 Code 16 I/O major fault
when bit 0 of its effective Mode word is set. The command applies at a
scan boundary and preserves the completed scan count. A configured handler
can write diagnostics and [clear the controller fault in ladder logic](controller-handlers.md#clear-an-active-fault-in-ladder-logic).
Device I/O retains the applied input.
`/api/state` exposes the controller fault under
`controller.module_major_fault` with `type`, `code`, the canonical
`module` name, the injected `fault_code` and `fault_info`, the `fault_id`
for this occurrence, and `clear_ready`.

Loss of an optional module leaves Run active unless it interrupts a
[required connection downstream](#required-module-loss-through-an-upstream-fault).
A module that was inhibited, waiting or unknown cannot directly trip the
controller on a fault injection. Program-mode changes and isolated routine
harnesses leave the controller latch alone. A supported [controller fault handler](controller-handlers.md#simulated-io-fault-capture)
can record the simulated fault before recovery.

In **Module status lab**, set ModeCommand to 1 and ApplyMode to true,
then Step once to uninhibit RackOutput and keep it required. Set
ApplyMode back to false. Under **Device I/O**, apply Running to RackOutput,
start Run, then apply Faulted to RackOutput with fault code 516 and
fault info -42. The browser displays **I/O MAJOR FAULT · 3/16**. Applying
Running again restores the module's displayed state. Choose **Clear I/O
major fault** to clear the controller latch and return to Program. Tags,
simulated time, scan counters and connection inputs are preserved. Choose
**Run** separately to perform the usual prescan and resume execution.
**Reset** remains available to reinitialize the project.

Automation can send a token-protected POST to
`/api/module-major-fault-clear` with the current `project_generation` and
`fault_id` from `/api/state`. The faulting module must be effectively
Running. An unknown or waiting module cannot qualify, and an identifier
from a previous fault cannot clear a later one. The response is the updated
emulator state. Clearing this simulated fault is a local control.
[Rockwell Logix 5000 Controllers Information and Status](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf)
[Rockwell Clear Faults help](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/studio-5000-logix-designer/controller-properties/clear-faults.html)

## Required module loss through an upstream fault

A simulated Faulted input on a routed upstream module can take a required
downstream module from effective Running to Waiting during whole-project Run.
This trips Type 3 Code 16 even when the upstream module is optional. The
latched record names the required module in `module` and the injected source
in `upstream_module`. Its `fault_code` and `fault_info` come from the injected
upstream fault. The downstream module retains its own staged input and
reports Waiting. If the upstream module also qualifies for a direct trip,
it is reported first. Otherwise the first affected required module in source
order is recorded.

In **Module status lab**, RemoteInput is required and RemoteRack starts
inhibited. Set RackModeCommand to 0, Step with ApplyRackMode true, then
set ApplyRackMode back to false. Apply Running to RemoteRack and RemoteInput
in **Device I/O**. Start Run and inject Faulted on RemoteRack. The controller
fault names both modules. Restore both modules to effective Running before
using **Clear I/O major fault**. Clearing the upstream input to Unknown
leaves the controller fault latched.
[Rockwell Module status help](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/status.html)

## Required module fault at Run entry

A whole-project Program-to-Run request trips Type 3 Code 23 if a module
is required by its effective Mode word and has an effective simulated
Faulted connection or is Waiting on an explicitly faulted routed ancestor.
The fault occurs before prescan and preserves simulated time and scan
counters. A configured controller fault handler can write diagnostics
and clear the fault to let the Run request proceed. Direct faults take
precedence over upstream faults. Within
each group, the controller reports the first qualifying module in source order.

An inhibited route and an unmodeled connection without a known upstream
fault do not trigger the startup check. An optional module can still block a
required descendant. A required descendant with no staged input can trip
when its route is known and an ancestor has an explicit fault. Manual Step
and isolated routine Run stay available for diagnostics when there is no
controller fault latch. The simulator checks the explicit input immediately.
Rockwell's connection attempt and startup delay require live I/O and are
outside this model.

In **Module status lab**, set ModeCommand to 1, Step with ApplyMode true,
and set ApplyMode back to false. In **Device I/O**, apply Faulted to
RackOutput while still in Program. Select **Run** to see **I/O MAJOR FAULT
· 3/23**. Restore RackOutput to Running, clear the fault, then select
Run again. The same API fault record and recovery controls apply to both
3/23 and 3/16. If another required module is still faulted, the next Run
request reports that module.

For the upstream case, uninhibit RemoteRack as shown in the previous
section, then apply Faulted to it while still in Program. A Run request
reports required RemoteInput and names RemoteRack as the upstream source.
Set both modules to effective Running before clearing the fault.
[Rockwell Logix 5000 Controllers Information and Status](https://literature.rockwellautomation.com/idc/groups/literature/documents/pm/1756-pm015_-en-p.pdf)

## Module backplane path

`GSV(Module,RackOutput,Path,PathBytes[1])` writes a modeled CIP route in
ladder or ST. The first two SINT cells contain the little-endian payload
length, 2. The next two contain the backplane port number, 1, and the
module's slot. In **Module status lab**, set ReadModule and step to see
PathBytes change to `[-99, 2, 0, 1, 2, 99]`. The guard cells retain their
saved values, and the route is independent of the current Mode word.

The model requires explicit ICP port 1 on Local and a unique upstream ICP
port 1 on the module under that backplane. The slot must be inside Local's
declared chassis size and distinct from the CPU and other declared slots.
Path is withheld for missing or ambiguous topology. The route is derived
from configuration and native returned bytes have yet to be verified.

The destination must have at least four writable SINT cells from the
selected start in one dimension. A skipped call leaves the array alone
and defers any indirect index. A reached short window faults and rolls
back the emulator scan. The native short-buffer zeroing and minor-fault
log and live message forwarding remain open.
[Rockwell Module object](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/input-output-instructions/access-the-module-object.html)
[Rockwell backplane routing reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/at/enet-at002_-en-p.pdf)

## Module Ethernet path

In ladder and ST, GSV Module Path also reads configured IPv4 routes through
the 5580 controller's embedded Ethernet port or through a local 1756-EN2T or
1756-EN2TR. The L5X must identify a single downstream Ethernet port 2 and a
single upstream Ethernet port on the target. A local bridge also needs an
unambiguous backplane slot. The target IP must be unambiguous under that
parent and distinct from any explicit parent address. The same qualified
target can use GSV Mode, inhibited EntryStatus and SSV Mode.

The route starts with a two-byte little-endian payload length. A bridged
route prepends port 1 and the bridge slot to the Ethernet segment. The
segment uses 16#12, the address character count, the dotted IPv4 address
as ASCII and a zero pad byte if that count is odd. The payload length
includes the padding. The SINT destination needs space for the full
counted route and keeps bytes outside that window.

In **Module status lab**, ReadModule writes the configured PointAdapter
route to EthernetPath starting at index 1. It begins with `0C 00 12 0A`
followed by the ASCII bytes for `192.0.2.42`. The first and last array
cells stay at -99 and 99. The route is configuration data. Native
GSV byte parity, hostname resolution, IPv6, and live I/O remain open.
[Rockwell ControlLogix EtherNet/IP routing reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/1756-um004_-en-p.pdf)

## Remote ControlLogix backplane path

GSV Module Path can extend a qualified IPv4 route to a remote
1756-EN2T or 1756-EN2TR by appending port 1 and a slot on that chassis.
This works with the controller's embedded Ethernet port or a qualified
local bridge. The adapter must declare a downstream ICP port 1, its
own slot and the remote chassis size. The target needs an upstream
ICP port 1, and its slot must be in range and unique within that chassis.
An ambiguous adapter address also withholds routes to its children.

In **Module status lab**, ReadModule writes the route for RemoteInput
at slot 4 on the remote chassis. At RemotePath[1], the prefix is
`0E 00 12 09` followed by the ASCII address `192.0.2.7`, a pad byte,
and `01 04`. The existing SINT destination and Mode rules apply.
The model covers one remote ControlLogix backplane. Native byte parity,
other remote bus types and live module connections remain open.
[Rockwell ControlLogix backplane routing reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/1756-um003_-en-p.pdf)

## Changing a periodic task rate

`SSV(Task,FastTask,Rate,FastRateCommandUs)` changes the effective period of a
Standard Periodic task with an explicit source rate. The source is a scalar
DINT in microseconds, from 1000 through 60000000 in multiples of 1000. Ladder
and ST calls in project execution accept a literal task name or `THIS` in an
eligible scheduled Program. False ladder rungs, skipped ST calls and prescan
skip source values. A reached invalid value faults and rolls back the advance.

GSV Rate sees the latest successful write in the current advance. Releases
already scheduled for that advance run at their original times. When the
advance commits a changed period, the next release is one new period after
the end of the advance. Writing the same rate keeps the phase, including
when multiple writes leave the original period in effect. Inhibited tasks
use the same phase rule and discard missed releases. A later fault restores
the previous rate, release schedule and values together.

Program-to-Run restarts phase using the effective period. Routine replacement
retains the rate and phase. Reset and reload restore the source rate. The
scheduler reports both `rate_ms` and `source_rate_ms`. A project with one
initially enabled Periodic task uses its effective rate for automatic Run and
updates the Step interval after a committed change. A multi-task project's
Step or Run advance interval is independent of each task's period.

In **System lab**, leave FastRateCommandUs at 20000, enable ApplyFastRate,
and step 25 ms. LiveFastRateUs reads 20000. Task schedule shows FastTask at
20 ms with its 10 ms source rate. Set FastRateCommandUs to 10000 and step
to restore the original rate before disabling the gate.

The installed v35 Task object help 14646 and Rockwell's
[Task object reference](https://www.rockwellautomation.com/en-in/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
specify DINT microseconds. The whole-millisecond range and commit boundary
are software scheduler policies. CIP Task rate reads retain the source value.
Native phase and fault behavior, sub-millisecond periods,
Safety, AOI SSV and routine-harness SSV remain outside this profile.

## Changing a task priority

`SSV(Task,SlowTask,Priority,SlowPriorityCommand)` accepts an exact scalar
INT from 1 through 15 for a Standard Periodic or qualified instruction-only
Event task. A lower number means higher priority. The target is a configured
task name or `THIS` in an eligible scheduled Program. False rungs, skipped
ST calls and prescan skip source values.

GSV Priority reads the latest write during the advance. Periodic release
order, immediate EVENT dispatch and pending Event arbitration all use the
priorities captured at the start of that advance. A successful commit
changes the order for subsequent advances and keeps the existing periodic
phase. Coincident Periodic releases with equal priority use source order,
and pending Events with equal priority use request order. A fault restores
the prior priorities, task progress and values.

Run entry and routine replacement retain effective priorities. Reset or
reload restores the source priorities. The Coverage panel shows effective
and source priorities when they differ. In **System lab**, set the advance
to 25 ms, enable ApplySlowPriority, and step. SlowTask now reads 1 with
source priority 5. On the next step, SlowTask runs before FastTask at their
coincident 50 ms release.

The installed v35 Task object help 14646 lists the INT operand and a wider
0..15 attribute range. This software profile follows the
[ControlLogix 5580 task configuration range](https://www.rockwellautomation.com/en-mde/docs/technical/logix5000/_online/1756-um543/controllogix-5580-and-guardlogix-5580-controllers-/develop-standard-applications/tasks.html)
of 1..15. CIP Task Priority reads retain source metadata. Continuous, Safety,
other Event profiles, AOI and routine-harness setters, and native arbitration
remain outside this profile.

## Changing a task watchdog

`SSV(Task,THIS,Watchdog,WatchdogCommandUs)` changes the effective watchdog
setting of a Standard Continuous, Periodic or qualified instruction-only
Event task with an explicit positive source setting. The source operand is
an exact scalar DINT tag in microseconds. Positive values from 1000 through
2000000000 retain microsecond precision. A zero write selects 500000
microseconds for a Periodic task or 5000000 for a Continuous task. Event
watchdog writes require a positive value.

Named tasks and `THIS` use the existing scheduled Program context. GSV
Watchdog immediately reads the latest write. A later fault restores the
previous setting, tag values and task progress together. False rungs, skipped
ST calls and prescan skip the source value. Run entry and routine replacement
retain the setting. Reset or reload restores the explicit source setting.

In **System lab**, enable ApplyWatchdog and step. LiveWatchdogUs reads
125001 microseconds. The earlier BackgroundWatchdog read sees it on the
following step. Set WatchdogCommandUs to zero and step to see the 5-second
Continuous default in LiveWatchdogUs. Disable the gate to retain it.
Task schedule reports `watchdog_override_us` after a runtime write.

Installed v35 help 14646 defines the DINT operand and zero-write defaults.
Topic 18424 describes the configured range. See Rockwell's
[Task object](https://www.rockwellautomation.com/en-in/docs/studio-5000-logix-designer/38-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
and [task configuration](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/37-01/contents-ditamap/studio-5000-logix-designer/tasks--programs--and-routines/tasks.html)
references. The emulator models the setting and keeps CIP reads bound to
source metadata. Expiration, fault handlers, CPU timing and Safety watchdogs
remain separate. Missing or zero values in the source remain unavailable.

## Destinations and execution

Numeric destinations must be exact scalar INT or DINT tags as listed above;
cross-type byte copies/conversions and packed bits are blocked. Strings use
represented DINT LEN / SINT DATA storage, with declared capacity enforced.
Aliases, indexed array elements, UDT members, Program-local scope and existing
AOI output/InOut bindings retain normal memory rules. Unknown destinations can
be established; strings preserve unused destination bytes.

Prescan, false ladder rungs and skipped ST branches retain outputs. Each reached
call reads the loaded configuration or the current project-mode
[InhibitTask flag](task-inhibition.md), Periodic Rate, Periodic/Event Priority
or Watchdog. Event Rate and EnableTimeOut use the [runtime timeout
settings](event-tasks.md#runtime-timeout-settings). A disk edit takes effect on project reload. Bound metadata with a different source hash is rejected. ST FOR checks
track every destination, including a string's LEN/DATA region. Capacity/bounds
errors and later failures retain whole-advance rollback of data and scheduling.

GSV reads the effective settings without changing them. Output I/O, watchdog
enforcement, CPU time slicing and native arbitration are separate profiles.
See [Task InhibitTask SSV](task-inhibition.md) for live inhibition.

## System Lab

Choose System lab in the header and step 25 ms. The authored
[SystemLab.L5X](../source/samples/SystemLab.L5X) combines the scheduling example
with configuration reads in background/periodic ladder and a called ST routine.
Task Lab remains unchanged.

FastRate/SlowRate read 10000/25000; FastWatchdog/BackgroundWatchdog read 500000.
FastPriority/SlowPriority read 2/5. FastTaskName and ControllerName become
FastTask and SystemLab. CommTimeSlice/ShareUnused read 30/1. FastInhibit and
FastNoOutput are zero; StSlowRate/StCommTimeSlice/StFastTaskName match ladder.
Background/Fast/Slow execution counts are 1/2/1 after that advance.

ReadConfig gates the examples. Set it false and scan to retain output tags while
the three tasks continue running. Editing a result tag changes that result;
reenabling reads restores the source setting when its task next executes.

The baseline uses installed v35 help 14636 (Controller) and 14646 (Task).
Rockwell's published [Task object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-task-object.html)
and [Controller object reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/input-output-instructions/access-the-controller-object.html)
provide context. Software tests do not establish native Studio/controller
acceptance. See [implementation](../source/logixlab/gsv_configuration.py).
