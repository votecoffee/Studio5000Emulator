"""Decimal ST integer suffixes; magnitude is checked with its unary sign."""
import re

TYPES={'L':'LINT','U':'UDINT','UL':'ULINT'}
TOKEN=re.compile(r'(\d+)(UL|L|U)(?![\w.])',re.IGNORECASE)


def scan(text,position):
    match=TOKEN.match(text,position)
    if match is None:return None
    return match.end(),(int(match[1]),TYPES[match[2].upper()])
