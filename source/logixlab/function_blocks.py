"""Bounded single-sheet acyclic FBD execution with explicit typed wires."""
import heapq
import re
from . import fbd_blocks
from .calls import overlaps
from .model import ModelError,coerce,literal

SCALARS=('BOOL','DINT','REAL')
MAX_NODES=512
MAX_WIRES=4096
ATTRS={
    'IRef':{'ID','X','Y','Operand','HideDesc'},'ORef':{'ID','X','Y','Operand','HideDesc'},
    'Block':{'ID','X','Y','Type','Operand','VisiblePins','HideDesc'},
    'Wire':{'FromID','FromParam','ToID','ToParam'}}


def uint(text,label,limit=0xffffffff):
    if not isinstance(text,str) or not re.fullmatch(r'[0-9]+',text) or len(text)>10 or int(text)>limit:
        raise ModelError('FBD '+label+' must be a bounded unsigned integer')
    return int(text)


def parse(element):
    if any(child.tag not in ('Description','FBDContent') for child in element):
        raise ModelError('Unsupported/protected FBD routine content')
    contents=element.findall('FBDContent')
    if len(contents)!=1:raise ModelError('FBD requires one unprotected FBDContent; online edit variants remain unsupported')
    content=contents[0]
    if set(content.attrib)-{'SheetSize','SheetOrientation'}:
        raise ModelError('FBD content attributes/online edits remain unsupported')
    if len(content)!=1 or content[0].tag!='Sheet':raise ModelError('FBD currently requires exactly one Sheet')
    sheet=content[0]
    if set(sheet.attrib)-{'Number'}:raise ModelError('Unsupported FBD Sheet attribute')
    number=uint(sheet.get('Number'),'sheet number');nodes={};wires=[]
    if len(sheet)>MAX_NODES+MAX_WIRES+1:raise ModelError('FBD sheet size limit exceeded')
    for child in sheet:
        kind=child.tag
        if kind=='Description':continue
        if kind not in ATTRS:raise ModelError('Unsupported FBD element '+kind)
        if set(child.attrib)-ATTRS[kind] or len(child) or (child.text or '').strip():
            raise ModelError('Unsupported FBD '+kind+' attributes/content')
        if kind=='Wire':
            wires.append(dict(source=uint(child.get('FromID'),'FromID'),source_pin=child.get('FromParam',''),
                              target=uint(child.get('ToID'),'ToID'),target_pin=child.get('ToParam','')))
            continue
        ident=uint(child.get('ID'),'element ID')
        if ident in nodes:raise ModelError('Duplicate FBD element ID')
        operand=child.get('Operand','').strip()
        if not operand:raise ModelError('FBD operand is required')
        node=dict(id=ident,kind=kind,operand=operand,x=uint(child.get('X','0'),'X',10000),y=uint(child.get('Y','0'),'Y',10000))
        if kind=='Block':
            name=child.get('Type','')
            if name not in fbd_blocks.TYPES:raise ModelError('Unsupported FBD block '+name)
            node['type']=name
            schema=fbd_blocks.PINS[fbd_blocks.TYPES[name]]
            if any(pin not in schema for pin in child.get('VisiblePins','').split()):
                raise ModelError('Unknown FBD visible pin')
        nodes[ident]=node
    if not nodes or len(nodes)>MAX_NODES or len(wires)>MAX_WIRES:raise ModelError('FBD node/wire limits exceeded or empty sheet')
    incoming={};dependencies={ident:set() for ident in nodes}
    for wire in wires:
        source,target=nodes.get(wire['source']),nodes.get(wire['target'])
        if source is None or target is None:raise ModelError('FBD wire references a missing element')
        if source['kind']=='ORef' or target['kind']=='IRef':raise ModelError('Invalid FBD wire direction')
        source_pins=('In',) if source['kind']=='IRef' else fbd_blocks.OUTPUTS[fbd_blocks.TYPES[source['type']]]
        if wire['source_pin'] not in source_pins:raise ModelError('Invalid FBD source pin')
        if target['kind']=='ORef':target_pins=('Out',)
        else:
            dtype=fbd_blocks.TYPES[target['type']]
            target_pins=set(fbd_blocks.SCHEMAS[dtype])-set(fbd_blocks.OUTPUTS[dtype])
        if wire['target_pin'] not in target_pins:raise ModelError('Invalid FBD destination pin')
        pin=(wire['target'],wire['target_pin'])
        if pin in incoming:raise ModelError('Multiple FBD wires drive one input')
        incoming[pin]=wire;dependencies[wire['target']].add(wire['source'])
    for ident,node in nodes.items():
        if node['kind']=='ORef' and (ident,'Out') not in incoming:raise ModelError('FBD ORef requires one incoming wire')
    # Stable ID tie ordering is a software policy, not a native execution-order claim.
    followers={ident:[] for ident in nodes};degree={ident:len(deps) for ident,deps in dependencies.items()}
    for ident,deps in dependencies.items():
        for source in deps:followers[source].append(ident)
    ready=[i for i,n in degree.items() if not n];heapq.heapify(ready);order=[]
    while ready:
        ident=heapq.heappop(ready);order.append(ident)
        for target in followers[ident]:
            degree[target]-=1
            if not degree[target]:heapq.heappush(ready,target)
    if len(order)!=len(nodes):raise ModelError('Cyclic FBD wires/feedback remain unsupported')
    return dict(number=number,nodes=list(nodes.values()),wires=wires,order=order)


