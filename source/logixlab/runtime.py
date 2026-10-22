from __future__ import annotations

import copy
import operator
from collections import Counter
from time import perf_counter_ns
from .program_timing import ProgramTiming
from . import task_runtime
from .wall_clock import current_value_microseconds
from .runtime_references import RuntimeReferences
from .change_detection import ChangeDetection
from . import system_values
from .model import ARITIES, Branch, Memory, ModelError, Op, operations
from .extended import Extensions
from .addons import AddOns
from .calls import Calls
from .structured import Structured
from . import __version__


class ReturnRoutine(Exception):
    pass


class JumpRoutine(Exception):
    def __init__(self,label):self.label=label.lower()


class Engine:
    """Deterministic model; a failed scan rolls back all simulator state."""
    def __init__(self, project, mode="project", routine="", *, defer_prescan=False):
        self.project = project
        self.change_detection=ChangeDetection(project.sha256,project.controller_configuration.changes_to_detect)
        self.runtime_references = RuntimeReferences(project)
        self.mode = mode
        self.selected = routine.lower()
        self.memory = Memory(project)
        self.extensions = Extensions(self)
        self.labels = {}
        self.instruction_limit = 100000
        self.budget = self.instruction_limit
        self.scan_count = 0
        self.time_ms = 0
        self.last_timer = {}
        self.trace = []
        self.changes = []
        self._native_fault_history_uncertain = False
        self.fault = ""
        self.prescan_count = 0
        self._initial_prescan_pending = defer_prescan
        self.entries = []
        self._empty_programs = set()
        self.active = set()
        self.blockers = []
        self.addons = AddOns(self)
        self.calls = Calls(self)
        self.structured = Structured(self)
        self._program_timings = {}
        self._task_measurements = None
        self._measured_task = None
        self._plan()
        if not self.blockers:
            try:self._apply_prescan(preview=defer_prescan,report_fault=False)
            except ModelError as e:
                self.blockers.append(f"Prescan: {e}")
            self.trace=[]
        if self.mode=='project' and not self.blockers:
            for name in self._empty_programs:self._program_timings[name]=ProgramTiming()
            for entry in self.entries:
                name=self.project.routines[entry].program
                if self.project.program_configuration.type_attributes(name,source_sha256=project.sha256):
                    self._program_timings[name.casefold()]=ProgramTiming()
            task=project.tasks[0]['name']
            if project.task_configuration.measurement_supported(task,source_sha256=project.sha256):
                self._measured_task=task.casefold()
                self._task_measurements=task_runtime.TaskMeasurements()

    def _task_runtime_available(self,task,source_sha256):
        if (source_sha256!=self.project.sha256 or self.mode!='project' or self.blockers
                or not isinstance(task,str) or task.casefold()!=self._measured_task
                or self._task_measurements is None or len(self.project.tasks)!=1
                or self.project.tasks[0]['name'].casefold()!=self._measured_task
                or self.project.tasks[0]['inhibited']
                or not self.project.task_configuration.measurement_supported(task,source_sha256=source_sha256)
                or self.runtime_references.task_slot(self.project,task) is None):
            return False
        return True

    def task_measurement_attributes(self,task,*,source_sha256):
        return self._task_measurements.attributes() if self._task_runtime_available(task,source_sha256) else {}

    def task_status_attributes(self,task,*,source_sha256):
        # This runner executes one complete Task serially. It has no EVENT or
        # timeout trigger and never dispatches a second overlapping execution.
        # Do not classify a simulator failure as a native Task fault/status.
        if (not self._task_runtime_available(task,source_sha256) or self.fault
                or self._native_fault_history_uncertain):return {}
        return {3:bytes(4),9:bytes(4)}

    def task_status_description(self):
        available=bool(self.task_status_attributes(self._measured_task,source_sha256=self.project.sha256))
        return {'attributes':[3,9],'known_clean_tasks':int(available),
                'execution':'One complete Task at a time; no queued overlapping dispatch',
                'event_triggered':False,'timeout_triggered':False,
                'unclassified_fault_seen_since_reset':self._native_fault_history_uncertain,
                'unknown_status_withheld_until_reset':True,'native_fault_classification':False,
                'periodic_deadline_overlaps_modeled':False,'native_watchdog_enforcement':False,
                'physical_history_imported':False,'native_writes':False}

    def task_measurement_description(self):
        available=bool(self.task_measurement_attributes(self._measured_task,source_sha256=self.project.sha256))
        return {'attributes':[7,8,13,14,15],'tasks_available':int(available),
                'successful_task_executions':self._task_measurements.executions if self._task_measurements else 0,
                'measurement':'Host monotonic perf_counter_ns; complete scheduled interpreter Task',
                'scan_time_bits':32,'interval_bits':64,'units':'Whole microseconds',
                'interval_scope':'Between successful Task starts; zero until two executions',
                'start_time_available':bool(available and self._task_measurements.start_time_us is not None),
                'start_time_source':'Simulator WALLCLOCKTIME; UTC microseconds since 1970-01-01',
                'start_time_before_first_success':'Unavailable',
                'wall_clock_adjustments_visible':True,
                'prescan_included':False,'failed_scans_update_counters':False,
                'watchdog_enforced':False,'controller_performance_prediction':False}

    @property
    def fault(self):return self._fault

    @fault.setter
    def fault(self,value):
        self._fault=value
        # No native type/code/info mapping exists for simulator failures.
        # A later successful scan cannot turn that unknown history into clean.
        if value:
            self._native_fault_history_uncertain=True
            self.change_detection.invalidate()

    def program_fault_attributes(self,program,*,source_sha256):
        if (source_sha256!=self.project.sha256 or self.mode!='project' or self.blockers or self.fault or
                self._native_fault_history_uncertain or not isinstance(program,str) or
                program.casefold() not in self._program_timings):return {}
        return {20:bytes(44),21:bytes(44)}

    def program_fault_description(self):
        available=(self.mode=='project' and not self.blockers and not self.fault and not self._native_fault_history_uncertain)
        return {'attributes':[20,21],'known_clean_programs':len(self._program_timings) if available else 0,
                'unclassified_fault_seen_since_reset':self._native_fault_history_uncertain,
                'record_bytes':44,'native_fault_classification':False,'physical_fault_history_imported':False,
                'unknown_records_withheld_until_reset':True}

    def program_status_attributes(self,program,*,source_sha256,task_owner,idle):
        # Only the reference's normal zero state is modeled. Neither the
        # unscheduled 0x0110 word nor unclassified fault/edit bits are inferred.
        if (type(task_owner) is not int or not 1<=task_owner<=0xFFFF or
                not self.program_fault_attributes(program,source_sha256=source_sha256) or
                not self.project.program_diagnostics.edit_attributes(program,source_sha256=source_sha256,idle=idle)):
            return {}
        return {1:bytes(2)}

    def program_timing_attributes(self, program, *, source_sha256):
        if (source_sha256!=self.project.sha256 or self.mode!='project' or self.blockers
                or not isinstance(program,str)):return {}
        timing=self._program_timings.get(program.casefold())
        return timing.attributes() if timing is not None else {}

    def program_timing_description(self):
        return {'attributes':[2,3],'programs_available':len(self._program_timings),
                'empty_programs_available':len(self._empty_programs) if not self.blockers else 0,
                'successful_program_executions':sum(t.executions for t in self._program_timings.values()),
                'measurement':'Host monotonic perf_counter_ns; completed main routine including nested calls; empty Programs retain zero without executing a main',
                'units':'Whole microseconds; initial counters are zero until a successful scan',
                'failed_scans_update_counters':False,'prescan_included':False,'controller_performance_prediction':False}

    def _apply_prescan(self, *, preview=False, report_fault=True):
        # AOI prescan routines can copy parameters and mutate instance state.
        # Preserve bindings and execution context as well as values on failure.
        before=copy.deepcopy((self.memory.values,self.memory.frames,self.memory._resolved,
                              self.addons.instances,self.calls.stack,self.last_timer,
                              self.memory.first_scan,self.trace,self.budget))
        def restore():
            (self.memory.values,self.memory.frames,self.memory._resolved,self.addons.instances,
             self.calls.stack,self.last_timer,self.memory.first_scan,self.trace,self.budget)=before
        self.budget=self.instruction_limit
        self.last_timer={}
        self.memory.first_scan=True
        self.trace=[]
        try:self._prescan()
        except Exception as error:
            restore()
            message=f'Prescan rolled back: {str(error) or type(error).__name__}'
            if report_fault:self.fault=message
            raise ModelError(message) from error
        if preview:restore()
        else:
            self.prescan_count+=1
            self._initial_prescan_pending=False
            self.trace=[]

    def enter_run(self):
        """Initialize a Program-to-Run transition without a normal scan."""
        if self.blockers:raise ModelError('Execution blocked; inspect the coverage report')
        if self.fault:raise ModelError('Reset the faulted project before running')
        self._apply_prescan()

    def _plan(self):
        if self.mode == "routine":
            self.blockers.extend(self.project.issues)
            if self.selected not in self.project.routines:
                self.blockers.append("Select a routine for the isolated harness")
                return
            self.entries = [self.selected]
        elif self.mode == "project":
            self.blockers.extend(self.project.issues)
            if len(self.project.tasks) != 1:
                self.blockers.append("Whole-project mode requires exactly one Standard Continuous or Periodic task")
            for task in self.project.tasks:
                if task["inhibited"]: self.blockers.append(f"Task {task['name']} is inhibited")
                if task["type"] not in ("Continuous", "Periodic") or task["class"] != "Standard":
                    self.blockers.append(f"Task {task['name']}: {task['class']} {task['type']} task is unsupported")
                for name in task["programs"]:
                    program = self.project.programs.get(name)
                    if program is None:
                        self.blockers.append(f"Scheduled program {name} is missing")
                    elif program['use_as_folder']:
                        self.blockers.append(f"Program {name} is a folder and cannot be scheduled")
                    elif not program["disabled"]:
                        if (not program['main'] and self.project.program_diagnostics.is_empty(
                                name,source_sha256=self.project.sha256)):
                            self._empty_programs.add(name.casefold())
                        else:self.entries.append(f"{name}/{program['main']}".lower())
                        # Program prescan includes all its routines, including routines not called.
                        self.active.update(k for k, r in self.project.routines.items() if r.program == name)
            for tag in self.project.tags.values():
                if tag.problem: self.blockers.append(f"Tag {tag.key}: {tag.problem}")
            if not self.entries and not self._empty_programs:self.blockers.append("No scheduled main routine")
        else:
            self.blockers.append("Unknown execution mode")
            return
        visiting = set()
        visited = set()
        def visit(key):
            if key in visiting:
                self.blockers.append(f"Recursive JSR cycle at {key}")
                return
            if key in visited: return
            visited.add(key)
            r = self.project.routines.get(key)
            if r is None:
                self.blockers.append(f"Routine {key} is missing")
                return
            visiting.add(key)
            self.active.add(key)
            if self.project.programs[r.program]["class"] != "Standard":
                self.blockers.append(f"{r.key}: safety program execution is unsupported")
            if self.project.programs[r.program]['use_as_folder']:
                self.blockers.append(f"{r.key}: folder program execution is unsupported")
            for p in r.problems: self.blockers.append(f"{r.key}: {p}")
            try:self.calls.validate_routine(r,entry=key in self.entries)
            except ModelError as e:self.blockers.append(str(e))
            if r.kind=='ST':
                try:self.structured.validate(r,r.program)
                except ModelError as e:self.blockers.append(r.key+': '+str(e))
            try:self._build_labels(r)
            except ModelError as e:self.blockers.append(str(e))
            labels=self.labels.get(key,{})
            for rung in r.rungs:
                for op in operations(rung["nodes"]):
                    previous=(self.memory.structural,self.memory.validating)
                    if r.kind=='ST':self.memory.structural=True;self.memory.validating=True
                    try:
                        if not(r.kind=='ST' and op.name=='MID'):self._validate(op, r.program)
                        if op.name=='JMP' and op.args and op.args[0].lower() not in labels:
                            raise ModelError(f'Missing label {op.args[0]}')
                        if op.name == "JSR" and op.args:
                            self.calls.call_spec(op,r.program)
                            visit(f"{r.program}/{op.args[0]}".lower())
                    except (ModelError, ValueError, TypeError) as e:
                        self.blockers.append(f"{r.key}, rung {rung['number']}: {op.name}: {e}")
                    finally:self.memory.structural,self.memory.validating=previous
            visiting.remove(key)
        for key in list(self.active) + self.entries: visit(key)
        self.blockers = list(dict.fromkeys(self.blockers))

    def _build_labels(self,routine):
        labels={};self.labels[routine.key.lower()]=labels
        for index,rung in enumerate(routine.rungs):
            for op in operations(rung['nodes']):
                if op.name=='LBL' and len(op.args)==1:
                    if not rung['nodes'] or rung['nodes'][0] is not op:
                        raise ModelError(f'{routine.key}: LBL must be the first unbranched instruction in its rung')
                    label=op.args[0].lower()
                    if label in labels:raise ModelError(f'{routine.key}: duplicate label {label}')
                    labels[label]=index

    def _validate(self, op, scope):
        n, a = op.name, op.args
        if n in self.project.aois:
            self.addons.validate(op,scope);return
        if n in ('JSR','SBR','RET'):
            self.calls.validate_operands(op,scope);return
        if n not in ARITIES or len(a) != ARITIES[n]: return
        if n in ('JMP','LBL'):
            if not __import__('re').fullmatch(r'[A-Za-z_][\w]*',a[0]):raise ModelError('Invalid label name')
            return
        if n=='GSV':system_values.validate(self,op,scope);return
        if self.extensions.validate(op,scope):return
        if n in ("TND", "AFI", "NOP"): return
        if n in ("TON", "TOF", "RTO", "CTU", "CTD", "RES"):
            key, _, dtype = self.memory.resolve(a[0], scope)
            if self.project.tags[key].constant: raise ModelError("Constant timer/counter cannot be modified")
            expected = "COUNTER" if n in ("CTU", "CTD") else "TIMER"
            if n == "RES":
                if dtype not in ("TIMER", "COUNTER"): raise ModelError("RES requires TIMER or COUNTER")
            elif dtype != expected: raise ModelError(f"Requires {expected}")
            if n != "RES" and a[1:] != ["?", "?"]:
                raise ModelError("Use neutral-text ?,? operands; PRE/ACC are taken from tag data")
            for member in ("PRE", "ACC"): self.memory.resolve(a[0] + "." + member, scope)
            return
        writes = {"OTE": [0], "OTL": [0], "OTU": [0], "ONS": [0], "OSR": [0, 1], "OSF": [0, 1],
                  "MOV": [1], "CLR": [0], "NEG": [1], "ABS": [1], "NOT": [1],
                  "ADD": [2], "SUB": [2], "MUL": [2], "DIV": [2], "MOD": [2],
                  "AND": [2], "OR": [2], "XOR": [2]}.get(n, [])
        for i, arg in enumerate(a):
            value = self.memory.read(arg, scope)
            if isinstance(value, (list, dict)): raise ModelError("Scalar operand required")
            if n not in ("XIC", "XIO", "OTE", "OTL", "OTU", "ONS", "OSR", "OSF") and isinstance(value, bool):
                raise ModelError("This numeric instruction does not support BOOL operands")
            if i in writes:
                self.memory.check_writable(arg,scope)
        if n in ("XIC", "XIO", "OTE", "OTL", "OTU", "ONS", "OSR", "OSF"):
            for arg in a:
                if self.memory.resolve(arg, scope)[2] != "BOOL": raise ModelError("Bit instruction requires BOOL or an integer bit")
        if n in ("AND", "OR", "XOR", "NOT"):
            for arg in a:
                if isinstance(self.memory.read(arg, scope), (bool, float)): raise ModelError("Bitwise operands require integers")
        narrow={'LINT','USINT','UINT','UDINT','ULINT'}
        types=[]
        for arg in a:
            try:types.append(self.memory.resolve(arg,scope)[2])
            except ModelError:types.append(None)
        if any(dtype in narrow for dtype in types):
            if n=='CLR':pass
            elif n=='MOV' and types[0]==types[1]:pass
            else:raise ModelError('Wide/unsigned types support same-type MOV, CLR, COPY, and bit access; this arithmetic form is unsupported')

    def _prescan(self):
        for key in sorted(self.active):
            r = self.project.routines.get(key)
            if not r: continue
            self._prescan_routine(r,r.program,0)

    def _prescan_routine(self,routine,scope,depth):
        if routine.kind=='ST':self.structured.prescan(routine,scope,depth);return
        for rung in routine.rungs:
            for op in operations(rung['nodes']):
                self.budget-=1
                if self.budget<0:raise ModelError('Prescan instruction budget exceeded')
                n,a=op.name,op.args
                def w(member,value):self.memory.write(a[0]+member,value,scope)
                if n in self.project.aois:self.addons.call(op,False,scope,depth+1,prescan=True)
                elif n=='OTE':w('',False)
                elif n in ('ONS','OSR','OSF'):
                    w('',n!='OSF')
                    if n!='ONS':self.memory.write(a[1],False,scope)
                elif n in ('TON','TOF','RTO'):
                    w('.EN',False);w('.TT',False)
                    if n!='RTO':w('.DN',False);w('.ACC',0)
                elif n in ('CTU','CTD'):w('.CU' if n=='CTU' else '.CD',True)

    def validate_interval(self, dt):
        if self.blockers: raise ModelError("Execution blocked; inspect the coverage report")
        if not isinstance(dt, int) or not 1 <= dt <= 60000: raise ModelError("Scan interval must be 1..60000 ms")
        if self.mode == "project" and self.project.tasks[0]["type"] == "Periodic":
            rate = float(self.project.tasks[0]["rate"])
            if dt != rate: raise ModelError(f"Periodic task requires a {rate:g} ms scan interval")

    def prepare_step(self, dt=10):
        self.validate_interval(dt)
        if self._initial_prescan_pending:self.enter_run()

    def step(self, dt=10):
        self.prepare_step(dt)
        before = copy.deepcopy(self.memory.values)
        previous = (self.time_ms, copy.deepcopy(self.last_timer), self.memory.first_scan, self.trace)
        self.time_ms += dt
        self.trace = []
        self.budget = self.instruction_limit
        timings=dict(self._program_timings)
        try:
            task_wall_time=current_value_microseconds() if self._task_measurements is not None else None
            task_start=task_runtime.perf_counter_ns() if self._task_measurements is not None else None
            for entry in self.entries:
                name=self.project.routines[entry].program.casefold()
                if name in timings:
                    start=perf_counter_ns()
                    self._routine(entry, 0)
                    timings[name]=timings[name].record(perf_counter_ns()-start)
                else:self._routine(entry, 0)
            measured=(self._task_measurements.record(task_start,task_runtime.perf_counter_ns(),start_time_us=task_wall_time)
                      if self._task_measurements is not None else None)
            self.scan_count += 1
            self.memory.first_scan = False
            self.fault = ""
            self._program_timings=timings
            self._task_measurements=measured
        except (ModelError, ArithmeticError, ValueError, TypeError, KeyError, IndexError, OverflowError) as e:
            self.memory.values = before
            self.time_ms, self.last_timer, self.memory.first_scan, self.trace = previous
            self.fault = str(e) or type(e).__name__
            raise ModelError(f"Scan rolled back: {e}") from e
        changes = []
        def compare(path, old, new):
            if isinstance(new, dict):
                for k in new: compare(f"{path}.{k}", old[k], new[k])
            elif isinstance(new, list):
                for i in range(len(new)):
                    indexed=(path[:-1]+f',{i}]') if path.endswith(']') else f'{path}[{i}]'
                    compare(indexed, old[i], new[i])
            elif old != new:
                changes.append({"scan": self.scan_count, "ms": self.time_ms, "tag": path, "before": old, "after": new})
        for k, v in self.memory.values.items(): compare(self.project.tags[k].key, before[k], v)
        self.changes = (changes + self.changes)[:2000]
        return changes

    def _routine(self, key, depth):
        if depth > 32: raise ModelError("JSR nesting limit exceeded")
        routine = self.project.routines[key]
        self._execute_routine(routine,routine.program,depth)

    def _execute_routine(self,routine,scope,depth,context=''):
        if depth>32:raise ModelError('Routine/AOI nesting limit exceeded')
        if routine.kind=='ST':self.structured.execute(routine,scope,depth,context);return
        pc=0
        while pc<len(routine.rungs):
            rung=routine.rungs[pc];events=[];power=False;control=''
            try:
                power = self._sequence(rung["nodes"], True, scope, depth, events)
                pc+=1
            except JumpRoutine as jump:
                pc=self.labels[routine.key.lower()][jump.label];control='jump '+jump.label
            except ReturnRoutine:
                control='return';pc=len(routine.rungs)
            self.trace.append({"routine":routine.key,"context":context,"number":rung['number'],"power":power,"events":events,'control':control})
            if len(self.trace)>5000:self.trace=self.trace[-5000:]

    def _sequence(self, nodes, power, scope, depth, events):
        for node in nodes:
            if isinstance(node, Branch):
                # All branch paths execute, including de-energized output instructions.
                results = [self._sequence(path, power, scope, depth, events) for path in node.paths]
                power = any(results)
            else:
                self.budget -= 1
                if self.budget < 0: raise ModelError("Instruction budget exceeded")
                incoming = power
                try:power = self._op(node, power, scope, depth)
                except (JumpRoutine,ReturnRoutine):
                    events.append({'instruction':node.name,'args':node.args,'in':incoming,'out':incoming,'transfer':True})
                    raise
                events.append({"instruction": node.name, "args": node.args, "in": incoming, "out": power})
        return power

    def _op(self, op, p, scope, depth):
        n, a = op.name, op.args
        if n in self.project.aois:return self.addons.call(op,p,scope,depth+1)
        if n=='GSV':
            if p:system_values.execute(self,op,scope)
            return p
        r = lambda i: self.memory.read(a[i], scope)
        w = lambda i, value: self.memory.write(a[i], value, scope)
        extra=self.extensions.execute(op,p,scope)
        if extra is not None:return extra
        if n=='LBL':return p
        if n=='JMP':
            if p:raise JumpRoutine(a[0])
            return p
        if n == "XIC": return p and bool(r(0))
        if n == "XIO": return p and not bool(r(0))
        if n == "AFI": return False
        if n == "NOP": return p
        if n == "OTE": w(0, p)
        elif n == "OTL":
            if p: w(0, True)
        elif n == "OTU":
            if p: w(0, False)
        elif n in ("ONS", "OSR", "OSF"):
            old = bool(r(0))
            pulse = (p and not old) if n != "OSF" else (not p and old)
            w(0, p)
            if n == "ONS": return pulse
            w(1, pulse)
        elif n in ("EQU", "NEQ", "LES", "LEQ", "GRT", "GEQ"):
            return p and {"EQU": operator.eq, "NEQ": operator.ne, "LES": operator.lt,
                          "LEQ": operator.le, "GRT": operator.gt, "GEQ": operator.ge}[n](r(0), r(1))
        elif n == "LIM":
            lo, test, hi = r(0), r(1), r(2)
            return p and ((lo <= test <= hi) if lo <= hi else (test >= lo or test <= hi))
        elif n == "MOV":
            if p: w(1, r(0))
        elif n == "CLR":
            if p: w(0, 0)
        elif n in ("NEG", "ABS", "NOT"):
            if p: w(1, {"NEG": operator.neg, "ABS": abs, "NOT": operator.invert}[n](r(0)))
        elif n in ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR"):
            if p:
                x, y = r(0), r(1)
                if n in ("DIV", "MOD") and y == 0: raise ModelError(f"{n} divide by zero")
                if n == "MOD":
                    if not isinstance(x, int) or not isinstance(y, int): raise ModelError("MOD supports integers only")
                    q = abs(x) // abs(y) * (-1 if (x < 0) != (y < 0) else 1)
                    value = x - q * y
                else:
                    value = {"ADD": operator.add, "SUB": operator.sub, "MUL": operator.mul,
                             "DIV": operator.truediv, "AND": operator.and_, "OR": operator.or_, "XOR": operator.xor}[n](x, y)
                    if n in ("AND", "OR", "XOR"):
                        dtype = self.memory.resolve(a[2], scope)[2]
                        bits = {"SINT": 8, "INT": 16, "DINT": 32}.get(dtype)
                        if bits:
                            value &= (1 << bits) - 1
                            if value >= 1 << (bits - 1): value -= 1 << bits
                w(2, value)
        elif n in ("TON", "TOF", "RTO"):
            timer = r(0)
            if timer["PRE"] < 0 or timer["ACC"] < 0: raise ModelError(f"{n}: negative PRE/ACC")
            key, parts, _ = self.memory.resolve(a[0], scope)
            identity = (key, tuple(parts))
            elapsed = self.time_ms - self.last_timer.get(identity, self.time_ms)
            self.last_timer[identity] = self.time_ms
            if n == "TOF":
                if p: timer.update(EN=True, TT=False, DN=True, ACC=0)
                else:
                    if timer["EN"]: elapsed = 0
                    timer["EN"] = False
                    if timer["DN"]:
                        timer["ACC"] += elapsed
                        timer["DN"] = timer["ACC"] < timer["PRE"]
                    timer["TT"] = timer["DN"]
            elif not p:
                timer.update(EN=False, TT=False)
                if n == "TON": timer.update(ACC=0, DN=False)
            else:
                if not timer["EN"]: elapsed = 0
                timer["EN"] = True
                if not timer["DN"]:
                    timer["ACC"] += elapsed
                    timer["DN"] = timer["ACC"] >= timer["PRE"]
                timer["TT"] = not timer["DN"]
            if timer["ACC"] > 2147483647: raise ModelError("Timer accumulator overflow")
        elif n in ("CTU", "CTD"):
            counter = r(0)
            edge = "CU" if n == "CTU" else "CD"
            if p and not counter[edge]:
                value = counter["ACC"] + (1 if n == "CTU" else -1)
                if value > 2147483647: counter.update(OV=True); value = -2147483648
                if value < -2147483648: counter.update(UN=True); value = 2147483647
                counter["ACC"] = value
            counter[edge] = p
            counter["DN"] = counter["ACC"] >= counter["PRE"]
        elif n == "RES":
            if p:
                obj = r(0)
                for k in obj:
                    if k != "PRE": obj[k] = 0 if k == "ACC" else False
        elif n == "JSR":
            if p:self.calls.call(op,scope,depth)
        elif n=='SBR':
            if p:self.calls.receive(op,scope)
        elif n=='RET':
            if p:
                self.calls.returned(op,scope)
                raise ReturnRoutine()
        elif n == "TND":
            if p: raise ReturnRoutine()
        else: raise ModelError(f"Unsupported instruction {n}")
        return p

    def report(self):
        return {"application": "LogixLab "+__version__, "controller": self.project.name,
                "revision": self.project.version, "processor": self.project.processor,
                "source_l5x_sha256": self.project.sha256,
                "mode": self.mode, "selected_routine": self.selected,
                "executable": not self.blockers, "blockers": self.blockers,
                "active_routines": sorted(self.active),
                'entry_routines':self.entries,
                "instructions": dict(sorted(self.project.instruction_counts.items())),
                'structured_text':{'constructs':dict(self.project.st_counts),'supported':['assign', '[:=]', 'IF/ELSIF/ELSE','CASE (integer)','FOR','WHILE','REPEAT','EXIT','supported calls'],
                                   'policy':'Typed structural preflight; actual unknown reads/bounds/arithmetic faults stop and roll back. Integer division, wide arithmetic and FBD instructions remain blocked.'},
                "supported_instructions": sorted(ARITIES),
                'known_add_on_instructions':sorted(self.project.aois),
                'data_only_types':sorted(self.project.data_only_types),
                'add_on_instructions':self.addons.report(),
                'routine_parameters':self.calls.report(),
                'instruction_limit_per_scan':self.instruction_limit,
                "project_routine_issues": {r.key: r.problems for r in self.project.routines.values() if r.problems},
                "limits": ["Custom deterministic software model; native/controller equivalence is unverified",
                           "One Standard task; scan interval is simulated time, not controller timing",
                           "Routine harness ignores task scheduling and unrelated program prescan",
                           "JSR/SBR/RET use exact parameter counts/types/dimensions, static references and by-value copies; cross-parameter overlap is rejected",
                           "JSR calls are bounded to 25 levels and 40 parameters each direction; prescan does not transfer routine parameters; RET in a main routine is blocked",
                           "RLL/ST AOIs support required scalar Input/Output and exact-type InOut bindings; optional parameters use instance members",
                           "Hidden saved AOI locals stay unknown until written; definition defaults are never substituted for saved values",
                           "AOI alias/constant/nullable parameters, JSR inside AOIs, FBD, SFC/Postscan, motion, CIP/network, module I/O and safety execution are unsupported",
                           "ST supports a bounded typed subset and reached-statement calls; FOR bounds/step must remain unchanged by its body; dynamic counter references are blocked",
                           "ST [:=] clears during prescan; ordinary assignments retain imported values until executed; native runtime equivalence is unverified",
                           "COP/CPS require matching types and stay inside modeled array/member boundaries; no raw layout reinterpretation",
                           "FLL supports numeric arrays and DINT-zero structure fills; narrowing overflow is blocked",
                           "CPT uses a bounded expression grammar and float32 REAL operations; native arithmetic equivalence is unverified",
                           "CMP supports typed numeric/BOOL/string comparisons and eager logical evaluation; unknowns/faults cannot hide behind logical operands",
                           "MEQ supports SINT/INT/DINT with documented zero-extension; wide/unsigned forms remain blocked",
                           "GSV reads simulator Controller AuditValue/ChangesToDetect into LINT or two DINT elements; other objects/attributes and SSV are unsupported",
                           "Strings preserve LEN and backing SINT DATA; string faults roll back rather than reproduce native fault handling",
                           "Arithmetic overflow/divide faults stop and roll back; controller fault/status semantics differ",
                           "No online connection or download; source files are never saved by the engine"]}
