"""Bounded deterministic releases; instruction-triggered events share the advance."""
import copy
import heapq
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .model import ModelError

MAX_TASKS = 32
MAX_RELEASES = 4096


@dataclass(frozen=True)
class Task:
    name: str
    kind: str
    priority: int
    period: int | None
    inhibited: bool
    entries: tuple


@dataclass(frozen=True)
class Batch:
    start: int
    end: int
    releases: tuple
    next_due: dict


class TaskScheduler:
    def __init__(self, source, entries):
        if not 1 <= len(source) <= MAX_TASKS:
            raise ModelError('Task scheduler requires 1..32 Standard tasks')
        self.source = source
        self.configuration = copy.deepcopy(source)
        tasks = []; names = set(); programs = set(); continuous = 0
        for row in source:
            name = row['name']
            if not isinstance(name, str) or not name or name.casefold() in names:
                raise ModelError('Task names must be nonempty and unique')
            names.add(name.casefold())
            if row['class'] != 'Standard' or row['type'] not in ('Continuous', 'Periodic', 'Event'):
                raise ModelError('Task scheduler supports Standard Continuous/Periodic and qualified Event tasks only')
            for program in row['programs']:
                if not isinstance(program, str) or not program or program.casefold() in programs:
                    raise ModelError('Each Program may be scheduled only once')
                programs.add(program.casefold())
            period = None; priority = 16
            if row['type'] == 'Continuous':
                continuous += 1
                if continuous > 1: raise ModelError('Only one Continuous task may be configured')
            elif row['type']=='Periodic':
                try:
                    rate = Decimal(row['rate'])
                    if not rate.is_finite() or not 1 <= rate <= 60000 or rate != rate.to_integral_value():
                        raise ValueError()
                    period = int(rate)
                except (InvalidOperation, ValueError, TypeError):
                    raise ModelError('Periodic task rate must be whole milliseconds in 1..60000') from None
            if row['type']=='Event' and row.get('event')!={'trigger':'EVENT Instruction Only','timeout':False}:
                raise ModelError('Event task requires EVENT Instruction Only with timeout disabled')
            if row['type']!='Continuous':
                raw = row.get('priority', '10')
                if not isinstance(raw, str) or not raw.isdecimal() or not 1 <= int(raw) <= 15:
                    raise ModelError('Periodic task priority must be an integer in 1..15')
                priority = int(raw)
            tasks.append(Task(name, row['type'], priority, period, row['inhibited'], tuple(entries.get(name.casefold(), ()))))
        self.tasks = tuple(tasks)
        self.reset(0)

    def reset(self, now):
        self.origin = now
        self.clock = now
        self.next_due = {i: now + task.period for i, task in enumerate(self.tasks)
                         if task.period is not None and not task.inhibited}
        self.counts = {i: 0 for i in range(len(self.tasks))}
        self.last = {i: None for i in range(len(self.tasks))}
        self.overlaps = {i:0 for i,t in enumerate(self.tasks) if t.kind=='Event'}
        self.coalesced = dict(self.overlaps)

    def prepare(self, end):
        if self.source != self.configuration:
            raise ModelError('Task configuration changed; reload the project')
        if type(end) is not int or end <= self.clock:
            raise ModelError('Task scheduler requires an advancing integer clock')
        next_due = dict(self.next_due)
        heap = [(due, self.tasks[i].priority, i) for i, due in next_due.items()]
        heapq.heapify(heap); releases = []
        while heap and heap[0][0] <= end:
            if len(releases) >= MAX_RELEASES:
                raise ModelError('Task release budget exceeded; use a smaller simulation step')
            due, _, i = heapq.heappop(heap)
            releases.append((due, i))
            next_due[i] = due + self.tasks[i].period
            heapq.heappush(heap, (next_due[i], self.tasks[i].priority, i))
        for i, task in enumerate(self.tasks):
            if task.kind == 'Continuous' and not task.inhibited:
                if len(releases) >= MAX_RELEASES:
                    raise ModelError('Task release budget exceeded; use a smaller simulation step')
                releases.append((end, i))
        return Batch(self.clock, end, tuple(releases), next_due)

    def continue_from(self, previous):
        """Carry only runtime progress into an unchanged, newly bound task graph."""
        if self.configuration != previous.configuration or self.tasks != previous.tasks:
            raise ModelError('Task graph changed during routine replacement')
        for name in ('clock', 'origin', 'next_due', 'counts', 'last', 'overlaps', 'coalesced'):
            setattr(self, name, copy.deepcopy(getattr(previous, name)))

    def commit(self, batch, *, events=(), overlaps=None, coalesced=None):
        if batch.start != self.clock:
            raise ModelError('Task scheduler batch is stale')
        if (len(batch.releases)+len(events)>MAX_RELEASES or
                any(type(i) is not int or not 0<=i<len(self.tasks) or self.tasks[i].kind!='Event'
                    or self.tasks[i].inhibited or not batch.start<due<=batch.end for due,i in events)
                or any(i not in self.overlaps or type(n) is not int or n<0
                       for counts in (overlaps,coalesced) for i,n in (counts or {}).items())):
            raise ModelError('Invalid Event task completion batch')
        self.clock = batch.end
        self.next_due = dict(batch.next_due)
        for due, i in (*batch.releases,*events):
            self.counts[i] += 1
            self.last[i] = due
        for i,n in (overlaps or {}).items():self.overlaps[i]+=n
        for i,n in (coalesced or {}).items():self.coalesced[i]+=n

    def description(self):
        return dict(policy='Periodic releases in simulated time; Continuous once per step, after due Periodic tasks',
                    clock_ms=self.clock, run_epoch_ms=self.origin, preemptive=False, event_tasks=any(t.kind=='Event' for t in self.tasks), safety_tasks=False,
                    event_dispatch='Immediate higher-priority EVENT; deferred lower/equal at task returns; no CPU timing/preemption model',
                    watchdog_enforced=False, release_limit=MAX_RELEASES,
                    equal_priority='Base releases use source order and precede queued Events; Event ties use request order',
                    first_periodic_release='One configured period after Run entry',
                    tasks=[dict(name=t.name, kind=t.kind, priority=t.priority if t.kind!='Continuous' else None, rate_ms=t.period,
                                inhibited=t.inhibited, executions=self.counts[i],
                                last_release_ms=self.last[i], next_release_ms=self.next_due.get(i),
                                **({'event_instruction_overlaps':self.overlaps[i],
                                    'event_pending_requests_coalesced':self.coalesced[i]} if t.kind=='Event' else {}))
                           for i, t in enumerate(self.tasks)])
