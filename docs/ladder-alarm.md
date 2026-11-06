# Ladder digital alarms

The v35 ControlLogix 5580 software profile supports
`ALMD(Alarm,ProgAck,ProgReset,ProgDisable,ProgEnable,MinDurationPRE,MinDurationACC)`.
The writable scalar `ALARM_DIGITAL` tag may be controller-scoped, program-scoped
or an alias. The importer reads `Data Format="Alarm"` with one
`AlarmDigitalParameters` element and applies documented defaults for omitted
parameters. The last two ladder operands accept a nonnegative DINT preset
and a zero accumulator. With `?,?`, the preset comes from the tag and the
public accumulator still reports zero, as in v35.

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
- `InFault` sets `Status.1` (`InFaulted`) while evaluation continues.
  Prescan clears active alarms and operator commands, acknowledges alarms
  and resets hidden timing and command history. The count is retained.

The software applies acknowledgment after activation within a single call
and gives a coincident count-reset request precedence over the increment.
Delayed state and edge history roll back with tag writes after a failed
advance. This model covers valid severity settings from 1 through 1000.

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

## Scope

Timestamp generation, alarm messages/events and native packed records
remain open. A program-time command stops the modeled advance. ST, FBD, AOI alarms, ALMA and ASO remain
separate. The native alarm discovery services still expose only verified empty
catalogs. Runtime behavior is based on the installed v35 ALMD help and
the import/export record description. Native execution and transfer parity
remain unverified. [ALMD reference](https://www.rockwellautomation.com/en-hu/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/alarm-instructions/digital-alarm---almd.html) · [Import/export manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)
