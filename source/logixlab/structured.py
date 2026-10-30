"""Bounded Structured Text parser and execution; never Python eval/exec."""
import copy
import re
from dataclasses import dataclass,field
from .model import ModelError,Op,operand_problem
from .st_expression import STExpression
from . import system_values, array_sort, st_cases, st_timers, st_counter, st_oneshot, st_scale, st_signal, st_rate, st_moving, st_capture, st_filter
from .integer_math import WIDE_TYPES

ST_CALLS={'COP','CPS','FLL','SIZE','CONCAT','MID','DTOS','STOD','FIND','INSERT','DELETE','LOWER','UPPER','STOR','RTOS','EVENT','JSR','SBR','RET','GSV','SSV','SWPB','SRT',*st_timers.INSTRUCTIONS,*st_counter.INSTRUCTIONS,*st_oneshot.INSTRUCTIONS,*st_scale.INSTRUCTIONS,*st_signal.INSTRUCTIONS,*st_rate.INSTRUCTIONS,*st_moving.INSTRUCTIONS,*st_capture.INSTRUCTIONS,*st_filter.INSTRUCTIONS}


@dataclass
class Statement:
    kind:str
    line:int
    text:str
    target:str=''
    expr:str=''
    start:str=''
    limit:str=''
    step:str='1'
    reset:bool=False
    op:object=None
    body:list=field(default_factory=list)
    tests:list=field(default_factory=list)
    otherwise:list=field(default_factory=list)
    cases:list=field(default_factory=list)


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.body)
        for _,body in node.tests:yield from walk(body)
        for _,body in node.cases:yield from walk(body)
        yield from walk(node.otherwise)


def clean_comments(source):
    result=list(source);pos=0
    while pos<len(source):
        if source[pos]=="'":
            pos+=1
            while pos<len(source) and source[pos]!="'":
                if source[pos] in '\r\n':raise ModelError('ST string literals cannot span lines')
                pos+=2 if source[pos]=='$' else 1
            if pos>=len(source):raise ModelError('Unclosed ST string literal')
            pos+=1;continue
        end=None
        if source[pos:pos+2]=='//':
            end=source.find('\n',pos+2)
            if end<0:end=len(source)
        elif source[pos:pos+2] in ('(*','/*'):
            opening=source[pos:pos+2];closing='*)' if opening=='(*' else '*/'
            end=source.find(closing,pos+2)
            if end<0:raise ModelError('Unclosed ST comment')
            if opening in source[pos+2:end]:raise ModelError('Nested ST comments are unsupported')
            end+=2
        if end is not None:
            for i in range(pos,end):
                if result[i]!='\n':result[i]=' '
            pos=end
        else:pos+=1
    return ''.join(result)


