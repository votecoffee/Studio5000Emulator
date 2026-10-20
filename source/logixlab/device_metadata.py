"""Fixed properties of the LogixLab software device, independent of L5X.

The application has an English UI, no assigned device location, no emulated
trusted slots and no authorized system operator. These are model properties,
not recovered hardware settings or a claim of implemented security services.
"""


def attributes():
    # v35 Extended Device: UINT-length strings, counted trusted-slot list,
    # and a DWORD system operator identity. Strings have no padding here.
    return {3: b'\0\0', 6: b'\5\0en-US', 7: b'\0\0', 8: bytes(4)}


def description():
    return {'location': '', 'locale': 'en-US', 'trusted_slot_count': 0,
            'system_operator_identity': 0, 'available_attributes': [3, 6, 7, 8],
            'source': 'LogixLab software-device defaults; not imported hardware settings',
            'writable': False, 'trusted_slot_enforcement': False,
            'operator_authorization': False, 'authority_services': False}
