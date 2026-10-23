"""Source-exact Controller metadata retained by one prepared download."""
import hashlib
from types import MappingProxyType
from .download_image import ImageError
from .incremental_download import metadata_stamp,value_identity
from .metadata_query import download_records
from .native_metadata_values import encode_records

MAX_PACKET_BYTES=16384
MAX_VALUES=4096
MAX_VALUE_BYTES=262144
MAX_PACKETS=256


def key(row):return row.target,row.locale_word,row.definition


class DownloadProperties:
    def __init__(self):
        self._values=MappingProxyType({});self._packets=();self._source=None;self._binding=None;self._effect=None

    def _digest(self):
        rows=tuple(sorted(self._values.items(),key=lambda pair:repr(pair[0])))
        return hashlib.sha256(repr((rows,self._packets)).encode()).hexdigest()

    def validate(self,source,values):
        if self._binding is None:
            if self._values or self._packets or self._source is not None or self._effect is not None:
                raise ImageError('download_property_effect_changed')
            return
        if source!=self._source or metadata_stamp(values,source)!=self._binding:
            raise ImageError('download_property_source_changed')
        if self._digest()!=self._effect:raise ImageError('download_property_effect_changed')
        original={value_identity(row) for row in values.rows}
        if any(key(row)!=target or value_identity(row) not in original for target,row in self._values.items()):
            raise ImageError('download_property_effect_changed')

    def stage(self,payload,definition,source,values):
        self.validate(source,values);stamp=metadata_stamp(values,source)
        if not isinstance(payload,bytes) or len(payload)>MAX_PACKET_BYTES:
            raise ImageError('download_property_packet_limit')
        try:rows=download_records(payload,definition)
        except ValueError as error:raise ImageError('download_property_packet_invalid') from error
        original={}
        for row in values.rows:
            target=key(row)
            if target in original and value_identity(original[target])!=value_identity(row):
                raise ImageError('download_property_source_ambiguous')
            original[target]=row
        proposal=dict(self._values)
        for row in rows:
            target=row.target;stored=original.get(key(row))
            if (target.class_id!=0x8E or target.instance_word!=1 or target.context_word or target.selector_word
                    or stored is None or value_identity(row)!=value_identity(stored)):
                raise ImageError('download_property_source_value_required')
            # Packet ordinals are local framing; the actual property key and
            # typed source value are preserved independently of those ordinals.
            proposal[key(row)]=row
        digest=hashlib.sha256(payload+definition.to_bytes(2,'little')).hexdigest()
        packets=self._packets if digest in self._packets else (*self._packets,digest)
        size=sum(len(encode_records((row,))) for row in proposal.values())
        if len(proposal)>MAX_VALUES or size>MAX_VALUE_BYTES or len(packets)>MAX_PACKETS:
            raise ImageError('download_property_storage_limit')
        if metadata_stamp(values,source)!=stamp:raise ImageError('download_property_source_changed')
        self._values=MappingProxyType(proposal);self._packets=packets;self._source=source;self._binding=stamp
        self._effect=self._digest();self.validate(source,values)

    def read(self,ordinal,source,values):
        self.validate(source,values)
        if type(ordinal) is not int or not 0<=ordinal<len(self._values):raise ImageError('download_property_read_range')
        return tuple(self._values.values())[ordinal]

    def description(self):
        return dict(packets=len(self._packets),values=len(self._values),source_bound=self._binding is not None,
            active_metadata_changed=False,identity_changed=False,commit=False,payloads_exposed=False)
