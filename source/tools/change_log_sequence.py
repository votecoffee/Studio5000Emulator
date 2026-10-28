"""Inspect ordered saved Change Log pairs without interpreting log records.

Cursor equality describes only adjacent supplied pairs. It does not identify a
client, order generations, prove end-of-history or authorize a runtime reply.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.change_log_query import frame

MAX_PAIRS=4096
MAX_INPUT_BYTES=2*1024*1024
MAX_HASH_ROWS=64


def analyze(pairs):
    """Validate every frame before publishing one payload-free sequence report."""
    counts=Counter();hashes=Counter();seen=set();previous=None
    for ordinal,pair in enumerate(pairs,1):
        if ordinal>MAX_PAIRS:raise ValueError('Change Log pair limit exceeded')
        if not isinstance(pair,(tuple,list)) or len(pair)!=2:
            raise ValueError('Change Log pair must contain request and response bytes')
        try:query,cursor,summary,status=frame(*pair)
        except ValueError as error:
            raise ValueError('Invalid Change Log pair '+str(ordinal)+': '+str(error)) from error
        counts['pairs']+=1
        if query in seen:counts['repeated_queries']+=1
        seen.add(query)
        if previous is not None:
            counts['linked_queries' if query==previous else 'unlinked_queries']+=1
        if status:
            counts['rejected_replies']+=1
            # Rejection supplies no next cursor. Never link across it using a
            # cursor from an earlier successful response.
            previous=None
            continue
        previous=cursor
        changed=cursor!=query
        counts['cursor_changes' if changed else 'cursor_echoes']+=1
        if summary is None:
            counts['cursor_only_replies']+=1
            if not changed:counts['stationary_cursor_only_replies']+=1
        else:
            counts['opaque_summary_replies']+=1
            hashes[hashlib.sha256(summary).hexdigest()]+=1
            if not changed:counts['stationary_opaque_replies']+=1
    names=('pairs','repeated_queries','linked_queries','unlinked_queries',
           'rejected_replies','cursor_changes','cursor_echoes','cursor_only_replies',
           'stationary_cursor_only_replies','opaque_summary_replies','stationary_opaque_replies')
    return dict(profile='change-log-saved-sequence-v1',**{key:counts[key] for key in names},
        unique_opaque_summaries=len(hashes),
        opaque_summary_hashes=[dict(sha256=key,replies=value) for key,value in sorted(hashes.items())[:MAX_HASH_ROWS]],
        opaque_summary_hashes_truncated=len(hashes)>MAX_HASH_ROWS,
        sequence_scope='supplied_pair_order_only',client_isolation_verified=False,
        generation_order_inferred=False,summary_fields_interpreted=False,
        records_decoded=False,end_of_history_verified=False,history_supplied=False,
        source_binding_verified=False,mac_verified=False,native_acceptance_verified=False,payloads_exposed=False)


def _unique_object(items):
    value={}
    for key,item in items:
        if key in value:raise ValueError('Duplicate JSON key in Change Log input')
        value[key]=item
    return value


def load_pairs(path):
    path=Path(path)
    if not path.is_file() or not 2<=path.stat().st_size<=MAX_INPUT_BYTES:
        raise ValueError('Change Log input file is missing or outside its size limit')
    with path.open('rb') as stream:raw=stream.read(MAX_INPUT_BYTES+1)
    if not 2<=len(raw)<=MAX_INPUT_BYTES:raise ValueError('Change Log input size changed')
    rows=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=_unique_object)
    if type(rows) is not list or len(rows)>MAX_PAIRS:raise ValueError('Expected a bounded Change Log pair array')
    pairs=[]
    for row in rows:
        if type(row) is not dict or set(row)!={'request_hex','response_hex'}:
            raise ValueError('Each Change Log row needs only request_hex and response_hex')
        pair=[]
        for key,minimum,maximum in (('request_hex',10,22),('response_hex',4,72)):
            value=row[key]
            if (type(value) is not str or not 2*minimum<=len(value)<=2*maximum
                    or len(value)%2 or re.fullmatch('[0-9a-f]+',value) is None):
                raise ValueError('Invalid bounded lowercase hexadecimal '+key)
            pair.append(bytes.fromhex(value))
        pairs.append(tuple(pair))
    return pairs,hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',required=True,help='Private JSON array of exact request_hex/response_hex pairs')
    parser.add_argument('--output',required=True,help='New report path; existing files are preserved')
    args=parser.parse_args()
    pairs,digest=load_pairs(args.pairs);report=analyze(pairs);report['input_sha256']=digest
    with Path(args.output).open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({key:report[key] for key in ('pairs','linked_queries','unlinked_queries','rejected_replies','opaque_summary_replies')}))


if __name__=='__main__':main()
