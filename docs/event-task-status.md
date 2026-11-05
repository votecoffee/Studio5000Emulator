# Event task status reads and clears

The v35 ControlLogix 5580 project profile supports logical
`GSV(Task,EventTask,Status,Destination)` and
`SSV(Task,EventTask,Status,Source)` in ladder and ST for the existing
instruction-only Event task model. Inside the Event task, `THIS` selects its
own Task. Calls from other ordinary scheduled Programs use the named target.
AOI and isolated routine-harness contexts remain unqualified.

```text
GSV(Task,THIS,Status,EventStatus);
OTU(EventStatus.0);
SSV(Task,THIS,Status,EventStatus);
```

The example clears the accepted-request bit while retaining the active-overlap
bit. The scratch tag must be a scalar DINT. Other GSV classes, attributes and
current-instance contexts keep their existing profiles.

[OverlapCount GSV/SSV](event-overlap-count.md) additionally reads the live active-
request count and resets it from known zero. Counter and Status changes are
independent and commit with the same complete advance.

## Modeled bits and visibility

| Bit | Meaning | Set by |
| --- | --- | --- |
| 0 | Accepted EVENT instruction request | A valid uninhibited request accepted for immediate or deferred execution |
| 1 | Timeout | A [configured Event timeout](event-tasks.md#configured-timeouts) dispatched the task |
| 2 | Active-task overlap | A request discarded because its target is already executing |

These bits are latched until explicitly replaced. Reads during an advance see
the current status, including changes made by a nested Event or SSV before the
next caller instruction. Pending duplicates retain the existing coalescing
policy; they do not set the active-overlap bit. An inhibited Event does not
execute or set status through EVENT. SSV replaces the complete modeled word
without modifying its source. A timeout-enabled Event supports values 0
through 7. With timeout disabled, values 0, 1, 4 and 5 remain supported.
A reached setter faults if it includes a bit outside the modeled mask.

The state starts at zero when a model is loaded or reset. Run entry retains it;
scheduler overlap/coalescing diagnostic counters have their separate Run-entry
reset behavior. OverlapCount SSV additionally resets its counter independently. Supported routine replacement copies status into its detached
candidate. A successful complete advance commits status with tags, bindings,
scheduling, first scans and timings. Invalid indices, unsupported setter words,
unknown required values or later faults discard all uncommitted work.

Preflight checks source metadata, context, operand type, permissions and index
grammar. False ladder rungs, prescan and skipped ST bodies do not read live
indices or source values. GSV can establish a complete unknown destination
cell. Indirect and alias references follow normal memory rules. ST FOR analysis
protects complete static GSV outputs and conservatively covers changing or
aliased destination arrays.

## Event lab

Step **Event lab** with ReadEventStatus false. EventStatusIndex99 stays dormant.
Set EventStatusIndex=1, ReadEventStatus=true and TriggerRLL=true. WorkEvent
reads its entry, active and exit status using THIS; the called ReadEventStatus
ladder routine and BackgroundProgram ST read the same named status.
EventStatusWords[1] receives the value while guards101/999 remain unchanged.

Enable SelfTrigger to produce an active overlap. WorkActiveStatus becomes5
while the task still executes once per producer request. Enable
ClearEventStatus and set EventStatusCommand=4 to clear bit0 and retain bit2.
Set the command to0 to clear both bits. The Event body demonstrates THIS SSV;
BackgroundProgram demonstrates named ST SSV. Disable triggers to observe the
latched value without new Event requests.

TriggerDeferred demonstrates pending duplicate coalescing without bit2.
DeferredStatus exposes that target's logical status. StatusDivisor0 produces a
late ST fault after Event work; restore it to1 before retrying. A reached
EventStatusIndex99 or unsupported EventStatusCommand similarly rolls back the
advance. See [EventLab.L5X](../source/samples/EventLab.L5X),
[implementation](../source/logixlab/event_status.py) and
[focused tests](../source/tests/test_event_status.py).

## Remaining scope

This feature does not expand native Task protocol attributes or import physical
controller status/history. Reports expose the logical words under
event_task_status with native_protocol_expanded=false and
native_runtime_parity=false. External I/O or motion events, other Task bits,
Continuous/Periodic/Safety status setters, broader contexts, native pending
semantics, interrupt timing and fault/lifecycle equivalence remain separate.

Installed v35 help14708 describes EVENT status bits0/1/2 and a THIS GSV/SSV
read-clear example. Help14626/14646 describes system-value access and the Task
object. These references guide the bounded software model; software tests do
not establish native Studio/controller acceptance.
