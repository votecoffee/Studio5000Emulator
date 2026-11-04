"""Instruction-only Event tasks with bounded logical priority dispatch."""
import heapq
import re

from .integer_math import CONTROLLERS
from .model import ModelError
from .task_scheduler import MAX_RELEASES


def specification(node):
    related=[item for item in node.iter() if item is not node and item.tag.rsplit('}',1)[-1].casefold()=='eventinfo']
    if len(related)!=1 or related[0] not in list(node) or related[0].tag!='EventInfo':
        return dict(error='Event task requires one canonical EventInfo declaration')
    info=related[0]
    if (set(info.attrib)-{'EventTrigger','EnableTimeout','Use','EventTag'} or len(info) or (info.text or '').strip()
            or info.get('Use') not in (None,'Target') or info.get('EventTag') not in (None,'')
            or info.get('EventTrigger')!='EVENT Instruction Only' or info.get('EnableTimeout')!='false'):
        return dict(error='Only EVENT Instruction Only with explicit timeout disabled is supported')
    for name in ('Name','Type','Class','Priority','InhibitTask'):
        if [key for key in node.attrib if key.rsplit('}',1)[-1].casefold()==name.casefold()]!=[name]:
            return dict(error='Event task requires explicit unambiguous identity, priority and inhibition')
    if node.get('InhibitTask') not in ('true','false'):
        return dict(error='Event task InhibitTask must be true or false')
    return dict(trigger='EVENT Instruction Only',timeout=False)


def profile(project):
    if (project.version!='35' or project.processor.upper() not in CONTROLLERS
            or not project.task_configuration.source_complete
            or project.task_configuration.source_sha256!=project.sha256):
        raise ModelError('Event tasks require a complete v35 ControlLogix 5580 source profile')


def target(engine,op,scope):
    profile(engine.project)
    if engine.mode!='project' or engine._task_scheduler is None or scope in engine.memory.frames:
        raise ModelError('EVENT requires project task context; routine harness/AOI calls remain unqualified')
    if len(op.args)!=1 or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,39}',op.args[0]):
        raise ModelError('EVENT requires one literal configured task name')
    scheduler=engine._task_scheduler
    index=next((i for i,t in enumerate(scheduler.tasks) if t.name.casefold()==op.args[0].casefold()),None)
    if index is None:raise ModelError('EVENT task does not exist: '+op.args[0])
    caller=next((i for i,row in enumerate(engine.project.tasks)
                 if scope.casefold() in {p.casefold() for p in row['programs']}),None)
    if caller is None:raise ModelError('EVENT caller has no unique scheduled task context')
    return index


def execute(engine,op,power,scope):
    index=target(engine,op,scope)
    if power:
        if engine._event_dispatch is None:raise ModelError('EVENT has no active simulation advance')
        engine._event_dispatch.trigger(index)
    return power


def interrupt_target(engine,op,scope):
    profile(engine.project)
    if engine.mode!='project' or engine._task_scheduler is None or scope in engine.memory.frames:
        raise ModelError('UID/UIE requires project task context; routine harness/AOI calls remain unqualified')
    if op.args:raise ModelError(op.name+' requires no operands')
    if not any(scope.casefold() in {p.casefold() for p in task['programs']} for task in engine.project.tasks):
        raise ModelError('UID/UIE caller has no scheduled task context')


def execute_interrupt(engine,op,power,scope):
    interrupt_target(engine,op,scope)
    if power:
        if engine._event_dispatch is None:raise ModelError('UID/UIE has no active simulation advance')
        engine._event_dispatch.interrupt(op.name)
    return power


