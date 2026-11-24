from __future__ import annotations

import copy
import hashlib
import math
import re
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import contextmanager
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
from .io_map import IOMap, local_backplane_route
from . import time_values


class ModelError(Exception):
    pass


class UnknownValueError(ModelError):
    """The project export omitted a required initial value."""


class ArrayBoundsError(ModelError):
    """An array subscript overflowed or selected outside existing storage."""


class SubscriptOverflowBoundsError(ArrayBoundsError):
    """DINT arithmetic overflowed while evaluating a subscript."""


class BlockExtentError(ModelError):
    """A valid start selected a region larger than its storage boundary."""


class StringLengthError(ModelError):
    """A known string LEN exceeds its declared DATA capacity."""


class StringCapacityError(ModelError):
    """A complete string result exceeds the destination DATA capacity."""


class StringPositionError(ModelError):
    """A string instruction consumed a known invalid position or range."""


class StringNumericRangeError(ModelError):
    """A numeric result parsed from text exceeds the destination type."""


@dataclass
class Op:
    name: str
    args: list[str]
    source_args: list[str] | None = field(default=None, compare=False, repr=False)


@dataclass
class Branch:
    paths: list[list]


ARITIES = {"XIC": 1, "XIO": 1, "OTE": 1, "OTL": 1, "OTU": 1,
           "ONS": 1, "OSR": 2, "OSF": 2, "AFI": 0, "NOP": 0,
           "EQU": 2, "NEQ": 2, "LES": 2, "LEQ": 2, "GRT": 2, "GEQ": 2, "ISNAN": 1, "ISINF": 1,
           "LIM": 3, "MOV": 2, "CLR": 1, "ADD": 3, "SUB": 3, "MUL": 3,
           "DIV": 3, "MOD": 3, "NEG": 2, "ABS": 2,
           "AND": 3, "OR": 3, "XOR": 3, "NOT": 2, "MVM": 3, "BTD": 5,
           "TON": 3, "TOF": 3, "RTO": 3, "CTU": 3, "CTD": 3,
           "RES": 1, "JSR": 2, "SBR": 0, "RET": 0,
           "COP": 3, "CPS": 3, "FLL": 3, "SIZE": 3, "CPT": 2,
           "JMP": 1, "LBL": 1, "TND": 0, "FOR": 5, "BRK": 0,
           "CONCAT": 3, "MID": 4, "DTOS": 2, "STOD": 2, "TRN": 2,
           'CMP':1,'MEQ':3,'GSV':4,'FIND':4,'INSERT':4,'DELETE':4,'BSL':4,'BSR':4,'FFL':5,'FFU':5,'LFL':5,'LFU':5,'SQO':6,'SQI':6,'SQL':5,'FRD':2,'TOD':2,'SWPB':3,
           'SQR':2,'LN':2,'LOG':2,'XPY':3,'DEG':2,'RAD':2,'SIN':2,'COS':2,'TAN':2,'ASN':2,'ACS':2,'ATN':2,'AVE':6,'STD':6,'SRT':5,'FSC':5,'FAL':6,'LOWER':2,'UPPER':2,'STOR':2,'RTOS':2,'EVENT':1,'UID':0,'UIE':0,'SSV':4,'MCR':0,'DTR':3,'FBC':9,'DDT':9,'PID':7,'ALMD':5,'ALMA':5,'IOT':1,'MSG':1}


ST_ONLY_ARITIES = {"TONR":1,"TOFR":1,"RTOR":1,"CTUD":1,"OSRI":1,"OSFI":1,"SCL":1,"HLL":1,"SNEG":1,"SSUM":1,"RLIM":1,"MAVE":3,"MSTD":2,"MAXC":1,"MINC":1,"LPF":1,"DFF":1,"JKFF":1,"RESD":1,"SETD":1,"UPDN":1,"INTG":1,"ESEL":1,"DERV":1,"FGEN":5,"DEDT":2,"PI":1,"BTDT":1,"MVMT":1}

ROUTINE_PARAMETER_LIMIT = 40
ALMD_OPERAND_COUNTS = (ARITIES['ALMD'], 7)


def operand_problem(op):
    if op.name=='JSR':
        if len(op.args)<2:return 'JSR requires routine name and literal input count'
        if not re.fullmatch(r'[A-Za-z_][\w]*',op.args[0]):return 'Invalid JSR routine name'
        if not re.fullmatch(r'\d+',op.args[1]):return 'JSR input count must be a decimal literal'
        count=int(op.args[1])
        if not 0<=count<=ROUTINE_PARAMETER_LIMIT or not 0<=len(op.args)-2-count<=ROUTINE_PARAMETER_LIMIT:
            return f'JSR requires 0..{ROUTINE_PARAMETER_LIMIT} input and 0..{ROUTINE_PARAMETER_LIMIT} return operands'
    elif op.name=='MAVE':
        if len(op.args) not in (2,3):return 'MAVE requires record, storage and optional weight array'
    elif op.name=='FGEN':
        if len(op.args) not in (3,5):return 'FGEN requires record/X1/Y1 and an optional complete X2/Y2 pair'
    elif op.name=='ALMD':
        if len(op.args) not in ALMD_OPERAND_COUNTS:return 'ALMD requires five operands or a legacy preset and accumulator pair'
    elif op.name in ('SBR','RET'):
        if len(op.args)>ROUTINE_PARAMETER_LIMIT:return f'{op.name} permits at most {ROUTINE_PARAMETER_LIMIT} operands'
    elif len(op.args)!=ARITIES.get(op.name,ST_ONLY_ARITIES.get(op.name)):return f'{op.name} operand count {len(op.args)} unsupported'
    return ''


def ladder_operand_problem(op, aois):
    if op.name in aois:
        if len(op.args) != 1 + len(aois[op.name].required):
            return f'{op.name} requires instance plus required parameters in definition order'
        return ''
    if op.name not in ARITIES:
        return f'unsupported {op.name}'
    return operand_problem(op)


def ascii_literal_end(text, start):
    """Return the exclusive end of a single-quoted Logix literal."""
    pos = start + 1
    while pos < len(text):
        if text[pos] == "'":
            return pos + 1
        pos += 2 if text[pos] == '$' else 1
    raise ModelError('Unclosed single-quoted ASCII literal')


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
            args = []
            start_arg = pos
            depth = brackets = 0
            while pos < len(text):
                char = text[pos]
                if char == "'":
                    pos = ascii_literal_end(text, pos)
                    continue
                if char == "(":
                    depth += 1
                elif char == ")":
                    if not depth:
                        break
                    depth -= 1
                elif char == "[":
                    brackets += 1
                elif char == "]":
                    brackets -= 1
                elif char == "," and not depth and not brackets:
                    args.append(text[start_arg:pos].strip())
                    start_arg = pos + 1
                pos += 1
            if pos >= len(text):
                raise ModelError(f"Unclosed {name}")
            tail = text[start_arg:pos].strip()
            if tail or args:
                args.append(tail)
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
PRIMITIVE_ARRAY_TYPES = frozenset(('BOOL', 'REAL', 'LREAL', *INT_BITS, *time_values.TYPES))
JOURNALED_CELL_TYPES = (type(None), bool, int, float, str, list, dict)
MAX_TRACKED_CELLS_PER_TAG = 64


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
    escapes={'$':36,"'":39,'T':9,'L':10,'I':10,'R':13,'P':12}
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
    if dtype in time_values.TYPES:
        try:
            return time_values.coerce(value, dtype)
        except ValueError as error:
            raise ModelError(str(error)) from error
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
    if dtype == "LREAL":
        result = float(value)
        if not __import__("math").isfinite(result):raise ModelError("Nonfinite LREAL")
        return result
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
    diagram: dict = field(default_factory=dict)

    @property
    def key(self): return f"{self.program}/{self.name}"


