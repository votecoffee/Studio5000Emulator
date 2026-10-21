"""Compare observed Routine bulk shapes without exposing addresses or blobs.

This describes bytes, field statuses and local path consistency. It neither
authenticates a capture nor proves source binding or native client acceptance.
"""
import hashlib
import json
import struct
from .collection_inventory import decode_attribute_list,CollectionError

BULK_ATTRIBUTES=(1,2,8,*range(9,25),26,27,28)
IDENTITY_FIELDS=frozenset((8,9,22))


def describe(raw,requested,instance):
    """Describe only the exact observed 22-field request and its returned prefix."""
    if (not isinstance(requested,(tuple,list)) or tuple(requested)!=BULK_ATTRIBUTES
            or type(instance) is not int or not 1<=instance<=0xffffffff):
        raise CollectionError('Unsupported Routine bulk profile context')
    parsed=decode_attribute_list(raw,requested,0x6d,include_payloads=True)
    values={row['attribute']:bytes.fromhex(row['data_hex']) for row in parsed['attributes'] if row['status']==0}
    successful=[row['attribute'] for row in parsed['attributes'] if row['status']==0]
    failed=[row['attribute'] for row in parsed['attributes'] if row['status']!=0]
    complete=len(values)==len(BULK_ATTRIBUTES)
    # Stable comparison across objects keeps flags/type/state, excluding only
    # the header reference, original instance and opaque source-key metadata.
    normalized=[(row['attribute'],row['value_bytes'],row['value_sha256']) for row in parsed['attributes']
                if row['attribute'] not in IDENTITY_FIELDS]
    fingerprint=hashlib.sha256(json.dumps(normalized,separators=(',',':')).encode('ascii')).hexdigest() if complete else None
    def zero(number):return not any(values[number]) if number in values else None
    key=values.get(22)
    key_count=struct.unpack_from('<H',key)[0] if key is not None else None
    buffers=range(10,22)
    return dict(profile='routine-bulk-v35-observed',complete=complete,successful_attributes=successful,
                failed_attributes=failed,unreturned_attributes=parsed['remaining_attributes'],
                nonidentity_fields_sha256=fingerprint,code_address_zero=zero(2),
                header_reference_nonzero=not zero(8) if 8 in values else None,
                executable_instance_matches_path=int.from_bytes(values[9],'little')==instance if 9 in values else None,
                zero_edit_buffer_fields=sum(zero(number) is True for number in buffers),
                all_edit_buffer_fields_zero=all(zero(number) for number in buffers) if all(number in values for number in buffers) else None,
                source_key_bytes=key_count,
                source_key_observed_format=(key_count==66 and key[2:4]==b'\0\x08') if key is not None else None,
                protection_field_zero=zero(23),executable_flags_zero=zero(24),signature_field_zero=zero(28),
                field_semantics='LIMITED TO BYTE SHAPES AND PATH CONSISTENCY',
                source_binding_verified=False,mac_verified=False,native_acceptance_verified=False,payloads_exposed=False)
