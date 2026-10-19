"""Read-only source configuration, distinct from security enforcement.

The v35 Controller attribute definition identifies attribute 13 as a BITS32
SecurityCode. L5X Security@Code is the legacy RSI Security Server setting;
it neither authenticates a peer nor grants permission to run an operation.
"""
from dataclasses import dataclass
import re
import struct
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class ControllerConfiguration:
    security_code: int | None
    project_name: str
    project_description: str | None
    redundancy_configured: bool | None = None
    time_slice: int | None = 20
    share_unused_time_slice: int | None = 1
    time_slice_defaulted: bool = True
    share_unused_defaulted: bool = True
    empty_power_loss_handler: bool = False
    empty_fault_handler: bool = False

    @classmethod
    def from_controller(cls, controller, root=None):
        elements = controller.findall('Security')
        code = elements[0].get('Code', '') if len(elements) == 1 else ''
        value = int(code) if re.fullmatch(r'[0-9]{1,10}', code) else None
        descriptions = controller.findall('Description')
        description = '' if not descriptions else None
        if len(descriptions) == 1 and not len(descriptions[0]):
            description = descriptions[0].text or ''
        redundancy=controller.findall('RedundancyInfo')
        enabled=redundancy[0].get('Enabled') if len(redundancy)==1 else None
        slice_text=controller.get('TimeSlice')
        share_text=controller.get('ShareUnusedTimeSlice')
        time_slice=(20 if slice_text is None else int(slice_text)
                    if re.fullmatch(r'[0-9]{1,2}',slice_text) and 10<=int(slice_text)<=90 else None)
        share=(1 if share_text is None else {'0':0,'1':1}.get(share_text))
        complete=root is not None and complete_tag_source(root,controller)
        def empty_handler(*names):
            # A missing name is meaningful only in a complete source. UId-only
            # or namespaced handler declarations must not be replaced by null.
            names=set(names)
            related={n.lower() for n in names}|{(n+'uid').lower() for n in names}
            for name,value in controller.attrib.items():
                local=name.rsplit('}',1)[-1]
                if local.lower() in related:
                    if name not in names or value:return False
            return complete
        return cls(value if value is not None and value <= 0xFFFFFFFF else None,
                   controller.get('Name', 'Controller'), description,
                   {'true':True,'false':False}.get(enabled),time_slice,share,
                   slice_text is None,share_text is None,
                   empty_handler('PowerLossProgram','PowerUpHandlerProgram'),
                   empty_handler('MajorFaultProgram'))

    def attributes(self):
        return {13: struct.pack('<I', self.security_code)} if self.security_code is not None else {}

    def compatibility_attributes(self):
        # The software controller has no hardware run-inhibit input and does
        # not implement downloads. These masks describe the model only.
        values={**self.attributes(),7:b'\0\0',26:bytes(4)}
        if self.time_slice is not None:values[3]=struct.pack('<H',self.time_slice)
        if self.share_unused_time_slice is not None:values[16]=struct.pack('<H',self.share_unused_time_slice)
        # Anonymous model sessions do not own a multi-workstation edit slot.
        values[8]=bytes(2)
        # Source absence is known, but the native handler-reference wire
        # encoding is unresolved. Do not acknowledge guessed null pointers.
        if self.redundancy_configured is not None:values[9]=bytes((self.redundancy_configured,))
        return values

    def extended_device_attributes(self):
        values = {}
        for number, text, maximum in ((1, self.project_name, 40), (2, self.project_description, 128)):
            if text is None:
                continue
            try:
                data = text.encode('ascii')
            except UnicodeEncodeError:
                continue
            if len(data) <= maximum:
                values[number] = struct.pack('<H', len(data)) + data
        return values

    def description(self):
        return {'object_revision': 1, 'security_code_available': self.security_code is not None,
                'legacy_security_configured': self.security_code != 0 if self.security_code is not None else None,
                'source': 'Controller/Security@Code', 'security_enforcement': 'NOT IMPLEMENTED',
                'time_slice':self.time_slice,'share_unused_time_slice':self.share_unused_time_slice,
                'time_slice_defaulted':self.time_slice_defaulted,'share_unused_defaulted':self.share_unused_defaulted,
                'compatibility_defaults':{'time_slice':20,'share_unused_time_slice':1},
                'native_time_slice_scheduling':False,
                'empty_power_loss_handler':self.empty_power_loss_handler,'empty_fault_handler':self.empty_fault_handler,
                'handler_reference_encoding':False,
                'handler_execution':False,'multi_workstation_edit_slot':False,
                'operator_registration': False, 'authority_services': False}


def metadata_class_attributes():
    """Metadata Definition class with UINT revision and no UDINT instances."""
    return {1: struct.pack('<H', 1), 2: struct.pack('<I', 0), 3: struct.pack('<I', 0)}


def metadata_description():
    return {'object_revision': 1, 'maximum_instance': 0, 'instance_count': 0,
            'instance_list': True, 'metadata_services': False}


def empty_metadata_query(payload):
    """Recognize bounded read queries for the model's empty definition set.

    The native connection query selects controller attribute 26; project upload
    requests all controller definitions. Unknown selectors/targets and mutation
    opcodes must not receive a successful empty response.
    """
    prefix=struct.pack('<II',0x101,0)
    target=(0xFFFF,0x8E,1,0,0,0,0)
    return payload in (prefix+struct.pack('<8H',1,*target),
                       prefix+struct.pack('<9H',9,*target,26))
