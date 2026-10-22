"""Bounded v35 Program selector replies with a payload CRC, not a signature.

The observed one-record profile returns the selector as a UDINT, preceded by
its complemented IEEE CRC-32. It describes neither Program attribute values
nor compiled code. Original Program identity is checked separately by routing.
"""
import struct
import zlib

SELECTORS = (31, 32, 33)


def selection(data):
    if not isinstance(data, bytes) or len(data) != 8:
        raise ValueError('Program query requires exactly eight bytes')
    version, selector, position = struct.unpack('<HHI', data)
    if version != 0x101 or selector not in SELECTORS or position != 0:
        raise ValueError('Unsupported Program query selector, version or position')
    return selector


def checksum(data):
    """Wire CRC for this profile; independent of source hashes and message MACs."""
    return zlib.crc32(data) ^ 0xFFFFFFFF


def body(selector):
    if type(selector) is not int or selector not in SELECTORS:
        raise ValueError('Unsupported Program query selector')
    value = struct.pack('<I', selector)
    return struct.pack('<III', 0x301, 8, checksum(value)) + value


def description():
    return dict(service=0x50, selectors=list(SELECTORS), zero_position_only=True,
                payload='selector_uint32', checksum='complemented_ieee_crc32',
                source_program_required=True, read_only=True,
                program_attribute_values=False, compiled_code=False,
                project_signature=False, complete_upload=False)
