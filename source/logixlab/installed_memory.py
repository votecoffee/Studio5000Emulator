"""Narrow native online DINT reads at installed model value addresses.

The observed UserMemory request names a retained download address and one
word. Only an exact backed scalar DINT is served. No host/native memory,
allocation, pointer traversal, arbitrary ranges or writes are available.
"""
from .download_image import ImageError
from .download_headers import HeaderBindings


def read_dint(app,router,address,words):
    if type(address) is not int or not 0<=address<=0xFFFFFFFF or type(words) is not int or words!=1:
        raise ImageError('installed_memory_scalar_dint_request_required')
    engine=app.engine;project=engine.project;installed=getattr(engine,'installed_download',None)
    if not router.endpoint.native_read_only or installed is None:
        raise ImageError('installed_memory_committed_download_required')
    installed.check(app.native_project_identity,project)
    ns=installed.namespace
    ns.validate_base(ns._source,app.native_types,native_symbols=app.native_symbols,native_routines=app.native_routines,
        native_auxiliary_symbols=app.native_auxiliary_symbols,native_tables=app.native_tables)
    headers=HeaderBindings(engine,ns,app.native_symbols,app.native_routines,app.native_auxiliary_symbols,app.native_tasks,app.native_tables)
    if ns._incremental is None:raise ImageError('installed_memory_headers_required')
    ns._incremental.verify_effects(ns._image,ns._source,app.native_metadata_values,headers)
    installed.values.validate(headers,app.native_types)
    handles=[row for row in ns._tables if row.value_address==address]
    if len(handles)!=1:raise ImageError('installed_memory_value_address_unavailable')
    rows=[row for row in installed.values.values if row[1]==handles[0].instance]
    if len(rows)!=1:raise ImageError('installed_memory_ordinary_tag_required')
    key,table,code,initial=rows[0];tag=project.tags.get(key)
    if (tag is None or tag.dtype.upper()!='DINT' or tag.constant or tag.alias or tag.problem or tag.tag_class!='Standard'
            or code!=0xC4 or len(initial)!=4):raise ImageError('installed_memory_scalar_dint_required')
    symbol=app.native_symbols.by_key.get(key)
    if symbol is None or ns._image._symbols.get((symbol.program_instance,symbol.instance))!=table:
        raise ImageError('installed_memory_symbol_binding_changed')
    router.access(tag.key)
    cell=router.scalar_storage().by_ref.get(key)
    if cell is None or cell.code!=0xC4 or cell.aggregate or cell.size!=4:
        raise ImageError('installed_memory_current_storage_unavailable')
    value=cell.value(engine.memory.read)
    if len(value)!=4:raise ImageError('installed_memory_current_value_unavailable')
    return value
