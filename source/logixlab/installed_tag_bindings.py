"""Validated ordinary tag bindings preserved through routine-only edits.

Only tag schema, committed table identities and original Symbol headers are
retained. Current values still come from interpreter memory. Historical routine
headers and compiled components are never made current by this read view.
"""
from dataclasses import dataclass,field,replace
import hashlib
import struct

from .download_image import ImageError

LAYOUT=('tags','initial','udts','programs','tasks')


def layout(project):return tuple(getattr(project,name) for name in LAYOUT)
def digest(value):return hashlib.sha256(repr(value).encode()).hexdigest()


@dataclass(frozen=True)
class Binding:
    key:str=field(repr=False)
    symbol:tuple
    table:object
    value_address:int
    code:int
    control:bytes=field(repr=False)
    header:tuple=field(repr=False)
    region:str


def bindings(namespace,values,symbols):
    stage=namespace._incremental
    if stage is None or symbols is None:raise ImageError('installed_tag_headers_required')
    result=[]
    for key,table,code,initial in values.values:
        row=symbols.by_key.get(key)
        if row is None:raise ImageError('installed_tag_symbol_changed')
        scope=(row.program_instance,row.instance)
        handles=[h for h in namespace._tables if h.key==table]
        header=stage._headers.get((0x6B,*scope));region=stage._tables.get(table,namespace._image._regions.get(table))
        if (namespace._image._symbols.get(scope)!=table or len(handles)!=1 or header is None or region is None
                or region.type_code!=code or region.data!=initial):
            raise ImageError('installed_tag_table_changed')
        fields=dict(header);control=fields.get(6)
        if (fields.get(2)!=struct.pack('<H',code) or type(control) is not bytes or len(control)!=4):
            raise ImageError('installed_tag_header_changed')
        result.append(Binding(key,scope,table,handles[0].value_address,code,control,header,digest(region)))
    return tuple(result)


@dataclass(frozen=True)
class Snapshot:
    project:object=field(repr=False)
    revision:int
    references:tuple=field(repr=False)
    shape:str
    namespace:object=field(repr=False)
    source:object=field(repr=False)
    incremental:object=field(repr=False)
    values:object=field(repr=False)
    rows:tuple=field(repr=False)

    @classmethod
    def prepare(cls,headers,values,native_types,metadata):
        ns=headers.namespace;project=headers._project()
        if ns._incremental is None:raise ImageError('installed_tag_headers_required')
        ns._incremental.verify_effects(ns._image,ns._source,metadata,headers)
        values.validate(headers,native_types)
        refs=layout(project)
        return cls(project,0,refs,digest(refs),ns,ns._source,ns._incremental,values,bindings(ns,values,headers.symbols))

    def check_layout(self,project):
        refs=layout(project);revision=getattr(project,'runtime_revision',0)
        if (project is not self.project or type(revision) is not int or revision!=self.revision
                or any(current is not original for current,original in zip(refs,self.references,strict=True))
                or digest(refs)!=self.shape):
            raise ImageError('installed_tag_layout_changed')
        edited=getattr(project,'runtime_edited_routines',())
        if (type(edited) is not tuple or bool(edited)!=(self.revision>0)
                or any(type(key) is not str or key not in project.routines for key in edited)):
            raise ImageError('installed_tag_edit_inventory_changed')

    def after_edit(self,previous,project):
        self.check_layout(previous)
        result=replace(self,project=project,revision=self.revision+1)
        result.check_layout(project)
        return result

    def _check_installation(self,app,installed):
        project=app.engine.project
        self.check_layout(project)
        if (app.engine.mode!='project' or app.engine.memory.project is not project
                or installed.tag_bindings is not self or installed.values is not self.values
                or installed.namespace is not self.namespace or self.namespace._source!=self.source
                or self.namespace._incremental is not self.incremental):
            raise ImageError('installed_tag_binding_changed')

    def check_metadata(self,app,installed):
        """Declarations/catalogs only; metadata never reads transfer RAM effects."""
        self._check_installation(app,installed)
        self.namespace.validate_catalogs(self.source,app.native_types,native_symbols=app.native_symbols,
            native_routines=app.native_routines,native_auxiliary_symbols=app.native_auxiliary_symbols,native_tables=app.native_tables)

    def check(self,app,installed):
        self._check_installation(app,installed)
        ns=self.namespace
        ns.validate_base(self.source,app.native_types,native_symbols=app.native_symbols,native_routines=app.native_routines,
            native_auxiliary_symbols=app.native_auxiliary_symbols,native_tables=app.native_tables)
        if bindings(ns,self.values,app.native_symbols)!=self.rows:
            raise ImageError('installed_tag_binding_changed')

    def control(self,key,code):
        rows=[r for r in self.rows if r.key==key]
        if len(rows)!=1 or rows[0].code!=code:raise ImageError('installed_symbol_type_changed')
        return rows[0].control
