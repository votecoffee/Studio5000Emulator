"""Native word reads at exact installed model value allocations.

Scalars keep their observed word widths. Word-aligned aggregates require the
complete allocation, verified source/layout and current accessible value bytes.
No host/native memory, pointer traversal, arbitrary ranges or writes exist.
"""
import struct

from .download_image import ImageError
from .download_headers import HeaderBindings
from .data_table import MAX_ARRAY_BYTES
from .model import ModelError,coerce
from .templates import ATOMS,MAX_BYTES

CONSTANT_ATOMS=frozenset(('BOOL',*ATOMS))


def scalar_word(dtype,code,value,words=1):
    """Exact scalar bytes; smaller one-word values have explicit zero padding."""
    if type(words) is not int or words not in (1,2):raise ImageError('installed_memory_scalar_word_request_required')
    if not isinstance(value,bytes):raise ImageError('installed_memory_current_value_unavailable')
    if dtype=='LINT' and code==0xC5 and len(value)==8 and words==2:return value
    if words!=1:raise ImageError('installed_memory_scalar_word_request_required')
    if (dtype,code,len(value)) in (('SINT',0xC2,1),('INT',0xC3,2)):return value+bytes(4-len(value))
    if dtype=='DINT' and code==0xC4 and len(value)==4:return value
    if dtype=='REAL' and code==0xCA and len(value)==4:return value
    if dtype=='BOOL' and code==0xC1 and value in (b'\0',b'\1'):return value+bytes(3)
    raise ImageError('installed_memory_scalar_word_required')


def constant_keys(app,router):
    """Candidate atomic/explicit UDT roots; each read still verifies all effects."""
    engine=app.engine;project=engine.project;installed=getattr(engine,'installed_download',None)
    if not router.endpoint.native_read_only or installed is None:return frozenset()
    try:installed.check(app.native_project_identity,project)
    except ImageError:return frozenset()
    return frozenset(key for key,table,code,data in installed.values.values if 1<=len(data)<=MAX_BYTES
        and (tag:=project.tags.get(key)) is not None and tag.constant
        and (tag.dtype.upper() in CONSTANT_ATOMS or tag.dtype.casefold() in project.udts)
        and not tag.alias and not tag.problem and tag.tag_class=='Standard')


def read_constant(app,router,key):
    """Read one complete source-backed constant root without exposing a setter."""
    if key not in constant_keys(app,router):raise ImageError('installed_constant_root_required')
    installed,ns=_verified_installation(app,router)
    rows=[row for row in installed.values.values if row[0]==key]
    if len(rows)!=1:raise ImageError('installed_constant_binding_required')
    _,table,code,initial=rows[0]
    handles=[row for row in ns._tables if row.key==table]
    if len(handles)!=1:raise ImageError('installed_constant_value_address_required')
    tag,cell=_bound_cell(app,router,installed,ns,key,table,code)
    if not tag.constant or cell.size!=len(initial):raise ImageError('installed_constant_storage_changed')
    def read(ref):
        router.access(ref)
        return app.engine.memory.read(ref)
    try:value=cell.value(read)
    except ModelError as error:raise ImageError('installed_constant_current_value_unavailable') from error
    if value!=initial:raise ImageError('installed_constant_source_value_changed')
    return value


def table_ids(app,router):
    """Committed Table identities are independent of scoped Symbol identities."""
    if not router.endpoint.native_read_only or getattr(app.engine,'installed_download',None) is None:
        return None
    installed,ns=_verified_installation(app,router)
    return _table_ids(app,installed,ns)


def _table_ids(app,installed,ns):
    """Reuse this read's complete verification, never a previous request's result."""
    if installed is not getattr(app.engine,'installed_download',None) or installed.namespace is not ns:
        raise ImageError('installed_memory_committed_download_changed')
    installed.check(app.native_project_identity,app.engine.project)
    result={};seen=set()
    for key,table,code,initial in installed.values.values:
        symbol=app.native_symbols.by_key.get(key) if app.native_symbols is not None else None
        parent,instance=table if isinstance(table,tuple) else (0,table)
        if (symbol is None or symbol.program_instance!=parent or key in result or (parent,instance) in seen
                or ns._image._symbols.get((parent,symbol.instance))!=table
                or not any(row.key==table for row in ns._tables)):
            raise ImageError('installed_table_symbol_binding_changed')
        result[key]=instance;seen.add((parent,instance))
    return result


def _verified_installation(app,router):
    engine=app.engine;project=engine.project;installed=getattr(engine,'installed_download',None)
    if not router.endpoint.native_read_only or installed is None:
        raise ImageError('installed_memory_committed_download_required')
    installed.check(app.native_project_identity,project)
    ns=installed.namespace
    if getattr(project,'runtime_revision',0) or getattr(project,'runtime_edited_routines',()):
        if installed.tag_bindings is None:raise ImageError('installed_tag_bindings_required')
        installed.tag_bindings.check(app,installed)
        return installed,ns
    ns.validate_base(ns._source,app.native_types,native_symbols=app.native_symbols,native_routines=app.native_routines,
        native_auxiliary_symbols=app.native_auxiliary_symbols,native_tables=app.native_tables)
    headers=HeaderBindings(engine,ns,app.native_symbols,app.native_routines,app.native_auxiliary_symbols,app.native_tasks,app.native_tables)
    if ns._incremental is None:raise ImageError('installed_memory_headers_required')
    ns._incremental.verify_effects(ns._image,ns._source,app.native_metadata_values,headers)
    installed.values.validate(headers,app.native_types)
    return installed,ns


