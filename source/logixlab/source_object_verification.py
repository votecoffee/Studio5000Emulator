"""Compare temporary download identities with the original source bindings.

TagInfo can omit internal Symbols. Unknown Symbols stay unresolved; they are
never assigned names or treated as a complete source match. This checks IDs,
not native Table addresses, compiled routines, values or install authority.
"""
import hashlib
import json
from .native_symbols import NativeSymbols
from .native_routines import NativeRoutines
from .native_auxiliary_symbols import NativeAuxiliarySymbols
from .model import ModelError


def summary(status='idle',*,programs=0,routines=0,symbols=0,auxiliary=0,unresolved=0,errors=()):
    return dict(status=status,programs_matched=programs,routines_matched=routines,symbols_matched=symbols,
                auxiliary_symbols_matched=auxiliary,symbols_unresolved=unresolved,errors=list(errors),identity_checks_only=True,
                table_identities_verified=False,compiled_code_verified=False,addresses_verified=False,
                install_authority=False,active_catalog_replaced=False,commit=False)


def binding_stamp(symbols,routines,auxiliary=None):
    """Detect replacement or in-place mutation of a cached source manifest."""
    result=[]
    for value,kind in ((symbols,NativeSymbols),(routines,NativeRoutines),(auxiliary,NativeAuxiliarySymbols)):
        if value is None:result.append(None)
        elif not isinstance(value,kind):raise ValueError('invalid_native_object_binding')
        else:
            manifest=value.manifest()
            if isinstance(value,NativeSymbols):
                manifest={**manifest,'program_map':sorted(value.programs.items()),'program_ids':sorted(value.program_ids.items())}
            raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode('utf-8')
            result.append(hashlib.sha256(raw).hexdigest())
    return tuple(result)


def verify(objects,source,symbols=None,routines=None,auxiliary=None):
    """Verify the complete observed Program/Routine and known Symbol ID sets.

    The caller binds source to its current original ACD and L5X pair. A missing
    optional catalog leaves verification unavailable. Missing known Symbols or
    extra/missing Program/Routine IDs are mismatches, not partial successes.
    """
    if source is None:
        return summary('unavailable',unresolved=len(objects.symbols))
    if any(value is not None and (not isinstance(value,kind)
            or (value.source_acd_sha256,value.source_l5x_sha256)!=(source.acd_sha256,source.l5x_sha256))
           for value,kind in ((symbols,NativeSymbols),(routines,NativeRoutines),(auxiliary,NativeAuxiliarySymbols))):
        return summary('mismatch',errors=('native_object_source_mismatch',))
    if symbols is None or routines is None:
        return summary('unavailable',unresolved=len(objects.symbols))
    if symbols.program_inventory_error is not None:
        return summary('unavailable',unresolved=len(objects.symbols))
    expected_programs=set(symbols.program_ids)
    if (set(symbols.programs.values())!=expected_programs
            or any(symbols.program_ids.get(instance)!=name for name,instance in symbols.programs.items())
            or any(routines_row.program_instance not in expected_programs
                   or symbols.programs.get(routines_row.program.casefold())!=routines_row.program_instance
                   for routines_row in routines.rows)
            or any(s.program_instance and symbols.programs.get(s.scope.casefold())!=s.program_instance
                   for s in symbols.by_key.values())):
        return summary('mismatch',errors=('native_object_parent_mismatch',))
    expected_routines={(r.program_instance,r.instance) for r in routines.rows}
    expected_symbols={(s.program_instance,s.instance) for s in symbols.by_key.values()}
    auxiliary_ids=set()
    if auxiliary is not None:
        try:auxiliary.require_parents(symbols)
        except ModelError:return summary('mismatch',errors=('native_auxiliary_symbol_binding_mismatch',))
        auxiliary_ids=set(auxiliary.by_instance)
    staged_programs=set(objects.programs)
    staged_routines={(r.program,r.instance) for r in objects.routines}
    staged_symbols={(s.program,s.instance) for s in objects.symbols}
    errors=[]
    if staged_programs!=expected_programs:errors.append('native_program_identity_mismatch')
    if staged_routines!=expected_routines:errors.append('native_routine_identity_mismatch')
    if expected_symbols-staged_symbols:errors.append('native_symbol_identity_missing')
    if auxiliary_ids-staged_symbols:errors.append('native_auxiliary_symbol_identity_missing')
    unresolved=len(staged_symbols-expected_symbols-auxiliary_ids)
    return summary('mismatch' if errors else 'partial' if unresolved else 'matched',
        programs=len(staged_programs&expected_programs),routines=len(staged_routines&expected_routines),
        symbols=len(staged_symbols&(expected_symbols|auxiliary_ids)),auxiliary=len(staged_symbols&auxiliary_ids),
        unresolved=unresolved,errors=errors)
