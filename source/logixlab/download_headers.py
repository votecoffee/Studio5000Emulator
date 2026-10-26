"""Typed temporary header updates with source names and backed references.

Symbol Control words remain opaque metadata. No flag bits are executed, no
physical addresses are accepted and no update changes the running project.
"""
import hashlib
import struct

from . import device_payload
from .download_image import ImageError
from .object_staging import NULL_REFERENCE

WIDTHS={0x68:{5:4,7:4,9:4,11:2,19:1,27:4,29:1,31:1,32:'children'},
        0x69:{3:2,7:2,12:4},
        0x6B:{1:'string',2:2,3:4,6:4,10:1,11:1,13:'path',14:4},
        0x6D:{1:2,22:'string',23:1,26:1,27:1,28:4}}


def attributes(class_id,payload):
    widths=WIDTHS.get(class_id)
    if widths is None or not isinstance(payload,bytes) or len(payload)<2:
        raise ImageError('download_header_attributes_invalid')
    count=struct.unpack_from('<H',payload)[0];offset=2;result={}
    if count!=len(widths):raise ImageError('download_header_attribute_profile')
    for _ in range(count):
        if offset+2>len(payload):raise ImageError('download_header_attributes_truncated')
        number=struct.unpack_from('<H',payload,offset)[0];offset+=2
        if number not in widths or number in result:raise ImageError('download_header_attribute_profile')
        size=widths[number]
        if not isinstance(size,int):
            need=1 if size=='path' else 2
            if offset+need>len(payload):raise ImageError('download_header_attributes_truncated')
            length=payload[offset] if need==1 else struct.unpack_from('<H',payload,offset)[0]
            if size=='children' and length>1000:raise ImageError('download_header_child_limit')
            size=need+length*(2 if size=='path' else 4 if size=='children' else 1)
        if offset+size>len(payload):raise ImageError('download_header_attributes_truncated')
        result[number]=payload[offset:offset+size];offset+=size
    if offset!=len(payload):raise ImageError('download_header_attributes_trailing')
    return result


def path_key(row):
    leaf=row.scopes[-1];parent=0
    if any(s.attribute is not None or s.symbolic or type(s.instance) is not int or not 1<=s.instance<=0xFFFF for s in row.scopes):
        raise ImageError('download_header_path_invalid')
    if len(row.scopes)==2 and row.scopes[0].class_id==0x68 and leaf.class_id in (0x6B,0x6D):
        parent=row.scopes[0].instance
    elif len(row.scopes)!=1 or leaf.class_id==0x6D:raise ImageError('download_header_parent_required')
    return leaf.class_id,parent,leaf.instance


def reference_path(raw):
    if raw==b'\0':return ()
    try:scopes=device_payload.record_path(raw[1:])
    except device_payload.PayloadError as error:raise ImageError('download_header_logical_reference_invalid') from error
    if len(raw)!=1+2*raw[0] or any(s.attribute is not None or s.symbolic for s in scopes):
        raise ImageError('download_header_logical_reference_invalid')
    return tuple((s.class_id,s.instance) for s in scopes)