def _bound_cell(app,router,installed,ns,key,table,code):
    tag=app.engine.project.tags.get(key)
    if tag is None or tag.alias or tag.problem or tag.tag_class!='Standard':
        raise ImageError('installed_memory_ordinary_tag_required')
    symbol=app.native_symbols.by_key.get(key)
    if symbol is None or ns._image._symbols.get((symbol.program_instance,symbol.instance))!=table:
        raise ImageError('installed_memory_symbol_binding_changed')
    router.access(tag.key)
    cell=router.scalar_storage(_verified_installation=(installed,ns)).by_ref.get(key)
    instance=table[1] if isinstance(table,tuple) else table
    if cell is None or cell.symbol_id!=symbol.instance or cell.instance!=instance or cell.table_code!=code:
        raise ImageError('installed_memory_current_storage_unavailable')
    return tag,cell


def read_words(app,router,address,words):
    if (type(address) is not int or not 0<=address<=0xFFFFFFFF
            or type(words) is not int or not 1<=words<=MAX_ARRAY_BYTES//4):
        raise ImageError('installed_memory_scalar_word_request_required')
    installed,ns=_verified_installation(app,router)
    handles=[row for row in ns._tables if row.value_address==address]
    if len(handles)!=1:raise ImageError('installed_memory_value_address_unavailable')
    rows=[row for row in installed.values.values if row[1]==handles[0].key]
    if len(rows)!=1:raise ImageError('installed_memory_ordinary_tag_required')
    key,table,code,initial=rows[0];tag,cell=_bound_cell(app,router,installed,ns,key,table,code)
    if tag.constant:
        raise ImageError('installed_memory_scalar_word_required')
    if cell.aggregate:
        # The SDK asks for all words of numeric arrays and predefined roots.
        # Do not expose an interior, partial, padded or cross-allocation range.
        if not 4<=cell.size<=MAX_ARRAY_BYTES or cell.size%4 or len(initial)!=cell.size:
            raise ImageError('installed_memory_complete_word_allocation_required')
        if words!=cell.size//4:raise ImageError('installed_memory_scalar_word_request_required')
        def read(ref):
            router.access(ref)
            return app.engine.memory.read(ref)
        try:value=cell.value(read)
        except ModelError as error:raise ImageError('installed_memory_current_value_unavailable') from error
        if len(value)!=cell.size:raise ImageError('installed_memory_current_storage_unavailable')
        return value
    dtype=tag.dtype.upper();size={('SINT',0xC2):1,('INT',0xC3):2,('DINT',0xC4):4,('LINT',0xC5):8,('REAL',0xCA):4,('BOOL',0xC1):1}.get((dtype,code))
    if size is None or len(initial)!=size:raise ImageError('installed_memory_scalar_word_required')
    if words!=(2 if dtype=='LINT' else 1):raise ImageError('installed_memory_scalar_word_request_required')
    if cell.code!=code or cell.aggregate or cell.size!=size:
        raise ImageError('installed_memory_current_storage_unavailable')
    value=cell.value(app.engine.memory.read)
    return scalar_word(dtype,code,value,words)


def prepare_scalar_write(app,router,program,instance,data):
    """Decode one complete installed scalar; caller commits through store_atomic."""
    from .object_staging import table_key
    if (type(program) is not int or type(instance) is not int or not 0<=program<=0xFFFF
            or not 1<=instance<=0xFFFE or type(data) is not bytes):
        raise ImageError('native_tag_write_table_required')
    installed,ns=_verified_installation(app,router);table=table_key(program,instance)
    rows=[row for row in installed.values.values if row[1]==table]
    if len(rows)!=1:raise ImageError('native_tag_write_backing_required')
    key,table,code,initial=rows[0];tag,cell=_bound_cell(app,router,installed,ns,key,table,code)
    router.access(tag.key,True)
    profile={'BOOL':(0xC1,1,'B'),'SINT':(0xC2,1,'b'),'INT':(0xC3,2,'h'),
             'DINT':(0xC4,4,'i'),'LINT':(0xC5,8,'q'),'REAL':(0xCA,4,'f')}.get(tag.dtype.upper())
    if (tag.constant or profile is None or code!=profile[0] or cell.code!=code or cell.aggregate
            or cell.size!=profile[1] or len(initial)!=profile[1] or len(data)!=profile[1]):
        raise ImageError('native_tag_write_complete_scalar_required')
    dtype=tag.dtype.upper();value=struct.unpack('<'+profile[2],data)[0]
    try:value=coerce(value,dtype)
    except ModelError as error:raise ImageError('native_tag_write_value_invalid') from error
    return dtype,tag.key,value
