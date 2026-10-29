"""Bounded deterministic releases; tasks execute atomically without CPU timing."""
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
            if row['class'] != 'Standard' or row['type'] not in ('Continuous', 'Periodic'):
                raise ModelError('Task scheduler supports Standard Continuous/Periodic tasks only')
            for program in row['programs']:
                if not isinstance(program, str) or not program or program.casefold() in programs:
                    raise ModelError('Each Program may be scheduled only once')
                programs.add(program.casefold())
            period = None; priority = 16
            if row['type'] == 'Continuous':
                continuous += 1
                if continuous > 1: raise ModelError('Only one Continuous task may be configured')
            else:
                try:
                    rate = Decimal(row['rate'])
                    if not rate.is_finite() or not 1 <= rate <= 60000 or rate != rate.to_integral_value():
                        raise ValueError()
                    period = int(rate)
                except (InvalidOperation, ValueError, TypeError):
                    raise ModelError('Periodic task rate must be whole milliseconds in 1..60000') from None
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
        for name in ('clock', 'origin', 'next_due', 'counts', 'last'):
            setattr(self, name, copy.deepcopy(getattr(previous, name)))

    def commit(self, batch):
        if batch.start != self.clock:
            raise ModelError('Task scheduler batch is stale')
        self.clock = batch.end
        self.next_due = dict(batch.next_due)
        for due, i in batch.releases:
            self.counts[i] += 1
            self.last[i] = due

    def description(self):
        return dict(policy='Periodic releases in simulated time; Continuous once per step, after due Periodic tasks',
                    clock_ms=self.clock, run_epoch_ms=self.origin, preemptive=False, event_tasks=False, safety_tasks=False,
                    watchdog_enforced=False, release_limit=MAX_RELEASES,
                    equal_priority='Configured source order at coincident releases',
                    first_periodic_release='One configured period after Run entry',
                    tasks=[dict(name=t.name, kind=t.kind, priority=t.priority if t.period is not None else None, rate_ms=t.period,
                                inhibited=t.inhibited, executions=self.counts[i],
                                last_release_ms=self.last[i], next_release_ms=self.next_due.get(i))
                           for i, t in enumerate(self.tasks)])
