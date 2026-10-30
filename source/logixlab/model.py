from __future__ import annotations

import copy
import hashlib
import re
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from .controller_configuration import ControllerConfiguration
from .motion_catalog import MotionCatalog
from .alarm_catalog import AlarmCatalog
from .aoi_catalog import AOICatalog
from .data_log_catalog import DataLogCatalog
from .hmi_button_catalog import HmiButtonCatalog
from .energy_catalog import EnergyCatalog
from .message_catalog import MessageCatalog
from .pccc_mapping import PcccMapping
from .time_sync import TimeSync
from .wall_clock import WallClock
from .program_forces import ProgramForces
from .program_configuration import ProgramConfiguration
from .program_hierarchy import ProgramHierarchy
from .program_diagnostics import ProgramDiagnostics
from .task_configuration import TaskConfiguration
from .task_timing import TaskTiming
from .executable_configuration import ExecutableConfiguration
from .io_map import IOMap


class ModelError(Exception):
    pass


@dataclass
class Op:
    name: str
    args: list[str]


@dataclass
class Branch:
    paths: list[list]


ARITIES = {"XIC": 1, "XIO": 1, "OTE": 1, "OTL": 1, "OTU": 1,
           "ONS": 1, "OSR": 2, "OSF": 2, "AFI": 0, "NOP": 0,
           "EQU": 2, "NEQ": 2, "LES": 2, "LEQ": 2, "GRT": 2, "GEQ": 2,
           "LIM": 3, "MOV": 2, "CLR": 1, "ADD": 3, "SUB": 3, "MUL": 3,
           "DIV": 3, "MOD": 3, "NEG": 2, "ABS": 2,
           "AND": 3, "OR": 3, "XOR": 3, "NOT": 2, "MVM": 3, "BTD": 5,
           "TON": 3, "TOF": 3, "RTO": 3, "CTU": 3, "CTD": 3,
           "RES": 1, "JSR": 2, "SBR": 0, "RET": 0,
           "COP": 3, "CPS": 3, "FLL": 3, "SIZE": 3, "CPT": 2,
           "JMP": 1, "LBL": 1, "TND": 0, "FOR": 5, "BRK": 0,
           "CONCAT": 3, "MID": 4, "DTOS": 2, "STOD": 2, "TRN": 2,
           'CMP':1,'MEQ':3,'GSV':4,'FIND':4,'INSERT':4,'DELETE':4,'BSL':4,'BSR':4,'FFL':5,'FFU':5,'LFL':5,'LFU':5,'SQO':6,'SQI':6,'SQL':5,'FRD':2,'TOD':2,'SWPB':3,
           'SQR':2,'LN':2,'LOG':2,'XPY':3,'DEG':2,'RAD':2,'SIN':2,'COS':2,'TAN':2,'ASN':2,'ACS':2,'ATN':2,'AVE':6,'STD':6,'SRT':5,'FSC':5,'FAL':6,'LOWER':2,'UPPER':2,'STOR':2,'RTOS':2,'EVENT':1,'SSV':4,'MCR':0,'DTR':3,'FBC':9,'DDT':9}


ST_ONLY_ARITIES = {"TONR":1,"TOFR":1,"RTOR":1,"CTUD":1,"OSRI":1,"OSFI":1,"SCL":1,"HLL":1,"SNEG":1,"SSUM":1,"RLIM":1,"MAVE":3,"MSTD":2}


def operand_problem(op):
    if op.name=='JSR':
        if len(op.args)<2:return 'JSR requires routine name and literal input count'
        if not re.fullmatch(r'[A-Za-z_][\w]*',op.args[0]):return 'Invalid JSR routine name'
        if not re.fullmatch(r'\d+',op.args[1]):return 'JSR input count must be a decimal literal'
        count=int(op.args[1])
        if not 0<=count<=40 or not 0<=len(op.args)-2-count<=40:return 'JSR requires 0..40 input and 0..40 return operands'
    elif op.name=='MAVE':
        if len(op.args) not in (2,3):return 'MAVE requires record, storage and optional weight array'
    elif op.name in ('SBR','RET'):
        if len(op.args)>40:return op.name+' permits at most 40 operands'
    elif len(op.args)!=ARITIES.get(op.name,ST_ONLY_ARITIES.get(op.name)):return f'{op.name} operand count {len(op.args)} unsupported'
    return ''


def parse_rung(text: str) -> list:
    """Parse neutral-text RLL without eval. Branch commas never split operands."""
    text = text.strip()
    pos = 0

    def sequence(stops=""):
        nonlocal pos
        out = []
        while pos < len(text):
            if text[pos].isspace():
                pos += 1
                continue
            ch = text[pos]
            if ch in stops:
                break
            if ch == "[":
                pos += 1
                paths = [sequence(",]")]
                while pos < len(text) and text[pos] == ",":
                    pos += 1
                    paths.append(sequence(",]"))
                if pos >= len(text) or text[pos] != "]":
                    raise ModelError("Unclosed ladder branch")
                pos += 1
                out.append(Branch(paths))
                continue
            if ch == ";":
                pos += 1
                if text[pos:].strip():
                    raise ModelError("Unexpected text after rung terminator")
                break
            m = re.match(r"([A-Za-z_][\w]*)\s*\(", text[pos:])
            if not m:
                raise ModelError(f"Unrecognized ladder syntax at {text[pos:pos + 40]!r}")
            name = m[1].upper()
            pos += m.end()
            start = pos
            depth = 0
            while pos < len(text):
                if text[pos] == "(":
                    depth += 1
                elif text[pos] == ")":
                    if not depth:
                        break
                    depth -= 1
                pos += 1
            if pos >= len(text):
                raise ModelError(f"Unclosed {name}")
            args_text = text[start:pos]
            args = []
            start_arg = 0
            brackets = 0
            for i, c in enumerate(args_text):
                if c in "[(": brackets += 1
                if c in "])": brackets -= 1
                if c == "," and brackets == 0:
                    args.append(args_text[start_arg:i].strip())
                    start_arg = i + 1
            if args_text.strip(): args.append(args_text[start_arg:].strip())
            pos += 1
            out.append(Op(name, args))
        return out

    result = sequence()
    if pos != len(text): raise ModelError("Unexpected branch delimiter")
    return result


