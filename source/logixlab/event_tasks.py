"""Instruction-only Event tasks with synchronous higher-priority dispatch."""
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
    task=scheduler.tasks[index]
    if (task.kind=='Event' and not task.inhibited and index!=caller
            and task.priority>=scheduler.tasks[caller].priority):
        raise ModelError('EVENT lower/equal-priority target dispatch remains unqualified')
    return index


def execute(engine,op,power,scope):
    index=target(engine,op,scope)
    if power:
        if engine._event_dispatch is None:raise ModelError('EVENT has no active simulation advance')
        engine._event_dispatch.trigger(index)
    return power


class Dispatch:
    def __init__(self,engine,batch,run):
        self.engine=engine;self.batch=batch;self.run=run;self.active=set()
        self.releases=[];self.overlaps={};self.accepted=0

    def trigger(self,index):
        scheduler=self.engine._task_scheduler;task=scheduler.tasks[index]
        if task.kind!='Event' or task.inhibited:return
        if index in self.active:
            self.overlaps[index]=self.overlaps.get(index,0)+1
            return
        caller=next(t for t in scheduler.tasks if t.name==self.engine._executing_task)
        if task.priority>=caller.priority:raise ModelError('EVENT target priority changed outside the supported profile')
        self.accepted+=1
        if len(self.batch.releases)+self.accepted>MAX_RELEASES:raise ModelError('Event task release budget exceeded')
        due=self.engine.time_ms;self.active.add(index)
        try:self.run(due,task.name,task.entries)
        finally:self.active.remove(index)
        self.releases.append((due,index))


def description():
    return dict(profile='v35-5580-higher-priority-EVENT', languages=['RLL','ST'],
                source='Standard EventInfo EVENT Instruction Only; explicit EnableTimeout false',
                dispatch='Higher-priority target runs before caller next instruction at the same simulated time',
                retrigger='Each enabled EVENT requests one execution; active self-target increments modeled overlap and is discarded',
                non_event='Existing Continuous/Periodic target or inhibited Event target does not execute',
                rollback='Event writes, first scans, release counts and overlap diagnostics commit only with the complete advance',
                native_cpu_timing=False, native_status_parity=False,
                remaining=['Lower/equal-priority deferred dispatch','External/I/O/motion/consumed/timeout event sources',
                           'AOI/routine harness and FOR-loop EVENT calls','Native interrupt latency, watchdog/status/fault parity'])
