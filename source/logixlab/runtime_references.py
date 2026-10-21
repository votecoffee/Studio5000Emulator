"""Opaque DWORD references backed by this interpreter's live objects.

These addresses belong to the emulator process. They are neither original
controller heap addresses nor machine code, and grant no memory read/write or
execution service. Logical CIP instance IDs remain a separate namespace.
"""
import struct
import threading


_lock = threading.Lock()
_next_address = 0x10000000


def _allocate():
    global _next_address
    with _lock:
        if _next_address > 0xFFFFFFFC:
            raise OverflowError('Emulator object address space exhausted')
        address = _next_address
        _next_address += 4
    return address


class RuntimeReferences:
    """One Engine's object registry; allocations are never reused in-process."""
    def __init__(self, project):
        self._project = project
        self._addresses = {}
        self._objects = {}
        self._reference_catalog = None

    def _current(self, project, kind, key):
        if project is not self._project:
            return None
        if kind == 'program':
            return next((value for name,value in project.programs.items() if name.casefold()==key),None)
        if kind == 'routine':
            return project.routines.get(key)
        if kind == 'task':
            return next((row for row in project.tasks if row['name'].casefold()==key),None)
        if kind == 'symbol' and self._reference_catalog is not None and key.isdecimal():
            return self._reference_catalog.by_instance.get(int(key))
        return None

    def reference(self, project, kind, key):
        """Allocate only for a concrete current Program or Routine object."""
        if not isinstance(key,str):
            return None
        key=key.casefold();target=self._current(project,kind,key)
        if target is None:
            return None
        old=self._addresses.get((kind,key))
        if old is not None and self._objects[old][2] is target:
            return old
        if old is not None:
            del self._objects[old]
        try:address=_allocate()
        except OverflowError:return None
        self._addresses[(kind,key)]=address
        self._objects[address]=(kind,key,target)
        return address

    def resolve(self, project, address, kind):
        """Internal resolution refuses stale objects, foreign projects and kinds."""
        if type(address) is not int:
            return None
        row=self._objects.get(address)
        if row is None or row[0]!=kind:
            return None
        return row[2] if self._current(project,*row[:2]) is row[2] else None

    def program_attributes(self, project, program):
        """Router establishes complete source, native identity and edit guards."""
        if not isinstance(program,str):return {}
        target=self._current(project,'program',program.casefold())
        if target is None or not target.get('main'):return {}
        main=program.casefold()+'/'+target['main'].casefold()
        routine=self._current(project,'routine',main)
        if routine is None or routine.kind!='RLL':return {}
        # Validate both targets before allocating; an unavailable main must not
        # leave a partially advertised Program address.
        routine_address=self.reference(project,'routine',main)
        program_address=self.reference(project,'program',program)
        if routine_address is None or program_address is None:return {}
        return {5:struct.pack('<I',routine_address),16:struct.pack('<I',program_address)}

    def bind_reference_catalog(self,catalog):
        self._reference_catalog=catalog

    def routine_attributes(self,project,program,routine):
        """Header reference and main/subroutine flags for a guarded RLL model."""
        if not isinstance(program,str) or not isinstance(routine,str):return {}
        parent=self._current(project,'program',program.casefold())
        key=(program+'/'+routine).casefold();target=self._current(project,'routine',key)
        if parent is None or not parent.get('main') or target is None or target.kind!='RLL':return {}
        address=self.reference(project,'routine',key)
        if address is None:return {}
        return {8:struct.pack('<I',address),24:struct.pack('<I',0 if routine.casefold()==parent['main'].casefold() else 2)}

    def symbol_addresses(self,project,catalog,row):
        if (project is not self._project or catalog.source_l5x_sha256!=project.sha256 or
                catalog.by_instance.get(row.instance) is not row or
                self._current(project,row.kind,row.target.casefold()) is None):return None
        self.bind_reference_catalog(catalog)
        value=self.reference(project,row.kind,row.target)
        header=self.reference(project,'symbol',str(row.instance))
        return (value,header) if value is not None and header is not None else None

    def description(self):
        return {'attributes':[5,16],'address_bits':32,'alignment':4,
                'routine_attributes':[8,24],'routine_header_reference_backed':True,
                'backing':'Live interpreter Program, Routine, Task and validated reference Symbol objects',
                'scope':'Current Engine in this emulator process',
                'allocated_objects':len(self._objects),'addresses_reused':False,
                'logical_ids_used_as_addresses':False,'physical_addresses_imported':False,
                'native_machine_code':False,'memory_services':False,'native_upload_acceptance':False}
