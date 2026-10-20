"""Read-only empty SFC force state for complete, visibly non-SFC source.

The model has no SFC force engine. A source-bound absence check permits null
list addresses without inventing a force list for unsupported chart content.
"""
from dataclasses import dataclass
from .tag_catalog import complete_tag_source


@dataclass(frozen=True)
class ProgramForces:
    source_complete: bool = False
    empty_programs: frozenset[str] = frozenset()
    controller_empty: bool = False

    @classmethod
    def from_source(cls, root, controller):
        if not complete_tag_source(root, controller):
            return cls()
        declarations = {'programs': 'Programs', 'program': 'Program',
                        'routines': 'Routines', 'routine': 'Routine'}
        for node in controller.iter():
            local = node.tag.rsplit('}', 1)[-1].lower()
            if local in declarations and (node.tag != declarations[local]
                    or node.get('Use') not in (None, 'Target')):
                return cls()
        programs = controller.findall('./Programs/Program')
        names = [program.get('Name', '').casefold() for program in programs]
        if not all(names) or len(set(names)) != len(names):
            return cls()

        def visibly_non_sfc(element):
            for node in element.iter():
                local = node.tag.rsplit('}', 1)[-1].lower()
                if any(word in local for word in ('sfc', 'force', 'encoded', 'encrypted', 'protected')):
                    return False
                if any(any(word in name.lower() for word in ('encoded', 'encrypted', 'protected'))
                       for name in node.attrib):
                    return False
                if local == 'program':
                    containers = node.findall('Routines')
                    if len(containers) > 1:
                        return False
                    routines = node.findall('./Routines/Routine')
                    names = [routine.get('Name', '').casefold() for routine in routines]
                    if not all(names) or len(set(names)) != len(names):
                        return False
                    for field in ('MainRoutineName', 'FaultRoutineName'):
                        if node.get(field) and node.get(field).casefold() not in names:
                            return False
                if local == 'routines' and any(child.tag != 'Routine' for child in node):
                    return False
                if local == 'routine':
                    if node.get('Type') not in ('RLL', 'ST', 'FBD'):
                        return False
            return True

        empty = frozenset(name for name, program in zip(names, programs) if visibly_non_sfc(program))
        return cls(True, empty, visibly_non_sfc(controller))

    def attributes(self, program=None):
        available = self.controller_empty if program is None else program.casefold() in self.empty_programs
        # v35 Program attributes: UINT enable state, two null ACADDR DWORDs.
        return {15: bytes(2), 24: bytes(4), 25: bytes(4)} if available else {}

    def description(self):
        return {'source_complete': self.source_complete, 'controller_empty': self.controller_empty,
                'source_checked_empty_programs': len(self.empty_programs),
                'source': 'Complete visible non-SFC L5X routine declarations',
                'attributes': sorted(self.attributes()), 'sfc_force_engine': False,
                'force_writes': False, 'physical_force_state_imported': False}
