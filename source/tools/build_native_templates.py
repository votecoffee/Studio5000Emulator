"""Build a source-checked Template snapshot from a saved native device payload.

Offline only: never invokes the SDK or contacts a controller. The input payload
must already belong to the supplied original ACD/L5X pair. Member/identity
checks do not authenticate signatures or give compiled code execution authority.
Keep the output private: definitions can contain application names and metadata.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab import device_payload
from logixlab.model import ModelError, Project
from logixlab.native_types import NativeTypes
from logixlab.native_templates import NativeTemplates
from logixlab.template_staging import TemplateStaging, TemplateError


def build(payload, expanded_bytes, acd, l5x):
    paths = [Path(p).resolve(strict=True) for p in (payload, acd, l5x)]
    for path, maximum in zip(paths, (device_payload.MAX_ENCODED_BYTES, 100_000_000, 100_000_000), strict=True):
        if not 1 <= path.stat().st_size <= maximum:
            raise ModelError('Native Template snapshot input exceeds its file bound')
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    native = NativeTypes.from_acd(paths[1], before[2])
    batch = device_payload.decode(paths[0].read_bytes(), expanded_bytes)
    snapshot = NativeTemplates(native, TemplateStaging.from_batch(batch).templates)
    snapshot.bind(Project(paths[2]), native)
    if before != [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths] or native.source_acd_sha256 != before[1]:
        raise ModelError('Native Template snapshot inputs changed during analysis')
    return snapshot.manifest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--expanded-bytes', required=True, type=int)
    parser.add_argument('--source-acd', required=True, type=Path)
    parser.add_argument('--source-l5x', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        # A new output also prevents hard-link aliases from overwriting input.
        if args.out.exists() or args.out.is_symlink():raise ModelError('Snapshot output must be a new file')
        result = build(args.payload, args.expanded_bytes, args.source_acd, args.source_l5x)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8') as out:json.dump(result, out, indent=2)
    except (OSError, ValueError, ModelError, TemplateError, device_payload.PayloadError) as error:
        parser.exit(1, str(error)+'\n')
    print(json.dumps({'templates': len(result['templates']), 'offline_only': True,
                      'native_code_installed': False, 'input_files_preserved': True}))


if __name__ == '__main__':
    main()
