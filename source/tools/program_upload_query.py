"""Observed v35 Program service 0x50 framing and payload checksum validation.

The CRC covers only the returned four-byte selector. No Program attributes,
source identity, compiled code, signature or message MAC are validated here.
"""
import hashlib
import struct

from logixlab.ethernetip import CIPError,decode_path
from logixlab import program_query

SELECTORS=program_query.SELECTORS


def describe(request,response):
    """Accept the three observed zero-position queries and checked token replies."""
    if (not isinstance(request,bytes) or not isinstance(response,bytes) or
            not 6<=len(request)<=64 or not 4<=len(response)<=20 or request[0]!=0x50):
        raise ValueError('Unsupported Program upload query extent or service')
    end=2+2*request[1]
    if end>len(request):raise ValueError('Truncated Program upload query path')
    try:path=decode_path(request[2:end])
    except CIPError as error:raise ValueError('Invalid Program upload query path') from error
    if (path.class_id!=0x68 or not path.instance or path.attribute is not None or path.symbols or
            any(getattr(path,key) is not None for key in
                ('program_instance','io_map_instance','controller_instance','aoi_instance'))):
        raise ValueError('Unsupported Program upload query scope')
    if len(request)-end!=8:raise ValueError('Unsupported Program upload query payload extent')
    version,selector,position=struct.unpack_from('<HHI',request,end)
    if version!=0x101 or selector not in SELECTORS or position!=0:
        raise ValueError('Unsupported Program upload query selector or position')
    if response[0]!=0xd0 or response[1]!=0 or response[3]!=0:
        raise ValueError('Unsupported Program upload query response header')
    result=dict(profile='program-upload-query-v35-observed',selector=selector,position=position,
        status=response[2],response_bytes=len(response),record_count=0,opaque_word_sha256=None,
        returned_selector_matches=None,field_semantics='NOT INFERRED',source_binding_verified=False,
        checksum_verified=False,mac_verified=False,native_acceptance_verified=False,payloads_exposed=False)
    if response[2]:
        if len(response)!=4:raise ValueError('Unexpected rejected Program upload query data')
        return result
    if len(response)!=20:raise ValueError('Unsupported successful Program upload query extent')
    container,size,word,returned_selector=struct.unpack_from('<4I',response,4)
    if container!=0x301 or size!=8:
        raise ValueError('Unsupported Program upload query container or byte count')
    if returned_selector!=selector:raise ValueError('Program upload query selector mismatch')
    if word!=program_query.checksum(response[16:20]):
        raise ValueError('Program upload query payload checksum mismatch')
    result.update(record_count=1,opaque_word_sha256=hashlib.sha256(struct.pack('<I',word)).hexdigest(),
                  returned_selector_matches=True,checksum_verified=True,
                  checksum_algorithm='complemented_ieee_crc32',checksum_scope='returned_selector_uint32')
    return result