class Parser:
    def __init__(self,source):
        if len(source)>1_000_000:raise ModelError('ST routine exceeds 1 MB')
        self.source=clean_comments(source);self.lines=source.split('\n');self.tokens=[];pos=0;line=0
        while pos<len(self.source):
            c=self.source[pos]
            if c.isspace():line+=c=='\n';pos+=1;continue
            start=pos
            if c=="'":
                pos+=1
                while pos<len(self.source) and self.source[pos]!="'":pos+=2 if self.source[pos]=='$' else 1
                if pos>=len(self.source):raise ModelError('Unclosed ST string literal')
                pos+=1
            else:
                match=re.match(r'(?:2|8|16)#[0-9A-Fa-f_]+|(?:\d+(?:\.(?!\.)\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[A-Za-z_][\w]*|\[:=\]|:=|\.\.|<=|>=|<>|\*\*|[+*/(),;:\[\].=<>\-&]',self.source[pos:])
                if not match:raise ModelError(f'ST line {line+1}: unsupported syntax near {self.source[pos:pos+24]!r}')
                pos+=len(match[0])
            self.tokens.append((self.source[start:pos],start,pos,line))
        if len(self.tokens)>50000:raise ModelError('ST routine exceeds 50000 tokens')
        self.tokens.append(('<END>',len(source),len(source),line));self.pos=0;self.depth=0

    def word(self):return self.tokens[self.pos][0].upper()

    def expect(self,value):
        if self.word()!=value:raise ModelError(f'ST line {self.tokens[self.pos][3]+1}: expected {value}, found {self.word()}')
        token=self.tokens[self.pos];self.pos+=1;return token

    def capture(self,stops):
        start=self.pos;depth=0
        while self.word()!='<END>':
            word=self.word()
            if not depth and word in stops:break
            if word in ('(','['):depth+=1
            elif word in (')',']'):
                depth-=1
                if depth<0:raise ModelError('Unbalanced ST expression')
            self.pos+=1
        if self.pos==start:raise ModelError('Missing ST expression/operand')
        if depth:raise ModelError('Unclosed ST expression')
        return self.source[self.tokens[start][1]:self.tokens[self.pos-1][2]].strip()

    def node(self,kind,start):return Statement(kind,start[3],self.lines[start[3]].strip())

    def case_label(self):
        cursor=self.pos
        while cursor<len(self.tokens):
            word=self.tokens[cursor][0]
            if word==':':return True
            if not re.fullmatch(r'[+\-]|\.\.|,|'+st_cases.NUMBER,word):return False
            cursor+=1
        return False

    def block(self,stops=(),case=False):
        self.depth+=1
        if self.depth>64:raise ModelError('ST construct nesting exceeds 64')
        out=[]
        try:
            while self.word()!='<END>' and self.word() not in stops and not(case and self.case_label()):
                if self.word()==';':self.pos+=1;continue
                out.append(self.statement())
            return out
        finally:self.depth-=1

    def statement(self):
        token=self.tokens[self.pos];word=self.word()
        if word=='IF':
            self.pos+=1;n=self.node('if',token)
            while True:
                expr=self.capture({'THEN'});self.expect('THEN')
                n.tests.append((expr,self.block({'ELSIF','ELSE','END_IF'})))
                if self.word()!='ELSIF':break
                self.pos+=1
            if self.word()=='ELSE':self.pos+=1;n.otherwise=self.block({'END_IF'})
            self.expect('END_IF');self.expect(';');return n
        if word=='FOR':
            self.pos+=1;n=self.node('for',token);n.target=self.capture({':='});self.expect(':=')
            n.start=self.capture({'TO'});self.expect('TO');n.limit=self.capture({'BY','DO'})
            if self.word()=='BY':self.pos+=1;n.step=self.capture({'DO'})
            self.expect('DO');n.body=self.block({'END_FOR'});self.expect('END_FOR');self.expect(';');return n
        if word=='WHILE':
            self.pos+=1;n=self.node('while',token);n.expr=self.capture({'DO'});self.expect('DO')
            n.body=self.block({'END_WHILE'});self.expect('END_WHILE');self.expect(';');return n
        if word=='REPEAT':
            self.pos+=1;n=self.node('repeat',token);n.body=self.block({'UNTIL'});self.expect('UNTIL')
            n.expr=self.capture({'END_REPEAT'});self.expect('END_REPEAT');self.expect(';');return n
        if word=='CASE':
            self.pos+=1;n=self.node('case',token);n.expr=self.capture({'OF'});self.expect('OF')
            while self.word() not in ('ELSE','END_CASE','<END>'):
                labels=self.capture({':'});self.expect(':');ranges=st_cases.labels(labels)
                n.cases.append((ranges,self.block({'ELSE','END_CASE'},case=True)))
            if self.word()=='ELSE':self.pos+=1;n.otherwise=self.block({'END_CASE'})
            self.expect('END_CASE');self.expect(';');return n
        if word=='EXIT':self.pos+=1;self.expect(';');return self.node('exit',token)
        start=self.pos;fragment=self.capture({';'});self.expect(';')
        assignment=re.match(r'^(.*?)\s*(\[:=\]|:=)\s*(.+)$',fragment,re.S)
        if assignment:
            n=self.node('assign',token);n.target,n.expr=assignment[1].strip(),assignment[3].strip();n.reset=assignment[2]=='[:=]';return n
        tokens=self.tokens[start:self.pos-1]
        if len(tokens)<3 or not re.fullmatch(r'[A-Za-z_]\w*',tokens[0][0]) or tokens[1][0]!='(' or tokens[-1][0]!=')':
            raise ModelError(f'ST line {token[3]+1}: expected assignment or instruction call')
        args=[];first=2;depth=0
        for i in range(2,len(tokens)-1):
            t=tokens[i][0]
            if t in ('(','['):depth+=1
            elif t in (')',']'):depth-=1
            elif t==',' and not depth:
                args.append(self.source[tokens[first][1]:tokens[i][1]].strip());first=i+1
        if first<len(tokens)-1:args.append(self.source[tokens[first][1]:tokens[-1][1]].strip())
        if tokens[0][0].upper()=='SRT':
            if len(args)!=3:raise ModelError('ST SRT requires array, dimension and CONTROL operands')
            args+=['?','?']
        n=self.node('call',token);n.op=Op(tokens[0][0].upper(),args);return n

    def parse(self):
        result=self.block();self.expect('<END>');return result


