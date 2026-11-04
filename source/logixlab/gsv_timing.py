"""Read committed interpreter Program/Task scan durations through typed GSV."""
import struct

from .integer_math import CONTROLLERS
from .model import ModelError
from .numeric_copy import static_reference
from . import gsv_wall_clock
from .gsv_configuration import current_instance

ATTRIBUTES={'program':{'lastscantime':2,'maxscantime':3},
            'task':{'lastscantime':8,'maxscantime':7,'starttime':13,'minimuminterval':14,'maximuminterval':15}}


def matches(op):
    return (len(op.args)>=3 and all(isinstance(a,str) for a in op.args[:3])
            and op.args[0].casefold() in ATTRIBUTES and op.args[2].casefold() in ATTRIBUTES[op.args[0].casefold()])


def specification(engine,op,scope='',*,executing=False):
    if len(op.args)!=4 or any(not isinstance(a,str) for a in op.args):
        raise ModelError('Timing GSV requires four neutral-text operands')
    project=engine.project
    if project.version!='35' or project.processor.upper() not in CONTROLLERS or engine.mode!='project':
        raise ModelError('Timing GSV requires the v35 ControlLogix 5580 project execution profile')
    cls,instance,attribute,_=op.args;cls=cls.casefold();attribute=attribute.casefold()
    if cls not in ATTRIBUTES or attribute not in ATTRIBUTES[cls]:raise ModelError('Unsupported timing GSV class/attribute')
    instance=current_instance(engine,cls,instance,scope,executing=executing,allow_event=True)
    if cls=='task':
        name=next((t['name'] for t in project.tasks if t['name'].casefold()==instance.casefold()),None)
        if not name or not engine.task_scan_timing_eligible(name):
            raise ModelError('Task timing GSV requires a complete eligible Standard Task and explicit measurement settings')
        task=next(t for t in project.tasks if t['name']==name)
        if task['type']=='Event':
            current_instance(engine,'Program','THIS',scope,executing=executing,allow_event=True)
        elif len(project.tasks)==1 and engine.runtime_references.task_slot(project,name) is None:
            raise ModelError('Single-Task timing GSV requires the existing Task registry identity')
    else:
        name=next((n for n in project.programs if n.casefold()==instance.casefold()),None)
        program=project.programs.get(name)
        scheduled=(name is not None and (name.casefold() in engine._no_main_programs or
                   any(project.routines[entry].program==name for entry in engine.entries if entry in project.routines)))
        if (not program or program['class']!='Standard' or program['disabled'] or program['use_as_folder']
                or not scheduled or not project.program_configuration.type_attributes(name,source_sha256=project.sha256)):
            raise ModelError('Program timing GSV requires an explicit eligible scheduled Standard Program name')
    return cls,name,ATTRIBUTES[cls][attribute]


def destination(memory,ref,scope,number):
    if number in (13,14,15):
        if number!=13 and memory.check_writable(ref,scope)[2]!='DINT':
            raise ModelError('Task interval GSV destination requires two contiguous DINT elements')
        return gsv_wall_clock.destination(memory,ref,scope,2)

    key,parts,dtype=memory.check_writable(ref,scope)
    if dtype!='DINT' or isinstance(memory.at(key,parts),(dict,list)):
        raise ModelError('Timing GSV destination requires one writable DINT scalar element')
    return key,[parts],dtype


def validate(engine,op,scope):
    _,_,number=specification(engine,op,scope);memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        return destination(memory,op.args[3],scope,number)
    finally:memory.structural=previous


def execute(engine,op,scope):
    cls,name,number=specification(engine,op,scope,executing=True);memory=engine.memory
    key,paths,dtype=destination(memory,op.args[3],scope,number)
    reader=engine.task_scan_timing_attributes if cls=='task' else engine.program_timing_attributes
    raw=reader(name,source_sha256=engine.project.sha256).get(number)
    count=2 if number in (13,14,15) else 1
    if raw is None or len(raw)!=count*4:raise ModelError('Timing GSV measurement is unavailable')
    # Keep the same DWORD bits as the existing protocol counters in signed DINT storage.
    values=struct.unpack('<q' if dtype=='LINT' else '<'+'i'*count,raw)
    for path,value in zip(paths,values,strict=True):memory.store(key,path,value)


def write_effects(engine,op,scope):
    memory=engine.memory;previous=memory.structural;memory.structural=True
    try:
        key,paths,_=validate(engine,op,scope)
        if static_reference(memory,op.args[3],scope):return [(key,path) for path in paths]
        key,parts,_=memory.check_writable(op.args[3],scope)
        boundary=next((i for i,part in enumerate(parts) if isinstance(part,int)),len(parts))
        return [(key,parts[:boundary])]
    finally:memory.structural=previous


def description():
    return dict(profile='v35-5580-committed-GSV-timing',languages=['RLL','ST'],
                classes=['Program','Task'],attributes=['LastScanTime','MaxScanTime'],
                task_attributes=['StartTime','MinimumInterval','MaximumInterval'],
                destination='Scan durations: exact DINT; Task intervals: two contiguous DINTs; Task StartTime: scalar LINT or two contiguous DINTs',
                source='Committed host perf_counter_ns interpreter durations/start intervals, in whole microseconds; StartTime samples existing host UTC WallClockTime',
                intervals='Independent successive actual host invocation starts; zero until two executions; include host idle time, not simulated rate',
                start_time='Zero before execution; previous committed invocation UTC microseconds since 1970; missing clock sample withholds only StartTime',
                visibility='Zero until a successful advance; reads during an advance see the preceding committed timing snapshot',
                task_scope='Complete-source Standard Continuous/Periodic and instruction-only Event tasks; independent successful invocation durations; existing single-Task native contract retained',
                program_scope='Eligible scheduled ordinary Standard Programs, including the existing zero-initialized no-main profile',
                selection='Structural preflight without live destination indices or timing reads; false/prescan skip outputs; full writes establish unknown cells',
                failures='Unavailable measurements, invalid indices and later faults roll back tags, bindings, scheduling and uncommitted measurements',
                st_for_effects='Exact static cells; aliases/AOI/indirect destinations conservatively cover their enclosing array',
                native_runtime_parity=False,controller_performance_prediction=False,
                current_instance='Program/Task THIS in ordinary scheduled Continuous/Periodic/qualified Event Program routines; prior committed snapshot',
                remaining=['Empty/numeric instances, AOI/harness THIS contexts, additional attributes and timing setters',
                           'TIME/DT destination types, simulated-time intervals and newer shortened interval names',
                           'Multi-Task/Event native protocol timing, Safety/other Event profiles, routine harnesses and other profiles',
                           'Native per-execution visibility, precision, overflow/status/layout/lifecycle parity'])
