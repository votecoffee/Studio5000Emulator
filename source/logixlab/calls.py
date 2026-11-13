"""Typed JSR/SBR/RET transfers and ladder FOR/BRK, sharing a 25-call limit."""
import copy
import re
from dataclasses import dataclass
from .model import ArrayBoundsError, ModelError, Op, coerce, literal, operand_problem, operations
from .integer_math import CONTROLLERS
from .time_values import TYPES as TIME_TYPES
from .numeric_storage import typed_literal


MAX_NESTING = 25


class BreakLoop(Exception):
    """Unwind calls to the nearest active ladder FOR in the current task."""


class CallOperandBoundsError(ArrayBoundsError):
    """A live operand of this JSR or FOR faulted outside the called routine."""

    def __init__(self, call, message):
        super().__init__(message)
        self.call = call


@dataclass
class Operand:
    ref:str
    scope:str
    key:object
    parts:list
    dtype:str
    dims:tuple
    deferred_overlap:bool=False
    immediate:object=None


def shape(value):
    result=[]
    while isinstance(value,list):
        result.append(len(value));value=value[0] if value else None
    return tuple(result)


def overlaps(a,b):
    if a.key is None or a.key!=b.key:return False
    # A whole tag overlaps any selection within it, even at preflight.
    if not a.parts or not b.parts:return True
    if a.deferred_overlap or b.deferred_overlap:return False
    return a.parts[:len(b.parts)]==b.parts or b.parts[:len(a.parts)]==a.parts


def operand_sample(operand, value):
    sample = {'address': operand.ref if operand.key is not None else None, 'type': operand.dtype}
    if isinstance(value, (dict, list)):
        sample['aggregate'] = True
    elif value is not None and (operand.dtype in TIME_TYPES or operand.dtype in ('LINT', 'ULINT')):
        sample['value'] = str(value)
    else:
        sample['value'] = value
    return sample


def transfer_samples(operands, values):
    return [operand_sample(operand, value) for operand, value in zip(operands, values, strict=True)]


