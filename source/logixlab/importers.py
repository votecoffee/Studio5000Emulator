"""Read-only import: native conversion operates on a private, hash-bound copy."""
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .model import ModelError
from .native_project import NativeProjectIdentity

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
    if digest(source) != original_hash: raise ModelError("Source hash changed during correlation import")
    (destination.parent / "provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
