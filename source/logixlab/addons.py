"""RLL Add-On Instructions: copied parameters, reference bindings and scan modes.

Local values absent from the export remain unknown. Definition DefaultData is
not evidence of the saved state of an existing instance.
"""
from .model import ModelError, coerce, dimensions, literal, operations


def shape(value):
    result=[]
    while isinstance(value,list):
        result.append(len(value));value=value[0] if value else None
    return tuple(result)


class AddOns:
    def __init__(self,engine):
        self.engine=engine;self.memory=engine.memory
        self.validated=set();self.active=set();self.instances={}

    def bind(self,op,scope):
        definition=self.engine.project.aois[op.name]
        if definition.problems:raise ModelError('; '.join(definition.problems))
        if len(op.args)!=len(definition.required)+1:
            raise ModelError('Expected instance plus required parameters in definition order')
        key,parts,dtype=self.memory.check_writable(op.args[0],scope)
        if dtype!=definition.name.upper() or not isinstance(self.memory.at(key,parts),dict):
            raise ModelError('Instance must be a scalar tag/member of type '+definition.name)
        address=self.memory.address(key,parts);frame='@AOI:'+address.lower()
        bindings={}
        for item in definition.parameters+definition.locals:
            if item.get('Usage')!='InOut':bindings[item.get('Name').lower()]=(address+'.'+item.get('Name'),'')
        for parameter,argument in zip(definition.required,op.args[1:]):
            usage=parameter.get('Usage');expected=parameter.get('DataType','').upper()
            if usage=='InOut':
                k,p,t=self.memory.check_writable(argument,scope)
                if any(isinstance(x,tuple) for x in p):raise ModelError('InOut bit selections are unsupported')
                if t!=expected or shape(self.memory.at(k,p))!=dimensions(parameter.get('Dimensions','0')):
                    raise ModelError(parameter.get('Name')+': InOut type/array dimensions must match exactly')
                bindings[parameter.get('Name').lower()]=(self.memory.address(k,p),'')
            elif usage=='Output':
                k,p,t=self.memory.check_writable(argument,scope)
                if any(isinstance(x,tuple) for x in p):raise ModelError('Output bit selections are unsupported')
                if t!=expected or isinstance(self.memory.at(k,p),(dict,list)):
                    raise ModelError(parameter.get('Name')+': Output destination type must match exactly')
            else:
                try:value=literal(argument);source_type='BOOL' if isinstance(value,bool) else 'REAL' if isinstance(value,float) else 'DINT'
                except ValueError:
                    k,p,source_type=self.memory.resolve(argument,scope)
                    value=self.memory.at(k,p) if not any(isinstance(x,tuple) for x in p) else False
                if isinstance(value,(dict,list)):raise ModelError('Input requires a scalar value')
                if expected=='BOOL' and source_type!='BOOL' and argument.strip().upper() not in ('0','1'):
                    raise ModelError('BOOL Input requires BOOL or literal 0/1')
                if expected!='BOOL' and source_type=='BOOL':raise ModelError('Numeric Input does not accept BOOL')
                if source_type not in ('BOOL','SINT','INT','DINT','REAL') and source_type!=expected:
                    raise ModelError('Unsupported Input conversion')
        self.memory.frames[frame]=bindings
        # InOut arguments can differ between calls using the same instance.
        self.memory._resolved={k:v for k,v in self.memory._resolved.items() if k[1]!=frame.lower()}
        self.instances[address]={'definition':definition.name,'scope':frame}
        return definition,frame,address

    def validate(self,op,scope,stack=()):
        definition,frame,address=self.bind(op,scope)
        if definition.name.upper() in stack:raise ModelError('Recursive AOI call: '+definition.name)
        identity=(definition.name.upper(),frame,tuple(op.args[1:]),scope)
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

    def call(self,op,power,scope,depth,prescan=False):
        if depth>32:raise ModelError('AOI nesting limit exceeded')
        definition,frame,address=self.bind(op,scope)
        self.memory.write(address+'.EnableIn',bool(power) if not prescan else False)
        self.memory.write('EnableOut',bool(power) if not prescan else False,frame)
        for parameter,argument in zip(definition.required,op.args[1:]):
            if parameter.get('Usage')=='Input':
                value=self.memory.read(argument,scope)
                if isinstance(value,float):value=coerce(value,'REAL')
                self.memory.write(parameter.get('Name'),value,frame)
        if prescan:
            self.engine._prescan_routine(definition.routines['logic'],frame,depth+1)
            if definition.modes['Prescan']:
                self.engine._execute_routine(definition.routines['prescan'],frame,depth+1,address)
        elif power:
            self.engine._execute_routine(definition.routines['logic'],frame,depth+1,address)
        elif definition.modes['EnableInFalse']:
            self.engine._execute_routine(definition.routines['enableinfalse'],frame,depth+1,address)
        if prescan or power or definition.modes['EnableInFalse']:
            for parameter,argument in zip(definition.required,op.args[1:]):
                if parameter.get('Usage')=='Output':
                    self.memory.write(argument,self.memory.read(parameter.get('Name'),frame),scope)
        # An EnableInFalse routine cannot energize rung-out.
        if not power or prescan:self.memory.write('EnableOut',False,frame)
        return bool(power and self.memory.read('EnableOut',frame))

    def report(self):
        project=self.engine.project
        return {'definitions':len(project.aois),'active_definitions':sorted(self.active),
                'instances':self.instances,
                'local_state_policy':'Hidden saved local values remain unknown; Prescan or normal writes must establish them before reads',
                'definition_issues':{a.name:a.problems for a in project.aois.values() if a.problems},
                'instructions':{a.name:dict(__import__('collections').Counter(op.name for r in a.routines.values()
                                           for rung in r.rungs for op in operations(rung['nodes'])))
                                for a in project.aois.values()}}
