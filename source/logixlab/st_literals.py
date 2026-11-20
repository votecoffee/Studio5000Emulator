"""Integer literal syntax for Structured Text and subscripts."""
import re

TYPES={'L':'LINT','U':'UDINT','UL':'ULINT'}
TOKEN=re.compile(r'(\d+)(UL|L|U)(?![\w.])',re.IGNORECASE)
RADIX=r'(?:2|8|16)#[0-9A-Fa-f_]+(?: +[0-9A-Fa-f_]+)*'
SUFFIX=r'(?:[Uu][Ll]?|[Ll])'
RADIX_TOKEN=re.compile(rf'{RADIX}{SUFFIX}?(?!\w)')
DINT_RADIX_TOKEN=re.compile(rf'{RADIX}(?!\w)')


def scan(text,position):
    match=TOKEN.match(text,position)
    if match is None:return None
    return match.end(),(int(match[1]),TYPES[match[2].upper()])
