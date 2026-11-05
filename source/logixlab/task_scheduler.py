"""Bounded deterministic releases; instruction-triggered events share the advance."""
import copy
import heapq
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .model import ModelError

MAX_TASKS = 32
MAX_RELEASES = 4096
MIN_PERIOD_MS = 1
MAX_PERIOD_MS = 60000


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
    periods: dict


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
                    if not rate.is_finite() or not MIN_PERIOD_MS <= rate <= MAX_PERIOD_MS or rate != rate.to_integral_value():
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
        self.inhibitions={i:t.inhibited for i,t in enumerate(self.tasks)}
        self.periods={i:t.period for i,t in enumerate(self.tasks) if t.period is not None}
        self.reset(0)

    def reset(self, now):
        self.origin = now
        self.clock = now
        self.next_due = {i: now + period for i, period in self.periods.items()}
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
            next_due[i] = due + self.periods[i]
            heapq.heappush(heap, (next_due[i], self.tasks[i].priority, i))
        for i, task in enumerate(self.tasks):
            if task.kind == 'Continuous':
                if len(releases) >= MAX_RELEASES:
                    raise ModelError('Task release budget exceeded; use a smaller simulation step')
                releases.append((end, i))
        return Batch(self.clock, end, tuple(releases), next_due, dict(self.periods))

    def continue_from(self, previous):
        """Carry only runtime progress into an unchanged, newly bound task graph."""
        if self.configuration != previous.configuration or self.tasks != previous.tasks:
            raise ModelError('Task graph changed during routine replacement')
        for name in ('clock', 'origin', 'next_due', 'counts', 'last', 'overlaps', 'coalesced', 'inhibitions', 'periods'):
            setattr(self, name, copy.deepcopy(getattr(previous, name)))

    def commit(self, batch, *, executed=None, events=(), overlaps=None, coalesced=None, event_overlap_counts=None):
        if batch.start != self.clock:
            raise ModelError('Task scheduler batch is stale')
        # Event eligibility is checked at dispatch. A completed body may now be
        # self-inhibited, or may have been enabled after loading inhibited source.
        if (len(batch.releases)+len(events)>MAX_RELEASES or
                any(type(i) is not int or not 0<=i<len(self.tasks) or self.tasks[i].kind!='Event'
                    or not batch.start<due<=batch.end for due,i in events)
                or any(i not in self.overlaps or type(n) is not int or n<0
                       for counts in (overlaps,coalesced) for i,n in (counts or {}).items())):
            raise ModelError('Invalid Event task completion batch')
        if event_overlap_counts is not None and (
                not isinstance(event_overlap_counts,dict) or event_overlap_counts.keys()!=self.overlaps.keys()
                or any(type(i) is not int for i in event_overlap_counts)
                or any(type(n) is not int or n<0 or n>self.overlaps[i]+(overlaps or {}).get(i,0)
                       for i,n in event_overlap_counts.items())):
            raise ModelError('Invalid absolute Event overlap counters')
        executed=tuple((due,i) for due,i in batch.releases if not self.inhibitions[i]) if executed is None else tuple(executed)
        positions={release:i for i,release in enumerate(batch.releases)}
        order=[positions.get(release,-1) for release in executed]
        if any(i<0 for i in order) or order!=sorted(set(order)):raise ModelError('Invalid completed base-task releases')
        self.clock = batch.end
        # Rate writes leave the prepared releases intact and start a new phase
        # at the commit boundary only when the effective period changed.
        self.next_due = dict(batch.next_due)
        for i, period in self.periods.items():
            if period != batch.periods[i]:
                self.next_due[i] = batch.end + period
        for due, i in (*executed,*events):
            self.counts[i] += 1
            self.last[i] = due
        if event_overlap_counts is None:
            for i,n in (overlaps or {}).items():self.overlaps[i]+=n
        else:self.overlaps=dict(event_overlap_counts)
        for i,n in (coalesced or {}).items():self.coalesced[i]+=n

    def description(self):
        return dict(policy='Periodic releases in simulated time; Continuous once per step, after due Periodic tasks',
                    clock_ms=self.clock, run_epoch_ms=self.origin, preemptive=False, event_tasks=any(t.kind=='Event' for t in self.tasks), safety_tasks=False,
                    event_dispatch='Immediate higher-priority EVENT; deferred lower/equal at task returns; no CPU timing/preemption model',
                    watchdog_enforced=False, release_limit=MAX_RELEASES,
                    inhibition='Live at each release; current body completes; periodic phase continues without catch-up',
                    release_budget='Counts potential release slots, including inhibited tasks',
                    equal_priority='Base releases use source order and precede queued Events; Event ties use request order',
                    first_periodic_release='One effective period after Run entry',
                    rate_change='Changed periods start at the next advance boundary; prepared releases keep their original phase',
                    tasks=[dict(name=t.name, kind=t.kind, priority=t.priority if t.kind!='Continuous' else None, rate_ms=self.periods.get(i), source_rate_ms=t.period,
                                inhibited=self.inhibitions[i], source_inhibited=t.inhibited, executions=self.counts[i],
                                last_release_ms=self.last[i], next_release_ms=None if self.inhibitions[i] else self.next_due.get(i),
                                **({'event_instruction_overlaps':self.overlaps[i],
                                    'event_pending_requests_coalesced':self.coalesced[i]} if t.kind=='Event' else {}))
                           for i, t in enumerate(self.tasks)])