@dataclass(frozen=True)
class LocalAlias:
    parts: tuple[str | int | tuple[str, int, int, bool], ...]
    dtype: str

    @property
    def is_bit(self):
        return isinstance(self.parts[-1], tuple)

    @property
    def reference(self):
        suffix = []
        for part in self.parts[1:]:
            if isinstance(part, tuple):
                suffix.append(f'.{part[1]}')
            elif isinstance(part, int):
                suffix.append(f'[{part}]')
            else:
                suffix.append(f'.{part}')
        return self.parts[0] + ''.join(suffix)

    def parent(self, record):
        for part in self.parts[:-1]:
            record = record[part]
        return record

    def read(self, record):
        try:
            parent = self.parent(record)
            if self.is_bit:
                if parent is None:
                    return None
                if type(parent) is not int:
                    raise TypeError('Expected packed integer')
                return bool((parent >> self.parts[-1][1]) & 1)
            return parent[self.parts[-1]]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelError(f'AOI alias storage does not match {self.reference}') from error


LADDER_RECORD_TYPES = ('TIMER', 'COUNTER', 'CONTROL')


def validate_local_bit_alias(schema, member):
    """Qualify a named BOOL cell without exposing its hidden host as storage."""
    nodes = schema.findall('Members/Member')
    target = member.get('Target', '')
    hosts = [node for node in nodes if node.get('Name') == target]
    bit = member.get('BitNumber', '')
    if (len(hosts) != 1 or hosts[0].get('DataType') != 'SINT'
            or hosts[0].get('Hidden', 'false').lower() != 'true'
            or dimensions(hosts[0].get('Dimension', '0'))
            or dimensions(member.get('Dimension', '0')) or not re.fullmatch('[0-7]', bit)):
        raise ModelError('named BIT alias requires one scalar bit in a hidden SINT host')
    if any(node is not member and node.get('DataType') == 'BIT' and node.get('Target') == target
           and int(node.get('BitNumber', '-1')) == int(bit) for node in nodes):
        raise ModelError('overlapping named BIT alias targets are unsupported')


def local_alias_target(reference, locals_by_name, project):
    """Resolve a fixed path through declared local storage before reading tag data."""
    name = r'[A-Za-z_][A-Za-z_0-9]*'
    index = r'\[\s*[0-9]{1,6}(?:\s*,\s*[0-9]{1,6}){0,2}\s*\]'
    bit = r'[0-9]{1,6}'
    if not re.fullmatch(rf'{name}(?:\.{name}|{index})*(?:\.{bit})?', reference):
        raise ModelError('use a local tag, member, fixed array element or fixed bit')
    base, *selectors = re.findall(rf'{name}|{index}|{bit}', reference)
    local = locals_by_name.get(base.lower())
    if local is None or local.get('AliasFor') or local.get('TagType') == 'Alias':
        raise ModelError('target must start at a local tag')
    parts = [local.get('Name')]
    dtype = local.get('DataType', '').upper()
    dims = dimensions(local.get('Dimensions', '0'))
    for selector in selectors:
        if selector.startswith('['):
            indices = tuple(int(value) for value in selector[1:-1].split(','))
            if len(indices) > len(dims) or any(i >= size for i, size in zip(indices, dims)):
                raise ModelError('array index is outside the declared local dimensions')
            parts.extend(indices)
            dims = dims[len(indices):]
            continue
        if dims:
            raise ModelError('select a complete array element before its member')
        if selector.isdigit():
            if dtype not in ('SINT', 'INT', 'DINT') or int(selector) >= INT_BITS[dtype]:
                raise ModelError('bit must be within a local SINT, INT or DINT')
            parts.append(('bit', int(selector), INT_BITS[dtype], True))
            return LocalAlias(tuple(parts), 'BOOL')
        if dtype in LADDER_RECORD_TYPES:
            fields = project.default(dtype)
            field_name = selector.upper()
            if field_name not in fields:
                raise ModelError(f'{dtype} has no field {selector}')
            parts.append(field_name)
            dtype = 'BOOL' if type(fields[field_name]) is bool else 'DINT'
            continue
        schema = project.udts.get(dtype.lower())
        if schema is None or schema.get('Class') in ('AOI', 'DecoratedDataOnly'):
            raise ModelError('member must belong to a declared UDT, TIMER, COUNTER or CONTROL')
        member = next((entry for entry in schema.findall('Members/Member')
                       if entry.get('Name', '').lower() == selector.lower()), None)
        if member is None or member.get('Hidden', 'false').lower() == 'true':
            raise ModelError(f'unknown or hidden member {selector}')
        parts.append(member.get('Name'))
        dtype = member.get('DataType', '').upper()
        dims = dimensions(member.get('Dimension', '0'))
        if dtype == 'BIT':
            validate_local_bit_alias(schema, member)
            dtype = 'BOOL'
    if dims:
        raise ModelError('select one scalar value')
    return LocalAlias(tuple(parts), dtype)


@dataclass
class AddOn:
    name: str
    parameters: list
    locals: list
    routines: dict = field(default_factory=dict)
    modes: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    description: str = ''
    constant_inouts: set[str] = field(default_factory=set)
    local_aliases: dict[str, LocalAlias] = field(default_factory=dict)

    @property
    def required(self):
        return [p for p in self.parameters if p.get('Required','false').lower()=='true'
                and p.get('Name','').lower() not in ('enablein','enableout')]

    def register_local_alias(self, parameter, locals_by_name, project, used_targets):
        name = parameter.get('Name', '')
        usage = parameter.get('Usage')
        dtype = parameter.get('DataType', '').upper()
        try:
            if (usage not in ('Input', 'Output') or name.lower() in ('enablein', 'enableout')
                    or parameter.get('Constant', 'false').lower() == 'true'
                    or dtype not in ('BOOL', 'SINT', 'INT', 'DINT', 'REAL')
                    or dimensions(parameter.get('Dimensions', '0'))):
                raise ModelError('requires a matching scalar local target and an ordinary Input or Output')
            target = local_alias_target(parameter.get('AliasFor', '').strip(), locals_by_name, project)
            if target.dtype != dtype:
                raise ModelError(f'requires a matching scalar local target of type {dtype}')
        except (ModelError, ValueError) as error:
            self.problems.append(f'{name}: AOI alias {error}')
            return
        if (usage, target.parts) in used_targets:
            self.problems.append(f'{name}: AOI local target may have only one {usage} alias')
            return
        if any(other_usage == usage
               and (other == target.parts[:len(other)] or target.parts == other[:len(target.parts)])
               for other_usage, other in used_targets):
            self.problems.append(f'{name}: AOI {usage} alias overlaps an existing target')
            return
        used_targets.add((usage, target.parts))
        self.local_aliases[name.lower()] = target