def operations(nodes):
    for node in nodes:
        if isinstance(node, Op): yield node
        else:
            for path in node.paths: yield from operations(path)


def literal(text):
    text = text.strip().replace("_", "")
    if text.upper() in ("TRUE", "FALSE"): return text.upper() == "TRUE"
    m = re.fullmatch(r"(-?)(2|8|16)#([0-9A-Fa-f]+)", text)
    if m: return (-1 if m[1] else 1) * int(m[3], int(m[2]))
    if re.fullmatch(r"[+-]?\d+", text): return int(text)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?", text):
        return float(text)
    raise ValueError(text)


UNSIGNED_BITS = {'USINT':8,'UINT':16,'UDINT':32,'ULINT':64}
INT_BITS = {"SINT": 8, "INT": 16, "DINT": 32, "LINT": 64, **UNSIGNED_BITS}


def dimensions(text):
    text=','.join(text.split()) if text else text
    if not text or text == '0': return ()
    if not re.fullmatch(r'\d+(?:,\d+){0,2}', text): raise ModelError('Unsupported array dimensions')
    result = tuple(int(x) for x in text.split(','))
    if any(x < 1 for x in result) or __import__('math').prod(result) > 100000:
        raise ModelError('Array size must be 1..100000 elements')
    return result


def array_default(value, dims):
    if not dims: return copy.deepcopy(value)
    return [array_default(value, dims[1:]) for _ in range(dims[0])]


def unknown_shape(value):
    if isinstance(value,dict):return {k:unknown_shape(v) for k,v in value.items()}
    if isinstance(value,list):return [unknown_shape(v) for v in value]
    return None


def split_indices(text):
    result=[];start=0;depth=0
    for i,c in enumerate(text):
        if c in '[(': depth+=1
        elif c in '])': depth-=1
        elif c==',' and not depth: result.append(text[start:i].strip());start=i+1
    result.append(text[start:].strip())
    if any(not x for x in result):raise ModelError('Empty array subscript')
    return result


def ascii_bytes(text):
    """Rockwell single-quoted ASCII representation, preserving every data byte."""
    text=text.strip()
    if len(text)<2 or text[0]!="'" or text[-1]!="'":raise ModelError('Expected single-quoted ASCII data')
    text=text[1:-1];out=[];pos=0
    escapes={'$':36,"'":39,'T':9,'L':10,'R':13,'P':12}
    while pos<len(text):
        c=text[pos];pos+=1
        if c=='$':
            if pos>=len(text):raise ModelError('Incomplete ASCII escape')
            if re.fullmatch(r'[0-9a-fA-F]{2}',text[pos:pos+2]):
                byte=int(text[pos:pos+2],16);pos+=2
            elif text[pos].upper() in escapes:byte=escapes[text[pos].upper()];pos+=1
            else:raise ModelError('Unsupported ASCII escape')
        else:
            byte=ord(c)
            if byte>255:raise ModelError('String initial data must contain single-byte characters')
        out.append(byte if byte<128 else byte-256)
    return out


def coerce(value, dtype):
    dtype = dtype.upper()
    if dtype == "BOOL":
        if value not in (0, 1, False, True): raise ModelError("BOOL must be 0 or 1")
        return bool(value)
    if dtype in INT_BITS:
        # Logix MOV/math real-to-integer rounding uses ties to even.
        n = round(value) if isinstance(value, float) else int(value)
        bits = INT_BITS[dtype]
        lower,upper=(0,1<<bits) if dtype in UNSIGNED_BITS else (-(1<<(bits-1)),1<<(bits-1))
        if not lower <= n < upper:
            raise ModelError(f"{dtype} overflow: {n}; overflow-status emulation is not implemented")
        return n
    if dtype == "REAL":
        result = struct.unpack("<f", struct.pack("<f", float(value)))[0]
        if not __import__("math").isfinite(result): raise ModelError("Nonfinite REAL")
        return result
    raise ModelError(f"Cannot assign scalar to {dtype}")


@dataclass
class Tag:
    name: str
    dtype: str
    value: object
    scope: str = ""
    alias: str = ""
    constant: bool = False
    problem: str = ""
    external_access: str = 'Read/Write'
    tag_class: str = 'Standard'

    @property
    def key(self): return f"Program:{self.scope}.{self.name}" if self.scope else self.name


@dataclass
class Routine:
    program: str
    name: str
    kind: str
    rungs: list = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    lines: list = field(default_factory=list)
    statements: list = field(default_factory=list)

    @property
    def key(self): return f"{self.program}/{self.name}"


@dataclass
class AddOn:
    name: str
    parameters: list
    locals: list
    routines: dict = field(default_factory=dict)
    modes: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)

    @property
    def required(self):
        return [p for p in self.parameters if p.get('Required','false').lower()=='true'
                and p.get('Name','').lower() not in ('enablein','enableout')]