class HeaderBindings:
    def __init__(self,engine,namespace,symbols,routines,auxiliary=None,tasks=None,tables=None):
        self.engine=engine;self.namespace=namespace;self.symbols=symbols;self.routines=routines
        self.auxiliary=auxiliary;self.tasks=tasks;self.tables=tables
        self.source=namespace._source

    def _project(self):
        project=self.engine.project
        if (project.sha256!=self.source.l5x_sha256 or getattr(project,'runtime_revision',0)
                or getattr(project,'runtime_edited_routines',()) or self.engine.mode!='project'):
            raise ImageError('download_header_source_changed')
        return project

    def _program(self,instance):
        name=self.symbols.program_ids.get(instance)
        project=self._project()
        if name is None or instance not in self.namespace._image.programs:
            raise ImageError('download_header_program_missing')
        actual=next((n for n in project.programs if n.casefold()==name),None)
        if actual is None:raise ImageError('download_header_program_source_missing')
        return actual

    def _routine(self,program,instance):
        row=self.routines.by_instance.get((program,instance)) if self.routines is not None else None
        project=self._project()
        if (row is None or not any(r.program==program and r.instance==instance for r in self.namespace._image.routines)
                or project.routines.get((row.program+'/'+row.name).casefold()) is None):
            raise ImageError('download_header_routine_missing')
        active=project.routines[(row.program+'/'+row.name).casefold()]
        if active.kind!='RLL' or not project.program_diagnostics.edit_attributes(row.program,source_sha256=project.sha256,idle=True):
            raise ImageError('download_header_rll_source_required')
        return row

    def _routine_address(self,program,instance):
        self._routine(program,instance)
        row=next((r for r in self.namespace._routines if (r.program,r.instance)==(program,instance)),None)
        if row is None:raise ImageError('download_header_routine_reference_missing')
        self.namespace.resolve_routine(row.address)
        return row.address

    def _map_address(self):
        project=self._project();registry=self.engine.runtime_references
        raw=registry.io_map_attributes(project).get(13)
        if (not isinstance(raw,bytes) or len(raw)!=4
                or registry.resolve(project,int.from_bytes(raw,'little'),'io_map') is not project.io_map):
            raise ImageError('download_header_local_map_required')
        return int.from_bytes(raw,'little')

    def expected(self,class_id,program,instance):
        project=self._project();image=self.namespace._image;source=project.sha256
        if class_id==0x6D:
            row=self._routine(program,instance)
            if row.type_word is None or row.source_key is None:raise ImageError('download_header_original_routine_metadata_required')
            values={1:struct.pack('<H',row.type_word),22:struct.pack('<H',len(row.source_key))+row.source_key,
                    23:b'\0',26:b'\0',27:b'\0'}
            values.update(project.program_diagnostics.signature_attributes(row.program,source_sha256=source))
        elif class_id==0x68 and not program:
            name=self._program(instance);values={}
            values.update(project.program_configuration.attributes(name,source_sha256=source))
            values.update(project.program_configuration.flag_attributes(name,source_sha256=source))
            values.update(project.program_diagnostics.output_attributes(name,source_sha256=source))
            values.update(project.program_diagnostics.edit_attributes(name,source_sha256=source,idle=True))
            values.update(project.program_hierarchy.attributes(name,source_sha256=source))
            values.update(project.program_hierarchy.child_attributes(name,source_sha256=source,
                source_acd_sha256=self.source.acd_sha256,program_ids=self.symbols.programs,
                program_source_l5x_sha256=self.symbols.source_l5x_sha256,program_source_acd_sha256=self.symbols.source_acd_sha256))
            main=project.programs[name].get('main','')
            if main:
                routine=self.routines.by_key.get((name.casefold(),main.casefold()))
                if routine is None:raise ImageError('download_header_main_source_missing')
                values[5]=struct.pack('<I',self._routine_address(instance,routine.instance))
            elif project.program_diagnostics.has_no_main(name,source_sha256=source):values[5]=bytes(4)
            if (project.aoi_catalog.empty and not project.aois and not self.engine.blockers
                    and project.executable_configuration.routine_names(name,source_sha256=source) is not None):values[27]=bytes(4)
        elif class_id==0x69 and not program and instance==1:
            self._map_address()
            # Exact Local software-header profile. These opaque configuration
            # scalars do not allocate physical map storage or operate I/O.
            values={3:bytes(2),7:b'\5\0',12:b'\1\0\0\0'}
        elif class_id==0x6B:
            table=image._symbols.get((program,instance))
            if table is None:raise ImageError('download_header_symbol_missing')
            known=next((s for s in self.symbols.by_key.values() if (s.program_instance,s.instance)==(program,instance)),None)
            extra=self.auxiliary.by_instance.get((program,instance)) if self.auxiliary else None
            name=known.name if known else (extra.reference_name or extra.name) if extra else None
            if name is None:raise ImageError('download_header_symbol_name_unavailable')
            if extra is not None and extra.component_type==1288 and name=='__Map:Local':name='Map:Local'
            access=constant=0;logical=();address=0
            if table!=NULL_REFERENCE:
                descriptor=image._tables[table];code=descriptor.type_code
                handle=next(t for t in self.namespace._tables if t.key==table)
                self.namespace.resolve_table(handle.address);address=handle.value_address
                logical=(((0x68,descriptor.program),) if descriptor.program else ())+((0x6A,descriptor.instance),)
                tag=next((t for t in project.tags.values() if t.name==name and t.scope.casefold()==(self._program(program).casefold() if program else '')),None)
                if tag is not None:
                    access={'Read/Write':0,'Read Only':1,'None':2}.get(tag.external_access)
                    if tag.alias or tag.problem or access is None:raise ImageError('download_header_tag_profile_unavailable')
                    constant=int(tag.constant)
            elif name.startswith('Program:') and not program:
                target=name[8:];target_id=self.symbols.programs.get(target.casefold())
                self._program(target_id)
                header=next(p for p in self.namespace._programs if p.instance==target_id)
                self.namespace.resolve_program(header.address);code=0x1068;address=header.address;logical=((0x68,target_id),)
            elif name.startswith('Routine:') and program:
                parent=self._program(program);row=self.routines.by_key.get((parent.casefold(),name[8:].casefold()))
                if row is None:raise ImageError('download_header_routine_symbol_missing')
                address=self._routine_address(program,row.instance);code=0x106D;logical=((0x68,program),(0x6D,row.instance))
            elif name=='Map:Local' and not program:
                code=0x1069;address=self._map_address();logical=((0x69,1),)
            elif name.startswith('Task:') and not program:
                target=name[5:].casefold()
                if (self.tasks is None or (self.tasks.source_acd_sha256,self.tasks.source_l5x_sha256)!=(self.source.acd_sha256,source)
                        or target not in self.tasks.tasks or not any(t['name'].casefold()==target for t in project.tasks)):
                    raise ImageError('download_header_task_symbol_source_missing')
                code=0x1070 # Explicit unresolved Task data address/path in this profile.
            else:raise ImageError('download_header_symbol_reference_unsupported')
            raw=name.encode('ascii')
            values={1:struct.pack('<H',len(raw))+raw,2:struct.pack('<H',code),3:struct.pack('<I',address),
                    6:None,10:bytes((access,)),11:bytes((constant,)),13:logical,14:bytes(4)}
        else:raise ImageError('download_header_scope_unsupported')
        if values.keys()!=WIDTHS[class_id].keys():raise ImageError('download_header_source_fields_unavailable')
        return values

    def stamp(self,image,source):
        if image is not self.namespace._image or source!=self.source:raise ImageError('download_header_image_mismatch')
        self.namespace.validate_base(source,self.namespace._types,native_symbols=self.symbols,native_routines=self.routines,
            native_auxiliary_symbols=self.auxiliary,native_tables=self.tables)
        project=self._project();digest=hashlib.sha256()
        identities=[(0x6B,p,i) for p,i in image._symbols]+[(0x68,0,i) for i in image.programs]
        identities += [(0x6D,r.program,r.instance) for r in image.routines]
        # Only advertise a map when a Local map really exists in this source.
        if project.io_map.root_link_port==1:identities.append((0x69,0,1))
        for key in sorted(identities):
            digest.update(repr(key).encode())
            for number,value in sorted(self.expected(*key).items()):digest.update(repr((number,value)).encode())
        digest.update(repr((id(project),id(project.io_map),[(k,id(v)) for k,v in project.routines.items()])).encode())
        return digest.hexdigest()

    def check(self,row):
        key=path_key(row);values=attributes(key[0],row.request[2+2*row.request[1]:]);expected=self.expected(*key)
        for number,value in values.items():
            if key[0]==0x6B and number==13:
                if reference_path(value)!=expected[number]:raise ImageError('download_header_reference_mismatch')
            elif expected[number] is not None and value!=expected[number]:raise ImageError('download_header_source_value_mismatch')
        return key,tuple(sorted(values.items()))