class Calls:
    def __init__(self,engine):
        self.engine=engine;self.memory=engine.memory;self.stack=[];self.signatures={};self.edges={};self.loop_targets=set()

    def indirect_profile(self,scope):
        return (self.engine.project.version=='35' and self.engine.project.processor.upper() in CONTROLLERS
                and scope not in self.memory.frames)

    def operand(self,ref,scope,writable=False,*,indirect=False):
        typed=typed_literal(ref) if self.indirect_profile(scope) and '#' not in ref else None
        if typed is not None:
            if writable:raise ModelError('Parameter destination must be a writable tag')
            dtype,value=typed
            return Operand(ref,scope,None,[],dtype,(),immediate=value)
        try:
            value=literal(ref)
            if writable:raise ModelError('Parameter destination must be a writable tag')
            dtype='BOOL' if isinstance(value,bool) else 'REAL' if isinstance(value,float) else 'DINT'
            value=coerce(value,dtype)
            return Operand(ref,scope,None,[],dtype,(),immediate=value)
        except ValueError:pass
        dynamic=any(not re.fullmatch(r'\s*\d+\s*(?:,\s*\d+\s*)*',indices)
                    for indices in re.findall(r'\[([^\]]*)\]',ref))
        if dynamic and not indirect:raise ModelError('Routine parameters require static array indices')
        key,parts,dtype=self.memory.check_writable(ref,scope) if writable else self.memory.resolve(ref,scope)
        if key is None or any(isinstance(p,tuple) for p in parts):raise ModelError('Routine parameter system/bit selections are unsupported')
        value=self.memory.at(key,parts)
        if dynamic and shape(value):raise ModelError('Indirect routine arguments must select one complete element')
        return Operand(self.memory.address(key,parts),'',key,parts,dtype,shape(value),
                       self.memory.structural and dynamic)

    def check_pairs(self,sources,destinations):
        if len(sources)!=len(destinations):raise ModelError('Routine parameter counts must match exactly')
        for source,dest in zip(sources,destinations):
            if source.dtype!=dest.dtype or source.dims!=dest.dims:
                raise ModelError('Routine parameter data types and array dimensions must match exactly')
        for i,dest in enumerate(destinations):
            for j,source in enumerate(sources):
                if i!=j and overlaps(source,dest):raise ModelError('Cross-parameter source/destination overlap is unsupported')
            for other in destinations[:i]:
                if overlaps(dest,other):raise ModelError('Overlapping parameter destinations are unsupported')

    def signature(self,routine):
        if routine.key.lower() in self.signatures:return self.signatures[routine.key.lower()]
        ops=[op for rung in routine.rungs for op in operations(rung['nodes'])]
        headers=[op for op in ops if op.name=='SBR'];returns=[op for op in ops if op.name=='RET']
        if len(headers)>1:raise ModelError(routine.key+': only one SBR is permitted')
        first=routine.statements[0].op if routine.kind=='ST' and routine.statements and routine.statements[0].kind=='call' else None
        if headers and ((routine.kind=='ST' and first is not headers[0]) or (routine.kind!='ST' and (not routine.rungs or not routine.rungs[0]['nodes'] or routine.rungs[0]['nodes'][0] is not headers[0]))):
            raise ModelError(routine.key+': SBR must be the first unbranched instruction')
        main=self.engine.project.programs[routine.program]['main']
        if routine.name.lower()==main.lower() and returns:raise ModelError(routine.key+': RET in a main routine is invalid')
        result=(headers[0] if headers else None,returns)
        self.signatures[routine.key.lower()]=result;return result

    def validate_routine(self,routine,entry=False):
        header,returns=self.signature(routine)
        if entry and (header and header.args or any(op.args for op in returns)):
            raise ModelError('Parameterized routine requires a JSR caller; select its caller for the harness')

    def validate_operands(self,op,scope,*,kind):
        problem=operand_problem(op)
        if problem:raise ModelError(problem)
        indirect=self.indirect_profile(scope)
        if op.name!='JSR':
            self._callee_operands(op,scope,indirect=indirect and kind=='RLL',structural=True)
            return
        previous=self.memory.structural
        if indirect:self.memory.structural=True
        try:
            count=int(op.args[1])
            for ref in op.args[2:2+count]:self.operand(ref,scope,indirect=indirect)
            for ref in op.args[2+count:]:self.operand(ref,scope,writable=True,indirect=indirect)
        finally:self.memory.structural=previous

    def _callee_operands(self,op,scope,*,indirect,structural=False):
        previous=self.memory.structural
        if structural and indirect:self.memory.structural=True
        try:
            return [self.operand(ref,scope,writable=op.name=='SBR',indirect=indirect)
                    for ref in op.args]
        finally:self.memory.structural=previous

    def call_spec(self,op,scope,*,execute=False):
        previous=self.memory.structural
        if not execute and self.indirect_profile(scope):self.memory.structural=True
        try:return self._call_spec(op,scope)
        finally:self.memory.structural=previous

    def _caller_operand(self, op, ref, scope, *, writable=False):
        try:
            return self.operand(ref, scope, writable=writable, indirect=self.indirect_profile(scope))
        except ArrayBoundsError as error:
            raise CallOperandBoundsError(op, str(error)) from error

    def _call_spec(self,op,scope):
        problem=operand_problem(op)
        if problem:raise ModelError(problem)
        key=(scope+'/'+op.args[0]).lower();routine=self.engine.project.routines.get(key)
        if routine is None:raise ModelError('Routine '+key+' is missing')
        if key == self.engine.project.program_fault_routines.get(scope):
            raise ModelError('Normal calls to a Program fault routine are outside the emulator profile')
        if routine.name.lower()==self.engine.project.programs[scope]['main'].lower():raise ModelError('JSR cannot call a main routine')
        header,returns=self.signature(routine);count=int(op.args[1])
        sources=[self._caller_operand(op,x,scope) for x in op.args[2:2+count]]
        indirect=self.indirect_profile(scope) and routine.kind=='RLL'
        inputs=self._callee_operands(header,scope,indirect=indirect,structural=True) if header else []
        self.check_pairs(sources,inputs)
        destinations=[self._caller_operand(op,x,scope,writable=True) for x in op.args[2+count:]]
        if destinations and not returns:raise ModelError('JSR return destinations require RET operands')
        for ret in returns:
            self.check_pairs(self._callee_operands(ret,scope,indirect=indirect,structural=True),destinations)
        self.edges[key]={'inputs':count,'returns':len(destinations)}
        return key,sources,destinations

    def loop_spec(self,op,scope):
        previous=self.memory.structural;self.memory.structural=True
        try:return self._loop_spec(op,scope)
        finally:self.memory.structural=previous

    def _loop_spec(self,op,scope):
        if self.engine.project.version!='35' or self.engine.project.processor.upper() not in CONTROLLERS:
            raise ModelError('FOR/BRK requires the v35 ControlLogix 5580 software profile')
        if scope in self.memory.frames:raise ModelError('FOR/BRK within an AOI is unsupported')
        problem=operand_problem(op)
        if problem:raise ModelError(problem)
        if op.name=='BRK':return
        if not re.fullmatch(r'[A-Za-z_][\w]*',op.args[0]):raise ModelError('Invalid FOR routine name')
        # FOR passes no SBR/RET parameters. The same target/call graph rules apply.
        key,_,_=self.call_spec(Op('JSR',[op.args[0],'0']),scope)
        index=self.operand(op.args[1],scope,writable=True,indirect=True)
        if index.dtype!='DINT' or index.dims:raise ModelError('FOR index requires a writable scalar DINT')
        sources=[self.operand(ref,scope,indirect=True) for ref in op.args[2:]]
        if any(p.dtype not in ('SINT','INT','DINT') or p.dims for p in sources):
            raise ModelError('FOR initial/terminal/step requires scalar SINT, INT, DINT or DINT literals')
        self.loop_targets.add(key)
        return key,index,sources

    def loop(self,op,scope,depth,event=None):
        if len(self.stack)>=MAX_NESTING:raise ModelError(f'JSR/FOR nesting limit of {MAX_NESTING} exceeded')
        key,_,_=self.loop_spec(op,scope)
        index = None
        samples = [None] * len(op.args)
        visits = 0
        reason = 'terminal'

        def value(argument):
            operand = self._caller_operand(op,op.args[argument],scope)
            result = self.values([operand])[0]
            samples[argument] = (operand,result)
            return result

        frame={'key':key,'sources':[],'values':[],'destinations':[],'received':False,'returned':False,'loop':True}
        self.stack.append(frame)
        try:
            # Retain the selected index cell for this invocation. Bounds are live.
            index=self._caller_operand(op,op.args[1],scope,writable=True)
            saved_index=self.memory.at(index.key,index.parts)
            self.memory.write(index.ref,value(2),index.scope)
            while True:
                # Even an empty routine and a zero step consume a bounded budget.
                self.engine.budget-=1
                if self.engine.budget<0:raise ModelError('FOR instruction budget exceeded')
                try:
                    limit,step=value(3),value(4)
                except CallOperandBoundsError:
                    if not visits:
                        self.memory.store(index.key,index.parts,saved_index)
                    raise
                current=self.memory.read(index.ref,index.scope)
                if (step<0 and current<limit) or (step>=0 and current>limit):break
                visits += 1
                frame['received']=frame['returned']=False
                try:self.engine._routine(key,depth+1)
                except BreakLoop:
                    reason = 'brk'
                    break
                # Reread after the routine: it may modify index or step.
                self.memory.write(index.ref,self.memory.read(index.ref,index.scope)+value(4),index.scope)
        except CallOperandBoundsError as error:
            if error.call is op:
                reason = 'bounds'
            raise
        finally:
            self.stack.pop()
            if event is not None:
                # Snapshot before any surrounding handler or later instruction writes.
                if index is not None:
                    samples[1] = (index,self.memory.at(index.key,index.parts))
                event['operand_samples'] = [operand_sample(*item) if item is not None else None for item in samples]
                event['loop_trace'] = {'visits':visits,'exit':reason}

    def break_loop(self):
        if any(frame.get('loop') for frame in self.stack):raise BreakLoop()

    def loop_description(self):
        return dict(profile='v35-5580-ladder-FOR-BRK',language='RLL',targets=sorted(self.loop_targets),
                    index='Writable scalar DINT tag/member/element or alias; selected index address retained for one invocation',
                    bounds='Scalar SINT/INT/DINT or signed DINT literals; inclusive, either direction',
                    selection='Structural preflight; false/prescan skip live operand indices and values; complete scalar selections only',
                    sampling='Index address retained at entry; initial selected before assignment; terminal/step reselected per test; step reselected after each normal call',
                    control='BRK unwinds to the nearest active FOR in the current task; outside FOR it has no action',
                    lifecycle='Reachable routines prescanned once; no parameters; shared 25-level call limit and instruction budget',
                    array_recovery='A cleared Type 4 Code 20 on an owned FOR operand exits the loop; an entry fault preserves the saved index and a later fault retains completed work',
                    overflow='Modeled DINT overflow and budget exhaustion roll back the entire advance',
                    native_runtime_parity=False,
                    remaining=['Native live-operand sampling, overflow/status/watchdog parity','Recursive calls and other controller profiles',
                               'AOI FOR/BRK, BRK inside MCR zones and SFC targets','Native postscan and hardware scheduling'])

    def values(self,operands):
        return [coerce(p.immediate,p.dtype) if p.key is None else copy.deepcopy(self.memory.read(p.ref,p.scope)) for p in operands]

    def store(self,destinations,values):
        for dest,value in zip(destinations,values):
            # Scalar coercion is unnecessary: the declared types already match.
            self.memory.check_writable(dest.ref,dest.scope)
            self.memory.store(dest.key,dest.parts,value)

    def call(self,op,scope,depth,event=None):
        if len(self.stack)>=MAX_NESTING:raise ModelError(f'JSR nesting limit of {MAX_NESTING} exceeded')
        key,sources,destinations=self.call_spec(op,scope,execute=True)
        frame={'key':key,'sources':sources,'values':self.values(sources),'destinations':destinations,'received':False,'returned':False}
        if event is not None:
            frame['operand_samples'] = [None, None, *transfer_samples(sources, frame['values'])]
        self.stack.append(frame)
        try:
            self.engine._routine(key,depth+1)
            if destinations and not frame['returned']:raise ModelError('Subroutine ended without passing required RET values')
            if event is not None and len(frame['operand_samples']) > 2:
                event['operand_samples'] = frame['operand_samples']
        finally:self.stack.pop()

    def receive(self,op,scope,event=None):
        if not self.stack:
            if op.args:raise ModelError('SBR has no JSR caller')
            return
        frame=self.stack[-1]
        if frame['received']:raise ModelError('SBR executed more than once in one call')
        indirect=self.indirect_profile(scope) and self.engine._executing_routine.kind=='RLL'
        destinations=self._callee_operands(op,scope,indirect=indirect)
        self.check_pairs(frame['sources'],destinations)
        self.store(destinations,frame['values']);frame['received']=True
        if event is not None and destinations:
            event['operand_samples'] = transfer_samples(destinations, frame['values'])

    def returned(self,op,scope,event=None):
        if not self.stack:
            if op.args:raise ModelError('RET has no JSR caller')
            return
        frame=self.stack[-1]
        indirect=self.indirect_profile(scope) and self.engine._executing_routine.kind=='RLL'
        sources=self._callee_operands(op,scope,indirect=indirect)
        self.check_pairs(sources,frame['destinations'])
        values = self.values(sources)
        self.store(frame['destinations'],values);frame['returned']=True
        if event is not None and sources:
            event['operand_samples'] = transfer_samples(sources, values)
        if 'operand_samples' in frame:
            frame['operand_samples'].extend(transfer_samples(frame['destinations'], values))

    def report(self):
        return {'calls':self.edges,'nesting_limit':MAX_NESTING,'parameters_per_direction':40,
                'contract':'Exact counts/types/dimensions; copied values; bounded indirect JSR and ladder SBR/RET elements; cross-parameter overlap rejected; prescan does not transfer parameters',
                'typed_constants':dict(available=self.indirect_profile(''),types=['LINT','UDINT','ULINT','LREAL'],
                    syntax='Decimal L/l, U/u and UL/ul/Ul/uL integers; floating L/l constants',
                    transfers='JSR inputs and RET values keep their declared type; exact matching formal/return types; literal range checked before execution',
                    trace='LINT/ULINT values recorded as decimal text; LREAL retained as binary64',
                    excluded='Typed radix/time/date/aggregate constants, numeric promotion, other controller profiles and AOI calls',native_runtime_parity=False),
                'indirect':dict(available=self.indirect_profile(''),profile='v35-5580-caller-elements',
                                selection='Structural JSR preflight; false/prescan skip live caller indices and values',
                                capture='Input and return-destination addresses captured at call entry before input copies; current values copied before SBR writes',
                                callee='Ladder SBR destinations and RET sources select live elements only on the reached transfer, with all addresses and values captured before the first write',
                                boundaries='One selected element per explicit indirect operand; ST SBR/RET retain static rules; FOR uses its separate profile; preflight defers element overlap for explicit indirect operands until the live call or transfer',
                                native_runtime_parity=False)}