class Project:
    def __init__(self, path):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.tags = {}
        self.routines = {}
        self.programs = {}
        self.tasks = []
        self.issues = []
        self.instruction_counts = Counter()
        self.st_counts = Counter()
        self.udts = {}
        self.aois = {}
        self.data_only_types = set()
        data = self.path.read_bytes()
        if len(data) > 150_000_000: raise ModelError("Project exceeds 150 MB limit")
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ModelError("XML DTD/entity declarations are not supported")
        root = ET.fromstring(data)
        if root.tag != "RSLogix5000Content" or root.get("TargetType") != "Controller":
            raise ModelError("Import a complete Controller L5X export")
        c = root.find("Controller")
        if c is None: raise ModelError("Controller element is missing")
        self.motion_catalog = MotionCatalog.from_source(root, c)
        self.alarm_catalog = AlarmCatalog.from_source(root, c)
        self.aoi_catalog = AOICatalog.from_source(root, c)
        self.data_log_catalog = DataLogCatalog.from_source(root, c)
        self.hmi_button_catalog = HmiButtonCatalog.from_source(root, c)
        self.energy_catalog = EnergyCatalog.from_source(root, c)
        self.message_catalog = MessageCatalog.from_source(root, c)
        self.pccc_mapping = PcccMapping.from_source(root, c)
        self.time_sync = TimeSync.from_source(root, c)
        self.wall_clock = WallClock.from_source(root, c)
        self.program_forces = ProgramForces.from_source(root, c)
        self.program_configuration = ProgramConfiguration.from_source(root, c, self.sha256)
        self.program_hierarchy = ProgramHierarchy.from_source(root,c,self.sha256,self.program_configuration)
        self.task_configuration = TaskConfiguration.from_source(root, c, self.sha256)
        self.task_timing = TaskTiming.from_source(root, c, self.sha256, self.task_configuration)
        self.executable_configuration = ExecutableConfiguration.from_source(root, c, self.sha256)
        self.io_map = IOMap.from_source(root, c)
        self.program_diagnostics = ProgramDiagnostics.from_source(root,c,self.sha256,
            self.program_configuration,self.executable_configuration,self.io_map)
        self.controller_configuration = ControllerConfiguration.from_controller(c, root)
        from .component_tracking import EmptyComponentTracking
        self.component_tracking = EmptyComponentTracking.from_source(root,c,self.sha256,
            aoi_empty=self.aoi_catalog.empty,io_empty=self.io_map.empty)
        declared_names = [key for key in c.attrib if key.rsplit('}', 1)[-1].casefold() == 'name']
        self.source_controller_name = c.get('Name') if declared_names == ['Name'] else None
        self.source_controller_settings = frozenset(name for name in ('TimeSlice', 'ShareUnusedTimeSlice')
            if [key for key in c.attrib if key.rsplit('}', 1)[-1].casefold() == name.casefold()] == [name])
        self.name = c.get("Name", "Controller")
        self.version = c.get("MajorRev", root.get("SoftwareRevision", "unknown"))
        self.processor = c.get("ProcessorType", "unknown")
        self.minor_version = c.get('MinorRev','0')
        if self.version != "35": self.issues.append(f"Revision {self.version}: this prototype targets v35")
        for attr in ("PowerLossProgram", "PowerUpHandlerProgram", "MajorFaultProgram"):
            if c.get(attr): self.issues.append(f"{attr} execution is unsupported")
        for d in c.findall("./DataTypes/DataType"):
            self.udts[d.get("Name").lower()] = d
        for d in c.findall('./AddOnInstructionDefinitions/AddOnInstructionDefinition'):
            aoi=AddOn(d.get('Name',''),list(d.findall('./Parameters/Parameter')),
                      list(d.findall('./LocalTags/LocalTag')))
            self.aois[aoi.name.upper()]=aoi
            if d.get('Class','Standard')!='Standard':aoi.problems.append('Safety AOI execution is unsupported')
            for mode in ('Prescan','EnableInFalse','Postscan'):
                aoi.modes[mode]=d.get('Execute'+mode,'false').lower()=='true'
            names=set()
            schema=ET.Element('DataType',Name=aoi.name,Class='AOI')
            members=ET.SubElement(schema,'Members')
            for item in aoi.parameters+aoi.locals:
                name=item.get('Name','');usage=item.get('Usage','Local')
                if not name or name.lower() in names:aoi.problems.append('Duplicate or missing parameter/local name')
                names.add(name.lower())
                if item.get('AliasFor'):aoi.problems.append('Alias parameters are unsupported')
                if item.get('Constant','false').lower()=='true':aoi.problems.append('Constant parameter/local semantics are unsupported')
                if usage not in ('Input','Output','InOut','Local'):aoi.problems.append('Unknown parameter usage')
                if usage=='InOut':
                    if item.get('Required','false').lower()!='true':aoi.problems.append('InOut must be required')
                    if item.get('CanBeNull','false').lower()=='true':aoi.problems.append('Nullable InOut is unsupported')
                    continue
                ET.SubElement(members,'Member',Name=name,DataType=item.get('DataType',''),
                              Dimension=item.get('Dimensions','0'),Hidden='false',AOILocal=str(usage=='Local').lower(),
                              ExternalAccess=item.get('ExternalAccess','None' if usage=='Local' else 'Read/Write'))
                if usage in ('Input','Output') and (item.get('DataType','').upper() not in {'BOOL',*INT_BITS,'REAL'}
                                                    or dimensions(item.get('Dimensions','0'))):
                    aoi.problems.append('Input/Output parameters require supported atomic scalar types')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                p=next((p for p in aoi.parameters if p.get('Name','').lower()==name.lower()),None)
                if p is None or p.get('DataType')!='BOOL' or p.get('Usage')!=usage:
                    aoi.problems.append('Missing or invalid '+name)
            self.udts[aoi.name.lower()]=schema
        for d in c.findall('./AddOnInstructionDefinitions/AddOnInstructionDefinition'):
            aoi=self.aois[d.get('Name','').upper()]
            for r in d.findall('./Routines/Routine'):
                routine=self._routine(r,'AOI:'+aoi.name,count=False)
                aoi.routines[routine.name.lower()]=routine
            if 'logic' not in aoi.routines:aoi.problems.append('Logic is missing or protected')
            for mode,enabled in aoi.modes.items():
                if enabled and mode.lower() not in aoi.routines:aoi.problems.append(mode+' routine is missing or protected')
        builtin={'BOOL',*INT_BITS,'REAL','TIMER','COUNTER','CONTROL','STRING','FBD_TIMER','FBD_COUNTER','FBD_ONESHOT','SCALE','HL_LIMIT','SELECTABLE_NEGATE','SELECTED_SUMMER','RATE_LIMITER','MOVING_AVERAGE','MOVING_STD_DEV'}
        # Decorated structures explicitly describe stored fields, even where an
        # instruction's executable definition is unavailable. Never infer code.
        for data_node in c.findall('.//Data[@Format="Decorated"]'):
            for node in data_node.iter():
                if node.tag not in ('Structure','StructureMember'):continue
                dtype=node.get('DataType','')
                if dtype.upper() in builtin or dtype.lower() in self.udts:continue
                if any(m.get('Name')=='DATA' and m.get('Radix')=='ASCII' for m in node):
                    continue  # A custom string capacity cannot be inferred from visible text.
                schema=ET.Element('DataType',Name=dtype,Class='DecoratedDataOnly')
                members=ET.SubElement(schema,'Members')
                for member in node:
                    member_type=member.get('DataType','')
                    if member.get('Name')=='DATA' and member_type=='STRING':member_type='SINT'
                    dim=member.get('Dimensions','0') if member.tag=='ArrayMember' else '0'
                    ET.SubElement(members,'Member',Name=member.get('Name',''),DataType=member_type,Dimension=dim,Hidden='false')
                self.udts[dtype.lower()]=schema
                self.data_only_types.add(dtype)
        for tag in c.findall("./Tags/Tag"): self._tag(tag, "")
        for p in c.findall("./Programs/Program"):
            name = p.get("Name")
            self.programs[name] = {"main": p.get("MainRoutineName", ""), "class": p.get("Class", "Standard"),
                                   "disabled": p.get("Disabled", "false").lower() == "true",
                                   "use_as_folder": p.get('UseAsFolder') == 'true'}
            for tag in p.findall("./Tags/Tag"): self._tag(tag, name)
            for r in p.findall("./Routines/Routine"):
                routine = self._routine(r,name)
                self.routines[routine.key.lower()] = routine
        from .event_tasks import specification as event_specification
        for t in c.findall("./Tasks/Task"):
            self.tasks.append({"name": t.get("Name"), "type": t.get("Type", "").title(),
                               "rate": t.get("Rate", "10"), "priority": t.get("Priority", "10"),
                               "inhibited": t.get("InhibitTask", "false").lower() == "true",
                               "class": t.get("Class", "Standard"),
                               "programs": [p.get("Name") for p in t.findall("./ScheduledPrograms/ScheduledProgram")]})
            if self.tasks[-1]["type"]=="Event":self.tasks[-1]["event"]=event_specification(t)
        self.initial = {k: copy.deepcopy(t.value) for k, t in self.tags.items()}

    def _routine(self,r,scope,count=True):
        routine=Routine(scope,r.get('Name',''),r.get('Type','unknown'))
        if routine.kind=='ST':
            from .structured import Parser,walk
            content=r.find('STContent')
            if content is None:routine.problems.append('ST content is missing or protected');return routine
            # Native v35 exports wrap the CDATA of each numbered source line in
            # formatting newlines. Keep source indentation, but do not count
            # those XML wrappers as extra ST source lines.
            routine.lines=[{'number':line.get('Number',str(i)),'text':(line.text or '').strip('\r\n')} for i,line in enumerate(content.findall('Line'))]
            try:
                if any(line['number']!=str(i) for i,line in enumerate(routine.lines)):raise ModelError('ST line numbering must be sequential from zero')
                if any('\n' in line['text'] or '\r' in line['text'] for line in routine.lines):raise ModelError('Each numbered ST Line must contain one source line')
                routine.statements=Parser('\n'.join(line['text'] for line in routine.lines)).parse()
                for stmt in walk(routine.statements):
                    if count:self.st_counts[stmt.kind]+=1
                    if stmt.kind=='call':
                        op=stmt.op
                        routine.rungs.append({'number':str(stmt.line),'text':stmt.text,'comment':'','nodes':[op]})
                        if count:self.instruction_counts[op.name]+=1
                return routine
            except ModelError as e:routine.problems.append(str(e));return routine
        if routine.kind!='RLL':routine.problems.append(f'{routine.kind} logic is unsupported')
        if routine.kind=='RLL' and r.find('RLLContent') is None:routine.problems.append('RLL content is missing or protected')
        for rung in r.findall('./RLLContent/Rung'):
            number=rung.get('Number',str(len(routine.rungs)));text=rung.findtext('Text','')
            if rung.get('Type','N')!='N':routine.problems.append(f'Rung {number}: pending/test edit rung type')
            try:
                nodes=parse_rung(text)
                if not text.strip():raise ModelError('Empty or protected rung')
                routine.rungs.append({'number':number,'text':text,'comment':rung.findtext('Comment',''),'nodes':nodes})
                for op in operations(nodes):
                    if count:self.instruction_counts[op.name]+=1
                    if op.name in self.aois:
                        if len(op.args)!=1+len(self.aois[op.name].required):
                            routine.problems.append(f'Rung {number}: {op.name} requires instance plus required parameters in definition order')
                    elif op.name not in ARITIES:routine.problems.append(f'Rung {number}: unsupported {op.name}')
                    elif operand_problem(op):routine.problems.append(f'Rung {number}: '+operand_problem(op))
            except ModelError as e:routine.problems.append(f'Rung {number}: {e}')
        return routine

    def default(self, dtype, stack=()):
        upper = dtype.upper()
        if upper in INT_BITS or upper == "REAL": return 0.0 if upper == "REAL" else 0
        if upper == "BOOL": return False
        if upper in ("HL_LIMIT","SELECTABLE_NEGATE","SELECTED_SUMMER"):
            from .st_signal import default
            return default(upper)
        if upper in ("MOVING_AVERAGE","MOVING_STD_DEV"):
            from .st_moving import default
            return default(upper)
        if upper == "RATE_LIMITER":
            from .st_rate import default
            return default()
        if upper == "SCALE":
            from .st_scale import default
            return default()
        if upper == "FBD_ONESHOT":
            from .st_oneshot import default
            return default()
        if upper == "FBD_COUNTER":
            from .st_counter import default
            return default()
        if upper == "FBD_TIMER":
            from .st_timers import default
            return default()
        if upper == "TIMER": return {"PRE": 0, "ACC": 0, "EN": False, "TT": False, "DN": False}
        if upper == "COUNTER": return {"PRE": 0, "ACC": 0, "CU": False, "CD": False, "DN": False, "OV": False, "UN": False}
        if upper == "CONTROL":
            from .control_operations import default
            return default()
        capacity = self.string_capacity(dtype)
        if capacity is not None:return {'LEN':0,'DATA':[0]*capacity}
        if dtype.lower() in stack: raise ModelError("Recursive UDT")
        udt = self.udts.get(dtype.lower())
        if udt is None: raise ModelError(f"Unsupported data type {dtype}")
        value = {}
        for m in udt.findall("./Members/Member"):
            if m.get("Hidden", "false").lower() == "true": continue
            if m.get('DataType')=='BIT':
                target=next((x for x in udt.findall('./Members/Member') if x.get('Name')==m.get('Target')),None)
                if target is None or target.get('DataType') not in INT_BITS or not 0<=int(m.get('BitNumber','-1'))<INT_BITS[target.get('DataType')]:
                    raise ModelError('Invalid UDT BIT target/bit metadata')
                peers=[x for x in udt.findall('./Members/Member') if x.get('DataType')=='BIT' and x.get('Target')==m.get('Target') and x.get('BitNumber')==m.get('BitNumber')]
                if len(peers)!=1:raise ModelError('Overlaid UDT BIT aliases are unsupported')
                v=False
            else:
                try:v = self.default(m.get("DataType"), stack + (dtype.lower(),))
                except ModelError:
                    if m.get('AOILocal')!='true':raise
                    # Unsupported hidden storage does not invalidate unrelated
                    # exported public fields. Reading it still fails closed.
                    v=None
            value[m.get("Name")] = array_default(v, dimensions(m.get('Dimension','0')))
        return value

    def string_capacity(self, dtype):
        if dtype.upper()=='STRING':return 82
        udt=self.udts.get(dtype.lower())
        if udt is None:return None
        members={m.get('Name'):m for m in udt.findall('./Members/Member')}
        if set(members)=={'LEN','DATA'} and members['LEN'].get('DataType')=='DINT' and members['DATA'].get('DataType')=='SINT':
            dims=dimensions(members['DATA'].get('Dimension','0'))
            if len(dims)==1:return dims[0]
        return None

    def decorated(self, element, default):
        if element.tag in ("DataValue", "DataValueMember"):
            if isinstance(default,list) and element.get('Radix')=='ASCII':
                raw=element.get('Value')
                if raw is None:
                    content=(element.text or '').strip()
                    raw=content if content.startswith("'") else "'"+content+"'"
                values=ascii_bytes(raw)
                if len(values)>len(default):raise ModelError('ASCII data exceeds the backing array')
                return values+[None]*(len(default)-len(values))
            return coerce(literal(element.get("Value", "0")), element.get("DataType"))
        if element.tag in ("Structure", "StructureMember"):
            result = unknown_shape(default)
            if not isinstance(result, dict): raise ModelError("Structure data mismatch")
            for child in element:
                name = child.get("Name")
                if name not in result: raise ModelError(f"Unknown decorated member {name}")
                result[name] = self.decorated(child, result[name])
            return result
        if element.tag in ("Array", "ArrayMember"):
            result = unknown_shape(default)
            if not isinstance(result, list): raise ModelError("Array data mismatch")
            for child in element:
                idx = child.get("Index", "").strip("[]")
                if not re.fullmatch(r'\d+(?:,\d+){0,2}',idx):raise ModelError('Invalid decorated array index')
                parts=[int(x) for x in idx.split(',')];parent=result
                for i in parts[:-1]:
                    if not isinstance(parent,list) or i>=len(parent):raise ModelError('Decorated array index out of range')
                    parent=parent[i]
                i=parts[-1]
                if not isinstance(parent,list) or i>=len(parent):raise ModelError('Decorated array index out of range')
                if child.get("Value") is not None:
                    parent[i] = coerce(literal(child.get("Value")), element.get("DataType"))
                elif len(child): parent[i] = self.decorated(child[0], parent[i])
                else: raise ModelError("Missing array element data")
            return result
        raise ModelError(f"Unsupported decorated element {element.tag}")

    def _tag(self, e, scope):
        tag = Tag(e.get("Name"), e.get("DataType", ""), None, scope,
                  e.get("AliasFor", ""), e.get("Constant", "false").lower() == "true")
        tag.external_access=e.get('ExternalAccess','Read/Write')
        tag.tag_class=e.get('Class','Standard')
        try:
            if tag.alias: pass
            else:
                tag.value = self.default(tag.dtype)
                tag.value = array_default(tag.value,dimensions(e.get('Dimensions','')))
                d = e.find("./Data[@Format='Decorated']")
                if d is not None and len(d): tag.value = self.decorated(d[0], tag.value)
                elif self.string_capacity(tag.dtype) is not None and not isinstance(tag.value,list):
                    raw=e.findtext("./Data[@Format='L5K']",'')
                    match=re.fullmatch(r"\s*\[\s*(-?\d+)\s*,\s*('.*')\s*\]\s*",raw,re.S)
                    if match is None:raise ModelError('String import requires full L5K or Decorated backing data')
                    values=ascii_bytes(match[2]);capacity=self.string_capacity(tag.dtype)
                    if len(values)!=capacity:raise ModelError('String backing DATA size differs from declared capacity')
                    length=int(match[1])
                    if not 0<=length<=capacity:raise ModelError('String LEN outside backing DATA bounds')
                    tag.value={'LEN':length,'DATA':values}
                elif e.find("Data") is not None: raise ModelError("Initial data requires Decorated format")
                elif e.get("TagType", "Base") == "Base":
                    raise ModelError("Initial data missing; zero initialization was not assumed")
                if e.get("TagType", "Base") != "Base":
                    raise ModelError(f"{e.get('TagType')} tag semantics unsupported")
        except (ModelError, ValueError, TypeError, KeyError, IndexError) as ex: tag.problem = str(ex)
        self.tags[tag.key.lower()] = tag


