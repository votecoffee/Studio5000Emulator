"""Bounded SSV Task settings over deterministic releases."""
import struct
from .model import ModelError
from . import gsv_configuration
from .task_configuration import NAME
from .task_scheduler import EventTimeout, MIN_PERIOD_MS, MAX_PERIOD_MS, MIN_PRIORITY, MAX_PRIORITY

MIN_WATCHDOG_US = 1000
MAX_WATCHDOG_US = 2_000_000_000
DEFAULT_WATCHDOG_US = {'Continuous': 5_000_000, 'Periodic': 500_000}


def validate(engine,op,scope,*,executing=False):
    if (len(op.args)!=4 or any(not isinstance(a,str) for a in op.args)
            or op.args[0].casefold()!='task' or op.args[2].casefold() not in ('inhibittask','rate','priority','watchdog','enabletimeout')
            or not NAME.fullmatch(op.args[1])):
        raise ModelError('SSV supports Task InhibitTask, Rate, Priority, Watchdog or EnableTimeOut and a task name or THIS')
    if engine.mode!='project' or engine._task_scheduler is None or scope in engine.memory.frames:
        raise ModelError('SSV Task requires project task context; AOI/routine harness calls remain unqualified')
    source_type,_=gsv_configuration.source(engine,op,scope,executing=executing)
    name=gsv_configuration.current_instance(engine,'Task',op.args[1],scope,executing=executing,allow_event=True)
    scheduler=engine._task_scheduler
    if scheduler.source!=scheduler.configuration:raise ModelError('Task configuration changed; reload the project')
    index=next(i for i,t in enumerate(scheduler.tasks) if t.name.casefold()==name.casefold())
    if scheduler.tasks[index].kind not in ('Continuous','Periodic','Event'):
        raise ModelError('SSV InhibitTask supports Standard Continuous/Periodic/qualified Event targets only')
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,parts,dtype=memory.resolve(op.args[3],scope)
        if dtype!=source_type or isinstance(memory.at(key,parts),(list,dict,bool)):
            raise ModelError(f'SSV {op.args[2]} source requires an exact scalar {source_type} tag')
    finally:memory.structural=previous
    return index


def execute(engine,op,power,scope):
    index=validate(engine,op,scope,executing=bool(power))
    if power:
        value=engine.memory.read(op.args[3],scope)
        attribute=op.args[2].casefold()
        if type(value) is not int:raise ModelError(f'SSV {op.args[2]} source must contain a known integer')
        if attribute=='rate':
            period,remainder=divmod(value,1000)
            if remainder or not MIN_PERIOD_MS<=period<=MAX_PERIOD_MS:
                raise ModelError(f'SSV Rate requires {MIN_PERIOD_MS}..{MAX_PERIOD_MS} whole milliseconds in DINT microseconds')
            if index in engine._task_scheduler.event_timeouts:
                settings=engine._event_dispatch.event_timeouts
                settings[index]=EventTimeout(period,settings[index].enabled)
            else:engine._task_scheduler.periods[index]=period
        elif attribute=='enabletimeout':
            settings=engine._event_dispatch.event_timeouts
            period=settings[index].period_ms
            if value and period is None:
                raise ModelError('SSV EnableTimeOut requires a defined Event Rate')
            settings[index]=EventTimeout(period,value!=0)
        elif attribute=='priority':
            if not MIN_PRIORITY<=value<=MAX_PRIORITY:
                raise ModelError(f'SSV Priority requires an INT in {MIN_PRIORITY}..{MAX_PRIORITY}')
            engine._task_scheduler.priorities[index]=value
        elif attribute=='watchdog':
            scheduler=engine._task_scheduler
            if value==0:
                value=DEFAULT_WATCHDOG_US.get(scheduler.tasks[index].kind)
                if value is None:raise ModelError('SSV Watchdog zero is qualified only for Continuous and Periodic tasks')
            if not MIN_WATCHDOG_US<=value<=MAX_WATCHDOG_US:
                raise ModelError(f'SSV Watchdog requires DINT microseconds in {MIN_WATCHDOG_US}..{MAX_WATCHDOG_US}')
            scheduler.watchdog_overrides[index]=value
        else:engine._task_scheduler.inhibitions[index]=value!=0
    return power


