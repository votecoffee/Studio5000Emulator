"""Parse and normalize immediate CASE labels in the selector comparison type."""
import re
from .integer_math import WIDE_TYPES
from .model import ModelError,coerce,literal
from .numeric_storage import typed_literal

RADIX=r'(?:2|8|16)#[0-9a-fA-F_]+'
TYPED_NUMBER=rf'(?:{RADIX}|\d+)(?:[Uu][Ll]?|[Ll])(?!\w)'
NUMBER=rf'{TYPED_NUMBER}|{RADIX}|(?:\d+(?:\.(?!\.)\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def labels(text):
    ranges=[]
    for item in text.split(','):
        parts=item.split('..');values=[]
        if not 1<=len(parts)<=2:raise ModelError('CASE labels require numeric literals or a range')
        for part in parts:
            match=re.fullmatch(r'\s*([+-]?)\s*('+NUMBER+r')\s*',part)
            if match is None:raise ModelError('CASE labels require numeric literals')
            sign,token=match.groups()
            try:
                if re.fullmatch(TYPED_NUMBER,token):
                    if '#' in token:
                        dtype,value=typed_literal(token)
                        value=coerce(-value if sign=='-' else value,dtype)
                    else:
                        dtype,value=typed_literal(sign+token)
                else:
                    value=literal(token)
                    value=-value if sign=='-' else value
                    dtype=None
            except ValueError as error:
                raise ModelError('Invalid CASE numeric literal') from error
            values.append((value,dtype))
        lo,hi=values[0],values[-1]
        if lo[0]>hi[0]:raise ModelError('Descending CASE range is unsupported')
        ranges.append((lo,hi))
    return ranges


def normalize(ranges,dtype):
    result=[]
    for pair in ranges:
        converted=[]
        for value,label_type in pair:
            if label_type is not None and label_type!=dtype:
                raise ModelError(f'{label_type} CASE label requires a matching selector')
            if dtype!='REAL' and type(value) is not int:
                raise ModelError('Integer CASE requires integer labels')
            if dtype in WIDE_TYPES and label_type is None:
                coerce(value,'DINT')
            try:converted.append(coerce(value,dtype))
            except (ValueError,OverflowError) as error:raise ModelError('CASE label outside finite REAL range') from error
        result.append(tuple(converted))
    return result


def description():
    return dict(numeric_types=['SINT','INT','DINT',*sorted(WIDE_TYPES),'REAL'],labels='Immediate numeric values, lists and inclusive ascending ranges',
                comparison='DINT or exact wide integers, or float32 REAL; labels follow the selector type',
                selection='First matching branch; otherwise ELSE or retain previous values',native_runtime_parity=False)
