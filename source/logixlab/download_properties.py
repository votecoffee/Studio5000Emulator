"""Original Controller metadata and a bounded, source-bound v35 L85E controller-profile marker."""
import hashlib
from dataclasses import dataclass,field,replace
from types import MappingProxyType
from .download_image import ImageError
from .incremental_download import metadata_stamp,value_identity
from .metadata_query import download_records
from .native_metadata_values import encode_records
from .model import Project

MAX_PACKET_BYTES=16384
MAX_VALUES=4096
MAX_VALUE_BYTES=262144
MAX_PACKETS=256


def key(row):return row.target,row.locale_word,row.definition


def controller_profile(project,source):
    if (not isinstance(project,Project) or project.sha256!=source.l5x_sha256
            or project.version!='35' or project.processor!='1756-L85E'
            or not project.task_configuration.source_complete or not project.executable_configuration.source_complete
            or getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',())):
        raise ImageError('download_property_controller_profile_required')
    return id(project),project.sha256,project.version,project.processor


def profile_marker(row,values):
    # The tested v35 L85E client emits 0x4C in SystemNumeric metadata.
    # A stored property still takes precedence; this cannot replace its value.
    return (row.target.class_id==0x8E and row.target.instance_word==1 and not row.target.context_word and not row.target.selector_word
        and row.target.qualifier==b'ProjectType' and row.locale_word==0x7F and row.kind==2
        and row.type_code==0xC4 and row.elements==1 and row.data==(0x4C).to_bytes(4,'little')
        and any(d.instance==row.definition and d.name=='SystemNumeric' for d in values.definitions.rows)
        and any(r.target.class_id==0x349 and r.target.instance_word==row.definition and not r.target.context_word
            and not r.target.selector_word and not r.target.qualifier and r.definition==17 and r.locale_word==0x7F
            and r.kind==2 and r.type_code==0xC2 and r.elements==1 and r.data==b'\1' for r in values.rows))


@dataclass(frozen=True)
class CommittedProperties:
    """Detached metadata read view; the original ACD catalog remains unchanged."""
    catalog:object=field(repr=False)
    source:object=field(repr=False)
    binding:str
    rows:tuple=field(repr=False)
    additions:int
    _all:bytes=field(repr=False)
    _controller:bytes=field(repr=False)

    @classmethod
    def prepare(cls,stage,source,values,project):
        stage.validate(source,values,project)
        if values is None:return None
        stamp=metadata_stamp(values,source)
        proposal={key(row):row for row in values.rows}
        before=len(proposal)
        proposal.update(stage._values)
        # Each download packet numbers its own records. The committed stream
        # needs one set of ordinals while retaining typed values and targets.
        rows=tuple(replace(row,record_word=n) for n,row in enumerate(proposal.values(),1))
        controller=tuple(row for row in rows if row.target.class_id==0x8E and row.target.instance_word==1
            and not row.target.context_word and not row.target.selector_word)
        result=cls(values,source,stamp,rows,len(rows)-before,encode_records(rows),encode_records(controller))
        stage.validate(source,values,project)
        result.body(values,'all-objects')
        return result

    def body(self,values,selection):
        if values is not self.catalog or metadata_stamp(values,self.source)!=self.binding:
            raise ImageError('installed_metadata_source_changed')
        if selection=='controller-attribute-26':return b''
        if selection=='all-objects':return self._all
        if selection=='controller-all':return self._controller
        raise ImageError('installed_metadata_selection_unsupported')


class DownloadProperties:
    def __init__(self):
        self._values=MappingProxyType({});self._packets=();self._source=None;self._binding=None;self._effect=None;self._profile=None

    def _digest(self):
        rows=tuple(sorted(self._values.items(),key=lambda pair:repr(pair[0])))
        return hashlib.sha256(repr((rows,self._packets,self._profile)).encode()).hexdigest()

    def validate(self,source,values,project=None):
        if self._binding is None:
            if self._values or self._packets or self._source is not None or self._effect is not None or self._profile is not None:
                raise ImageError('download_property_effect_changed')
            return
        if source!=self._source or metadata_stamp(values,source)!=self._binding:
            raise ImageError('download_property_source_changed')
        if self._digest()!=self._effect:raise ImageError('download_property_effect_changed')
        if self._profile is not None and controller_profile(project,source)!=self._profile:
            raise ImageError('download_property_controller_profile_changed')
        original={value_identity(row) for row in values.rows}
        original_keys={key(row) for row in values.rows}
        if any(key(row)!=target or (value_identity(row) not in original and
                not (self._profile is not None and target not in original_keys and profile_marker(row,values)))
                for target,row in self._values.items()):
            raise ImageError('download_property_effect_changed')

    def stage(self,payload,definition,source,values,project=None):
        self.validate(source,values,project);stamp=metadata_stamp(values,source)
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
        proposal=dict(self._values);profile=self._profile
        for row in rows:
            target=row.target;stored=original.get(key(row))
            if target.class_id!=0x8E or target.instance_word!=1 or target.context_word or target.selector_word:
                raise ImageError('download_property_source_value_required')
            if stored is None and profile_marker(row,values):
                profile=controller_profile(project,source)
            elif stored is None or value_identity(row)!=value_identity(stored):
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
        if profile is not None and controller_profile(project,source)!=profile:raise ImageError('download_property_controller_profile_changed')
        self._values=MappingProxyType(proposal);self._packets=packets;self._source=source;self._binding=stamp
        self._profile=profile;self._effect=self._digest();self.validate(source,values,project)

    def read(self,ordinal,source,values,project=None):
        self.validate(source,values,project)
        if type(ordinal) is not int or not 0<=ordinal<len(self._values):raise ImageError('download_property_read_range')
        return tuple(self._values.values())[ordinal]

    def description(self):
        return dict(packets=len(self._packets),values=len(self._values),source_bound=self._binding is not None,
            controller_profile_marker=self._profile is not None,
            active_metadata_changed=False,identity_changed=False,commit=False,payloads_exposed=False)
