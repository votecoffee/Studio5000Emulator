"""Explicit, source-checked identities for local protocol compatibility tests."""
from dataclasses import dataclass
import struct
from .model import ModelError

PROFILES=('research','logix-v35-l85e')


@dataclass(frozen=True)
class Identity:
    profile:str
    vendor:int
    device_type:int
    product_code:int
    major:int
    minor:int
    product_name:str
    serial:int=0x4C4C0001

    @classmethod
    def from_project(cls,profile,project):
        if profile not in PROFILES:raise ModelError('Unknown protocol identity profile')
        if profile=='research':return cls(profile,0xFFFF,0x0E,1,35,1,'LogixLab v35 research target')
        if project.processor!='1756-L85E' or project.version!='35':
            raise ModelError('The experimental L85E profile requires a 1756-L85E v35 project')
        try:minor=int(project.minor_version)
        except (ValueError,TypeError):raise ModelError('Controller minor revision is unknown')
        if not 1<=minor<=255:raise ModelError('Controller minor revision must be 1..255 for the identity profile')
        # 1756-L85E product code 168 is published in Rockwell 1756-UM543.
        # Firmware revision comes from the loaded source, not from that manual.
        return cls(profile,1,0x0E,168,35,minor,'1756-L85E/B')

    def attributes(self):
        name=self.product_name.encode('ascii')
        return {1:struct.pack('<H',self.vendor),2:struct.pack('<H',self.device_type),
                3:struct.pack('<H',self.product_code),4:bytes((self.major,self.minor)),
                5:b'\x00\x00',6:struct.pack('<I',self.serial),7:bytes((len(name),))+name,8:b'\x03'}

    def all_attributes(self):return b''.join(self.attributes()[n] for n in range(1,8))

    def description(self):
        return {'profile':self.profile,'vendor':self.vendor,'device_type':self.device_type,'product_code':self.product_code,
                'revision':{'major':self.major,'minor':self.minor},'product_name':self.product_name,
                'serial':f'{self.serial:08X}','experimental':True,'native_controller_equivalence':'UNVERIFIED'}
