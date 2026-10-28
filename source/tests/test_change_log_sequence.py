"""Cursor links never substitute for record, history or native acceptance proof."""
import hashlib
import itertools
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import change_log_sequence as tool


def pair(index,generation,next_index=None,next_generation=None,summary=None,status=0):
    request=bytes.fromhex('4f0220ac2401')+struct.pack('<HH',index,generation)
    response=bytes((0xCF,0,status,0))
    if not status:
        response+=(summary or b'')+struct.pack('<HH',index if next_index is None else next_index,
                                              generation if next_generation is None else next_generation)
    return request,response


class ChangeLogSequenceTests(unittest.TestCase):
    def test_linked_summary_then_cursor_echo_is_not_history_or_client_proof(self):
        opaque=bytes(range(32))
        report=tool.analyze([pair(12,3,13,summary=opaque),pair(13,3)])
        for key,value in dict(pairs=2,linked_queries=1,unlinked_queries=0,
                              opaque_summary_replies=1,cursor_changes=1,
                              stationary_cursor_only_replies=1).items():self.assertEqual(report[key],value)
        self.assertEqual(report['opaque_summary_hashes'],[dict(sha256=hashlib.sha256(opaque).hexdigest(),replies=1)])
        for key in ('client_isolation_verified','generation_order_inferred','summary_fields_interpreted',
                    'records_decoded','end_of_history_verified','history_supplied','source_binding_verified',
                    'mac_verified','native_acceptance_verified','payloads_exposed'):self.assertFalse(report[key])
        self.assertEqual(report['sequence_scope'],'supplied_pair_order_only')
        self.assertNotIn(opaque.hex(),json.dumps(report))
        self.assertNotIn('index',report);self.assertNotIn('cursor',report)

    def test_repeated_unlinked_and_wrapped_cursors_keep_only_equality_facts(self):
        report=tool.analyze([pair(65535,65535,0,0),pair(0,0),pair(65535,65535)])
        self.assertEqual(report['linked_queries'],1);self.assertEqual(report['unlinked_queries'],1)
        self.assertEqual(report['repeated_queries'],1);self.assertEqual(report['cursor_changes'],1)
        self.assertFalse(report['generation_order_inferred'])

    def test_rejection_breaks_adjacency_without_manufacturing_an_empty_reply(self):
        report=tool.analyze([pair(1,2,2),pair(2,2,status=12),pair(2,2)])
        self.assertEqual(report['rejected_replies'],1);self.assertEqual(report['linked_queries'],1)
        self.assertEqual(report['cursor_only_replies'],2);self.assertEqual(report['cursor_echoes'],1)
        self.assertEqual(report['unlinked_queries'],0)

    def test_stationary_summary_stays_opaque_and_hash_rows_are_bounded(self):
        report=tool.analyze(pair(0,1,summary=bytes((n,))*32) for n in range(tool.MAX_HASH_ROWS+1))
        self.assertEqual(report['stationary_opaque_replies'],65)
        self.assertEqual(report['unique_opaque_summaries'],65)
        self.assertEqual(len(report['opaque_summary_hashes']),64)
        self.assertTrue(report['opaque_summary_hashes_truncated'])
        self.assertFalse(report['end_of_history_verified'])

    def test_bad_pair_or_excess_input_fails_instead_of_publishing_partial_coverage(self):
        for rows in ([pair(0,1),(b'',b'')],[pair(0,1),(b'x',)],
                     itertools.repeat(pair(0,1),tool.MAX_PAIRS+1)):
            with self.assertRaises(ValueError):tool.analyze(rows)

    def test_input_schema_bounds_duplicate_keys_and_exact_input_hash(self):
        query,answer=pair(0,1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pairs.json'
            raw=json.dumps([dict(request_hex=query.hex(),response_hex=answer.hex())]).encode()
            path.write_bytes(raw)
            self.assertEqual(tool.load_pairs(path),([(query,answer)],hashlib.sha256(raw).hexdigest()))
            for raw in (b'{}',b'[{"request_hex":"00","request_hex":"00","response_hex":"00"}]',
                        b'[{"request_hex":true,"response_hex":"cf000c00"}]',
                        json.dumps([dict(request_hex=query.hex(),response_hex=answer.hex(),private='unused')]).encode(),
                        json.dumps([dict(request_hex=query.hex().upper(),response_hex=answer.hex())]).encode()):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):tool.load_pairs(path)
            path.write_bytes(bytes(tool.MAX_INPUT_BYTES+1))
            with self.assertRaises(ValueError):tool.load_pairs(path)

    def test_cli_never_overwrites_an_existing_report(self):
        query,answer=pair(0,1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pairs.json';path.write_text(json.dumps([dict(request_hex=query.hex(),response_hex=answer.hex())]),encoding='utf8')
            output=Path(tmp)/'report.json';output.write_bytes(b'keep')
            with patch('sys.argv',['change_log_sequence','--pairs',str(path),'--output',str(output)]):
                with self.assertRaises(FileExistsError):tool.main()
            self.assertEqual(output.read_bytes(),b'keep')


if __name__=='__main__':unittest.main()
