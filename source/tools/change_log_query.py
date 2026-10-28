"""Decode observed v35 Change Log search framing without supplying history.

The 32-byte summary is opaque. Its fields, records and runtime authority are
not inferred from its extent or from a successful CIP response.
"""
import hashlib
import struct

from logixlab.ethernetip import decode_path,CIPError


def frame(request,response):
    if (type(request) is not bytes or type(response) is not bytes or not 10<=len(request)<=22
            or not 4<=len(response)<=72 or request[0]!=0x4F):
        raise ValueError('Unsupported Change Log search message extent or service')
    end=2+2*request[1]
    if end+4!=len(request):raise ValueError('Change Log search requires a four-byte cursor')
    try:path=decode_path(request[2:end])
    except CIPError as error:raise ValueError('Invalid Change Log search path') from error
    if (path.class_id!=0xAC or path.instance!=1 or path.attribute is not None or path.symbols
            or any(getattr(path,key) is not None for key in
                ('program_instance','io_map_instance','controller_instance','aoi_instance','routine_instance'))):
        raise ValueError('Unsupported Change Log search scope')
    if response[0]!=0xCF or response[1] or response[3]>16:
        raise ValueError('Invalid Change Log search response header')
    start=4+2*response[3]
    if start>len(response):raise ValueError('Truncated Change Log additional status')
    query=struct.unpack('<HH',request[end:]);data=response[start:]
    if response[2]:
        if data:raise ValueError('Unexpected rejected Change Log search data')
        return query,None,None,response[2]
    if len(data) not in (4,36):raise ValueError('Unsupported Change Log search reply shape')
    return query,struct.unpack('<HH',data[-4:]),data[:-4] or None,0


def describe(request,response):
    query,cursor,summary,status=frame(request,response)
    return dict(profile='change-log-search-v35-observed',status=status,
        shape='rejected' if status else 'cursor_only' if summary is None else 'opaque_summary',
        summary_bytes=len(summary or b''),summary_sha256=hashlib.sha256(summary).hexdigest() if summary is not None else None,
        cursor_echoed=cursor==query if cursor is not None else None,
        cursor_changed=cursor!=query if cursor is not None else None,
        summary_fields_interpreted=False,records_decoded=False,history_supplied=False,
        source_binding_verified=False,mac_verified=False,native_acceptance_verified=False,payloads_exposed=False)
