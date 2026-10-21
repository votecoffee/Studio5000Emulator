"""Read-only import: native conversion operates on a private, hash-bound copy."""
import hashlib
import json
import os
import shutil
import subprocess
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from .model import ModelError
from .native_project import NativeProjectIdentity
from .native_symbols import NativeSymbols
from .native_types import NativeTypes
from .native_tasks import NativeTasks
from .task_configuration import TaskConfiguration
from .native_routines import NativeRoutines
from .native_aois import NativeAOIs
from .native_aoi_routines import NativeAOIRoutines
from .native_auxiliary_symbols import NativeAuxiliarySymbols
from .aoi_catalog import AOICatalog
from .executable_configuration import ExecutableConfiguration

def default_converter():
    """Resolve optional native tooling without depending on a checkout location."""
    configured = os.environ.get('LOGIXLAB_CONVERTER', '').strip()
    return str(Path(configured).expanduser()) if configured else (shutil.which('l5xgit') or '')


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def convert_acd(source, destination, converter=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    configured = converter or default_converter()
    executable = Path(configured).resolve() if configured else None
    if executable is None or not executable.is_file():
        raise ModelError("ACD import needs the l5xgit converter and installed Studio 5000/SDK. Set its path in Import settings, or load a complete L5X export.")
    if source == destination: raise ModelError("Source and export paths must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_hash = digest(source)
    copied = destination.parent / "import-copy.ACD"
    if source == copied: raise ModelError("Import copy must differ from source")
    shutil.copyfile(source, copied)
    try:
        result = subprocess.run([str(executable), "acd2l5x", "--acd", str(copied), "--l5x", str(destination)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=240, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as e:
        raise ModelError("Native ACD conversion timed out after 240 seconds; see the private import workspace") from e
    log = result.stdout + "\n" + result.stderr
    (destination.parent / "conversion.log").write_text(log, encoding="utf-8")
    if digest(source) != original_hash: raise ModelError("Source hash changed during import")
    if result.returncode or not destination.is_file() or not destination.stat().st_size:
        raise ModelError("Native conversion failed. Studio 5000/SDK version or activation may be unavailable.\n" + log[-5000:])
    manifest = {"utc": datetime.now(timezone.utc).isoformat(), "method": "Rockwell SDK via l5xgit acd2l5x",
                "original_filename": source.name, "original_acd_sha256": original_hash,
                "original_unchanged": True, "private_copy_after_conversion_sha256": digest(copied),
                "l5x_sha256": digest(destination), "converter": str(executable),
                "converter_sha256": digest(executable), "exit_code": result.returncode}
    try:
        manifest['native_project_identity'] = NativeProjectIdentity.from_acd(source, manifest['l5x_sha256']).manifest()
    except (ModelError, UnicodeError, OSError) as error:
        # Unsupported containers remain usable as offline L5X models. Never
        # substitute generated identifiers for a claimed native source binding.
        manifest['native_project_identity_error'] = str(error)
    try:
        manifest['native_symbols'] = NativeSymbols.from_acd(source, manifest['l5x_sha256']).manifest()
    except (ModelError, UnicodeError, OSError) as error:
        manifest['native_symbols_error'] = str(error)
    try:
        manifest['native_types'] = NativeTypes.from_acd(source, manifest['l5x_sha256']).manifest()
    except (ModelError, UnicodeError, OSError) as error:
        manifest['native_types_error'] = str(error)
    try:
        root = ET.parse(destination).getroot()
        settings = TaskConfiguration.from_source(root, root.find('Controller'), manifest['l5x_sha256'])
        if not settings.source_complete:raise ModelError('Native Task binding needs complete v35 source')
        manifest['native_tasks'] = NativeTasks.from_acd(source, manifest['l5x_sha256'], settings.names).manifest()
    except (ModelError, UnicodeError, OSError, ET.ParseError) as error:
        manifest['native_tasks_error'] = str(error)
    try:
        root = ET.parse(destination).getroot()
        configuration = ExecutableConfiguration.from_source(root, root.find('Controller'), manifest['l5x_sha256'])
        if not configuration.source_complete:raise ModelError('Native Executable binding needs complete v35 source')
        symbols = NativeSymbols.from_manifest(manifest.get('native_symbols'), manifest['l5x_sha256'])
        expected = [{'program':program,'name':name} for program in configuration.program_names
                    for name in configuration.routine_names(program,source_sha256=manifest['l5x_sha256'])]
        manifest['native_routines'] = NativeRoutines.from_acd(source,manifest['l5x_sha256'],expected,symbols).manifest()
    except (ModelError, UnicodeError, OSError, ET.ParseError) as error:
        manifest['native_routines_error'] = str(error)
    try:
        root=ET.parse(destination).getroot();catalog=AOICatalog.from_source(root,root.find('Controller'))
        if catalog.metadata is None:raise ModelError('Native AOI binding needs complete unambiguous declarations')
        manifest['native_aois']=NativeAOIs.from_acd(source,manifest['l5x_sha256'],[row.name for row in catalog.metadata]).manifest()
    except (ModelError,UnicodeError,OSError,ET.ParseError) as error:
        manifest['native_aois_error']=str(error)
    try:
        parents=NativeAOIs.from_manifest(manifest.get('native_aois'),manifest['l5x_sha256'])
        expected=[{'aoi':row.name,'name':r.name} for row in catalog.metadata for r in row.routines or ()]
        manifest['native_aoi_routines']=NativeAOIRoutines.from_acd(source,manifest['l5x_sha256'],expected,parents).manifest()
    except (ModelError,UnicodeError,OSError,ET.ParseError) as error:
        manifest['native_aoi_routines_error']=str(error)
    try:
        symbols=NativeSymbols.from_manifest(manifest.get('native_symbols'),manifest['l5x_sha256'])
        manifest['native_auxiliary_symbols']=NativeAuxiliarySymbols.from_acd(source,manifest['l5x_sha256'],symbols).manifest()
    except (ModelError,UnicodeError,OSError) as error:
        manifest['native_auxiliary_symbols_error']=str(error)
    if digest(source) != original_hash: raise ModelError("Source hash changed during correlation import")
    (destination.parent / "provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