class Project:
    def __init__(self, path):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.tags = {}
        self.message_configs = {}
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
        self.local_message_route = local_backplane_route(c)
        self.program_diagnostics = ProgramDiagnostics.from_source(root,c,self.sha256,
            self.program_configuration,self.executable_configuration,self.io_map)
        self.controller_configuration = ControllerConfiguration.from_controller(c, root)
        from .component_tracking import EmptyComponentTracking
        self.component_tracking = EmptyComponentTracking.from_source(root,c,self.sha256,
            aoi_empty=self.aoi_catalog.empty,io_empty=self.io_map.empty)
        declared_names = [key for key in c.attrib if key.rsplit('}', 1)[-1].casefold() == 'name']
        self.source_controller_name = c.get('Name') if declared_names == ['Name'] else None
        self.source_controller_settings = frozenset(name for name in (
            'TimeSlice', 'ShareUnusedTimeSlice', 'ProcessorType', 'MajorRev', 'MinorRev')
            if [key for key in c.attrib if key.rsplit('}', 1)[-1].casefold() == name.casefold()] == [name])
        self.name = c.get("Name", "Controller")
        self.version = c.get("MajorRev", root.get("SoftwareRevision", "unknown"))
        self.processor = c.get("ProcessorType", "unknown")
        self.minor_version = c.get('MinorRev','0')
        if self.version != "35": self.issues.append(f"Revision {self.version}: this prototype targets v35")
        for attr in ("PowerLossProgram", "PowerUpHandlerProgram"):
            if c.get(attr): self.issues.append(f"{attr} execution is unsupported")
        for d in c.findall("./DataTypes/DataType"):
            self.udts[d.get("Name").lower()] = d
        for d in c.findall('./AddOnInstructionDefinitions/AddOnInstructionDefinition'):
            aoi=AddOn(d.get('Name',''),list(d.findall('./Parameters/Parameter')),
                      list(d.findall('./LocalTags/LocalTag')), description=d.findtext('Description',''))
            self.aois[aoi.name.upper()]=aoi
            if d.get('Class','Standard')!='Standard':aoi.problems.append('Safety AOI execution is unsupported')
            for mode in ('Prescan','EnableInFalse','Postscan'):
                aoi.modes[mode]=d.get('Execute'+mode,'false').lower()=='true'
            names=set()
            schema=ET.Element('DataType',Name=aoi.name,Class='AOI')
            members=ET.SubElement(schema,'Members')
            from .integer_math import CONTROLLERS
            copied_types = {'BOOL', *INT_BITS, 'REAL'}
            qualified = self.version == '35' and self.processor.upper() in CONTROLLERS
            if qualified:copied_types.update(('LREAL', *time_values.TYPES))
            locals_by_name = {item.get('Name', '').lower(): item for item in aoi.locals}
            used_alias_targets = set()
            for item in aoi.parameters+aoi.locals:
                name=item.get('Name','');usage=item.get('Usage','Local')
                if not name or name.lower() in names:aoi.problems.append('Duplicate or missing parameter/local name')
                names.add(name.lower())
                if item.get('AliasFor') or item.get('TagType') == 'Alias':
                    if qualified and item in aoi.parameters:
                        aoi.register_local_alias(item, locals_by_name, self, used_alias_targets)
                    else:aoi.problems.append('Local aliases require v35 ControlLogix 5580 AOI Input or Output parameters')
                    continue
                if item.get('Constant','false').lower()=='true':
                    if usage=='InOut' and qualified:
                        aoi.constant_inouts.add(name.lower())
                    else:aoi.problems.append('Constant is supported only for v35 ControlLogix 5580 AOI InOut parameters')
                if usage not in ('Input','Output','InOut','Local'):aoi.problems.append('Unknown parameter usage')
                if usage=='InOut':
                    if item.get('Required','false').lower()!='true':aoi.problems.append('InOut must be required')
                    if item.get('CanBeNull','false').lower()=='true':aoi.problems.append('Nullable InOut is unsupported')
                    continue
                ET.SubElement(members,'Member',Name=name,DataType=item.get('DataType',''),
                              Dimension=item.get('Dimensions','0'),Hidden='false',AOILocal=str(usage=='Local').lower(),
                              ExternalAccess=item.get('ExternalAccess','None' if usage=='Local' else 'Read/Write'))
                if usage in ('Input','Output') and (item.get('DataType','').upper() not in copied_types
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
        builtin={'BOOL',*INT_BITS,*time_values.TYPES,'REAL','LREAL','PID','ALARM_DIGITAL','ALARM_ANALOG','TIMER','COUNTER','CONTROL','STRING','FBD_TIMER','FBD_COUNTER','FBD_ONESHOT','SCALE','HL_LIMIT','SELECTABLE_NEGATE','SELECTED_SUMMER','RATE_LIMITER','MOVING_AVERAGE','MOVING_STD_DEV','MAXIMUM_CAPTURE','MINIMUM_CAPTURE','FILTER_LOW_PASS','FLIP_FLOP_D','FLIP_FLOP_JK','DOMINANT_RESET','DOMINANT_SET','UP_DOWN_ACCUM','INTEGRATOR','SELECT_ENHANCED','DERIVATIVE','FUNCTION_GENERATOR','DEADTIME','PROP_INT','SELECT','MULTIPLEXER','FBD_BOOLEAN_AND','FBD_BOOLEAN_OR','FBD_BOOLEAN_NOT','FBD_BOOLEAN_XOR','FBD_MATH','FBD_MATH_ADVANCED','FBD_COMPARE','FBD_LIMIT','FBD_LOGICAL','FBD_CONVERT','FBD_MASK_EQUAL','FBD_MASKED_MOVE','FBD_TRUNCATE','FBD_BIT_FIELD_DISTRIBUTE'}
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
        self.program_fault_routines = self._program_fault_routines(c)
        self.fault_handler_routine = None
        self.fault_handler_routines = frozenset()
        try:
            self.fault_handler_routine, self.fault_handler_routines = self._controller_fault_routines(c)
        except ModelError as error:
            self.issues.append(str(error))
        if self.message_configs:
            from . import ladder_message
            ladder_message.initialize(self)
        self.initial = {k: copy.deepcopy(t.value) for k, t in self.tags.items()}
        from .pseudo_operands import initialize_ladder_operands
        initialize_ladder_operands(self)

    def _program_fault_routines(self, controller):
        from .integer_math import CONTROLLERS
        if self.version != '35' or self.processor.upper() not in CONTROLLERS:
            return {}
        assignments = {}
        for node in controller.findall('./Programs/Program'):
            name, target = node.get('Name'), node.get('FaultRoutineName')
            if not target or not self.program_configuration.type_attributes(name, source_sha256=self.sha256):
                continue
            names = self.executable_configuration.routine_names(name, source_sha256=self.sha256)
            if not names or target.casefold() not in {routine.casefold() for routine in names}:
                continue
            program = self.programs[name]
            main = self.routines.get(f"{name}/{program['main']}".lower())
            key = f'{name}/{target}'.lower()
            if main is not None and main.key.lower() != key and self.routines[key].kind == 'RLL':
                assignments[name] = key
        return assignments

    def _controller_fault_routines(self, controller):
        fields = [key for key in controller.attrib
                  if key.rsplit('}', 1)[-1].casefold() in ('majorfaultprogram', 'majorfaultprogramuid')]
        configured = [key for key in fields if controller.attrib[key]]
        if not configured:
            return None, frozenset()
        from .integer_math import CONTROLLERS
        if (configured != ['MajorFaultProgram']
                or any(key not in ('MajorFaultProgram', 'MajorFaultProgramUId') for key in fields)
                or self.version != '35' or self.processor.upper() not in CONTROLLERS):
            raise ModelError('Controller fault handler requires a named v35 ControlLogix 5580 source assignment')
        target = controller.attrib['MajorFaultProgram'].casefold()
        name = next((name for name in self.programs if name and name.casefold()==target), None)
        program = self.programs.get(name)
        if (not program or program['class'] != 'Standard' or program['use_as_folder']
                or not self.task_configuration.proves_unscheduled(name, source_sha256=self.sha256)
                or self.program_configuration.execution_disabled(name, source_sha256=self.sha256) is not False):
            raise ModelError('Controller fault handler requires an enabled, unscheduled Standard Program')
        node = next(item for item in controller.findall('./Programs/Program') if item.get('Name')==name)
        names = self.executable_configuration.routine_names(name, source_sha256=self.sha256)
        key = f"{name}/{program['main']}".casefold()
        routines = frozenset(f'{name}/{routine}'.casefold() for routine in names or ())
        if (key not in routines or any(self.routines[member].kind!='RLL' for member in routines)
                or node.get('FaultRoutineName') or node.findall('ChildPrograms/*')):
            raise ModelError('Controller fault handler requires ladder routines, a named main routine, '
                             'and no child Programs or Program fault routine')
        return key, routines

    def _routine(self,r,scope,count=True):
        routine=Routine(scope,r.get('Name',''),r.get('Type','unknown'))
        if routine.kind=='FBD':
            if scope.startswith('AOI:'):routine.problems.append('FBD within AOIs remains unsupported');return routine
            from .function_blocks import parse
            try:
                routine.diagram=parse(r)
                if count:
                    for node in routine.diagram['nodes']:
                        if node['kind']=='Block':self.instruction_counts[node['type']]+=1
            except ModelError as error:routine.problems.append(str(error))
            return routine
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
                    problem = ladder_operand_problem(op, self.aois)
                    if problem: routine.problems.append(f'Rung {number}: {problem}')
            except ModelError as e:routine.problems.append(f'Rung {number}: {e}')
        return routine

    def default(self, dtype, stack=()):
        upper = dtype.upper()
        if upper in time_values.TYPES:
            if not time_values.available(self):
                raise ModelError(f'{upper} storage requires the v35 ControlLogix 5580 profile')
            return 0
        if upper in INT_BITS or upper in ("REAL","LREAL"): return 0.0 if upper in ("REAL","LREAL") else 0
        if upper == "BOOL": return False
        if upper=='FBD_BIT_FIELD_DISTRIBUTE':
            from .st_bit_moves import default
            return default(upper)
        if upper=='FBD_TRUNCATE':
            from .fbd_convert import default
            return default(upper)
        if upper in ('FBD_LOGICAL','FBD_CONVERT','FBD_MASK_EQUAL','FBD_MASKED_MOVE'):
            from .fbd_bitwise import default
            return default(upper)
        if upper in ('FBD_COMPARE','FBD_LIMIT'):
            from .fbd_compare import default
            return default(upper)
        if upper in ('FBD_MATH','FBD_MATH_ADVANCED'):
            from .fbd_math import default
            return default(upper)
        if upper in ('FBD_BOOLEAN_AND','FBD_BOOLEAN_OR','FBD_BOOLEAN_NOT','FBD_BOOLEAN_XOR'):
            from .fbd_boolean import default
            return default(upper)
        if upper in ("HL_LIMIT","SELECTABLE_NEGATE","SELECTED_SUMMER"):
            from .st_signal import default
            return default(upper)
        if upper in ("FLIP_FLOP_D","FLIP_FLOP_JK","DOMINANT_RESET","DOMINANT_SET"):
            from .st_digital import default
            return default(upper)
        if upper in ("UP_DOWN_ACCUM","INTEGRATOR"):
            from .st_accumulate import default
            return default(upper)
        if upper == "SELECT_ENHANCED":
            from .st_select import default
            return default()
        if upper == "DERIVATIVE":
            from .st_derivative import default
            return default()
        if upper in ("FUNCTION_GENERATOR","DEADTIME"):
            from .st_curves import default
            return default(upper)
        if upper in ("SELECT","MULTIPLEXER"):
            from .fbd_select import default
            return default(upper)
        if upper == "PID":
            from .ladder_pid import default
            return default()
        if upper in ('ALARM_DIGITAL', 'ALARM_ANALOG'):
            from . import ladder_alarm, ladder_analog_alarm
            alarm_model = ladder_alarm if upper == 'ALARM_DIGITAL' else ladder_analog_alarm
            if not alarm_model.available(self):
                raise ModelError(f'{upper} storage requires the v35 ControlLogix 5580 profile')
            return alarm_model.default()
        if upper == "PROP_INT":
            from .st_pi import default
            return default()
        if upper == "FILTER_LOW_PASS":
            from .st_filter import default
            return default()
        if upper in ("MAXIMUM_CAPTURE","MINIMUM_CAPTURE"):
            from .st_capture import default
            return default()
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

    def _decorated_scalar(self, raw, dtype):
        if dtype.upper() in time_values.TYPES:
            self.default(dtype)
            return coerce(raw, dtype)
        return coerce(literal(raw if raw is not None else '0'), dtype)

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
            return self._decorated_scalar(element.get("Value"), element.get("DataType"))
        if element.tag in ("Structure", "StructureMember"):
            result = unknown_shape(default)
            if not isinstance(result, dict): raise ModelError("Structure data mismatch")
            definition = self.aois.get(element.get("DataType", "").upper())
            aliases = definition.local_aliases if definition else {}
            saved_alias_values = {}
            for child in element:
                name = child.get("Name")
                target = aliases.get((name or "").lower())
                if target is None:
                    if name not in result: raise ModelError(f"Unknown decorated member {name}")
                    result[name] = self.decorated(child, result[name])
                    continue
                if (child.tag != 'DataValueMember' or child.get('Value') is None
                        or child.get('DataType', '').upper() != target.dtype):
                    raise ModelError(f"Invalid decorated AOI alias {name}")
                value = self._decorated_scalar(child.get('Value'), target.dtype)
                if saved_alias_values.setdefault(target, value) != value:
                    raise ModelError(f"Conflicting decorated AOI values for {target.reference}")
            # A whole-word alias may supply storage for a saved bit alias.
            for target, value in sorted(saved_alias_values.items(), key=lambda entry: entry[0].is_bit):
                stored = target.read(result)
                if target.is_bit and stored is None:
                    raise ModelError(f"Saved AOI bit alias {target.reference} requires its backing word")
                if stored is not None and stored != value:
                    raise ModelError(f"Conflicting decorated AOI values for {target.reference}")
                if not target.is_bit:
                    target.parent(result)[target.parts[-1]] = value
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
                    parent[i] = self._decorated_scalar(child.get("Value"), element.get("DataType"))
                elif len(child): parent[i] = self.decorated(child[0], parent[i])
                else: raise ModelError("Missing array element data")
            return result
        raise ModelError(f"Unsupported decorated element {element.tag}")

    def _tag(self, e, scope):
        tag = Tag(e.get("Name"), e.get("DataType", ""), None, scope,
                  e.get("AliasFor", ""), e.get("Constant", "false").lower() == "true")
        tag.external_access=e.get('ExternalAccess','Read/Write')
        tag.tag_class=e.get('Class','Standard')
        self.message_configs.pop(tag.key.lower(), None)
        try:
            if tag.alias: pass
            elif tag.dtype.upper() == 'MESSAGE' and e.find("./Data[@Format='Message']") is not None:
                from . import ladder_message
                if e.get('TagType', 'Base') != 'Base':
                    raise ModelError('MESSAGE requires a base tag')
                config = ladder_message.from_tag(self, tag, e, dimensions(e.get('Dimensions','')))
                self.message_configs[tag.key.casefold()] = config
            else:
                dims = dimensions(e.get('Dimensions',''))
                tag.value = self.default(tag.dtype)
                alarm = tag.dtype.upper() in ('ALARM_DIGITAL', 'ALARM_ANALOG')
                if not alarm:
                    tag.value = array_default(tag.value,dims)
                d = e.find("./Data[@Format='Decorated']")
                if alarm:
                    from . import ladder_alarm, ladder_analog_alarm
                    if dims or tag.tag_class != 'Standard' or d is not None:
                        raise ModelError(f'{tag.dtype.upper()} requires scalar Standard Alarm data')
                    alarm_model = ladder_alarm if tag.dtype.upper() == 'ALARM_DIGITAL' else ladder_analog_alarm
                    tag.value = alarm_model.from_tag(e)
                elif d is not None and len(d):
                    data_type = d[0].get('DataType', '').upper()
                    if (tag.dtype.upper() in time_values.TYPES or data_type in time_values.TYPES) and data_type != tag.dtype.upper():
                        raise ModelError('Time/date tag and decorated data type must match')
                    tag.value = self.decorated(d[0], tag.value)
                elif self.string_capacity(tag.dtype) is not None and not dims:
                    capacity = self.string_capacity(tag.dtype)
                    string = e.find("./Data[@Format='String']")
                    if string is not None:
                        text = string.get('Length', '')
                        if not re.fullmatch(r'[0-9]{1,6}', text, re.ASCII) or len(string):
                            raise ModelError('String data requires a decimal Length and single-quoted text')
                        length = int(text)
                        values = ascii_bytes(string.text or '')
                        if not 0 <= length <= capacity or len(values) not in (length, capacity):
                            raise ModelError('String data does not match its Length or backing capacity')
                        values += [0] * (capacity - len(values))
                    else:
                        raw = e.findtext("./Data[@Format='L5K']", '')
                        match = re.fullmatch(r"\s*\[\s*(-?\d+)\s*,\s*('.*')\s*\]\s*", raw, re.S)
                        if match is None:
                            raise ModelError('String import requires String, full L5K or Decorated backing data')
                        values = ascii_bytes(match[2])
                        if len(values) != capacity:
                            raise ModelError('String backing DATA size differs from declared capacity')
                        length = int(match[1])
                        if not 0 <= length <= capacity:
                            raise ModelError('String LEN outside backing DATA bounds')
                    tag.value = {'LEN': length, 'DATA': values}
                elif e.find("Data") is not None: raise ModelError("Initial data requires Decorated format")
                elif e.get("TagType", "Base") == "Base":
                    raise ModelError("Initial data missing; zero initialization was not assumed")
                if e.get("TagType", "Base") != "Base":
                    raise ModelError(f"{e.get('TagType')} tag semantics unsupported")
        except (ModelError, ValueError, TypeError, KeyError, IndexError) as ex: tag.problem = str(ex)
        self.tags[tag.key.lower()] = tag


class Memory:
    def __init__(self, project, *, starting_values=None):
        self.project = project
        # Use store(), read() or at() for mutable access during a scan.
        self.values = copy.deepcopy(project.initial if starting_values is None else starting_values)
        self.value_order = {key: index for index, key in enumerate(self.values)}
        self._before = None
        self._before_cells = None
        self._store_undo = None
        self.message_cache = {}
        self.first_scan = True
        self.minor_fault = False
        self.on_minor_overflow = None
        self.rung_carry = None
        self.rung_negative = False
        self.rung_zero = False
        self.rung_overflow = False
        self._resolved = {}
        self._resolved_added = None
        self.frames = {}
        self.validating = False
        self.structural = False
        self.structural_constant_indices = False

    @contextmanager
    def track_values(self, *, rollback=False, track_resolutions=False):
        """Track changed values and optionally new canonical cache entries."""
        if self._before is not None:
            raise ModelError('Tag value tracking is already active')
        before = self._before = {}
        cells = self._before_cells = {}
        added = self._resolved_added = [] if self.project.aois or track_resolutions else None
        try:
            yield before, cells
        except Exception:
            rollback = True
            raise
        finally:
            self._before = None
            self._before_cells = None
            self._resolved_added = None
            if rollback:
                for key, paths in cells.items():
                    self._restore_cells(self.values[key], paths.items())
                self.values.update(before)
                if added is not None:
                    for key in added:
                        self._resolved.pop(key, None)

    @staticmethod
    def _restore_cells(root, cells):
        for path, original in cells:
            parent = root
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = original

    def _remember(self, key):
        if self._before is not None and key not in self._before:
            value = self.values[key]
            # A declared flat primitive array contains only immutable cells.
            # Multidimensional arrays still contain mutable row lists.
            if (type(value) is list and self.project.tags[key].dtype in PRIMITIVE_ARRAY_TYPES
                    and (not value or not isinstance(value[0], list))):
                snapshot = value.copy()
            else:
                snapshot = copy.deepcopy(value)
            self._restore_cells(snapshot, self._before_cells.pop(key, {}).items())
            self._before[key] = snapshot

    def _remember_store(self, key, parts, parent, slot, value):
        if self._before is None or key in self._before:
            return
        if parts and type(value) in JOURNALED_CELL_TYPES and (isinstance(parent, list) or slot in parent):
            old = parent[slot]
            if type(old) in JOURNALED_CELL_TYPES:
                cells = self._before_cells.setdefault(key, {})
                path = tuple(parts)
                if path in cells or any(path[:length] in cells for length in range(1, len(path))):
                    return
                compound = isinstance(old, (list, dict))
                descendants = [saved for saved in cells if saved[:len(path)] == path] if compound else []
                if len(cells) - len(descendants) < MAX_TRACKED_CELLS_PER_TAG:
                    # Local store rollback can put the old record back into
                    # live storage. Keep its snapshot detached from that record.
                    original = copy.deepcopy(old) if compound else old
                    if descendants:
                        self._restore_cells(original, ((saved[len(path):], cells[saved]) for saved in descendants))
                        for saved in descendants:
                            del cells[saved]
                    cells[path] = original
                    return
        self._remember(key)

    @contextmanager
    def atomic_stores(self):
        """Undo a short sequence of stores without undoing preceding scan work."""
        if self._store_undo is not None:
            raise ModelError('Atomic stores are already active')
        self._store_undo = []
        try:
            yield
        except Exception:
            for container, slot, value in reversed(self._store_undo):
                container[slot] = value
            raise
        finally:
            self._store_undo = None

    def index(self,expr,scope):
        from .expressions import parse_subscript
        parsed=parse_subscript(expr)
        if parsed.tree[0]=='ref':
            from .integer_math import CONTROLLERS
            key,parts,dtype=self.resolve(parsed.tree[1],scope)
            if (dtype in INT_BITS and dtype not in ('SINT','INT','DINT') and
                    self.project.version=='35' and self.project.processor.upper() in CONTROLLERS):
                if isinstance(self.at(key,parts),(list,dict)):
                    raise ModelError('Array index requires one integer scalar tag')
                if self.structural:return 0
                value=self.read(parsed.tree[1],scope)
                if type(value) is not int:raise ModelError('Array index tag requires a known integer')
                return coerce(value,dtype)
        if self.structural:
            from .st_literals import DINT_RADIX_TOKEN
            token=expr.strip()
            if re.fullmatch(r'\d+',token) or DINT_RADIX_TOKEN.fullmatch(token):
                return parsed.evaluate(self,scope,index=True)
            if not self.structural_constant_indices or parsed.refs:
                parsed.validate(self,scope,index=True);return 0
        return parsed.evaluate(self,scope,index=True)

    def _array_index(self,expr,scope):
        from .expressions import SubscriptOverflowError
        try:
            return self.index(expr,scope)
        except SubscriptOverflowError as error:
            raise SubscriptOverflowBoundsError(str(error)) from error

    def bound_suffix(self,suffix,scope):
        """Evaluate caller subscripts before following alias or AOI bindings."""
        out=[];pos=0
        while pos<len(suffix):
            start=suffix.find('[',pos)
            if start<0:out.append(suffix[pos:]);break
            out.append(suffix[pos:start]);end=start+1;depth=1
            while end<len(suffix) and depth:
                if suffix[end]=='[':depth+=1
                elif suffix[end]==']':depth-=1
                end+=1
            if depth:raise ModelError('Unclosed AOI array subscript')
            index=self.index if suffix[start-1:start]=='.' else self._array_index
            values=[index(expr,scope) for expr in split_indices(suffix[start+1:end-1])]
            if any(type(value) is not int for value in values):raise ModelError('AOI array subscript must be an integer')
            out.append('['+','.join(map(str,values))+']');pos=end
        return ''.join(out)

    def resolve(self, ref, scope="", seen=()):
        ref = ref.strip()
        scope_key = scope.lower()
        cache_key = (ref.lower(), scope_key)
        # Frame bindings can change between calls. Cache their resolved
        # canonical targets only, even if the frame is currently absent.
        cacheable = not scope_key.startswith('@aoi:')
        if cacheable and cache_key in self._resolved:
            return self._resolved[cache_key]
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
            return self.resolve(target+self.bound_suffix(ref[m.end():],scope),owner,seen)
        key = f"Program:{scope}.{name}".lower()
        if key not in self.project.tags: key = name.lower()
        tag = self.project.tags.get(key)
        if tag is None: raise ModelError(f"Unknown tag {ref} in {scope or 'controller'}")
        if tag.problem: raise ModelError(f"{tag.key}: {tag.problem}")
        if key in seen: raise ModelError("Alias cycle")
        tail = ref[m.end():]
        if tag.alias:
            # Caller suffixes use the caller's namespace; indices authored in
            # AliasFor itself still belong to the alias declaration's scope.
            return self.resolve(tag.alias + self.bound_suffix(tail,scope),tag.scope,seen+(key,))
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
                    idx = self._array_index(expr,scope)
                    if isinstance(idx, bool) or not isinstance(idx, int): raise ModelError("Array subscript must be an integer")
                    if not isinstance(value, list): raise ModelError(f"Array index outside bounds: {ref}")
                    if not 0 <= idx < len(value): raise ArrayBoundsError(f"Array index outside bounds: {ref}")
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
                    if dtype.upper() in ('FBD_TIMER','SCALE','HL_LIMIT','RATE_LIMITER','MOVING_AVERAGE','MOVING_STD_DEV','FILTER_LOW_PASS','INTEGRATOR','SELECT_ENHANCED','DERIVATIVE','FUNCTION_GENERATOR','DEADTIME','PROP_INT','MULTIPLEXER','ALARM_DIGITAL','ALARM_ANALOG'):
                        if dtype.upper()=='ALARM_ANALOG':
                            from .ladder_analog_alarm import STATUS_BITS
                        elif dtype.upper()=='ALARM_DIGITAL':
                            from .ladder_alarm import STATUS_BITS
                        elif dtype.upper()=='MULTIPLEXER':
                            from .fbd_select import STATUS_BITS
                        elif dtype.upper()=='PROP_INT':
                            from .st_pi import STATUS_BITS
                        elif dtype.upper() in ('FUNCTION_GENERATOR','DEADTIME'):
                            from .st_curves import STATUS_BITS as CURVE_STATUS_BITS
                            STATUS_BITS=CURVE_STATUS_BITS[dtype.upper()]
                        elif dtype.upper()=='SELECT_ENHANCED':
                            from .st_select import STATUS_BITS
                        elif dtype.upper()=='DERIVATIVE':
                            from .st_derivative import STATUS_BITS
                        elif dtype.upper()=='INTEGRATOR':
                            from .st_accumulate import STATUS_BITS
                        elif dtype.upper()=='FILTER_LOW_PASS':
                            from .st_filter import STATUS_BITS
                        elif dtype.upper() in ('MOVING_AVERAGE','MOVING_STD_DEV'):
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
                    if dtype.upper() == 'PID':
                        from .ladder_pid import ALIASES
                        if item.lower() in ALIASES:
                            if tail:raise ModelError('Invalid PID bit alias')
                            bit=ALIASES[item.lower()];parts.extend(['CTL',('bit',bit,32,True)])
                            dtype,value='BOOL',None if value['CTL'] is None else bool((value['CTL']>>bit)&1)
                            continue
                    if dtype.upper() == 'MESSAGE' and not parts and key in self.project.message_configs:
                        from .ladder_message import STATUS_BITS
                        bit = STATUS_BITS.get(item.upper())
                        if bit is not None:
                            if tail: raise ModelError(f'Invalid MESSAGE status alias {ref}')
                            parts.extend(['FLAGS', ('bit', bit, 16, True)])
                            dtype, value = 'BOOL', bool((value['FLAGS'] >> bit) & 1)
                            continue
                    definition = self.project.aois.get(dtype.upper())
                    alias = definition.local_aliases.get(item.lower()) if definition else None
                    if alias is not None:
                        value = alias.read(value)
                        dtype = alias.dtype
                        parts.extend(alias.parts)
                        continue
                    actual = next((k for k in value if k.lower() == item.lower()), None)
                    if actual is None: raise ModelError(f"Unknown member {ref}")
                    if dtype.upper() in LADDER_RECORD_TYPES:
                        dtype = "DINT" if actual in ("PRE", "ACC", "LEN", "POS") else "BOOL"
                    elif dtype.upper()=='FBD_TIMER':
                        from .st_timers import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='FBD_COUNTER':
                        from .st_counter import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='FBD_BIT_FIELD_DISTRIBUTE':
                        from .st_bit_moves import SCHEMAS
                        dtype=SCHEMAS['FBD_BIT_FIELD_DISTRIBUTE'][actual]
                    elif dtype.upper()=='FBD_TRUNCATE':
                        from .fbd_convert import SCHEMAS
                        dtype=SCHEMAS['FBD_TRUNCATE'][actual]
                    elif dtype.upper() in ('FBD_LOGICAL','FBD_CONVERT','FBD_MASK_EQUAL','FBD_MASKED_MOVE'):
                        from .fbd_bitwise import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('FBD_COMPARE','FBD_LIMIT'):
                        from .fbd_compare import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('FBD_MATH','FBD_MATH_ADVANCED'):
                        from .fbd_math import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('FBD_BOOLEAN_AND','FBD_BOOLEAN_OR','FBD_BOOLEAN_NOT','FBD_BOOLEAN_XOR'):
                        from .fbd_boolean import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper()=='FBD_ONESHOT':
                        from .st_oneshot import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='SCALE':
                        from .st_scale import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper() in ('HL_LIMIT','SELECTABLE_NEGATE','SELECTED_SUMMER'):
                        from .st_signal import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('FLIP_FLOP_D','FLIP_FLOP_JK','DOMINANT_RESET','DOMINANT_SET'):
                        from .st_digital import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('UP_DOWN_ACCUM','INTEGRATOR'):
                        from .st_accumulate import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper() in ('SELECT','MULTIPLEXER'):
                        from .fbd_select import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper()=='PID':
                        from .ladder_pid import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='ALARM_DIGITAL':
                        from .ladder_alarm import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='ALARM_ANALOG':
                        from .ladder_analog_alarm import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='MESSAGE' and not parts and key in self.project.message_configs:
                        from .ladder_message import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='PROP_INT':
                        from .st_pi import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper() in ('FUNCTION_GENERATOR','DEADTIME'):
                        from .st_curves import SCHEMAS
                        dtype=SCHEMAS[dtype.upper()][actual]
                    elif dtype.upper()=='SELECT_ENHANCED':
                        from .st_select import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='DERIVATIVE':
                        from .st_derivative import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper()=='FILTER_LOW_PASS':
                        from .st_filter import FIELDS
                        dtype=FIELDS[actual]
                    elif dtype.upper() in ('MAXIMUM_CAPTURE','MINIMUM_CAPTURE'):
                        from .st_capture import FIELDS
                        dtype=FIELDS[actual]
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
        if cacheable and re.fullmatch(r'(?:Program:[\w]+\.)?[A-Za-z_][\w:]*(?:\[\d+(?:,\d+)*\]|\.[\w]+)*',ref,re.I):
            self._resolved[cache_key] = result
            if self._resolved_added is not None:
                self._resolved_added.append(cache_key)
        return result

    def read(self, ref, scope="", *, allow_time=False, mutable=True):
        try: return literal(ref)
        except ValueError: pass
        key, parts, dtype = self.resolve(ref, scope)
        if key is None: return self.first_scan
        if dtype in time_values.TYPES and not allow_time:
            raise ModelError('Time/date operand requires a qualified same-type ladder instruction')
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
                raise UnknownValueError(f'Unknown initial byte/value omitted by export: {ref}')
            value = bool((value >> p[1]) & 1) if isinstance(p, tuple) else value[p]
        if value is None:
            if self.validating and scope in self.frames:return self.project.default(dtype)
            raise UnknownValueError(f'Unknown initial byte/value omitted by export: {ref}')
        # Instruction handlers can edit returned records and arrays in place.
        if mutable and isinstance(value, (dict, list)):
            self._remember(key)
        if not parts and key in self.project.message_configs:
            from .ladder_message import status_members
            return {**value, **status_members(value['FLAGS'])}
        return value

    def write(self, ref, value, scope="", *, math_result=False):
        key, parts, dtype = self.check_writable(ref,scope)
        # A scalar write establishes a previously unknown value. Bit writes still
        # require the other bits in their backing integer to be known.
        old = self.at(key,parts,mutable=False) if not any(isinstance(p,tuple) for p in parts) else self.read(ref,scope)
        if isinstance(old,dict) and isinstance(value,str) and self.project.string_capacity(dtype) is not None:
            self.write_string(ref,value,scope);return
        if isinstance(old, (dict, list)): raise ModelError("Whole aggregate assignment unsupported")
        value = coerce(value, dtype)
        if parts and isinstance(parts[-1], tuple):
            bit = parts[-1]
            parts = parts[:-1]
            word = self.at(key, parts)
            mask = 1 << bit[1]
            word = (word | mask) if value else (word & ~mask)
            # Interpret the modified packed integer as signed at its declared width.
            width = bit[2]
            value = word & ((1 << width) - 1)
            if bit[3] and value >= 1 << (width - 1): value -= 1 << width
        self.store(key, parts, value)
        if math_result and (dtype in INT_BITS or dtype in ('REAL', 'LREAL')):
            self.record_math_result(value)

    def write_floating_exception(self, ref, value, scope="", *, math_result=False):
        """Store an instruction-generated NaN or infinity in a floating scalar."""
        key, parts, dtype = self.check_writable(ref, scope)
        if (dtype not in ('REAL', 'LREAL') or isinstance(self.at(key, parts), (dict, list))
                or type(value) is not float or math.isfinite(value)):
            raise ModelError('A floating exception requires one writable REAL or LREAL scalar')
        self.store(key, parts, value)
        if math_result:
            self.record_math_result(value)

    def record_math_result(self, value, *, overflow=False):
        """Expose a completed numeric store to the current ladder rung."""
        if self.rung_carry is not None:
            self.rung_negative = value is not None and value < 0
            self.rung_zero = value == 0
            self.record_overflow(overflow)

    def record_overflow(self, overflow):
        if self.rung_carry is not None:
            self.rung_overflow = overflow
            if overflow and self.project.controller_configuration.report_minor_overflow is True:
                self.report_minor_overflow()

    def report_minor_overflow(self):
        self.minor_fault = True
        if self.on_minor_overflow is not None:
            self.on_minor_overflow()

    def check_writable(self,ref,scope=''):
        if scope in self.frames:
            name = ref.strip().partition('.')[0].partition('[')[0].lower()
            if name == 'enablein':raise ModelError('AOI EnableIn is read-only inside its logic')
            if name in self.frames[scope]:
                _, _, instance_type = self.resolve(scope.removeprefix('@AOI:'))
                if name in self.project.aois[instance_type].constant_inouts:
                    raise ModelError(f'Constant AOI InOut is read-only: {ref}')
        key,parts,dtype=self.resolve(ref,scope)
        if key is None or self.project.tags[key].constant:raise ModelError(f'Read-only destination {ref}')
        return key,parts,dtype

    def at(self,key,parts,*,mutable=True):
        """Access a resolved value and track aggregates that may be edited."""
        value=self.values[key]
        for part in parts:value=value[part]
        if mutable and isinstance(value, (dict, list)):
            self._remember(key)
        return value

    def read_cells(self, key, paths):
        """Read resolved cells without tracking aggregates for mutation."""
        for path in paths:
            value = self.at(key, path, mutable=False)
            if value is None:
                value = self.read(self.address(key, path), mutable=False)
            yield value

    def address(self,key,parts):
        ref=self.project.tags[key].key
        for p in parts:
            if isinstance(p,tuple):ref+='.'+str(p[1])
            elif isinstance(p,int):ref+='['+str(p)+']'
            else:ref+='.'+p
        return ref

    def store(self,key,parts,value):
        if self.project.tags[key].constant:raise ModelError('Constant destination')
        parent, slot = (self.at(key, parts[:-1], mutable=False), parts[-1]) if parts else (self.values, key)
        self._remember_store(key, parts, parent, slot, value)
        if len(parts) == 1 and parts[0] == 'FLAGS' and key in self.project.message_configs:
            from .ladder_message import CACHE_MASK, TO_MASK
            writable = TO_MASK
            if self.project.message_configs[key].connected:
                writable |= CACHE_MASK
            value = (parent['FLAGS'] & ~writable) | (coerce(value, 'INT') & writable)
            if not value & CACHE_MASK and key in self.message_cache:
                if self._store_undo is not None:
                    self._store_undo.append((self.message_cache, key, self.message_cache[key]))
                del self.message_cache[key]
        if self._store_undo is not None:
            self._store_undo.append((parent, slot, parent[slot]))
        parent[slot] = copy.deepcopy(value)

    def region(self,ref,count,scope='',*,offset=0,minimum_extent=0):
        """Return the requested addresses after checking the required extent."""
        if isinstance(count,bool) or not isinstance(count,int) or not 0<=count<=100000:
            raise ModelError('Block length must be an integer in 0..100000')
        if type(offset) is not int or offset < 0:
            raise ModelError('Block offset must be a nonnegative integer')
        if type(minimum_extent) is not int or minimum_extent < 0:
            raise ModelError('Block extent must be a nonnegative integer')
        required = max(offset + count, minimum_extent)
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
            base, array = candidate
            if array and not isinstance(array[0], list):
                # A selected one-dimensional element already identifies the
                # starting index, so only generate paths in the requested window.
                selection = parts[len(base):]
                if len(selection) > 1:
                    raise ModelError('Block start does not address an array element')
                start = selection[0] if selection else 0
                if start + required > len(array):
                    raise BlockExtentError('Block operation exceeds the modeled array/member boundary')
                first = start + offset
                return key, [base + [index] for index in range(first, first + count)], dtype
            def flatten(path,obj):
                if isinstance(obj,list):
                    for i,v in enumerate(obj):flatten(path+[i],v)
                else:addresses.append(path)
            flatten(*candidate)
            start=next((i for i,p in enumerate(addresses) if p[:len(parts)]==parts),None)
            if start is None:raise ModelError('Block start does not address an array element')
        else:
            addresses, start = [parts], 0
        if start + required > len(addresses):
            raise BlockExtentError('Block operation exceeds the modeled array/member boundary')
        first = start + offset
        return key,addresses[first:first + count],dtype

    def _string_data(self, ref, scope, *, unsigned_length=False):
        _,_,dtype=self.resolve(ref,scope)
        capacity=self.project.string_capacity(dtype)
        obj=self.read(ref,scope,mutable=False)
        if capacity is None or not isinstance(obj,dict):raise ModelError('String operand required')
        length=obj['LEN']
        if unsigned_length and type(length) is int and length < 0:
            length += 1 << 32
        if type(length) is int and length > capacity and isinstance(obj['DATA'], list) and len(obj['DATA']) == capacity:
            raise StringLengthError(f'String LEN {length} exceeds DATA capacity {capacity} for {ref}')
        if not isinstance(length,int) or not 0<=length<=capacity or len(obj['DATA'])!=capacity:raise ModelError('String LEN/DATA unknown or outside declared capacity')
        return obj['DATA'], length

    @staticmethod
    def _decode_string_data(active):
        if any(x is None for x in active):raise ModelError('String contains unknown active DATA bytes')
        return bytes(x&255 for x in active).decode('latin-1')

    def string(self,ref,scope='',*,limit=None,destination=None):
        data, length = self._string_data(ref, scope)
        result_length = length if limit is None else min(length, limit)
        if destination is not None:
            self._check_string_result_size(destination, result_length, scope)
        return self._decode_string_data(data[:result_length])

    def string_known_prefix(self, ref, scope=''):
        """Read consecutive known bytes and report whether they cover LEN."""
        data, length = self._string_data(ref, scope)
        try:
            end = data.index(None, 0, length)
        except ValueError:
            end = length
        return self._decode_string_data(data[:end]), end == length

    def compare_strings(self, refs, literals, scope, *, lengths_first, unsigned_length):
        """Compare only bytes that can affect a standalone ladder relation."""
        captured = []
        for ref, text in zip(refs, literals, strict=True):
            if text is None:
                captured.append(self._string_data(ref, scope, unsigned_length=unsigned_length))
            else:
                captured.append((text.encode('latin-1'), len(text)))

        (left_data, left_length), (right_data, right_length) = captured
        length_difference = left_length - right_length
        if lengths_first and length_difference:
            return length_difference
        for index in range(min(left_length, right_length)):
            left, right = left_data[index], right_data[index]
            if left is None or right is None:
                raise ModelError('String contains unknown active DATA bytes')
            difference = (left & 255) - (right & 255)
            if difference:
                return difference
        return length_difference

    def concatenate_strings(self, left, right, limit, scope=''):
        """Validate both lengths before reading the bytes that fit."""
        left_data, left_length = self._string_data(left, scope)
        right_data, right_length = self._string_data(right, scope)
        left_count = min(left_length, limit)
        right_count = min(right_length, limit - left_count)
        text = self._decode_string_data(left_data[:left_count] + right_data[:right_count])
        return text, left_length + right_length > limit

    def insert_strings(self, base, addition, start, destination, scope=''):
        """Check insertion extent and capacity before copying active bytes."""
        base_data, base_length = self._string_data(base, scope)
        if start > base_length + 1:
            raise ModelError('INSERT start exceeds the modeled active string boundary')
        added_data, added_length = self._string_data(addition, scope)
        self._check_string_result_size(destination, base_length + added_length, scope)
        first = start - 1
        return self._decode_string_data(base_data[:first] + added_data[:added_length] + base_data[first:base_length])

    def string_prefix(self, ref, limit, scope=''):
        """Read the copied bytes and determine whether active data was truncated."""
        data, length = self._string_data(ref, scope)
        return self._decode_string_data(data[:min(length, limit)]), length > limit

    def string_slice(self, ref, start, count, scope='', *, destination=None):
        """Read an exact one-based window within both declared DATA and active LEN."""
        data, length = self._string_data(ref, scope)
        first = start - 1
        end = first + count
        if not 1 <= start <= len(data) or count < 0 or end > length:
            raise StringPositionError('MID range exceeds source LEN or declared DATA bounds')
        if destination is not None:
            self._check_string_result_size(destination, count, scope)
        return self._decode_string_data(data[first:end])

    def string_find(self, ref, search_ref, start, scope='', *, allow_partial=False):
        """Return the first match when the available source bytes determine it."""
        data, length = self._string_data(ref, scope)
        if not 1 <= start <= len(data):
            raise StringPositionError('FIND start must be 1..source DATA capacity')
        search_data, search_length = self._string_data(search_ref, scope)
        if not length:
            if not allow_partial:
                self._decode_string_data(search_data[:search_length])
            raise StringPositionError('FIND requires nonempty source and search strings in this model')
        search = self._decode_string_data(search_data[:search_length])
        if not search:
            raise ModelError('FIND requires nonempty source and search strings in this model')
        first = start - 1
        end = length
        if allow_partial:
            if length - first < len(search):
                return 0
            try:
                end = data.index(None, first, length)
            except ValueError:
                pass

        suffix = self._decode_string_data(data[first:end])
        position = suffix.find(search)
        if position >= 0:
            return start + position
        if end < length:
            first_unchecked = max(first, end - len(search) + 1)
            return self._find_with_unknown_data(data, first_unchecked, length, search)
        return 0

    @staticmethod
    def _find_with_unknown_data(data, first, length, search):
        # Each bit marks a prefix of the needle that could end at the current byte.
        # Advance those prefixes and start a new one at every source position.
        needle = search.encode('latin-1')
        mask_size = (len(needle) + 7) // 8
        packed = {byte: bytearray(mask_size) for byte in set(needle)}
        for index, byte in enumerate(needle):
            packed[byte][index // 8] |= 1 << (index % 8)
        byte_masks = {byte: int.from_bytes(mask, 'little') for byte, mask in packed.items()}
        match_bit = 1 << (len(needle) - 1)
        unknown_mask = (match_bit << 1) - 1
        possible = 0
        last_unknown = -1
        for index in range(first, length):
            byte = data[index]
            if byte is None:
                last_unknown = index
                mask = unknown_mask
            else:
                mask = byte_masks.get(byte & 255, 0)
            possible = ((possible << 1) | 1) & mask
            if possible & match_bit:
                position = index - len(needle) + 1
                if last_unknown >= position:
                    raise ModelError('String contains unknown active DATA bytes')
                return position + 1
        return 0

    def string_without(self, ref, start, count, scope='', *, destination=None):
        """Capture DELETE's retained bytes without consuming its removed window."""
        data, length = self._string_data(ref, scope)
        first = start - 1
        end = first + count
        if not 1 <= start <= len(data) or count < 0 or end > length:
            raise StringPositionError('DELETE requires positive quantity within the active source string')
        if count == 0:
            raise ModelError('DELETE requires positive quantity within the active source string')
        if destination is not None:
            self._check_string_result_size(destination, length - count, scope)
        return self._decode_string_data(data[:first] + data[end:length])

    def _check_string_result_size(self, ref, length, scope):
        key, parts, dtype = self.check_writable(ref, scope)
        capacity = self.project.string_capacity(dtype)
        if capacity is None:
            raise ModelError('String destination required')
        if length > capacity:
            raise StringCapacityError(f'String length {length} exceeds capacity {capacity} for {ref}')
        return key, parts

    def write_string(self,ref,text,scope=''):
        try:data=text.encode('latin-1')
        except UnicodeEncodeError as e:raise ModelError('Strings require single-byte characters') from e
        key, parts = self._check_string_result_size(ref, len(data), scope)
        backing = self.read(ref, scope, mutable=False)['DATA']
        if self.structural:
            return
        data_path = parts + ['DATA']
        result = [byte if byte < 128 else byte - 256 for byte in data]
        self.store(key, parts + ['LEN'], len(result))
        if len(result) >= MAX_TRACKED_CELLS_PER_TAG:
            # Journal one DATA replacement for a long result, preserving its tail.
            updated = backing.copy()
            updated[:len(result)] = result
            self.store(key, data_path, updated)
        else:
            for index, byte in enumerate(result):
                self.store(key, data_path + [index], byte)

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
                if definition and definition.local_aliases:
                    for parameter in definition.parameters:
                        alias = parameter.get('Name', '')
                        target = definition.local_aliases.get(alias.lower())
                        if target is not None:
                            walk(f"{name}.{alias}", target.read(value), tag, local)
            elif isinstance(value, list):
                def array(path,obj):
                    if isinstance(obj,list):
                        for i,v in enumerate(obj):array(path+[i],v)
                    else:walk(name+'['+','.join(str(i) for i in path)+']',obj,tag,local)
                array([],value)
            else:
                dtype=self.resolve(name)[2]
                exact_text = dtype in ('LINT', 'ULINT') or dtype in time_values.TYPES
                result.append({"name": name, "type": dtype, "value": str(value) if value is not None and exact_text else value,
                               'kind':'integer_text' if exact_text else 'scalar',
                               'aoi_local':local,'unknown':value is None,
                               "constant": tag.constant or value is None, "alias": tag.alias,
                               "problem": 'Unknown backing byte omitted by export' if value is None else tag.problem})
        for tag in self.project.tags.values():
            if tag.problem:
                result.append({"name": tag.key, "type": tag.dtype, "value": None, "problem": tag.problem, "constant": True})
            else:
                try: walk(tag.key, self.read(tag.key, allow_time=True), tag)
                except ModelError as e: result.append({"name": tag.key, "type": tag.dtype, "value": None, "problem": str(e), "constant": True})
        return result
