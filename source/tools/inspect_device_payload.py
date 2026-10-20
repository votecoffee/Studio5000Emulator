"""Inspect an existing device payload offline; never dispatch its records."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.device_payload import MAX_ENCODED_BYTES,decode,summary
from logixlab.template_staging import TemplateStaging
from logixlab.native_types import NativeTypes
from logixlab.model import ModelError


def read_bounded(path):
    with path.open('rb') as stream:raw=stream.read(MAX_ENCODED_BYTES+1)
    if len(raw)>MAX_ENCODED_BYTES:raise ValueError('Encoded payload exceeds the implementation limit')
    return raw


def source_digest(path):
    if not 1<=path.stat().st_size<=100_000_000:raise ValueError('Source file exceeds the inspection limit')
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def run(payload,out,expected_bytes,*,inspect_templates=False,source_acd=None,source_l5x=None):
    payload=Path(payload).resolve(strict=True);out=Path(out).resolve()
    if (source_acd is None)!=(source_l5x is None) or source_acd is not None and not inspect_templates:
        raise ValueError('Source comparison requires --templates, --source-acd and --source-l5x together')
    sources=[Path(p).resolve(strict=True) for p in (source_acd,source_l5x) if p is not None]
    for path in (payload,*sources):
        if out==path or out.exists() and out.samefile(path):raise ValueError('Output must not overwrite an input')
    hashes=[source_digest(p) for p in sources]
    raw=read_bounded(payload);digest=hashlib.sha256(raw).hexdigest()
    batch=decode(raw,expected_bytes);result=summary(batch,expected_bytes)
    if inspect_templates:
        stage=TemplateStaging.from_batch(batch)
        result['template_layout_inspection']=stage.layout_inspection.description()
        if sources:
            types=NativeTypes.from_acd(sources[0],hashes[1])
            if types.source_acd_sha256!=hashes[0]:raise ValueError('Source ACD changed during inspection')
            result['source_type_verification']=types.verify(stage.templates)
            result.update(source_acd_sha256=hashes[0],source_l5x_sha256=hashes[1],sources_unchanged=True)
            if hashes!=[source_digest(p) for p in sources]:raise ValueError('Source changed during inspection')
    if hashlib.sha256(read_bounded(payload)).hexdigest()!=digest:raise ValueError('Payload changed during inspection')
    result.update(encoded_bytes=len(raw),payload_sha256=digest,input_unchanged=True)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload',required=True,type=Path)
    parser.add_argument('--expanded-bytes',required=True,type=int)
    parser.add_argument('--out',required=True,type=Path,help='New summary file; use private local storage')
    parser.add_argument('--templates',action='store_true',help='Also inspect staged Template member definitions')
    parser.add_argument('--source-acd',type=Path,help='Optional original ACD for source member comparison')
    parser.add_argument('--source-l5x',type=Path,help='Matching converted L5X bytes for the source binding')
    args=parser.parse_args()
    try:result=run(args.payload,args.out,args.expanded_bytes,inspect_templates=args.templates,
                   source_acd=args.source_acd,source_l5x=args.source_l5x)
    except (ValueError,OSError,ModelError) as error:parser.exit(1,str(error)+'\n')
    print(json.dumps({k:result[k] for k in ('status','expanded_bytes','record_count','records_executed')}))


if __name__=='__main__':main()
