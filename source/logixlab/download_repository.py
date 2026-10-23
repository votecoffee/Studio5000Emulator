"""Private device-registration handle for an owning prepared download.

The observed repository record is checked against this software device. It
does not grant operator authority or change the active Extended Device object.
"""
import hashlib
import struct
from .download_image import ImageError
from .download_properties import controller_profile
from .identity import Identity

HANDLE=0x75000001  # Local namespace handle, never a captured repository identity.


def expected(source,project,identity):
    profile=controller_profile(project,source)
    if (not isinstance(identity,Identity) or identity.profile!='logix-v35-l85e'
            or identity.major!=35 or not 0<identity.serial<=0xFFFFFFFF):
        raise ImageError('download_repository_device_identity_required')
    strings=(project.name,f'{identity.serial:08X}',identity.product_name)
    body=struct.pack('<4H',3,1,1,0)
    for text,maximum in zip(strings,(40,8,255),strict=True):
        if not isinstance(text,str) or not text or '\0' in text:
            raise ImageError('download_repository_device_identity_required')
        try:raw=text.encode('utf-16le')
        except UnicodeError as error:raise ImageError('download_repository_device_identity_required') from error
        if len(raw)//2>maximum:raise ImageError('download_repository_device_identity_required')
        body+=struct.pack('<H',len(raw)//2)+raw
    return struct.pack('<II',0x301,len(body))+body,(source,profile,identity)


class DownloadRepository:
    def __init__(self):
        self._record=None;self._binding=None;self._linked=False;self._digest=None

    def _effect(self):
        return hashlib.sha256(repr((self._record,self._binding,self._linked,HANDLE)).encode()).hexdigest()

    def validate(self,source,project,identity):
        if self._binding is None:
            if self._record is not None or self._linked is not False or self._digest is not None:
                raise ImageError('download_repository_effect_changed')
            return
        record,binding=expected(source,project,identity)
        if binding!=self._binding:raise ImageError('download_repository_source_changed')
        if (self._record!=record or type(self._linked) is not bool or self._effect()!=self._digest):
            raise ImageError('download_repository_effect_changed')

    def register(self,payload,source,project,identity):
        self.validate(source,project,identity);record,binding=expected(source,project,identity)
        if type(payload) is not bytes or payload!=record:raise ImageError('download_repository_record_mismatch')
        self._record=record;self._binding=binding;self._digest=self._effect()
        return struct.pack('<I',HANDLE)

    def link(self,payload,source,project,identity):
        self.validate(source,project,identity)
        if self._binding is None:raise ImageError('download_repository_registration_required')
        if type(payload) is not bytes or payload!=struct.pack('<HHI',1,8,HANDLE):
            raise ImageError('download_repository_link_mismatch')
        self._linked=True;self._digest=self._effect()
        return struct.pack('<3H',1,8,0)

    def description(self):
        return dict(registered=self._binding is not None,linked=self._linked,owner_only=True,
            modeled_handle=True,source_bound=self._binding is not None,active_device_changed=False,
            operator_authorization=False,commit=False,payloads_exposed=False)

    def identity_reference(self,source,project,identity):
        self.validate(source,project,identity)
        if not self._linked:raise ImageError('download_repository_link_required')
        return struct.pack('<I',HANDLE)
