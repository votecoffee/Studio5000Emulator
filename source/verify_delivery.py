"""Verify the unpacked delivery against its SHA-256 manifest."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'SHA256-MANIFEST.json').read_text(encoding='utf-8'))
failures=[]
for name,expected in manifest['files'].items():
    path=root/name
    if not path.is_file():failures.append(f'MISSING {name}')
    elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:failures.append(f'CHANGED {name}')
print('\n'.join(failures) if failures else f"PASS: {len(manifest['files'])} files match the manifest")
raise SystemExit(bool(failures))