class FunctionBlocks:
    def __init__(self,engine):self.engine=engine;self.memory=engine.memory

    def validate(self,routine,scope):
        if scope.startswith('AOI:') or scope in self.memory.frames:raise ModelError('FBD within AOIs remains unsupported')
        from .integer_math import CONTROLLERS
        if self.engine.project.version!='35' or self.engine.project.processor.upper() not in CONTROLLERS:
            raise ModelError('FBD requires the v35 ControlLogix 5580 software profile')
        graph=routine.diagram
        if not graph:raise ModelError('Missing FBD graph')
        types={};readers=[];writers=[];records=[]
        for node in graph['nodes']:
            kind=node['kind'];ref=node['operand']
            if kind=='Block':
                fbd_blocks.validate(self.engine,node['type'],ref,scope)
                value=self.engine.calls.operand(ref,scope,writable=True)
                if any(overlaps(value,other) for other in records):raise ModelError('Overlapping FBD backing records remain unsupported')
                records.append(value)
                dtype=fbd_blocks.TYPES[node['type']]
                types[node['id']]=fbd_blocks.PINS[dtype]
            else:
                value=self.engine.calls.operand(ref,scope,writable=kind=='ORef')
                if value.dtype not in SCALARS or value.dims:raise ModelError('FBD references require scalar BOOL, DINT or REAL with static indices')
                types[node['id']]={('In' if kind=='IRef' else 'Out'):value.dtype}
                (readers if kind=='IRef' else writers).append(value)
        for i,value in enumerate(writers):
            if any(overlaps(value,other) for other in readers+records+writers[:i]):
                raise ModelError('FBD ORef overlap/implicit tag feedback remains unsupported')
        for value in readers:
            if any(overlaps(value,other) for other in records):raise ModelError('Use FBD wires for block dependencies; implicit backing-tag reads remain unsupported')
        for wire in graph['wires']:
            if types[wire['source']][wire['source_pin']]!=types[wire['target']][wire['target_pin']]:
                raise ModelError('FBD wires require matching scalar types; implicit conversions remain unsupported')

    def raw(self,ref,scope):
        key,parts,_=self.memory.resolve(ref,scope);value=self.memory.values[key]
        for part in parts:
            if value is None:return None
            value=bool((value>>part[1])&1) if isinstance(part,tuple) else value[part]
        return value

    def prescan(self,routine,scope):
        for node in routine.diagram['nodes']:
            self.charge()
            if node['kind']=='Block':fbd_blocks.prescan(self.engine,node,scope)

    def charge(self):
        self.engine.budget-=1
        if self.engine.budget<0:raise ModelError('FBD instruction/wire budget exceeded')

    def execute(self,routine,scope,context=''):
        graph=routine.diagram;nodes={n['id']:n for n in graph['nodes']};values={};pending=[]
        inputs={ident:[] for ident in nodes}
        for wire in graph['wires']:inputs[wire['target']].append(wire)
        # Sample every IRef once before block writes; unknowns travel on wires.
        for node in graph['nodes']:
            if node['kind']!='IRef':continue
            self.charge();ref=node['operand']
            try:value=literal(ref)
            except ValueError:
                value=self.raw(ref,scope)
            values[(node['id'],'In')]=value
        for ident in graph['order']:
            node=nodes[ident];kind=node['kind']
            if kind=='IRef':continue
            self.charge()
            if kind=='Block':
                for wire in inputs[ident]:
                    self.charge();value=values[(wire['source'],wire['source_pin'])]
                    ref=node['operand']+'.'+wire['target_pin'];key,parts,dtype=self.memory.check_writable(ref,scope)
                    self.memory.store(key,parts,None if value is None else coerce(value,dtype))
                fbd_blocks.execute(self.engine,node,scope,wired_enable=any(w['target_pin']=='EnableIn' for w in inputs[ident]))
                for pin in fbd_blocks.OUTPUTS[fbd_blocks.TYPES[node['type']]]:
                    values[(ident,pin)]=self.raw(node['operand']+'.'+pin,scope)
                enabled=bool(values[(ident,'EnableOut')])
                self.engine.trace.append(dict(routine=routine.key,context=context,number=str(ident),language='FBD',
                    power=enabled,events=[],detail=node['type'],task=self.engine._executing_task,release_ms=self.engine.time_ms))
            else:
                wire=inputs[ident][0];self.charge();value=values[(wire['source'],wire['source_pin'])]
                if value is None:raise ModelError('FBD output value is unknown: '+node['operand'])
                pending.append((node['operand'],value))
        for ref,value in pending:self.memory.write(ref,value,scope)
        if len(self.engine.trace)>5000:self.engine.trace=self.engine.trace[-5000:]


def description():
    return dict(profile='v35-5580-single-sheet-signals',instructions=sorted(fbd_blocks.TYPES),
                graph='One FBDContent/Sheet; IRef, ORef, SEL/MUX/SCL/HLL/SNEG/SSUM Block and typed acyclic Wire',
                ordering='IRefs sampled once; dependency order with numeric-ID ties; ORefs written after all blocks',
                references='Static scalar BOOL/DINT/REAL; exact wire types; distinct backing records; no ORef/input/record overlap',
                limits=dict(nodes=MAX_NODES,wires=MAX_WIRES),blocks=fbd_blocks.description(),selectors=fbd_blocks.selector_description(),
                native_runtime_parity=False,
                remaining=['Multiple sheets, named connectors, feedback, explicit execution orders and implicit tag dependencies',
                           'Other blocks/functions, FBD JSR/SBR/RET/AOIs, native transfer/edit integration and complete lifecycle/status/fault parity'])
