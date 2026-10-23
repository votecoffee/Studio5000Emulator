"""Private Controller configuration for the observed post-Task download step."""
import hashlib
import struct
from types import MappingProxyType
from .download_image import ImageError

WIDTHS={1:4,6:4,3:2,13:4,15:1,16:2,17:1,23:1,28:8,25:4,31:1,35:1,33:32,34:32}
SETTINGS={10:1,11:2,12:2}


def attributes(payload):
    if not isinstance(payload,bytes) or len(payload)<2:raise ImageError('download_controller_attribute_extent')
    count=struct.unpack_from('<H',payload)[0]
    widths=WIDTHS if count==len(WIDTHS) else SETTINGS if count==1 else {}
    if not widths:raise ImageError('download_controller_attribute_profile')
    offset=2;values={}
    for _ in range(count):
        if offset+2>len(payload):raise ImageError('download_controller_attribute_extent')
        number=struct.unpack_from('<H',payload,offset)[0];offset+=2
        if number not in widths or number in values:raise ImageError('download_controller_attribute_profile')
        end=offset+widths[number]
        if end>len(payload):raise ImageError('download_controller_attribute_extent')
        values[number]=payload[offset:end];offset=end
    if offset!=len(payload):raise ImageError('download_controller_attribute_extent')
    return values


class ControllerBindings:
    def __init__(self,engine,namespace,identity):
        self.engine=engine;self.namespace=namespace;self.identity=identity

    def expected(self):
        project=self.engine.project;source=self.namespace._source;identity=self.identity
        if (identity is None or (identity.source_acd_sha256,identity.source_l5x_sha256)!=(source.acd_sha256,source.l5x_sha256)
                or project.sha256!=source.l5x_sha256 or project.processor!='1756-L85E' or self.engine.mode!='project'
                or getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',())):
            raise ImageError('download_controller_source_required')
        config=project.controller_configuration;values=config.compatibility_attributes()
        # Omitted legacy slice settings use the observed zero download profile,
        # independently of the declared read defaults. Neither drives scheduling.
        if config.time_slice_defaulted:values[3]=bytes(2)
        if config.share_unused_defaulted:values[16]=bytes(2)
        # Retain explicit zero reset operands without validating or advertising
        # a State Detection signature. Live signature reads remain unavailable.
        values.update({33:bytes(32),34:bytes(32)})
        if any(n not in values or len(values[n])!=size for n,size in WIDTHS.items()):
            raise ImageError('download_controller_complete_configuration_required')
        return tuple(sorted((n,values[n]) for n in WIDTHS))

    def stamp(self):
        expected=self.expected();project=self.engine.project
        return hashlib.sha256(repr((id(project),self.namespace._source,project.processor,
            project.controller_configuration,expected)).encode()).hexdigest()

    def settings(self):
        self.expected()
        values=self.engine.project.controller_configuration.compatibility_attributes()
        return {n:values[n] for n,size in SETTINGS.items() if n in values and len(values[n])==size}


class DownloadController:
    def __init__(self):
        self._values=MappingProxyType({});self._binding=None;self._digest=None

    def validate(self,bindings):
        if self._binding is None:
            if self._values or self._digest is not None:raise ImageError('download_controller_effect_changed')
            return
        if bindings is None or bindings.stamp()!=self._binding:raise ImageError('download_controller_binding_changed')
        expected=dict(bindings.expected())
        expected.update({n:v for n,v in bindings.settings().items() if n in self._values})
        if (dict(self._values)!=expected or
                hashlib.sha256(repr(tuple(sorted(self._values.items()))).encode()).hexdigest()!=self._digest):
            raise ImageError('download_controller_effect_changed')

    def configure(self,payload,bindings):
        self.validate(bindings);stamp=bindings.stamp();values=attributes(payload)
        if len(values)==1:
            if self._binding is None:raise ImageError('download_controller_base_configuration_required')
            if any(bindings.settings().get(n)!=v for n,v in values.items()):
                raise ImageError('download_controller_configuration_mismatch')
        elif tuple(sorted(values.items()))!=bindings.expected():raise ImageError('download_controller_configuration_mismatch')
        if bindings.stamp()!=stamp:raise ImageError('download_controller_binding_changed')
        updated=dict(self._values);updated.update(values)
        self._values=MappingProxyType(updated);self._binding=stamp
        self._digest=hashlib.sha256(repr(tuple(sorted(updated.items()))).encode()).hexdigest()
        self.validate(bindings)
        return struct.pack('<H',len(values))+b''.join(struct.pack('<HH',n,0) for n in values)

    def description(self):
        return dict(configured=self._binding is not None,attributes=len(self._values),source_bound=self._binding is not None,
            signature_reset_operands=33 in self._values and 34 in self._values,signature_verified=False,
            active_configuration_changed=False,active_scheduler_changed=False,commit=False,payloads_exposed=False)
