"""Source-checked post-registration settings retained in a private download."""
import hashlib
import struct
from types import MappingProxyType
from .download_image import ImageError
from .download_properties import controller_profile
from .network_objects import InterfaceSnapshot

PROFILES={0xF6:(9,),0x64:(1,2,3,6,7,8),0x67:(1,2),0x43:(16,17,1),0x8B:(4,2)}


def write_profile(class_id,payload):
    return (1,) if class_id==0x67 and type(payload) is bytes and payload[:2]==b'\1\0' else PROFILES[class_id]


class SetupBindings:
    def __init__(self,project,namespace,identity,interface=None):
        self.project=project;self.namespace=namespace;self.identity=identity;self.interface=interface

    def expected(self,class_id):
        if type(class_id) is not int or class_id not in PROFILES:raise ImageError('download_setup_class_unsupported')
        project=self.project;namespace=self.namespace;source=namespace._source
        controller_profile(project,source)
        if not namespace.controller.description()['configured']:raise ImageError('download_setup_controller_required')
        reference=namespace.repository.identity_reference(source,project,self.identity)
        if class_id==0xF6:
            if not isinstance(self.interface,InterfaceSnapshot) or self.interface.link is None:
                raise ImageError('download_setup_interface_unavailable')
            values={9:self.interface.link.attributes()[9]}
        elif class_id==0x64:
            config=project.controller_configuration
            if config.project_name!=project.name:raise ImageError('download_setup_device_name_mismatch')
            # Location/trusted slots have no assigned software-device values.
            # The observed empty download locale is a private unset marker;
            # it does not replace the active English management UI locale.
            values={**config.extended_device_attributes(),3:bytes(2),6:bytes(2),7:bytes(2),8:reference}
        elif class_id==0x67:values=project.pccc_mapping.attributes()
        elif class_id==0x43:values=project.time_sync.attributes()
        else:values=project.wall_clock.attributes(read_time=False)
        if any(n not in values for n in PROFILES[class_id]):raise ImageError('download_setup_source_incomplete')
        return {n:values[n] for n in PROFILES[class_id]}

    def stamp(self,class_id):
        values=self.expected(class_id);project=self.project
        setting=({0x64:project.controller_configuration,0x67:project.pccc_mapping,
                  0x43:project.time_sync,0x8B:project.wall_clock}.get(class_id)
                 if class_id!=0xF6 else self.interface)
        return hashlib.sha256(repr((controller_profile(project,self.namespace._source),self.namespace._source,
            self.identity,setting,tuple(values.items()))).encode()).hexdigest()


class DownloadSetup:
    def __init__(self):
        self._values=MappingProxyType({});self._bindings=MappingProxyType({});self._digest=None

    def _effect(self):
        rows=tuple((cls,tuple(sorted(values.items())),self._bindings[cls]) for cls,values in sorted(self._values.items()))
        return hashlib.sha256(repr(rows).encode()).hexdigest()

    def validate(self,bindings):
        if not self._values:
            if self._bindings or self._digest is not None:raise ImageError('download_setup_effect_changed')
            return
        if bindings is None or self._values.keys()!=self._bindings.keys():raise ImageError('download_setup_binding_changed')
        if self._effect()!=self._digest:raise ImageError('download_setup_effect_changed')
        for class_id,values in self._values.items():
            if bindings.stamp(class_id)!=self._bindings[class_id]:raise ImageError('download_setup_source_changed')
            if dict(values)!=bindings.expected(class_id):raise ImageError('download_setup_effect_changed')

    def stage(self,class_id,payload,bindings):
        self.validate(bindings);expected=bindings.expected(class_id);stamp=bindings.stamp(class_id)
        profile=write_profile(class_id,payload)
        if class_id==0x67 and profile==(1,) and class_id not in self._values:
            raise ImageError('download_setup_mapping_base_required')
        values={n:expected[n] for n in profile}
        encoded=struct.pack('<H',len(values))+b''.join(struct.pack('<H',n)+v for n,v in values.items())
        if type(payload) is not bytes or payload!=encoded:raise ImageError('download_setup_values_mismatch')
        if bindings.stamp(class_id)!=stamp:raise ImageError('download_setup_source_changed')
        retained={**self._values.get(class_id,{}),**values}
        self._values=MappingProxyType({**self._values,class_id:MappingProxyType(retained)})
        self._bindings=MappingProxyType({**self._bindings,class_id:stamp});self._digest=self._effect()
        return struct.pack('<H',len(values))+b''.join(struct.pack('<HH',n,0) for n in values)

    def require_complete(self,bindings):
        self.validate(bindings)
        if self._values.keys()!=PROFILES.keys() or any(set(self._values[cls])!=set(attrs) for cls,attrs in PROFILES.items()):
            raise ImageError('download_setup_complete_required')

    def read(self,class_id,attribute,bindings):
        self.validate(bindings)
        if type(class_id) is not int or type(attribute) is not int or attribute not in self._values.get(class_id,{}):
            raise ImageError('download_setup_read_unavailable')
        return self._values[class_id][attribute]

    def description(self):
        return dict(classes=sorted(self._values),attributes=sum(len(v) for v in self._values.values()),
            owner_only=True,source_bound=bool(self._values),active_configuration_changed=False,
            host_network_changed=False,clock_changed=False,operator_authorization=False,commit=False,payloads_exposed=False)
