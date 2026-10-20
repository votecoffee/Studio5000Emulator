"""Inspect an existing device payload offline; never dispatch its records."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.device_payload import MAX_ENCODED_BYTES,decode,summary


def read_bounded(path):
    with path.open('rb') as stream:raw=stream.read(MAX_ENCODED_BYTES+1)
    if len(raw)>MAX_ENCODED_BYTES:raise ValueError('Encoded payload exceeds the implementation limit')
    return raw


def run(payload,out,expected_bytes):
    payload=Path(payload).resolve(strict=True);out=Path(out).resolve()
    if out==payload or out.exists() and out.samefile(payload):raise ValueError('Output must not overwrite the payload')
    raw=read_bounded(payload);digest=hashlib.sha256(raw).hexdigest()
    batch=decode(raw,expected_bytes);result=summary(batch,expected_bytes)
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
    args=parser.parse_args()
    try:result=run(args.payload,args.out,args.expanded_bytes)
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')
    print(json.dumps({k:result[k] for k in ('status','expanded_bytes','record_count','records_executed')}))


if __name__=='__main__':main()
