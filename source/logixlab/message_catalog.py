"""Source-checked empty Message object discovery, without MSG execution."""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class MessageCatalog:
    empty: bool

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls(False)
        for node in controller.iter():
            name = node.tag.rsplit('}', 1)[-1].lower()
            if (node.get('DataType', '').upper() == 'MESSAGE'
                    or node.get('Format', '').lower() == 'message'
                    or name == 'messageparameters'):
                return cls(False)
        return cls(True)

    def description(self):
        return {'empty_catalog_available': self.empty,
                'instance_count': 0 if self.empty else None,
                'source': 'complete Controller L5X MESSAGE tags and configuration',
                'instance_list': self.empty, 'message_configuration': False,
                'msg_execution': False}