def description():
    return dict(profile='v35-5580-SSV-Task-InhibitTask',languages=['RLL','ST'],source='Exact scalar DINT tag; zero enables, any nonzero inhibits',
                targets=['Standard Continuous','Standard Periodic','Instruction-only Standard Event'],effect='Current body completes; each later release checks live inhibition',
                phase='Periodic phase continues while inhibited; missed releases are discarded without catch-up',
                events='Live inhibition gates new requests and pending dispatch; active body completes; accepted status remains latched when pending work is skipped',
                instances='Literal configured task name or THIS in ordinary scheduled Program context',
                lifecycle='Run entry retains inhibition and restarts phase; project reset/reload restores source settings',
                rollback='Flags, values, release counts, first scans and phase commit with the complete advance',
                native_runtime_parity=False,remaining=['Other inhibition contexts and profiles','Safety and other Event profiles','AOI/routine harness calls',
                                                    'Native abort/resume/phase/status/fault semantics'])


def rate_description():
    return dict(profile='v35-5580-SSV-Task-Rate',languages=['RLL','ST'],
                targets=['Standard Periodic','Instruction-only Standard Event'],source='Exact scalar DINT tag in microseconds',
                period_ms=[MIN_PERIOD_MS,MAX_PERIOD_MS],whole_milliseconds=True,
                visibility='GSV Rate immediately reads the staged value during the advance',
                effect='Prepared releases keep their original timing; a changed period starts a new phase at successful advance end',
                lifecycle='Run entry and routine replacement retain the effective period; reset/reload restores the source period',
                rollback='Rate and phase commit with task progress and tag values',
                event_timeouts=True,event_enable='EnableTimeOut uses exact DINT; zero disables and nonzero requires a defined rate',
                event_deadline='New or changed enabled timeout starts at commit; disabling cancels future deadlines',
                native_protocol_expanded=False,native_runtime_parity=False)


def priority_description():
    return dict(profile='v35-5580-SSV-Task-Priority',languages=['RLL','ST'],
                targets=['Standard Periodic','Instruction-only Standard Event'],source='Exact scalar INT tag',
                range=[MIN_PRIORITY,MAX_PRIORITY],visibility='GSV Priority immediately reads the staged value',
                effect='Periodic release order and Event dispatch use the advance-start priorities until the next advance',
                lifecycle='Run entry and routine replacement retain effective priorities; reset/reload restores source priorities',
                rollback='Priority and release ordering commit with task progress and tag values',
                native_protocol_expanded=False,native_runtime_parity=False)


def watchdog_description():
    return dict(profile='v35-5580-SSV-Task-Watchdog',languages=['RLL','ST'],
                targets=['Standard Continuous','Standard Periodic','Instruction-only Standard Event'],
                source='Exact scalar DINT microseconds and explicit source Watchdog setting',
                range_us=[MIN_WATCHDOG_US,MAX_WATCHDOG_US],zero_defaults_us=dict(DEFAULT_WATCHDOG_US),
                visibility='GSV Watchdog immediately reads the staged setting',
                lifecycle='Run entry and routine replacement retain overrides; reset/reload restores source settings',
                rollback='Overrides commit with tag values and task progress',
                watchdog_enforced=False,native_protocol_expanded=False,native_runtime_parity=False)


def attributes(engine,name,*,source_sha256):
    project=engine.project;scheduler=engine._task_scheduler
    if (source_sha256!=project.sha256 or not isinstance(name,str)
            or scheduler is None or scheduler.source!=scheduler.configuration):return {}
    index=next((i for i,t in enumerate(scheduler.tasks) if t.name.casefold()==name.casefold()),None)
    if index is None or 19 not in project.task_configuration.attributes(name,source_sha256=source_sha256):return {}
    return {19:struct.pack('<I',int(scheduler.inhibitions[index]))}
