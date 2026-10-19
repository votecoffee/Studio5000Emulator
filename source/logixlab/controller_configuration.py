"""Read-only source configuration, distinct from security enforcement.

The v35 Controller attribute definition identifies attribute 13 as a BITS32
SecurityCode. L5X Security@Code is the legacy RSI Security Server setting;
it neither authenticates a peer nor grants permission to run an operation.
"""
from dataclasses import dataclass
import re
import struct


@dataclass(frozen=True)
class ControllerConfiguration:
    security_code: int | None
    project_name: str
    project_description: str | None
    redundancy_configured: bool | None = None

    @classmethod
    def from_controller(cls, controller):
        elements = controller.findall('Security')
        code = elements[0].get('Code', '') if len(elements) == 1 else ''
        value = int(code) if re.fullmatch(r'[0-9]{1,10}', code) else None
        descriptions = controller.findall('Description')
        description = '' if not descriptions else None
        if len(descriptions) == 1 and not len(descriptions[0]):
            description = descriptions[0].text or ''
        redundancy=controller.findall('RedundancyInfo')
        enabled=redundancy[0].get('Enabled') if len(redundancy)==1 else None
        return cls(value if value is not None and value <= 0xFFFFFFFF else None,
                   controller.get('Name', 'Controller'), description,
                   {'true':True,'false':False}.get(enabled))

    def attributes(self):
        return {13: struct.pack('<I', self.security_code)} if self.security_code is not None else {}

    def compatibility_attributes(self):
        # The software controller has no hardware run-inhibit input and does
        # not implement downloads. These masks describe the model only.
        values={**self.attributes(),7:b'\0\0',26:bytes(4)}
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
                'operator_registration': False, 'authority_services': False}


def metadata_class_attributes():
    """Metadata Definition class with UINT revision and no UDINT instances."""
    return {1: struct.pack('<H', 1), 2: struct.pack('<I', 0), 3: struct.pack('<I', 0)}


def metadata_description():
    return {'object_revision': 1, 'maximum_instance': 0, 'instance_count': 0,
            'metadata_services': False}
