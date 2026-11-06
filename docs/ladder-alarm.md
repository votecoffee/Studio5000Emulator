# Ladder alarms

The v35 ControlLogix 5580 software profile supports
`ALMD(Alarm,ProgAck,ProgReset,ProgDisable,ProgEnable)` in neutral-text exports.
The writable scalar `ALARM_DIGITAL` tag may be controller-scoped, program-scoped
or an alias. The importer reads `Data Format="Alarm"` with one
`AlarmDigitalParameters` element and applies documented defaults for omitted
parameters. The preset comes from `Alarm.MinDurationPRE`. The earlier
seven-operand emulator form remains supported. Its final pair accepts a
nonnegative DINT preset and a zero accumulator, or `?,?` to use the tag.
The public accumulator reports zero, as in v35.
[Rockwell import/export manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf#page=212)

ALMD evaluates every time the rung reaches it. The rung state supplies `In`
and continues to the next ladder node. An active-low alarm can therefore
activate on a false rung. The first abnormal sample starts the minimum
duration at the current modeled time. A sampled return to normal or a
disable clears a pending delay. At the next qualifying sample, an activation
increments `AlarmCount` up to the signed DINT maximum.

- A nonlatched alarm clears on return to normal. If acknowledgment was
  required and is still pending, it stays pending after the alarm clears.
- A latched alarm can reset only when the input is normal. A successful
  latch reset also clears pending acknowledgment.
- Program acknowledgment and reset respond to rising edges. Operator
  commands are consumed and cleared on execution. Enable takes precedence
  over disable. Disabling clears `InAlarm` and allows acknowledgment of an
  existing unacknowledged alarm.
- Prescan clears active alarms and operator commands, acknowledges alarms
  and resets hidden timing and command history. The count is retained.

The software applies acknowledgment after activation within a single call
and gives a coincident count-reset request precedence over the increment.
Delayed state and edge history roll back with tag writes after a failed
advance.

## Diagnostics

`Status.0` (`InstructFault`) and `Status.2` (`SeverityInv`) indicate
severity outside 1 through 1000. `Status.1` (`InFaulted`) follows the
`InFault` input independently. Both conditions allow the alarm to keep
evaluating, timing and counting. Correction clears the corresponding
bits on the next ALMD call. Ladder can read each bit by name or number.
The configured `Severity` value stays available for inspection. Native
alarm subscribers use a bounded severity, and subscriber delivery is
outside the current software model.
[Rockwell ALMD reference](https://www.rockwellautomation.com/en-hu/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/alarm-instructions/digital-alarm---almd.html)

## Suppression

Set `ProgSuppress` or `OperSuppress` to latch `Suppressed`. Set
`ProgUnsuppress` or `OperUnsuppress` to clear it. Unsuppress takes precedence
when both are requested. Operator requests clear after each completed call,
while program commands retain their values. Suppression preserves detection,
minimum duration, latching and activation count. A previously unacknowledged
alarm can still be acknowledged. While suppressed, a new activation preserves
acknowledgment state. Clearing suppression on an active alarm that requires
acknowledgment makes it unacknowledged again if it is also unshelved.
Clearing suppression leaves the count unchanged.
Prescan retains suppression and clears pending operator requests.
[Rockwell alarm state model](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/proces-rm001_-en-p.pdf#page=60)

## Shelving

Pulse `OperShelve` to shelve an alarm for `ShelveDuration` minutes on the
emulator clock. A new rising edge reshelves from the current time. ALMD
consumes the request and requires a sampled false before another rising
edge. `ProgUnshelve` and `OperUnshelve` take precedence over shelving and
consume a simultaneous shelf edge. A winning shelf request requires a
duration from 1 through `MaxShelveDuration` minutes. The software rolls
back the advance for an invalid duration.

The shelf expires on the first ALMD execution at or after its deadline.
A fresh shelf request can extend it on that execution. Shelf time, edge
history and alarm state roll back together on a scan fault. Prescan clears
the shelf and its pending requests. Detection and counting continue while
shelved, and a pending alarm can still be acknowledged. An active alarm
requires acknowledgment again when both shelving and suppression have
cleared and `AckRequired` is true.
[Rockwell ALMD reference](https://www.rockwellautomation.com/en-hu/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/alarm-instructions/digital-alarm---almd.html)

## Timestamps

The alarm records six LINT UTC timestamps in microseconds since 1970-01-01.
`InAlarmTime` retains the first abnormal sample that qualifies as an alarm
after the delay. `AckTime` records acknowledgment and matches detection
for an activation that requires no acknowledgment. `RetToNormalTime`
records the transition out of alarm. An `AlarmCountReset` tag command
records its event in `AlarmCountResetTime`.

`ShelveTime` records the shelf or reshelf event. `UnshelveTime` is the
planned timestamp and is replaced with the event time on manual unshelving.
The planned value remains visible after automatic expiration. The shelf
deadline and the minimum-duration timer still use simulated elapsed time.

Each event samples the existing WallClockTime UTC clock or, with
`UseProgTime` set, the current nonnegative LINT `ProgTime`. Events within
one call share a sample. Pending detection time and all timestamp writes
roll back with the advance. Prescan clears the six fields. The tag view
shows exact decimal strings for LINT values.
[Rockwell ALMD status parameters](https://www.rockwellautomation.com/en-pr/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/alarms/instruction-based-alarms/analog-and-digital-alarm-properties-dialog-boxes/almd-properties-dialog-box---status-tab-parameters.html)

## Alarm Lab

Select **Alarm lab** from Examples. Set `Trip` true and take three 10 ms
steps. `MotorAlarm.InAlarm` sets on the third step. Set `Trip` false to
see the latched output hold. Pulse `Acknowledge` to clear
`InAlarmUnack`, then pulse `ResetAlarm` with the input normal to clear
`InAlarm`. Set `Healthy` false to activate the nonlatched `SignalAlarm`.
Both records can be inspected from the ladder viewer and tag list.

For suppression, reload Alarm Lab and set `MotorAlarm.ProgSuppress` and
`Trip` true. After three 10 ms steps, the ladder block shows SUP and ALM.
The alarm has counted one activation and is still acknowledged. Set
`MotorAlarm.ProgUnsuppress` true and step. SUP clears, acknowledgment is
required, and the count stays at one. Clear both program commands when done.

For shelving, reload Alarm Lab and step once to complete prescan. Set
`MotorAlarm.OperShelve` and `Trip` true. After three more 10 ms steps, the
ladder block shows SHV and ALM. Enter
60000 ms for the next step to expire the one-minute shelf and rearm
acknowledgment. The count remains one.

To try program-supplied time, reload Alarm Lab and set
`MotorAlarm.UseProgTime` true and `MotorAlarm.ProgTime` to
`1700000000000123` before setting `Trip`. Step three times. The detection
time remains at that value even if ProgTime changes during the delay.

For severity diagnostics, set `MotorAlarm.Severity` to 0 and step. The
ladder block shows FLT and SEV. Set `MotorAlarm.InFault` true to see BAD.
Restore severity to 500 and step to clear FLT and SEV.

## Analog level alarms

The v35 ControlLogix 5580 profile supports
`ALMA(Alarm,In,ProgAckAll,ProgDisable,ProgEnable)` with scalar Alarm-format
`ALARM_ANALOG` tags. Ladder copies a finite REAL, SINT, INT or DINT input
to the record's REAL `In`. A false rung clears the enable pins, retains
alarm results and skips live input reads and commands.

LL, L, H and HH pick up at inclusive limits. A high level clears below its
limit minus deadband, and a low level clears above its limit plus deadband.
Enabled levels share one minimum-duration clock per direction, using the
first sampled excursion. A false rung discards an unfinished delay and
its pending detection times. If the level is still beyond its limit on
the next powered scan, timing starts from that scan. A direction that
already met its delay keeps its qualification while the same excursion
continues. A level can bypass the delay with its `MinDurationEnable` bit.

The faceplate shows `MinDurationPRE` in milliseconds. The installed v35
instruction page specifies zero for `MinDurationACC`, while the v35
structure page describes an elapsed accumulator. The emulator follows
the instruction page for the exposed member. The structure page describes
interruption of unfinished timing on a false enable.
[ALMA instruction](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/alarm-instructions/analog-alarm---alma.html)
[ALARM_ANALOG structure](https://www.rockwellautomation.com/en-dk/docs/studio-5000-logix-designer/37-02/contents-ditamap/studio-5000-logix-designer/alarms/instruction-based-alarms/analog-and-digital-alarm-properties-dialog-boxes/structure-definition-for-alarm_analog-tags--all-la.html)

Enabled limits must be ordered. The software
clears the active levels on invalid order and uses zero deadband when the
configured band is invalid, exposing the corresponding status bits.

Level and global acknowledgments, enable/disable, suppression and
saturating level counts are modeled. Prescan clears outputs and operator
requests and retains configuration and counts. A failed advance restores
level state, counts and the qualification clocks.

In Alarm Lab, set `AnalogRun` true and `Pressure` to 80, then take three
10 ms steps. H activates. Set `Pressure` to 90 and step to activate HH
on the same high excursion. HH remains active at 88 and clears at 87.5.
H stays active. Pulse `AckAnalog` to acknowledge all conditions. To see a
restart, reload Alarm Lab and step once with `AnalogRun` true and
`Pressure` at 80. Step with `AnalogRun` false, then turn it back on. H
takes three powered 10 ms steps to qualify.
[Rockwell ALMA reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/alarm-instructions/analog-alarm---alma.html)

## Rate of change

Set `ROCPeriod` to a positive sampling period in seconds. ALMA stores the
first powered input as a baseline. On the first scan at or after the period,
it divides the difference between samples by the configured period and
holds the result in `ROC` until the next sample. `ROCPosLimit` and
`ROCNegLimit` are positive magnitudes. A zero limit disables its direction
and a zero period disables both. Rising rates at or above the positive
limit and falling rates at or below the negated limit activate their
respective conditions. Level delay and deadband apply to level alarms.

ROC alarms use the same per-condition and global acknowledgment,
suppression and count reset rules as level alarms. `ROCPosInAlarmCount`
and `ROCNegAlarmCount` saturate at the DINT maximum. False rungs retain the
displayed result. Power resumption, enable after disable and changes to the
sampling period establish a fresh baseline in the software model.

An out-of-range period or negative limit disables the affected detection
and sets its status bit. The model flags a rate outside finite REAL range
with `Status.8`, publishes zero and clears the rate conditions until a valid
sample is available. The level conditions continue to evaluate.

In Alarm Lab, set `AnalogRun` true, `ROCPeriod` to 0.01 and both rate limits
to 100. Step once at `Pressure` 50 to set the baseline. Change pressure to
51 and step 10 ms to light R+. Change it back to 50 and step 10 ms to light
R-. The faceplate shows +100 and -100 units per second respectively.
[Rockwell ALARM_ANALOG structure](https://www.rockwellautomation.com/en-za/docs/studio-5000-logix-designer/38-00/contents-ditamap/studio-5000-logix-designer/alarms/instruction-based-alarms/analog-and-digital-alarm-properties-dialog-boxes/structure-definition-for-alarm_analog-tags--all-la.html)

## Analog alarm shelving

Each of the four level and two rate-of-change conditions has a shelf timer.
Pulse the condition's `OperShelve` member, such as `HHOperShelve`, to start or
restart its timer. `ShelveDuration` specifies minutes and the emulator caps
it at `MaxShelveDuration`. Both must be positive for a new shelf. Each
condition's `OperUnshelve` cancels that shelf. `ProgUnshelveAll` cancels every
shelf while true. Unshelving takes precedence and consumes a simultaneous
shelf edge. The instruction clears operator requests when it executes.

Detection and counts continue while a condition is shelved. A condition
acknowledged while shelved remains acknowledged through retriggering.
If it is still active when its shelf expires or is cancelled, it requires
acknowledgment again once it is unsuppressed. The first powered execution
at or after the deadline processes the expiration. Prescan clears shelves.

In Alarm Lab, turn on `AnalogRun` and hold `Pressure` at 90 for three 10 ms
steps. Set `PressureAlarm.HHOperShelve` and `PressureAlarm.HHOperAck` and step.
The ALMA faceplate lights SHH for the one-minute high-high shelf. H stays
active and unacknowledged. Advance 60000 ms to clear SHH and rearm the
high-high acknowledgment. The other shelf indicators are SH, SL, SLL, S+
and S-.
[Rockwell ALMA reference](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/instruction-set/alarm-instructions/analog-alarm---alma.html)
[Rockwell shelf configuration](https://www.rockwellautomation.com/en-pl/docs/studio-5000-logix-designer/38-01/contents-ditamap/studio-5000-logix-designer/alarms/instruction-based-alarms/analog-and-digital-alarm-properties-dialog-boxes/alma-properties-dialog-box---configuration-tab-par.html)

## Analog alarm timestamps

ALMA uses the emulator's UTC WallClockTime in microseconds. Each
condition's `InAlarmTime` member is published when the condition goes
active. A level condition keeps its first crossing time through the
minimum duration, and a crossing that clears before qualification is
discarded. Rate-of-change conditions record the time they go active.
Prescan clears the timestamps and keeps the alarm counts.

`AckTime` records the most recent acknowledgment. When acknowledgment is
automatic, it uses the latest detection time among conditions that
activate on the scan. `RetToNormalTime` records the most recent transition
of a condition out of alarm. `AlarmCountResetTime` records the count reset.
Events on the same instruction execution share one clock sample.

`ShelveTime` records each new shelf or reshelf. Following the v35
instruction tag description, `UnshelveTime` records the planned end when
the first shelf starts. Automatic expiration retains that value. A
manual unshelve that leaves no remaining shelf records the current time.
Each shelf's actual deadline uses simulated elapsed time.

In Alarm Lab, set `AnalogRun` true and `Pressure` to 80. Step once,
raise `Pressure` to 90 and step twice more. Select the ALMA box to see
both detection times as exact `LINT` values in the inspector. The time
for H comes from the first step and the time for HH comes from the
second. The tags and HTTP state preserve exact decimal strings.
[Rockwell ALMA status tab](https://www.rockwellautomation.com/en-fi/docs/studio-5000-logix-designer/37-00/contents-ditamap/studio-5000-logix-designer/alarms/instruction-based-alarms/analog-and-digital-alarm-properties-dialog-boxes/alma-properties-dialog-box---status-tab.html)

## Scope

Native alarm messages, event delivery and packed records remain open.
ST, FBD, AOI alarms and ASO remain separate. The
native alarm discovery services still expose only verified empty catalogs.
Runtime behavior is based on the installed v35 alarm instruction help and
the import/export record description. Native execution and transfer parity
remain unverified. [ALMD reference](https://www.rockwellautomation.com/en-hu/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/alarm-instructions/digital-alarm---almd.html) · [Import/export manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
