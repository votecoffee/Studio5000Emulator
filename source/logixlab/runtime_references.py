"""Opaque DWORD references backed by this interpreter's live objects.

These addresses belong to the emulator process. They are neither original
controller heap addresses nor machine code, and grant no memory read/write or
execution service. Logical CIP instance IDs remain a separate namespace.
"""
import struct
import threading


_lock = threading.Lock()
_next_address = 0x10000000
ALIGNMENT = 8


def _allocate():
    global _next_address
    with _lock:
        address = (_next_address + ALIGNMENT - 1) & -ALIGNMENT
        if address > 0xFFFFFFFF - (ALIGNMENT - 1):
            raise OverflowError('Emulator object address space exhausted')
        _next_address = address + ALIGNMENT
    return address


class RuntimeReferences:
    """One Engine's object registry; allocations are never reused in-process."""
    def __init__(self, project):
        self._project = project
        self._source_sha256 = getattr(project,'sha256',None)
        self._addresses = {}
        self._objects = {}
        self._reference_catalog = None
        self._scoped_reference_catalog = None
        # Slots are owned by this interpreter registry, independently of CIP
        # identities and DWORD references. Replacing/reordering Tasks revokes
        # this registration; a new Engine creates its own registry.
        tasks=project.tasks
        names=[row['name'].casefold() for row in tasks]
        self._task_slots=tuple(zip(names,tasks)) if len(tasks)<=32 and len(set(names))==len(names) else ()

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
        if kind=='scoped_symbol' and self._scoped_reference_catalog is not None:
            parts=key.split(':')
            if len(parts)==2 and all(part.isdecimal() for part in parts):
                return self._scoped_reference_catalog.by_scope.get(tuple(map(int,parts)))
        if (kind == 'io_map' and key=='local' and self._source_sha256 is not None
                and getattr(project,'sha256',None)==self._source_sha256):
            from .io_map import IOMap
            target=getattr(project,'io_map',None)
            if (isinstance(target,IOMap) and target.empty is True
                    and type(target.root_link_port) is int and target.root_link_port==1
                    and type(target.root_link_address) is int and target.root_link_address==0):return target
        return None

    def reference(self, project, kind, key):
        """Allocate only for a concrete current interpreter object."""
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
            del self._addresses[(kind,key)]
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

    def _no_main_inventory(self,project,program):
        names=project.executable_configuration.routine_names(program,source_sha256=project.sha256)
        routines=[row for row in project.routines.values() if row.program.casefold()==program.casefold()]
        return (project.program_diagnostics.has_no_main(program,source_sha256=project.sha256) and names is not None
                and {name.casefold() for name in names}=={row.name.casefold() for row in routines}
                and all(row.kind=='RLL' for row in routines))

    def program_attributes(self, project, program):
        """Router establishes complete source, native identity and edit guards."""
        if not isinstance(program,str):return {}
        target=self._current(project,'program',program.casefold())
        if target is None:return {}
        if not target.get('main'):
            if not self._no_main_inventory(project,program):return {}
            address=self.reference(project,'program',program)
            return {5:bytes(4),16:struct.pack('<I',address)} if address is not None else {}
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

    def bind_scoped_reference_catalog(self,catalog):
        self._scoped_reference_catalog=catalog

    def io_map_attributes(self,project,identity=None):
        """Canonical Local link metadata and a backed software Map Address."""
        target=self._current(project,'io_map','local')
        if target is None:return {}
        values={9:struct.pack('<H',target.root_link_port),10:struct.pack('<I',target.root_link_address)}
        if identity is not None:
            from .identity import Identity
            from .model import ModelError
            if isinstance(identity,Identity) and identity.profile=='logix-v35-l85e':
                key=tuple(getattr(identity,name) for name in ('vendor','device_type','product_code','major','minor'))
                try:expected=Identity.from_project(identity.profile,project)
                except ModelError:expected=None
                if (expected is not None and all(type(value) is int for value in key) and key==target.local_identity
                        and key==tuple(getattr(expected,name) for name in ('vendor','device_type','product_code','major','minor'))):
                    values[2]=struct.pack('<HHHBB',*key)
        address=self.reference(project,'io_map','local')
        if address is not None:values[13]=struct.pack('<I',address)
        return values

    def task_attributes(self,project,task):
        """Router establishes the current complete single-Task model and source."""
        address=self.reference(project,'task',task)
        values={11:struct.pack('<I',address)} if address is not None else {}
        slot=self.task_slot(project,task)
        if slot is not None:values[16]=struct.pack('<I',slot)
        return values

    def resolve_task_slot(self,project,slot):
        """Resolve only this registry's unchanged current Task allocation."""
        if (project is not self._project or type(slot) is not int or not 0<=slot<len(self._task_slots)
                or len(project.tasks)!=len(self._task_slots)
                or any(row is not registered or row['name'].casefold()!=name
                       for row,(name,registered) in zip(project.tasks,self._task_slots))):return None
        return self._task_slots[slot][1]

    def task_slot(self,project,task):
        if not isinstance(task,str):return None
        slot=next((i for i,(name,_) in enumerate(self._task_slots) if name==task.casefold()),None)
        return slot if slot is not None and self.resolve_task_slot(project,slot) is not None else None

    def routine_attributes(self,project,program,routine):
        """Header reference and main/subroutine flags for a guarded RLL model."""
        if not isinstance(program,str) or not isinstance(routine,str):return {}
        parent=self._current(project,'program',program.casefold())
        key=(program+'/'+routine).casefold();target=self._current(project,'routine',key)
        if parent is None or target is None or target.kind!='RLL':return {}
        if not parent.get('main') and not self._no_main_inventory(project,program):return {}
        address=self.reference(project,'routine',key)
        if address is None:return {}
        return {8:struct.pack('<I',address),24:struct.pack('<I',0 if routine.casefold()==parent.get('main','').casefold() else 2)}

    def symbol_addresses(self,project,catalog,row):
        parent=getattr(row,'program_instance',0)
        bound=catalog.by_scope.get((parent,row.instance)) if parent else catalog.by_instance.get(row.instance)
        if (project is not self._project or catalog.source_l5x_sha256!=project.sha256 or
                bound is not row or
                self._current(project,row.kind,row.target.casefold()) is None):return None
        if parent:self.bind_scoped_reference_catalog(catalog)
        else:self.bind_reference_catalog(catalog)
        value=self.reference(project,row.kind,row.target)
        header=self.reference(project,'scoped_symbol' if parent else 'symbol',f'{parent}:{row.instance}' if parent else str(row.instance))
        return (value,header) if value is not None and header is not None else None

    def description(self):
        return {'attributes':[5,16],'address_bits':32,'alignment':ALIGNMENT,
                'routine_attributes':[8,24],'routine_header_reference_backed':True,
                'task_attributes':[11,16],'task_reference_backed':True,
                'io_map_attributes':[9,10,13],'io_map_reference_backed':True,
                'io_map_identity_attribute':2,'io_map_identity_requires_explicit_source':True,
                'task_slots':len(self._task_slots),'task_slot_limit':32,'task_slot_bits':32,
                'task_slot_backing':'Current interpreter registry in declaration order',
                'logical_ids_used_as_slots':False,'physical_task_slots_imported':False,
                'backing':'Live interpreter Program, Routine, Task, canonical Local I/O Map and validated reference Symbol objects',
                'scope':'Current Engine in this emulator process',
                'allocated_objects':len(self._objects),'addresses_reused':False,
                'logical_ids_used_as_addresses':False,'physical_addresses_imported':False,
                'native_machine_code':False,'memory_services':False,'native_upload_acceptance':False}