class Memory:
    def __init__(self, project):
        self.project = project
        self.values = copy.deepcopy(project.initial)
        self.first_scan = True
        self._resolved = {}
        self.frames = {}
        self.validating = False
        self.structural = False

    def index(self,expr,scope):
        from .expressions import Expression
        parsed=Expression(expr)
        if self.structural and not re.fullmatch(r'\d+',expr.strip()):
            parsed.validate(self,scope,index=True);return 0
        return parsed.evaluate(self,scope,index=True)

    def resolve(self, ref, scope="", seen=()):
        ref = ref.strip()
        cache_key=(ref.lower(),scope.lower())
        if cache_key in self._resolved:return self._resolved[cache_key]
        if ref.lower() == "s:fs":
            if scope in self.frames:raise ModelError('S:FS inside AOIs is unsupported')
            return None, [], "BOOL"
        explicit = re.match(r"Program:([\w]+)\.(.+)", ref, re.I)
        if explicit and scope in self.frames:raise ModelError('AOI logic can access only its parameters and locals')
        if explicit: scope, ref = explicit.groups()
        m = re.match(r"([A-Za-z_][\w:]*)", ref)
        if not m: raise ModelError(f"Invalid tag reference {ref}")
        name = m[1]
        if scope in self.frames:
            binding=self.frames[scope].get(name.lower())
            if binding is None:raise ModelError(f'Unknown AOI parameter/local {ref}')
            target,owner=binding
            return self.resolve(target+ref[m.end():],owner,seen)
        key = f"Program:{scope}.{name}".lower()
        if key not in self.project.tags: key = name.lower()
        tag = self.project.tags.get(key)
        if tag is None: raise ModelError(f"Unknown tag {ref} in {scope or 'controller'}")
        if tag.problem: raise ModelError(f"{tag.key}: {tag.problem}")
        if key in seen: raise ModelError("Alias cycle")
        tail = ref[m.end():]
        if tag.alias: return self.resolve(tag.alias + tail, tag.scope, seen + (key,))
        parts = []
        dtype = tag.dtype
        value = self.values[key]
        while tail:
            if tail[0] == "[":
                end=1;depth=1
                while end<len(tail) and depth:
                    if tail[end]=='[':depth+=1
                    elif tail[end]==']':depth-=1
                    if depth:end+=1
                if end < 0: raise ModelError(f"Invalid subscript {ref}")
                if depth:raise ModelError('Unclosed array subscript')
                for expr in split_indices(tail[1:end]):
                    idx = self.index(expr,scope)
                    if isinstance(idx, bool) or not isinstance(idx, int): raise ModelError("Array subscript must be an integer")
                    if not isinstance(value, list) or not 0 <= idx < len(value): raise ModelError(f"Array index outside bounds: {ref}")
                    parts.append(idx);value=value[idx]
                tail = tail[end + 1:]
            elif tail[0] == ".":
                if tail.startswith('.['):
                    end=2;depth=1
                    while end<len(tail) and depth:
                        if tail[end]=='[':depth+=1
                        elif tail[end]==']':depth-=1
                        if depth:end+=1
                    if depth:raise ModelError('Unclosed indirect bit index')
                    bit=self.index(tail[2:end],scope);tail=tail[end+1:]
                    if dtype.upper() not in INT_BITS or isinstance(bit,bool) or not isinstance(bit,int) or not 0<=bit<INT_BITS[dtype.upper()] or tail:
                        raise ModelError('Invalid indirect integer bit selection')
                    parts.append(('bit',bit,INT_BITS[dtype.upper()],dtype.upper() not in UNSIGNED_BITS))
                    dtype,value='BOOL',None if value is None else bool((value>>bit)&1)
                    continue
                member = re.match(r"\.([\w]+)", tail)
                if not member: raise ModelError(f"Invalid member {ref}")
                item = member[1]
                tail = tail[member.end():]
                if dtype.upper() in INT_BITS and item.isdigit() and not isinstance(value,list):
                    bit = int(item)
                    if dtype.upper() not in INT_BITS or not 0 <= bit < INT_BITS[dtype.upper()] or tail:
                        raise ModelError(f"Invalid bit selection {ref}")
                    parts.append(("bit", bit, INT_BITS[dtype.upper()],dtype.upper() not in UNSIGNED_BITS))
                    dtype, value = "BOOL", None if value is None else bool((value >> bit) & 1)
                else:
                    if not isinstance(value, dict): raise ModelError(f"Not a structure: {ref}")
                    if dtype.upper() in ('FBD_TIMER','SCALE','HL_LIMIT','RATE_LIMITER','MOVING_AVERAGE','MOVING_STD_DEV'):
                        if dtype.upper() in ('MOVING_AVERAGE','MOVING_STD_DEV'):
                            from .st_moving import STATUS_BITS
                        elif dtype.upper()=='RATE_LIMITER':
                            from .st_rate import STATUS_BITS
                        elif dtype.upper()=='HL_LIMIT':
                            from .st_signal import STATUS_BITS
                        elif dtype.upper()=='SCALE':
                            from .st_scale import STATUS_BITS
                        else:
                            from .st_timers import STATUS_BITS
                        if item.lower() in STATUS_BITS:
                            if tail:raise ModelError(f'Invalid {dtype.upper()} status alias {ref}')
                            bit=STATUS_BITS[item.lower()];parts.extend(['Status',('bit',bit,32,True)])
                            dtype,value='BOOL',None if value['Status'] is None else bool((value['Status']>>bit)&1)
                            continue
                    actual = next((k for k in value if k.lower() == item.lower()), None)
                    if actual is None: raise ModelError(f"Unknown member {ref}")
                    if dtype.upper() in ("TIMER", "COUNTER", "CONTROL"):
                        dtype = "DINT" if actual in ("PRE", "ACC", "LEN", "POS") else "BOOL"
                    elif dtype.upper()=='FBD_TIMER':
                        from .st_timers import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='FBD_COUNTER':
                        from .st_counter import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='FBD_ONESHOT':
                        from .st_oneshot import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='SCALE':
                        from .st_scale import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper() in ('HL_LIMIT','SELECTABLE_NEGATE','SELECTED_SUMMER'):
                        from .st_signal import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('MOVING_AVERAGE','MOVING_STD_DEV'):
                        from .st_moving import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper()=='RATE_LIMITER':
                        from .st_rate import FIELDS
                        dtype=FIELDS[actual]
                    elif self.project.string_capacity(dtype) is not None:
                        dtype='DINT' if actual=='LEN' else 'SINT'
                    else:
                        udt = self.project.udts.get(dtype.lower())
                        member_e = next((e for e in udt.findall("./Members/Member") if e.get("Name").lower() == actual.lower()), None) if udt is not None else None
                        if member_e is None: raise ModelError(f"Unknown member type: {ref}")
                        dtype = 'BOOL' if member_e.get('DataType')=='BIT' else member_e.get("DataType")
                    parts.append(actual)
                    value = value[actual]
            else: raise ModelError(f"Invalid reference tail {tail}")
        result=(key,parts,dtype.upper())
        if re.fullmatch(r'(?:Program:[\w]+\.)?[A-Za-z_][\w:]*(?:\[\d+(?:,\d+)*\]|\.[\w]+)*',ref,re.I):
            self._resolved[cache_key]=result
        return result

    def read(self, ref, scope=""):
        try: return literal(ref)
        except ValueError: pass
        key, parts, dtype = self.resolve(ref, scope)
        if key is None: return self.first_scan
        if self.structural:
            value=self.values[key]
            for p in parts:
                if isinstance(p,tuple):return False
                value=value[p]
            dims=[]
            while isinstance(value,list):dims.append(len(value));value=value[0] if value else None
            return array_default(self.project.default(dtype),tuple(dims))
        value = self.values[key]
        for p in parts:
            if value is None:
                if self.validating and scope in self.frames:return self.project.default(dtype)
                raise ModelError(f'Unknown initial byte/value omitted by export: {ref}')
            value = bool((value >> p[1]) & 1) if isinstance(p, tuple) else value[p]
        if value is None:
            if self.validating and scope in self.frames:return self.project.default(dtype)
            raise ModelError(f'Unknown initial byte/value omitted by export: {ref}')
        return value

    def write(self, ref, value, scope=""):
        key, parts, dtype = self.check_writable(ref,scope)
        # A scalar write establishes a previously unknown value. Bit writes still
        # require the other bits in their backing integer to be known.
        old = self.at(key,parts) if not any(isinstance(p,tuple) for p in parts) else self.read(ref,scope)
        if isinstance(old,dict) and isinstance(value,str) and self.project.string_capacity(dtype) is not None:
            self.write_string(ref,value,scope);return
        if isinstance(old, (dict, list)): raise ModelError("Whole aggregate assignment unsupported")
        value = coerce(value, dtype)
        if not parts: self.values[key] = value
        else:
            parent = self.values
            slot = key
            for p in parts[:-1]: parent, slot = parent[slot], p
            last = parts[-1]
            if isinstance(last, tuple):
                n = parent[slot]
                mask = 1 << last[1]
                n = (n | mask) if value else (n & ~mask)
                # Interpret the modified packed integer as signed at its declared width.
                bits = last[2]
                n &= (1 << bits) - 1
                if last[3] and n >= 1 << (bits - 1): n -= 1 << bits
                parent[slot] = n
            else: parent[slot][last] = value

    def check_writable(self,ref,scope=''):
        if scope in self.frames and ref.strip().lower()=='enablein':raise ModelError('AOI EnableIn is read-only inside its logic')
        key,parts,dtype=self.resolve(ref,scope)
        if key is None or self.project.tags[key].constant:raise ModelError(f'Read-only destination {ref}')
        return key,parts,dtype

    def at(self,key,parts):
        value=self.values[key]
        for part in parts:value=value[part]
        return value

    def address(self,key,parts):
        ref=self.project.tags[key].key
        for p in parts:
            if isinstance(p,tuple):ref+='.'+str(p[1])
            elif isinstance(p,int):ref+='['+str(p)+']'
            else:ref+='.'+p
        return ref

    def store(self,key,parts,value):
        if self.project.tags[key].constant:raise ModelError('Constant destination')
        if not parts:self.values[key]=copy.deepcopy(value);return
        parent=self.at(key,parts[:-1]);parent[parts[-1]]=copy.deepcopy(value)

    def region(self,ref,count,scope=''):
        if isinstance(count,bool) or not isinstance(count,int) or not 0<=count<=100000:
            raise ModelError('Block length must be an integer in 0..100000')
        key,parts,dtype=self.resolve(ref,scope)
        if key is None or any(isinstance(p,tuple) for p in parts) or dtype=='BOOL':raise ModelError('Block operand cannot be a bit')
        value=self.values[key];candidate=None
        for i,part in enumerate(parts):
            if isinstance(value,list) and (i==0 or not isinstance(parts[i-1],int)):
                candidate=(parts[:i],value)
            value=value[part]
        if isinstance(value,list) and candidate is None:candidate=(parts,value)
        addresses=[]
        if candidate is not None:
            def flatten(path,obj):
                if isinstance(obj,list):
                    for i,v in enumerate(obj):flatten(path+[i],v)
                else:addresses.append(path)
            flatten(*candidate)
            start=next((i for i,p in enumerate(addresses) if p[:len(parts)]==parts),None)
            if start is None:raise ModelError('Block start does not address an array element')
            addresses=addresses[start:]
        else:addresses=[parts]
        if count>len(addresses):raise ModelError('Block operation exceeds the modeled array/member boundary')
        return key,addresses[:count],dtype

    def string(self,ref,scope=''):
        _,_,dtype=self.resolve(ref,scope)
        capacity=self.project.string_capacity(dtype)
        obj=self.read(ref,scope)
        if capacity is None or not isinstance(obj,dict):raise ModelError('String operand required')
        length=obj['LEN']
        if not isinstance(length,int) or not 0<=length<=capacity or len(obj['DATA'])!=capacity:raise ModelError('String LEN/DATA unknown or outside declared capacity')
        if any(x is None for x in obj['DATA'][:length]):raise ModelError('String contains unknown active DATA bytes')
        return bytes(x&255 for x in obj['DATA'][:length]).decode('latin-1')

    def write_string(self,ref,text,scope=''):
        key,parts,dtype=self.check_writable(ref,scope)
        capacity=self.project.string_capacity(dtype)
        if capacity is None:raise ModelError('String destination required')
        try:data=text.encode('latin-1')
        except UnicodeEncodeError as e:raise ModelError('Strings require single-byte characters') from e
        if len(data)>capacity:raise ModelError(f'String length {len(data)} exceeds capacity {capacity}')
        obj=self.read(ref,scope)
        # String instructions overwrite LEN and result bytes, preserving unused backing DATA.
        obj['LEN']=len(data)
        obj['DATA'][:len(data)]=[x if x<128 else x-256 for x in data]

    def leaves(self):
        result = []
        def walk(name, value, tag, local=False):
            if isinstance(value, dict):
                dtype=self.resolve(name)[2]
                if self.project.string_capacity(dtype) is not None:
                    try:result.append({'name':name,'type':dtype,'value':self.string(name),'constant':tag.constant,'alias':tag.alias,'problem':'','kind':'string'})
                    except ModelError as e:result.append({'name':name,'type':dtype,'value':None,'constant':True,'problem':str(e),'kind':'string'})
                definition=self.project.aois.get(dtype)
                locals={p.get('Name').lower() for p in definition.locals} if definition else set()
                for k, v in value.items(): walk(f"{name}.{k}", v, tag,local or k.lower() in locals)
            elif isinstance(value, list):
                def array(path,obj):
                    if isinstance(obj,list):
                        for i,v in enumerate(obj):array(path+[i],v)
                    else:walk(name+'['+','.join(str(i) for i in path)+']',obj,tag,local)
                array([],value)
            else:
                dtype=self.resolve(name)[2]
                result.append({"name": name, "type": dtype, "value": str(value) if value is not None and dtype in ('LINT','ULINT') else value,
                               'kind':'integer_text' if dtype in ('LINT','ULINT') else 'scalar',
                               'aoi_local':local,'unknown':value is None,
                               "constant": tag.constant or value is None, "alias": tag.alias,
                               "problem": 'Unknown backing byte omitted by export' if value is None else tag.problem})
        for tag in self.project.tags.values():
            if tag.problem:
                result.append({"name": tag.key, "type": tag.dtype, "value": None, "problem": tag.problem, "constant": True})
            else:
                try: walk(tag.key, self.read(tag.key), tag)
                except ModelError as e: result.append({"name": tag.key, "type": tag.dtype, "value": None, "problem": str(e), "constant": True})
        return result
