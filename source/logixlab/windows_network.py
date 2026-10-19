"""Read IPv4 adapter metadata through Windows IP Helper, without a shell.

Layouts follow Microsoft's IP_ADAPTER_ADDRESSES_LH and related structures.
Only GetAdaptersAddresses is called; no configuration APIs are exposed.
"""
from __future__ import annotations

import ctypes as C
import ipaddress
import socket

U32 = C.c_uint32


class SocketAddress(C.Structure):
    _fields_ = [('pointer', C.c_void_p), ('length', C.c_int32)]


class AddressNode(C.Structure):
    pass


AddressNode._fields_ = [('alignment', C.c_uint64), ('next', C.POINTER(AddressNode)),
                       ('address', SocketAddress)]


class UnicastNode(C.Structure):
    pass


UnicastNode._fields_ = [('alignment', C.c_uint64), ('next', C.POINTER(UnicastNode)),
                       ('address', SocketAddress), ('prefix_origin', U32), ('suffix_origin', U32),
                       ('dad_state', U32), ('valid_lifetime', U32), ('preferred_lifetime', U32),
                       ('lease_lifetime', U32), ('prefix_length', C.c_ubyte)]


class AdapterNode(C.Structure):
    pass


AdapterNode._fields_ = [
    ('alignment', C.c_uint64), ('next', C.POINTER(AdapterNode)), ('adapter_name', C.c_char_p),
    ('unicast', C.POINTER(UnicastNode)), ('anycast', C.c_void_p), ('multicast', C.c_void_p),
    ('dns', C.POINTER(AddressNode)), ('dns_suffix', C.c_wchar_p), ('description', C.c_wchar_p),
    ('friendly_name', C.c_wchar_p), ('physical_address', C.c_ubyte * 8), ('physical_length', U32),
    ('flags', U32), ('mtu', U32), ('interface_type', U32), ('oper_status', U32),
    ('ipv6_index', U32), ('zone_indices', U32 * 16), ('prefix', C.c_void_p),
    ('transmit_speed', C.c_uint64), ('receive_speed', C.c_uint64), ('wins', C.c_void_p),
    ('gateway', C.POINTER(AddressNode)),
]


def _walk(pointer):
    seen = set()
    while pointer:
        address = C.addressof(pointer.contents)
        if address in seen or len(seen) >= 4096:
            raise ValueError('Invalid Windows adapter linked list')
        seen.add(address)
        value = pointer.contents
        if value.alignment & 0xFFFFFFFF < C.sizeof(type(value)):
            raise ValueError('Windows adapter structure is too short')
        yield value
        pointer = value.next


def _ipv4(value):
    if not value.pointer or value.length < 16:
        return None
    family = C.cast(value.pointer, C.POINTER(C.c_uint16)).contents.value
    return socket.inet_ntoa(C.string_at(value.pointer + 4, 4)) if family == socket.AF_INET else None


def _addresses(pointer):
    values = []
    for node in _walk(pointer):
        value = _ipv4(node.address)
        if value and value not in values:
            values.append(value)
    return values


def _adapters():
    library = C.WinDLL('iphlpapi.dll', use_last_error=True)
    query = library.GetAdaptersAddresses
    query.argtypes = [U32, U32, C.c_void_p, C.c_void_p, C.POINTER(U32)]
    query.restype = U32
    size = U32(15000)
    for _ in range(3):
        if not 0 < size.value <= 1024 * 1024:
            raise ValueError('Windows adapter buffer exceeds the supported size')
        buffer = C.create_string_buffer(size.value)
        # Keep unicast/DNS; include prefixes and gateways; skip anycast/multicast.
        code = query(socket.AF_INET, 0x96, None, buffer, C.byref(size))
        if code == 111:  # ERROR_BUFFER_OVERFLOW: the interface table grew.
            continue
        if code:
            raise OSError(code, 'GetAdaptersAddresses failed')
        return buffer, C.cast(buffer, C.POINTER(AdapterNode))
    raise OSError('Windows adapter table changed repeatedly')


def windows_interface(address):
    requested = ipaddress.IPv4Address(address)
    buffer, head = _adapters()  # Retain the native buffer while following pointers.
    fallback = None
    for adapter in _walk(head):
        for unicast in _walk(adapter.unicast):
            local = _ipv4(unicast.address)
            if local is None:
                continue
            prefix = int(unicast.prefix_length)
            if not 0 <= prefix <= 32:
                raise ValueError('Invalid IPv4 prefix from Windows')
            exact = local == str(requested)
            loopback_alias = (requested.is_loopback and ipaddress.IPv4Address(local).is_loopback
                              and requested in ipaddress.IPv4Network(local + '/' + str(prefix), strict=False))
            if not exact and not loopback_alias:
                continue
            gateways = _addresses(adapter.gateway)
            mac = bytes(adapter.physical_address[:6]) if adapter.physical_length == 6 and adapter.interface_type in (6, 71) else None
            value = {'address': str(requested), 'prefix': prefix,
                     'gateway': gateways[0] if gateways else '0.0.0.0',
                     'dns': _addresses(adapter.dns)[:2], 'domain': adapter.dns_suffix or '',
                     'name': adapter.friendly_name or (adapter.adapter_name or b'').decode('utf-8', errors='replace'),
                     'mac': mac.hex(':') if mac else None}
            if exact:
                return value
            if fallback is None:
                fallback = value
    if fallback is not None:
        return fallback
    raise ValueError('Selected IPv4 interface was not found')
