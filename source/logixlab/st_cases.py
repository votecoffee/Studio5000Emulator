"""Immediate numeric CASE labels with bounded DINT or float32 REAL comparison."""
import re
from .model import ModelError,coerce,literal

NUMBER=r'(?:2|8|16)#[0-9a-fA-F_]+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def labels(text):
    ranges=[]
    for item in text.split(','):
        parts=item.split('..');values=[]
        if not 1<=len(parts)<=2:raise ModelError('CASE labels require numeric literals or a range')
        for part in parts:
            match=re.fullmatch(r'\s*([+-]?)\s*('+NUMBER+r')\s*',part)
            if match is None:raise ModelError('CASE labels require numeric literals')
            try:value=literal(match[2])
            except ValueError as error:raise ModelError('Invalid CASE numeric literal') from error
            values.append(-value if match[1]=='-' else value)
        lo,hi=values[0],values[-1]
        if lo>hi:raise ModelError('Descending CASE range is unsupported')
        ranges.append((lo,hi))
    return ranges


def normalize(ranges,real):
    result=[]
    for pair in ranges:
        converted=[]
        for value in pair:
            if not real and type(value) is not int:raise ModelError('Integer CASE requires integer labels')
            try:converted.append(coerce(value,'REAL' if real else 'DINT'))
            except (ValueError,OverflowError) as error:raise ModelError('CASE label outside finite REAL range') from error
        result.append(tuple(converted))
    return result


def description():
    return dict(numeric_types=['SINT','INT','DINT','REAL'],labels='Immediate numeric values, lists and inclusive ascending ranges',
                comparison='DINT integers or float32 REAL; labels follow the expression profile',
                selection='First matching branch; otherwise ELSE or retain previous values',native_runtime_parity=False)
