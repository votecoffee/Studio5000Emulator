"""Bounded SSV Task InhibitTask control over deterministic release boundaries."""
import struct
from .model import ModelError
from . import gsv_configuration
from .task_configuration import NAME


def validate(engine,op,scope):
    if (len(op.args)!=4 or any(not isinstance(a,str) for a in op.args)
            or op.args[0].casefold()!='task' or op.args[2].casefold()!='inhibittask'
            or not NAME.fullmatch(op.args[1])):
        raise ModelError('SSV supports Task, literal task name, InhibitTask and a DINT source tag')
    if engine.mode!='project' or engine._task_scheduler is None or scope in engine.memory.frames:
        raise ModelError('SSV Task requires project task context; AOI/routine harness calls remain unqualified')
    gsv_configuration.source(engine,op)
    scheduler=engine._task_scheduler
    if scheduler.source!=scheduler.configuration:raise ModelError('Task configuration changed; reload the project')
    index=next(i for i,t in enumerate(scheduler.tasks) if t.name.casefold()==op.args[1].casefold())
    if scheduler.tasks[index].kind not in ('Continuous','Periodic'):
        raise ModelError('SSV InhibitTask supports Standard Continuous/Periodic targets only')
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,parts,dtype=memory.resolve(op.args[3],scope)
        if dtype!='DINT' or isinstance(memory.at(key,parts),(list,dict,bool)):
            raise ModelError('SSV InhibitTask source requires an exact scalar DINT tag')
    finally:memory.structural=previous
    return index


def execute(engine,op,power,scope):
    index=validate(engine,op,scope)
    if power:
        value=engine.memory.read(op.args[3],scope)
        if type(value) is not int:raise ModelError('SSV InhibitTask source must contain a known DINT')
        engine._task_scheduler.inhibitions[index]=value!=0
    return power


def description():
    return dict(profile='v35-5580-SSV-Task-InhibitTask',languages=['RLL','ST'],source='Exact scalar DINT tag; zero enables, any nonzero inhibits',
                targets=['Standard Continuous','Standard Periodic'],effect='Current body completes; each later release checks live inhibition',
                phase='Periodic phase continues while inhibited; missed releases are discarded without catch-up',
                lifecycle='Run entry retains inhibition and restarts phase; project reset/reload restores source settings',
                rollback='Flags, values, release counts, first scans and phase commit with the complete advance',
                native_runtime_parity=False,remaining=['Other SSV attributes/classes','Event/Safety targets','AOI/routine harness calls',
                                                    'Native abort/resume/phase/status/fault semantics'])


def attributes(engine,name,*,source_sha256):
    project=engine.project;scheduler=engine._task_scheduler
    if (source_sha256!=project.sha256 or not isinstance(name,str)
            or scheduler is None or scheduler.source!=scheduler.configuration):return {}
    index=next((i for i,t in enumerate(scheduler.tasks) if t.name.casefold()==name.casefold()),None)
    if index is None or 19 not in project.task_configuration.attributes(name,source_sha256=source_sha256):return {}
    return {19:struct.pack('<I',int(scheduler.inhibitions[index]))}