class Dispatch:
    def __init__(self,engine,batch,run):
        self.engine=engine;self.batch=batch;self.run=run;self.active=set()
        self.releases=[];self.overlaps={};self.coalesced={};self.accepted=0
        self.pending=set();self.queue=[];self.interrupt_depth={}
        self.status=dict(engine._task_event_status)
        self.overlap_counts=dict(engine._task_scheduler.overlaps)

    def masked(self):
        return self.interrupt_depth.get(self.engine._executing_task,0)>0

    def interrupt(self,name):
        task=self.engine._executing_task
        if task is None:raise ModelError('UID/UIE has no executing task')
        depth=self.interrupt_depth.get(task,0)
        if name=='UID':self.interrupt_depth[task]=depth+1
        elif depth==0:raise ModelError('UIE requires an active UID in this software profile')
        elif depth>1:self.interrupt_depth[task]=depth-1
        else:
            del self.interrupt_depth[task]
            priority=next(t.priority for t in self.engine._task_scheduler.tasks if t.name==task)
            self.drain(priority)

    def complete_task(self,task):
        if self.interrupt_depth.get(task,0):
            raise ModelError('Unbalanced UID/UIE at task completion in this software profile')

    def trigger(self,index):
        scheduler=self.engine._task_scheduler;task=scheduler.tasks[index]
        if task.kind!='Event' or scheduler.inhibitions[index]:return
        if index in self.active:
            self.overlaps[index]=self.overlaps.get(index,0)+1
            self.overlap_counts[index]+=1
            if task.name.casefold() in self.status:self.status[task.name.casefold()]|=4
            return
        if index in self.pending:
            self.coalesced[index]=self.coalesced.get(index,0)+1
            return
        caller=next(t for t in scheduler.tasks if t.name==self.engine._executing_task)
        self.accepted+=1
        if len(self.batch.releases)+self.accepted>MAX_RELEASES:raise ModelError('Event task release budget exceeded')
        if task.name.casefold() in self.status:self.status[task.name.casefold()]|=1
        if task.priority<caller.priority and not self.masked():
            self._execute(index,self.engine.time_ms)
            # Newly queued work may outrank the restored caller, but not the child.
            self.drain(caller.priority)
        else:
            self.pending.add(index)
            heapq.heappush(self.queue,(task.priority,self.accepted,index,self.engine.time_ms))

    def _execute(self,index,due):
        task=self.engine._task_scheduler.tasks[index]
        if self.engine._task_scheduler.inhibitions[index]:return
        self.active.add(index)
        try:self.run(due,task.name,task.entries)
        finally:self.active.remove(index)
        self.releases.append((due,index))

    def drain(self,ceiling=17):
        """Run ready Events before lower-priority work, using FIFO for Event ties."""
        while self.queue and self.queue[0][0]<ceiling and not self.masked():
            _,_,index,due=heapq.heappop(self.queue)
            self.pending.remove(index)
            self._execute(index,due)


def description():
    return dict(profile='v35-5580-instruction-EVENT', languages=['RLL','ST'],
                source='Standard EventInfo EVENT Instruction Only; explicit EnableTimeout false',
                dispatch='Unmasked higher-priority target runs immediately; UID queues requests until outer UIE; lower/equal targets wait for task return at the same simulated time',
                ordering='Ready Event priority then request order; coincident base releases precede queued Events at equal priority',
                retrigger='Active requests are discarded as modeled overlaps; pending duplicates coalesce and have a separate diagnostic',
                pending_policy='At most one pending execution per task; software policy, native pending-duplicate parity unverified',
                non_event='Existing Continuous/Periodic target or live-inhibited Event target does not execute; queued targets recheck before dispatch',
                rollback='Event writes, first scans, release counts and overlap diagnostics commit only with the complete advance',
                native_cpu_timing=False, native_status_parity=False,
                remaining=['Native equal-priority time slicing and pending-duplicate semantics','External/I/O/motion/consumed/timeout event sources',
                           'AOI/routine harness and ST FOR-loop EVENT calls','Native interrupt latency, watchdog/status/fault parity'])


def interrupt_description():
    return dict(profile='v35-5580-balanced-UID-UIE',languages=['RLL','ST'],
                operands='No operands; complete Standard project task context, outside AOIs',
                nesting='Task-local depth shared across calls and Programs in one invocation; only the outermost UIE enables dispatch',
                dispatch='EVENT requests queue while masked; outer UIE drains higher-priority requests before the next instruction; lower/equal wait for task return',
                duplicates='Existing pending coalescing, active-overlap and release/instruction budgets apply',
                lifecycle='False/prescan do nothing; transient depth discarded with the advance',
                guards='UIE without UID and nonzero depth at task completion fault and roll back the advance; conservative software boundaries',
                native_runtime_parity=False,
                remaining=['Native unmatched-pair and persistent-state behavior','CPU/Periodic preemption, interrupt latency, watchdogs and communications',
                           'Fault routines/Controller Fault Handler, Safety, other event sources','AOI, routine harness, ST FOR and other profiles'])
