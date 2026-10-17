"""Bounded expression parser. No Python eval, attribute lookup, or function dispatch."""
import math
import re
from .model import ModelError, coerce, literal

FUNCTIONS = {'ABS': abs, 'SQR': math.sqrt, 'SQRT': math.sqrt, 'TRN': math.trunc,
             'TRUNC': math.trunc, 'LN': math.log, 'LOG': math.log10,
             'SIN': math.sin, 'COS': math.cos, 'TAN': math.tan,
             'ASN': math.asin, 'ACS': math.acos, 'ATN': math.atan,
             'DEG': math.degrees, 'RAD': math.radians}
PRECEDENCE = {'OR': 1, 'XOR': 2, 'AND': 3, '+': 4, '-': 4,
              '*': 5, '/': 5, 'MOD': 5, '**': 7}


class Expression:
    def __init__(self, text, condition=False, structured=False):
        if len(text) > 4096: raise ModelError('Expression exceeds 4096 characters')
        self.precedence = dict(PRECEDENCE)
        self.minimum = -3 if condition else 0
        self.structured=structured
        self.function_map=dict(FUNCTIONS)
        if condition:self.precedence.update({'<':0,'<=':0,'>':0,'>=':0,'=':0,'<>':0,'&&':-1,'^^':-2,'||':-3})
        if structured:
            self.minimum=0
            self.precedence={'OR':1,'XOR':2,'AND':3,'=':4,'<>':4,'<':5,'<=':5,'>':5,'>=':5,'+':6,'-':6,'*':7,'/':7,'MOD':7,'**':10}
            self.function_map.update(ASIN=math.asin,ACOS=math.acos,ATAN=math.atan)
        self.tokens = []
        self.refs = []
        self.functions = set()
        self.operators = set()
        pos = 0
        while pos < len(text):
            if text[pos].isspace(): pos += 1; continue
            if structured and text[pos]=="'":
                start=pos;pos+=1
                while pos<len(text) and text[pos]!="'":
                    pos+=2 if text[pos]=='$' else 1
                if pos>=len(text):raise ModelError('Unclosed ST string literal')
                pos+=1
                from .model import ascii_bytes
                self.tokens.append(('string',bytes(x&255 for x in ascii_bytes(text[start:pos].replace('$I','$L').replace('$i','$L'))).decode('latin-1')))
                continue
            if structured and text[pos]=='&':self.tokens.append(('AND','AND'));pos+=1;continue
            number = re.match(r'(?:2|8|16)#[0-9a-fA-F_]+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text[pos:])
            if number:
                value = number[0]
                self.tokens.append(('number', value)); pos += len(value); continue
            if text[pos:pos+2] == '**': self.tokens.append(('**', '**')); pos += 2; continue
            if condition:
                pair=text[pos:pos+2]
                if pair in ('<=','>=','<>','&&','^^','||'):
                    self.tokens.append((pair,pair));pos+=2;continue
                if text[pos] in '<>=!':self.tokens.append((text[pos],text[pos]));pos+=1;continue
            if text[pos] in '+-*/(),':
                self.tokens.append((text[pos], text[pos])); pos += 1; continue
            name = re.match(r'[A-Za-z_][\w:]*', text[pos:])
            if not name: raise ModelError(f'Unsupported expression syntax near {text[pos:pos+30]!r}')
            start = pos; pos += len(name[0])
            word = name[0].upper()
            if word in {'AND','OR','XOR','MOD','NOT'}:
                self.tokens.append((word, word)); continue
            while pos < len(text):
                if text[pos] == '.':
                    if structured and text[pos:pos+2]=='.[':
                        pos+=1;continue
                    member = re.match(r'\.[\w]+', text[pos:])
                    if not member: raise ModelError('Invalid expression member')
                    pos += len(member[0])
                elif text[pos] == '[':
                    depth = 1; pos += 1
                    while pos < len(text) and depth:
                        if text[pos] == '[': depth += 1
                        if text[pos] == ']': depth -= 1
                        pos += 1
                    if depth: raise ModelError('Unclosed expression array subscript')
                else: break
            self.tokens.append(('name', text[start:pos]))
        if len(self.tokens) > 512: raise ModelError('Expression exceeds 512 tokens')
        self.tokens.append(('end',''))
        self.pos = 0
        self.tree = self._parse(self.minimum, 0)
        if self.tokens[self.pos][0] != 'end': raise ModelError('Unexpected expression token')

    def _parse(self, minimum, depth):
        if depth > 64: raise ModelError('Expression nesting limit exceeded')
        kind, value = self.tokens[self.pos]; self.pos += 1
        if kind == 'number': node = ('literal', literal(value))
        elif kind=='string':node=('string',value)
        elif kind in ('+','-','NOT','!'):
            self.operators.add(kind)
            node = ('unary', kind, self._parse((8 if kind=='NOT' else 9) if self.structured else 6, depth + 1))
        elif kind == '(':
            node = self._parse(self.minimum, depth + 1)
            if self.tokens[self.pos][0] != ')': raise ModelError('Unclosed expression parentheses')
            self.pos += 1
        elif kind == 'name':
            if self.structured and value.upper() in ('TRUE','FALSE'):node=('literal',value.upper()=='TRUE')
            elif self.tokens[self.pos][0] == '(':
                function = value.upper()
                if function not in self.function_map: raise ModelError(f'Unsupported expression function {value}')
                self.functions.add(function); self.pos += 1
                argument = self._parse(self.minimum, depth + 1)
                if self.tokens[self.pos][0] != ')': raise ModelError('Function requires one operand')
                self.pos += 1; node = ('call', function, argument)
            else:
                self.refs.append(value); node = ('ref', value)
        else: raise ModelError('Expected expression operand')
        while self.tokens[self.pos][0] in self.precedence and self.precedence[self.tokens[self.pos][0]] >= minimum:
            op = self.tokens[self.pos][0]; self.pos += 1
            self.operators.add(op)
            right = self._parse(self.precedence[op] + 1, depth + 1)
            node = ('binary', op, node, right)
        return node

    def validate(self, memory, scope='', destination_type=None, index=False):
        real = destination_type == 'REAL'
        for ref in self.refs:
            value = memory.read(ref, scope)
            dtype = memory.resolve(ref, scope)[2]
            if dtype not in ('SINT','INT','DINT','REAL') or isinstance(value, (list,dict,bool)):
                raise ModelError(f'Expression requires numeric scalar: {ref}')
            real |= dtype == 'REAL'
        def has_float(node):
            return node[0] == 'literal' and isinstance(node[1],float) or any(has_float(x) for x in node[1:] if isinstance(x,tuple))
        real |= has_float(self.tree)
        real |= bool(self.functions - {'ABS','TRN','TRUNC'})
        if index and (real or self.operators - {'+','-','*'} or self.functions):
            raise ModelError('Array index expressions support integer +, -, * and parentheses only')
        if not real and self.operators & {'/','**'}:
            raise ModelError('Integer CPT division/power is not modeled; use a REAL operand or destination')
        if real and self.operators & {'AND','OR','XOR','NOT'}:
            raise ModelError('Bitwise CPT operators require integer expressions')
        return real

    def evaluate(self, memory, scope='', destination_type=None, index=False):
        real = self.validate(memory, scope, destination_type, index)
        def number(value): return coerce(value, 'REAL' if real else 'DINT')
        def visit(node):
            kind, value = node[:2]
            if kind == 'literal': return number(value)
            if kind == 'ref': return number(memory.read(value,scope))
            if kind == 'unary':
                x=visit(node[2]);return number(x if value=='+' else -x if value=='-' else ~x)
            if kind == 'call': return number(FUNCTIONS[value](visit(node[2])))
            x,y=visit(node[2]),visit(node[3])
            if value in ('/','MOD') and not y: raise ModelError('Expression divide by zero')
            if value=='**' and abs(y)>1024: raise ModelError('Expression exponent outside modeled range')
            if value=='+': result=x+y
            elif value=='-': result=x-y
            elif value=='*': result=x*y
            elif value=='/': result=x/y
            elif value=='MOD': result=math.fmod(x,y) if real else x-(abs(x)//abs(y)*(-1 if (x<0)!=(y<0) else 1))*y
            elif value=='**': result=x**y
            elif value=='AND': result=x&y
            elif value=='OR': result=x|y
            elif value=='XOR': result=x^y
            else: raise ModelError(f'Unsupported expression operator {value}')
            if isinstance(result,complex):raise ModelError('Complex expression result')
            return number(result)
        return visit(self.tree)
