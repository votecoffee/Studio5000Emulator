# Runtime Event task inhibition

The v35 ControlLogix 5580 project profile extends
`SSV(Task,TaskName,InhibitTask,Source)` and live `GSV` feedback to the existing
instruction-only Standard Event task model. `THIS` also selects the current
ordinary scheduled Task for inhibition in Continuous, Periodic and qualified
Event contexts. Source remains an exact scalar DINT tag: zero enables, any
nonzero signed DINT inhibits, and the source is retained.

```text
SSV(Task,WorkEvent,InhibitTask,DisableEvent);
GSV(Task,WorkEvent,InhibitTask,EventDisabled);
```

Inside WorkEvent, these calls can use `THIS`. The Event body that inhibits
itself completes; subsequent requests see the new flag. This is the existing
software completion policy extended to Events, not native abort/resume
qualification. Event GSV configuration reads additionally support Name,
explicit Priority, Watchdog, DisableUpdateOutputs and InhibitTask. Event Rate
does not become a period or timeout. [Event scan timing](event-task-timing.md)
now records qualified completed Event bodies without expanding native timing
protocol attributes.

## Requests and pending work

Both a new EVENT request and a pending request about to dispatch check the live
inhibition flag. A request made while inhibited is ignored without status,
overlap, first-scan or execution progress. A previously accepted pending request
is discarded if its target is inhibited when dispatch becomes possible. Its
accepted-request status bit remains latched; it records acceptance, not
successful execution. Pending duplicate diagnostics retain their existing
meaning. Enabling does not replay ignored or discarded work.

If a caller inhibits and then enables a pending target before dispatch, the
current flag permits execution. UID/UIE uses the same check when masked work
becomes eligible. An initially inhibited Event can be enabled and run; if that
body inhibits itself again, its completed execution still commits. Existing
Continuous/Periodic phase and missed-release policies are unchanged.

Prescan includes initially inhibited Event routines. Run entry retains live
inhibition; load/reset restores source settings. Detached routine replacement
preserves inhibition and status independently. A later fault restores flags,
accepted status, data, bindings, first scans, scheduling and timing as one
advance. Pending queues remain transient and are discarded with that advance.

Preflight checks metadata, current-instance ownership, source type and index
grammar. A false rung, prescan or skipped ST body does not read live sources.
Unknown required values and invalid reached indices fault without partial
commit. Source bytes and declared Task settings are not rewritten.

## Event lab

Enable TriggerRLL and ControlEventInhibit. Set EventInhibitCommand=1 to block
WorkEvent; LiveEventInhibit becomes1 and EventCount holds. Set the command to0
to allow the next request. ReadEventConfig enables live flags and THIS reads of
the Event Task's name, priority and watchdog: WorkEvent,1 and500000 microseconds.

Disable ControlEventInhibit, enable SelfInhibitEvent and ReadEventConfig, then
request WorkEvent. ThisEventInhibit becomes1 while that body completes. A later
self-request is ignored; future producer requests also wait for a separate
enable. Clear SelfInhibitEvent and use the named control to enable it again.

For pending work, enable TriggerDeferred and ControlDeferredInhibit with
DeferredInhibitCommand=1. The producer accepts DeferredEvent requests before
inhibiting it, so the queued body is skipped. LiveDeferredInhibit becomes1;
the accepted status can remain1 while DeferredCount holds. Set the command to0:
requests earlier in that producer invocation were ignored, so another fresh
request is needed on a following release. No catch-up execution occurs.

InhibitDivisor0 produces a late Background ST fault after the control work;
restore it to1 before retrying. See [EventLab.L5X](../source/samples/EventLab.L5X),
[focused tests](../source/tests/test_event_inhibit.py),
[general task inhibition](task-inhibition.md) and
[logical Event status](event-task-status.md).

## Remaining scope

Safety, external Event sources, AOI/routine-harness setters, native task
abort/resume, pending cancellation, status/fault and scheduling lifecycle parity
remain unqualified. No controller mode, native transfer service or physical PLC
operation is added. Existing source-bound inhibition metadata follows live flags;
this does not establish Studio/controller acceptance.

Installed v35 Task object help14646 defines DINT InhibitTask and prescan of
inhibited tasks; EVENT help14708 supplies the instruction-trigger context.
The pending-dispatch and current-body completion rules above are explicit
software policies awaiting separate native qualification.
