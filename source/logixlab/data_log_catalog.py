"""Read-only discovery when complete source has no trends or data logs.

This software controller has no native Data Logging engine or log storage.
Source declarations must not disappear when the runtime ignores those objects.
"""
from dataclasses import dataclass
import struct
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class DataLogCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        sections = set()
        for section_name in ('Trends','DataLogs'):
            found = controller.findall(section_name)
            if len(found)>1:
                return cls(False)
            for section in found:
                if (len(section) or (section.text or '').strip() or set(section.attrib)-{'Use'}
                        or section.get('Use') not in (None,'Target')):
                    return cls(False)
                sections.add(section)
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if any(word in name for word in ('trend', 'datalog')) and (
                    node not in sections or node.tag not in ('Trends','DataLogs')):
                return cls(False)
            if any(word in node.get('DataType', '').lower() for word in ('trend', 'datalog')):
                return cls(False)
            if any(word in node.get('Format', '').lower() for word in ('encoded', 'encrypted', 'protected')):
                return cls(False)
            if any(word in name for word in ('encoded', 'encrypted', 'protected')) or any(
                    any(word in key.lower() for word in ('trend', 'datalog', 'encoded', 'encrypted', 'protected'))
                    for key in node.attrib):
                return cls(False)
        return cls(True)

    def class_attributes(self):
        # Revision UINT; maximum/count and storage/capacity limits UDINT.
        return {1:struct.pack('<H',1),
                **({number:bytes(4) for number in (2,3,10,11,12,13,14,15)} if self.empty else {})}

    def description(self):
        return {'class_id':0x71, 'object_revision':1, 'empty_catalog_available':self.empty,
                'instance_count':0 if self.empty else None, 'instance_list':self.empty,
                'storage_bytes':0 if self.empty else None, 'native_logging_engine':False,
                'configured_log_upload':False,
                'source':'Complete L5X without trends, data logs or protected configuration'}
