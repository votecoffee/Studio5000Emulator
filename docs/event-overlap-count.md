# Event overlap count reads and resets

The v35 ControlLogix 5580 project profile supports
`GSV(Task,EventTask,OverlapCount,Destination)` and
`SSV(Task,EventTask,OverlapCount,Source)` in ladder and ST for qualified
instruction-only Standard Event tasks. Ordinary scheduled Programs can name
the target; `THIS` inside the Event selects its Task. AOI, routine-harness,
Safety and Periodic deadline-overlap behavior remain unqualified.

```text
GSV(Task,THIS,OverlapCount,ActiveOverlaps);
SSV(Task,THIS,OverlapCount,Zero);
```

Both operands are exact scalar DINT tags. The SSV source must contain known
zero and is retained. Nonzero values are rejected when reached; this profile
provides a reset, not an arbitrary counter setter.

## Live counter and status

An uninhibited EVENT request made while its target is already executing is
discarded and increments that target's overlap counter. GSV reads the live
count, including requests earlier in the same Event body or caller advance.
A reset takes effect immediately; later active requests count from zero.
Repeated resets and several Event invocations in one advance retain their
instruction order.

Pending duplicate coalescing, ignored inhibited requests and pending work
canceled at dispatch do not increment this counter. The separate
event_pending_requests_coalesced diagnostic is retained. The API task row's
event_instruction_overlaps value and event_task_status.overlap_counts report
show the committed counter after successful advances.

Resetting OverlapCount does not clear the Status active-overlap bit. Clearing
Status does not reset the counter. Execution counts and timing measurements
are also separate. The existing scheduler lifecycle resets overlap diagnostics
at Run entry and model reset/load; Status retains its separate Run-entry
policy. Detached routine replacement preserves the current independent count.

GSV preserves the unsigned DWORD's bits in DINT storage, so a set high bit
appears negative. Internally unrepresentable counters are withheld instead of
wrapping or saturating; a direct zero reset is still supported. Native overflow
behavior is not established by this software policy.

## Atomic execution and operands

Counters, resets, status, tags, bindings, scheduling, first scans and timings
commit only with a successful complete advance. An invalid source value,
unavailable required count, bad selected address or later fault discards all
uncommitted changes. Scheduler commit validates absolute Event counts before
advancing any state, including valid keys, integer nonnegative values and no
unexplained increases beyond observed active requests.

Structural preflight checks context, metadata, type, permissions and index
grammar. False ladder rungs, prescan and skipped ST bodies do not consume live
indices or source values. A complete GSV write establishes an unknown cell.
Alias/indirect references and conservative ST FOR output effects use the shared
system-value rules.

## Event lab

Step **Event lab** with ReadOverlap false; OverlapIndex99 is dormant. Set
OverlapIndex=1, ReadOverlap=true, TriggerRLL=true and SelfTrigger=true.
ThisOverlapBefore reads the old count, ThisOverlapAfter includes the current
self-request, and ThisOverlapExit, NamedOverlap, StOverlap and OverlapWords[1]
show the resulting count. Guards101/999 remain unchanged.

Enable ResetOverlap with OverlapResetValue=0. The Event body uses THIS SSV and
Background ST uses named SSV; ThisOverlapExit and committed counts become zero.
The Status word can remain5 until explicitly cleared. Disable new triggers to
observe the separate ST reset without an Event body. Nonzero reset values and
OverlapDivisor0 demonstrate atomic failure; restore zero/one before retrying.
See [EventLab.L5X](../source/samples/EventLab.L5X),
[implementation](../source/logixlab/event_status.py) and
[focused tests](../source/tests/test_event_overlap.py).

Installed v35 Task help14646 defines OverlapCount, active-task triggers and a
zero reset. This bounded implementation adds no native Task protocol service,
physical history or controller acceptance. Broader Task/Event sources,
Periodic overlaps, native overflow, interrupt timing, status/fault and lifecycle
equivalence remain separate work.
