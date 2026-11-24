"""RLL Add-On Instructions: copied parameters, reference bindings and scan modes.

Local values absent from the export remain unknown. Definition DefaultData is
not evidence of the saved state of an existing instance.
"""
from contextlib import contextmanager, nullcontext

from . import time_values
from .calls import CallOperandBoundsError
from .model import ArrayBoundsError, ModelError, coerce, dimensions, literal, operations
from .numeric_storage import available as numeric_available, typed_literal


NUMERIC_OUTPUT_TYPES = frozenset(('SINT', 'INT', 'DINT', 'REAL'))


def input_immediate(project, argument):
    """Decode declared numeric or temporal constants in the qualified v35 profile."""
    if not numeric_available(project):
        return None
    try:
        temporal = time_values.literal(argument)
    except ValueError as error:
        raise ModelError(str(error)) from error
    return temporal or typed_literal(argument)


def shape(value):
    result=[]
    while isinstance(value,list):
        result.append(len(value));value=value[0] if value else None
    return tuple(result)


class AddOns:
    def __init__(self,engine):
        self.engine=engine;self.memory=engine.memory
        self.validated=set();self.active=set();self.instances={}
        self.caller_program = None
        self.prescanning = False
        self.prescan_recovery = False

    @contextmanager
    def program_context(self, scope, *, prescan=False, recover_prescan=False):
        """Keep the outer Program and prescan state across nested AOI calls."""
        previous = self.caller_program, self.prescanning, self.prescan_recovery
        if scope not in self.memory.frames:
            self.caller_program = scope
        self.prescanning = self.prescanning or prescan
        self.prescan_recovery = self.prescan_recovery or recover_prescan
        try:
            yield
        finally:
            self.caller_program, self.prescanning, self.prescan_recovery = previous

    def _prepare_binding(self,op,scope,*,resolve_outputs_and_inouts=True):
        definition=self.engine.project.aois[op.name]
        if definition.problems:raise ModelError('; '.join(definition.problems))
        if len(op.args)!=len(definition.required)+1:
            raise ModelError('Expected instance plus required parameters in definition order')
        key,parts,dtype=self.memory.check_writable(op.args[0],scope)
        if dtype!=definition.name.upper() or not isinstance(self.memory.at(key, parts, mutable=False), dict):
            raise ModelError('Instance must be a scalar tag/member of type '+definition.name)
        address=self.memory.address(key,parts);frame='@AOI:'+address.lower()
        bindings={}
        for item in definition.parameters+definition.locals:
            if item.get('Usage')!='InOut':bindings[item.get('Name').lower()]=(address+'.'+item.get('Name'),'')
        for parameter,argument in zip(definition.required,op.args[1:]):
            usage=parameter.get('Usage');expected=parameter.get('DataType','').upper()
            if not resolve_outputs_and_inouts and usage in ('Output', 'InOut'):
                continue
            if usage=='InOut':
                parameter_name = parameter.get('Name').lower()
                resolve = self.memory.resolve if parameter_name in definition.constant_inouts else self.memory.check_writable
                k,p,t=resolve(argument,scope)
                if k is None:raise ModelError('InOut requires a tag reference')
                if any(isinstance(x,tuple) for x in p):raise ModelError('InOut bit selections are unsupported')
                if t != expected:
                    raise ModelError(f"{parameter.get('Name')}: InOut requires type {expected}, received {t}")
                declared = dimensions(parameter.get('Dimensions', '0'))
                actual = shape(self.memory.at(k, p, mutable=False))
                larger_vector = (len(declared) == len(actual) == 1 and actual[0] > declared[0]
                                 and numeric_available(self.engine.project))
                if actual != declared and not larger_vector:
                    raise ModelError(f"{parameter.get('Name')}: InOut dimensions {actual} do not meet {declared}")
                bindings[parameter_name]=(self.memory.address(k,p),'')
            elif usage=='Output':
                key, parts, dtype = self.memory.check_writable(argument, scope)
                if dtype != expected and not (
                    numeric_available(self.engine.project)
                    and expected in NUMERIC_OUTPUT_TYPES
                    and dtype in NUMERIC_OUTPUT_TYPES
                ):
                    raise ModelError(parameter.get('Name')+': Output destination type must match exactly')
                if parts and isinstance(parts[-1], tuple):
                    _, _, width, signed = parts[-1]
                    if not (numeric_available(self.engine.project) and signed and width in (8, 16, 32)):
                        raise ModelError('Output bit selections require v35 5580 SINT, INT, or DINT storage')
                elif isinstance(self.memory.at(key, parts, mutable=False), (dict, list)):
                    raise ModelError(parameter.get('Name')+': Output destination type must match exactly')
            else:
                immediate=input_immediate(self.engine.project,argument)
                if immediate is not None:
                    source_type,value=immediate
                    if source_type!='DINT' and source_type!=expected:
                        raise ModelError('Typed AOI Input constant must match its declared parameter type')
                else:
                    try:value=literal(argument);source_type='BOOL' if isinstance(value,bool) else 'REAL' if isinstance(value,float) else 'DINT'
                    except ValueError:
                        k,p,source_type=self.memory.resolve(argument,scope)
                        value = self.memory.at(k, p, mutable=False) if not any(isinstance(x, tuple) for x in p) else False
                if isinstance(value,(dict,list)):raise ModelError('Input requires a scalar value')
                if expected in time_values.TYPES and source_type != expected:
                    raise ModelError(parameter.get('Name')+': Time/date Input source type must match exactly')
                if expected=='BOOL' and source_type!='BOOL' and argument.strip().upper() not in ('0','1'):
                    raise ModelError('BOOL Input requires BOOL or literal 0/1')
                if expected!='BOOL' and source_type=='BOOL':raise ModelError('Numeric Input does not accept BOOL')
                if source_type not in ('BOOL','SINT','INT','DINT','REAL') and source_type!=expected:
                    raise ModelError('Unsupported Input conversion')
        return definition,frame,address,bindings

    def _set_frame(self, frame, bindings):
        if bindings is None:
            self.memory.frames.pop(frame, None)
        else:
            self.memory.frames[frame] = bindings

    def validate(self,op,scope,stack=()):
        definition,frame,address,bindings=self._prepare_binding(op,scope)
        self._set_frame(frame, bindings)
        self.instances[address]={'definition':definition.name,'scope':frame}
        if definition.name.upper() in stack:raise ModelError('Recursive AOI call: '+definition.name)
        with self.program_context(scope):
            identity=(definition.name.upper(),frame,tuple(op.args[1:]),scope,self.caller_program)
            if identity in self.validated:return
            self.validated.add(identity);self.active.add(definition.name)
            previous=self.memory.validating;self.memory.validating=True
            try:
                names=['logic']+[name.lower() for name in ('Prescan','EnableInFalse') if definition.modes[name]]
                # Postscan is an SFC behavior. SFC execution remains blocked.
                for name in names:
                    routine=definition.routines[name]
                    if routine.problems:raise ModelError(routine.key+': '+'; '.join(routine.problems))
                    if routine.kind=='ST':self.engine.structured.validate(routine,frame)
                    self.engine._build_labels(routine)
                    for rung in routine.rungs:
                        for nested in operations(rung['nodes']):
                            old_structural=self.memory.structural
                            if routine.kind=='ST':self.memory.structural=True
                            try:
                                if nested.name in ('JSR','SBR','RET','FOR','BRK'):raise ModelError('JSR/SBR/RET/FOR/BRK within an AOI is unsupported')
                                if nested.name in self.engine.project.aois:
                                    self.validate(nested,frame,stack+(definition.name.upper(),))
                                else:
                                    if not(routine.kind=='ST' and nested.name=='MID'):self.engine._validate(nested,frame)
                                    if nested.name=='JMP' and nested.args[0].lower() not in self.engine.labels[routine.key.lower()]:
                                        raise ModelError('Missing label '+nested.args[0])
                            except ModelError as e:raise ModelError(f'{routine.key}, rung {rung["number"]}: {nested.name}: {e}') from e
                            finally:self.memory.structural=old_structural
            finally:self.memory.validating=previous

    def call(self,op,power,scope,depth,prescan=False,*,recover_prescan=False):
        if depth>32:raise ModelError('AOI nesting limit exceeded')
        definition = self.engine.project.aois[op.name]
        copy_outputs = prescan or power or definition.modes['EnableInFalse']
        qualified = numeric_available(self.engine.project)
        if prescan:
            recover_operands = qualified and recover_prescan
        else:
            recover_operands = qualified and (not self.prescanning or self.prescan_recovery)
        # In v35, a false ladder call without EnableInFalse only copies Inputs.
        resolve_outputs_and_inouts = copy_outputs or not qualified
        try:
            definition, frame, address, bindings = self._prepare_binding(
                op, scope, resolve_outputs_and_inouts=resolve_outputs_and_inouts
            )
        except ArrayBoundsError as error:
            if recover_operands:
                raise CallOperandBoundsError(op, f'AOI call binding: {error}') from error
            raise
        previous = self.memory.frames.get(frame)
        self._set_frame(frame, bindings)
        enabled = bool(power and not prescan)
        try:
            with self._transfer(op, 'input', recover_operands):
                self.memory.write(address+'.EnableIn', enabled)
                self.memory.write('EnableOut', enabled, frame)
                self._copy_inputs(definition, op, scope, frame)
        except CallOperandBoundsError:
            self._set_frame(frame, previous)
            raise
        self.instances[address]={'definition':definition.name,'scope':frame}
        if copy_outputs:
            try:
                with self.program_context(scope, prescan=prescan, recover_prescan=prescan and recover_operands):
                    if prescan:
                        self.engine._prescan_routine(definition.routines['logic'],frame,depth+1)
                        if definition.modes['Prescan']:
                            self.engine._execute_routine(definition.routines['prescan'],frame,depth+1,address)
                    else:
                        mode = 'logic' if power else 'enableinfalse'
                        self.engine._execute_routine(definition.routines[mode],frame,depth+1,address)
                with self._transfer(op, 'output', recover_operands):
                    self._copy_outputs(definition, op, scope, frame)
            finally:
                if not enabled:
                    self.memory.write('EnableOut', False, frame)
        return bool(power and self.memory.read('EnableOut',frame))

    @contextmanager
    def _transfer(self, op, stage, recover_operands):
        stores = self.memory.atomic_stores() if recover_operands else nullcontext()
        try:
            with stores:
                yield
        except ArrayBoundsError as error:
            if recover_operands:
                raise CallOperandBoundsError(op, f'AOI {stage} transfer: {error}') from error
            raise

    def _copy_inputs(self, definition, op, scope, frame):
        for parameter, argument in zip(definition.required, op.args[1:]):
            if parameter.get('Usage') != 'Input':
                continue
            immediate = input_immediate(self.engine.project, argument)
            if immediate is not None:
                value = immediate[1]
            else:
                temporal = parameter.get('DataType', '').upper() in time_values.TYPES
                value = self.memory.read(argument, scope, allow_time=temporal, mutable=False)
                if isinstance(value, float):
                    try:
                        literal(argument)
                    except ValueError:
                        source_type = self.memory.resolve(argument, scope)[2]
                    else:
                        source_type = 'REAL'
                    value = coerce(value, source_type)
            self.memory.write(parameter.get('Name'), value, frame)

    def _copy_outputs(self, definition, op, scope, frame):
        for parameter, argument in zip(definition.required, op.args[1:]):
            if parameter.get('Usage') == 'Output':
                temporal = parameter.get('DataType', '').upper() in time_values.TYPES
                value = self.memory.read(parameter.get('Name'), frame, allow_time=temporal, mutable=False)
                self.memory.write(argument, value, scope)

    def report(self):
        project=self.engine.project
        return {'definitions':len(project.aois),'active_definitions':sorted(self.active),
                'instances':self.instances,
                'typed_inputs':dict(available=numeric_available(project),types=['LINT','UDINT','ULINT','LREAL'],
                    radix_bases=[2,8,16],syntax='Decimal and attached radix L/l, U/u and UL/ul/Ul/uL integers; finite floating L/l values',
                    contract='Required scalar Input parameters only; exact declared type and literal range; ordinary copied-input lifecycle',
                    excluded='Aggregate literals, numeric promotion, Output/InOut constants and other controller profiles',native_runtime_parity=False),
                'temporal_parameters':dict(available=time_values.available(project),types=sorted(time_values.TYPES),
                    contract='Scalar Inputs accept exact-type tags or typed literals; scalar Outputs copy exact ticks to matching writable tags',
                    native_runtime_parity=False),
                'dint_radix_inputs':dict(available=numeric_available(project),radix_bases=[2,8,16],
                    contract='Grouped unsuffixed signed DINT words, with existing DINT input conversions',
                    lifecycle='Required scalar Inputs are copied in prescan and on reached calls, including false ladder calls',
                    native_runtime_parity=False),
                'numeric_outputs':dict(available=numeric_available(project),types=sorted(NUMERIC_OUTPUT_TYPES),
                    contract='Scalar copied Outputs between classic numeric types; binary32 REAL and checked nearest-even integer results',
                    native_math_status=False,native_runtime_parity=False),
                'local_state_policy':'Hidden saved local values remain unknown; Prescan or normal writes must establish them before reads',
                'inout_arrays':dict(larger_one_dimension=numeric_available(project),
                    contract='Exact element type; one-dimensional actual length may exceed formal length',
                    bounds='References and SIZE use the actual array; other ranks require exact dimensions',
                    native_runtime_parity=False),
                'constant_inouts':{a.name:sorted(a.constant_inouts) for a in project.aois.values() if a.constant_inouts},
                'local_aliases':{a.name:{name:target.reference for name,target in a.local_aliases.items()}
                                 for a in project.aois.values() if a.local_aliases},
                'definition_issues':{a.name:a.problems for a in project.aois.values() if a.problems},
                'instructions':{a.name:dict(__import__('collections').Counter(op.name for r in a.routines.values()
                                           for rung in r.rungs for op in operations(rung['nodes'])))
                                for a in project.aois.values()}}