class ExitLoop(Exception):pass


class Structured:
    def __init__(self,engine):self.engine=engine;self.memory=engine.memory;self.expressions={}

    def expression(self,text):
        if text not in self.expressions:self.expressions[text]=STExpression(text)
        return self.expressions[text]

    def type(self,text,scope,dtype=None):return self.expression(text).analyze(self.memory,scope,dtype)[0]

    def value(self,text,scope,dtype=None):return self.expression(text).evaluate(self.memory,scope,dtype)

    def boolean(self,text,scope):
        result=self.value(text,scope)
        if not isinstance(result,bool):raise ModelError('ST condition requires BOOL')
        return result

    def integer(self,text,scope):
        value=self.value(text,scope)
        if isinstance(value,bool) or not isinstance(value,int):raise ModelError('ST loop operand requires an integer')
        return value

    def loop_contract(self,node,scope):
        from .calls import overlaps
        counter=self.engine.calls.operand(node.target,scope,writable=True)
        if counter.dims:raise ModelError('FOR counter must be a scalar static reference')
        dependencies=[]
        for expr in (node.limit,node.step):
            for ref in self.expression(expr).refs:
                dependencies.append(self.engine.calls.operand(ref,scope))
        if any(overlaps(counter,dep) for dep in dependencies):raise ModelError('FOR bounds/step cannot depend on its counter')
        writes=[];extra_writes=[]
        for item in walk(node.body):
            if item.kind in ('assign','for'):writes.append(item.target)
            elif item.kind=='call':
                op=item.op
                if op.name=='EVENT':raise ModelError('EVENT inside FOR remains unqualified because task logic may change the loop counter/bounds')
                if op.name=='JSR' and dependencies:raise ModelError('JSR inside FOR with tag-based bounds/step is unsupported')
                if op.name=='GSV':
                    key,parts,_=system_values.validate(self.engine,op,scope)
                    extra_writes.extend((key,part) for part in parts)
                elif op.name=='SRT':extra_writes.extend(array_sort.write_effects(self.memory,op,scope))
                elif op.name in st_moving.INSTRUCTIONS:writes.extend(op.args[:2])
                elif op.name in st_timers.INSTRUCTIONS|st_counter.INSTRUCTIONS|st_oneshot.INSTRUCTIONS|st_scale.INSTRUCTIONS|st_signal.INSTRUCTIONS|st_rate.INSTRUCTIONS|st_capture.INSTRUCTIONS|st_filter.INSTRUCTIONS:writes.append(op.args[0])
                elif op.name in self.engine.project.aois:
                    writes.append(op.args[0])
                    for p,arg in zip(self.engine.project.aois[op.name].required,op.args[1:]):
                        if p.get('Usage') in ('Output','InOut'):writes.append(arg)
                else:
                    positions={'COP':[1],'CPS':[1],'FLL':[1],'SIZE':[2],'CONCAT':[2],'MID':[3],'DTOS':[1],'STOD':[1],'LOWER':[1],'UPPER':[1],'STOR':[1],'RTOS':[1],'FIND':[3],'INSERT':[3],'DELETE':[3],
                               'SWPB':[2],'SBR':list(range(len(op.args)))}.get(op.name,[])
                    writes.extend(op.args[i] for i in positions if i<len(op.args))
        for ref in writes:
            key,parts,_=self.memory.resolve(ref,scope);extra_writes.append((key,parts))
        for key,parts in extra_writes:
            if any(dep.key==key and (parts[:len(dep.parts)]==dep.parts or dep.parts[:len(parts)]==parts) for dep in dependencies):
                raise ModelError('FOR body cannot modify tags used by its bounds/step')

    def validate(self,routine,scope):
        previous=(self.memory.structural,self.memory.validating);self.memory.structural=True;self.memory.validating=True
        def check(nodes,loops=0):
            for n in nodes:
                try:
                    if n.kind=='assign':
                        _,_,dtype=self.memory.check_writable(n.target,scope);result=self.type(n.expr,scope,dtype)
                        if isinstance(self.memory.read(n.target,scope),list):raise ModelError('Whole-array ST assignment is unsupported; use COP')
                        if dtype=='BOOL':
                            tree=self.expression(n.expr).tree
                            if result!='bool' and not(tree[0]=='literal' and type(tree[1]) is int and tree[1] in (0,1)):raise ModelError('BOOL assignment requires BOOL or literal 0/1')
                        elif dtype in ('SINT','INT','DINT','REAL',*WIDE_TYPES):
                            if result!='number':raise ModelError('Numeric assignment requires a numeric expression')
                        elif self.engine.project.string_capacity(dtype) is not None:
                            if result!='string':raise ModelError('String assignment requires a string expression')
                            tree=self.expression(n.expr).tree
                            if tree[0]=='ref' and self.memory.resolve(tree[1],scope)[2]!=dtype:raise ModelError('ST string tag assignment requires matching declared types')
                            if tree[0]=='string' and len(tree[1])>self.engine.project.string_capacity(dtype):raise ModelError('ST string literal exceeds destination capacity')
                        else:raise ModelError('Unsupported ST assignment type '+dtype)
                    elif n.kind=='call':
                        if n.op.name not in ST_CALLS and n.op.name not in self.engine.project.aois:raise ModelError('Unsupported ST instruction '+n.op.name)
                        if n.op.name in ST_CALLS:
                            problem=operand_problem(n.op)
                            if problem:raise ModelError(problem)
                        # MID values are runtime-checked; structural validation must
                        # not mistake a placeholder start value for an actual start.
                        if n.op.name=='MID':
                            a=n.op.args
                            for ref in (a[0],a[3]):self.memory.string(ref,scope)
                            self.memory.check_writable(a[3],scope)
                            for ref in a[1:3]:self.engine.extensions.integer(ref,scope)
                    elif n.kind=='if':
                        for expr,body in n.tests:
                            if self.type(expr,scope)!='bool':raise ModelError('IF requires a BOOL expression')
                            check(body,loops)
                        check(n.otherwise,loops)
                    elif n.kind=='for':
                        if self.memory.check_writable(n.target,scope)[2] not in ('SINT','INT','DINT'):raise ModelError('FOR counter requires SINT/INT/DINT')
                        for expr in (n.start,n.limit,n.step):
                            t,real,_=self.expression(expr).analyze(self.memory,scope,self.memory.resolve(n.target,scope)[2])
                            if t!='number' or real:raise ModelError('FOR bounds and step must be integers')
                        self.loop_contract(n,scope)
                        check(n.body,loops+1)
                    elif n.kind in ('while','repeat'):
                        if self.type(n.expr,scope)!='bool':raise ModelError('Loop condition requires BOOL')
                        check(n.body,loops+1)
                    elif n.kind=='case':
                        self.case_contract(n,scope)
                        for _,body in n.cases:check(body,loops)
                        check(n.otherwise,loops)
                    elif n.kind=='exit' and not loops:raise ModelError('EXIT requires a surrounding loop')
                except ModelError as e:raise ModelError(f'ST line {n.line+1}: {e}') from e
        try:check(routine.statements)
        finally:self.memory.structural,self.memory.validating=previous

    def case_contract(self,node,scope):
        expression=self.expression(node.expr)
        if expression.typed_types or any(self.memory.resolve(ref,scope)[2] in WIDE_TYPES for ref in expression.refs):
            raise ModelError('Wide ST CASE selectors remain unqualified')
        kind,real,_=expression.analyze(self.memory,scope)
        if kind!='number':raise ModelError('CASE requires a numeric expression')
        return [(st_cases.normalize(ranges,real),body) for ranges,body in node.cases]

    def tick(self):
        self.engine.budget-=1
        if self.engine.budget<0:raise ModelError('ST instruction budget exceeded')

    def trace(self,routine,n,context,power=True,detail=''):
        self.engine.trace.append({'routine':routine.key,'number':str(n.line),'context':context,'language':'ST','power':power,
                                  'statement':n.kind,'detail':str(detail),'events':[],
                                  'task':self.engine._executing_task,'release_ms':self.engine.time_ms})
        if len(self.engine.trace)>5000:self.engine.trace=self.engine.trace[-5000:]

    def execute(self,routine,scope,depth,context=''):
        from .runtime import ReturnRoutine
        from .calls import BreakLoop
        def run(nodes):
            for n in nodes:
                self.tick()
                try:
                    if n.kind=='assign':
                        key,parts,dtype=self.memory.check_writable(n.target,scope);value=self.value(n.expr,scope,dtype)
                        if isinstance(value,str):
                            tree=self.expression(n.expr).tree
                            if tree[0]=='ref':
                                sk,sp,st=self.memory.resolve(tree[1],scope)
                                if st!=dtype:raise ModelError('ST string tag assignment currently requires matching declared types')
                                self.memory.store(key,parts,copy.deepcopy(self.memory.read(tree[1],scope)))
                            else:self.memory.write_string(n.target,value,scope)
                        else:self.memory.write(n.target,value,scope)
                        self.trace(routine,n,context,detail=n.target+' = '+str(value))
                    elif n.kind=='call':
                        try:
                            if n.op.name=='SRT':array_sort.execute_st(self.memory,n.op,scope)
                            elif n.op.name in st_timers.INSTRUCTIONS:st_timers.execute(self.engine,n.op,scope)
                            elif n.op.name in st_counter.INSTRUCTIONS:st_counter.execute(self.engine,n.op,scope)
                            elif n.op.name in st_oneshot.INSTRUCTIONS:st_oneshot.execute(self.engine,n.op,scope)
                            elif n.op.name in st_scale.INSTRUCTIONS:st_scale.execute(self.engine,n.op,scope)
                            elif n.op.name in st_signal.INSTRUCTIONS:st_signal.execute(self.engine,n.op,scope)
                            elif n.op.name in st_rate.INSTRUCTIONS:st_rate.execute(self.engine,n.op,scope)
                            elif n.op.name in st_moving.INSTRUCTIONS:st_moving.execute(self.engine,n.op,scope)
                            elif n.op.name in st_capture.INSTRUCTIONS:st_capture.execute(self.engine,n.op,scope)
                            elif n.op.name in st_filter.INSTRUCTIONS:st_filter.execute(self.engine,n.op,scope)
                            else:self.engine._op(n.op,True,scope,depth)
                        except ReturnRoutine:
                            self.trace(routine,n,context,detail='return');raise
                        except BreakLoop:
                            self.trace(routine,n,context,detail='break');raise
                        self.trace(routine,n,context,detail=n.op.name)
                    elif n.kind=='if':
                        chosen=n.otherwise;result=False
                        for expr,body in n.tests:
                            if self.boolean(expr,scope):chosen=body;result=True;break
                        self.trace(routine,n,context,result,detail='branch selected' if result else 'else / no branch');run(chosen)
                    elif n.kind=='case':
                        cases=self.case_contract(n,scope);value=self.value(n.expr,scope);chosen=n.otherwise
                        for ranges,body in cases:
                            if any(lo<=value<=hi for lo,hi in ranges):chosen=body;break
                        self.trace(routine,n,context,detail=value);run(chosen)
                    elif n.kind=='for':
                        self.memory.write(n.target,self.integer(n.start,scope),scope)
                        # Bounds and increment are re-evaluated at each loop test.
                        while True:
                            self.tick();step=self.integer(n.step,scope);limit=self.integer(n.limit,scope)
                            if not step:raise ModelError('FOR step cannot be zero')
                            current=self.memory.read(n.target,scope)
                            if (step>0 and current>limit) or (step<0 and current<limit):break
                            self.trace(routine,n,context,detail=current)
                            try:run(n.body)
                            except ExitLoop:break
                            self.memory.write(n.target,self.memory.read(n.target,scope)+step,scope)
                    elif n.kind in ('while','repeat'):
                        while True:
                            self.tick()
                            if n.kind=='while' and not self.boolean(n.expr,scope):break
                            self.trace(routine,n,context)
                            try:run(n.body)
                            except ExitLoop:break
                            if n.kind=='repeat' and self.boolean(n.expr,scope):break
                    elif n.kind=='exit':self.trace(routine,n,context,detail='exit loop');raise ExitLoop()
                except ModelError as e:raise ModelError(f'{routine.key}, ST line {n.line+1}: {e}') from e
        try:run(routine.statements)
        except ReturnRoutine:pass

    def prescan(self,routine,scope,depth):
        for n in walk(routine.statements):
            self.tick()
            if n.kind=='assign' and n.reset:
                dtype=self.memory.resolve(n.target,scope)[2]
                if self.engine.project.string_capacity(dtype) is not None:self.memory.write_string(n.target,'',scope)
                else:self.memory.write(n.target,False if dtype=='BOOL' else 0,scope)
            elif n.kind=='call' and n.op.name in st_timers.INSTRUCTIONS:st_timers.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_counter.INSTRUCTIONS:st_counter.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_oneshot.INSTRUCTIONS:st_oneshot.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_scale.INSTRUCTIONS:st_scale.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_signal.INSTRUCTIONS:st_signal.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_rate.INSTRUCTIONS:st_rate.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_moving.INSTRUCTIONS:st_moving.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_capture.INSTRUCTIONS:st_capture.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in st_filter.INSTRUCTIONS:st_filter.prescan(self.engine,n.op,scope)
            elif n.kind=='call' and n.op.name in self.engine.project.aois:
                self.engine.addons.call(n.op,False,scope,depth+1,prescan=True)
