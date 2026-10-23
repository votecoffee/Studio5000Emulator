"""Lease-local Change Log header proposals, never active correlation or history."""
import hashlib
import struct
from types import MappingProxyType
from .download_image import ImageError
from .native_project import NativeProjectIdentity

ADDRESS=0x76000001
WIDTHS={3:4,4:4,5:2,7:4,8:4,10:4,9:4}
CREATE=struct.pack('<HHH',1,6,1000)


def attributes(payload):
    if type(payload) is not bytes or len(payload)<2 or struct.unpack_from('<H',payload)[0]!=len(WIDTHS):
        raise ImageError('download_changelog_attribute_profile')
    result={};offset=2
    for _ in WIDTHS:
        if offset+2>len(payload):raise ImageError('download_changelog_attribute_extent')
        number=struct.unpack_from('<H',payload,offset)[0];offset+=2
        size=WIDTHS.get(number)
        if size is None or number in result:raise ImageError('download_changelog_attribute_profile')
        if offset+size>len(payload):raise ImageError('download_changelog_attribute_extent')
        result[number]=payload[offset:offset+size];offset+=size
    if offset!=len(payload):raise ImageError('download_changelog_attribute_extent')
    return result


class ChangelogBindings:
    def __init__(self,map_bindings,identity):self.map=map_bindings;self.identity=identity

    def original(self):
        source=self.map.headers.namespace._source;identity=self.identity
        if (not isinstance(identity,NativeProjectIdentity) or identity.source_acd_sha256!=source.acd_sha256
                or identity.source_l5x_sha256!=source.l5x_sha256):raise ImageError('download_changelog_source_required')
        return identity.attributes()

    def stamp(self):
        original=self.original();ns=self.map.headers.namespace
        if ns.local_map.read(self.map)!=b'\1\0':raise ImageError('download_changelog_prepared_map_required')
        return hashlib.sha256(repr((self.map.stamp(),id(self.identity),tuple(original.items()),self.identity.empty_change_log)).encode()).hexdigest()

    def check(self,values):
        original=self.original()
        # Download UID is a new caller proposal. Source copy/project/timeline
        # anchors must match; it is not an authentication credential or commit.
        for number in WIDTHS:
            if number!=3 and values[number]!=original[number]:raise ImageError('download_changelog_source_value_mismatch')


class DownloadChangelog:
    def __init__(self):
        self._values=MappingProxyType({});self._binding=None;self._digest=None;self._configured=False

    def _effect(self):return hashlib.sha256(repr((tuple(sorted(self._values.items())),self._binding,self._configured)).encode()).hexdigest()

    def validate(self,bindings):
        if not self._values:
            if self._binding is not None or self._digest is not None or self._configured is not False:
                raise ImageError('download_changelog_effect_changed')
            return
        if bindings is None or bindings.stamp()!=self._binding:raise ImageError('download_changelog_binding_changed')
        if self._effect()!=self._digest or type(self._configured) is not bool:raise ImageError('download_changelog_effect_changed')
        original=bindings.original()
        if (self._values.keys()!=original.keys() or self._values[6]!=struct.pack('<H',1000)
                or any(type(v) is not bytes or len(v)!=len(original[n]) for n,v in self._values.items())):
            raise ImageError('download_changelog_header_profile')
        expected={**original,6:struct.pack('<H',1000)}
        if self._configured:expected[3]=self._values[3]
        if dict(self._values)!=expected:raise ImageError('download_changelog_source_value_mismatch')

    def create(self,payload,bindings):
        self.validate(bindings)
        if type(payload) is not bytes or payload!=CREATE:raise ImageError('download_changelog_create_profile')
        if not self._values:
            proposal=DownloadChangelog();proposal._binding=bindings.stamp()
            proposal._values=MappingProxyType({**bindings.original(),6:struct.pack('<H',1000)})
            proposal._digest=proposal._effect();proposal.validate(bindings)
            self._values,self._binding,self._digest=proposal._values,proposal._binding,proposal._digest
        return struct.pack('<II',1,ADDRESS)

    def configure(self,payload,bindings):
        self.validate(bindings)
        if not self._values:raise ImageError('download_changelog_create_required')
        values=attributes(payload);bindings.check(values)
        if self._configured and any(self._values[n]!=v for n,v in values.items()):
            raise ImageError('download_changelog_proposal_already_configured')
        proposal=DownloadChangelog();proposal._binding=self._binding;proposal._configured=True
        proposal._values=MappingProxyType({**self._values,**values});proposal._digest=proposal._effect();proposal.validate(bindings)
        self._values,self._configured,self._digest=proposal._values,proposal._configured,proposal._digest
        return struct.pack('<H',len(values))+b''.join(struct.pack('<HH',n,0) for n in values)

    def read(self,bindings):
        self.validate(bindings)
        if not self._values:raise ImageError('download_changelog_create_required')
        return dict(self._values)

    def require_configured(self,bindings):
        self.validate(bindings)
        if not self._configured:raise ImageError('download_changelog_configuration_required')

    def resolve(self,address,bindings):
        if type(address) is not int or address!=ADDRESS:raise ImageError('download_changelog_address_unavailable')
        return self.read(bindings)

    def description(self):
        return dict(created=bool(self._values),configured=self._configured,attributes=len(self._values),
            parameter6=1000 if self._values else None,parameter6_units='uninterpreted',modeled_handle=True,
            source_anchors_verified=self._configured,download_uid_proposed=self._configured,
            physical_address_imported=False,records_logged=0,active_correlation_changed=False,
            native_authentication=False,owner_only=True,commit=False,payloads_exposed=False)
