"""Empty simulator tracking group, separate from native membership/signatures.

An L5X conversion may omit native tracking metadata. Absence selects this
emulator's empty-group policy; it is never proof of an untracked original ACD.
Nonempty declarations and hidden/ambiguous input do not select that policy.
"""
from dataclasses import dataclass
import re

from .tag_catalog import complete_tag_source
from .executable_configuration import _hidden
from .program_configuration import SHA256
from .program_diagnostics import signature_free

TRACKABLE=frozenset(('Tag','LocalTag','Routine','Module','AddOnInstructionDefinition'))


@dataclass(frozen=True)
class EmptyComponentTracking:
    source_sha256: str
    policy_available: bool = False

    def __post_init__(self):
        if (not isinstance(self.source_sha256,str) or not SHA256.fullmatch(self.source_sha256)
                or type(self.policy_available) is not bool):raise ValueError('Invalid component-tracking policy')

    @classmethod
    def from_source(cls,root,controller,source_sha256,*,aoi_empty=False,io_empty=False):
        unavailable=cls(source_sha256)
        if (not complete_tag_source(root,controller) or root.get('SchemaRevision')!='1.0'
                or not re.fullmatch(r'35\.[0-9]{2}',root.get('SoftwareRevision',''))
                or controller.get('MajorRev')!='35' or controller.get('ProcessorType')!='1756-L85E'
                or aoi_empty is not True or io_empty is not True or _hidden(root) or not signature_free(root)):
            return unavailable
        for program in controller.findall('./Programs/Program'):
            if (program.get('Class') not in (None,'Standard') or program.get('Type') not in (None,'Normal')
                    or program.get('TestEdits')!='false'):return unavailable
        for node in root.iter():
            local=node.tag.rsplit('}',1)[-1].casefold()
            if any(word in local for word in ('tracking','tracked','statedetection','statechangedetection')):
                return unavailable
            for key,value in node.attrib.items():
                local=key.rsplit('}',1)[-1].casefold()
                if not any(word in local for word in ('tracking','tracked','statedetection','statechangedetection')):continue
                if key!='TrackingGroups' or node.tag not in TRACKABLE or value!='0':return unavailable
        return cls(source_sha256,True)

    def attributes(self,source_sha256,*,idle):
        if source_sha256!=self.source_sha256 or not self.policy_available or idle is not True:return {}
        # The model has no members in either active or test tracking group.
        # No nonempty/native signature calculation or saved hash is inferred.
        return {33:bytes(32),34:bytes(32)}

    def description(self):
        return dict(policy='Empty simulator component-tracking group',policy_available=self.policy_available,
            modeled_tracked_components=0 if self.policy_available else None,attributes=[33,34],signature_bytes=32,
            native_membership_imported=False,native_signatures_imported=False,
            absence_proves_native_membership=False,nonempty_group_calculation=False,
            signature_verification=False,membership_writes=False,tracked_state_msg_service=False)
