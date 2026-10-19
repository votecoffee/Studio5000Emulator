"""Offline protocol evidence: conservative pairing, byte boundaries and privacy."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.inspect_cip_capture import describe, inspect, summarize


def packet(frame, raw, reference=None, stream=0):
    layers = {'frame': {'frame.number': str(frame)}, 'tcp': {'tcp.stream': str(stream)},
              'cip_raw': [raw.hex(), 94, len(raw), 0, 1, 0], 'enip': {}}
    if reference is not None:
        layers['enip']['Command Specific Data'] = {'enip.response_to': str(reference)}
    return {'_source': {'layers': layers}}


class CaptureInspectionTests(unittest.TestCase):
    def test_vendor_failure_is_paired_without_assigning_semantics(self):
        request = bytes.fromhex('4b0220642401a900')
        response = bytes.fromhex('cb000800')
        result = summarize([packet(4, request), packet(5, response, 4)])
        exchange, = result['exchanges']
        self.assertEqual((exchange['request']['class_id'], exchange['request']['instance']), (100, 1))
        self.assertEqual(exchange['response']['status'], 8)
        self.assertEqual(exchange['request']['payload_sha256'], hashlib.sha256(b'\xA9\0').hexdigest())
        self.assertEqual(result['vendor_semantics'], 'NOT INFERRED')
        self.assertEqual(result['studio_go_online'], 'NOT ASSESSED')
        self.assertEqual(result['unpaired_requests'], [])

    def test_success_zero_status_and_additional_status_have_correct_payload_offset(self):
        response = describe(bytes.fromhex('8e0000023412cdab0100'), True)
        self.assertEqual(response['status'], 0)
        self.assertEqual(response['additional_status'], [0x1234, 0xabcd])
        self.assertEqual(response['payload_bytes'], 2)
        self.assertEqual(response['payload_sha256'], hashlib.sha256(b'\1\0').hexdigest())
        self.assertEqual(response['message_hex'], '8e0000023412cdab0100')

    def test_missing_mismatched_late_and_other_stream_requests_are_unpaired(self):
        request, response = bytes.fromhex('4b0220642401'), bytes.fromhex('cb000000')
        for reply, reference, stream in [(response, None, 0), (response, 99, 0),
                                         (response, 4, 2), (b'\xCC\0\0\0', 4, 0)]:
            result = summarize([packet(4, request), packet(5, reply, reference, stream)])
            self.assertEqual(result['exchanges'], [])
            self.assertEqual(len(result['unpaired_requests']), 1)
            self.assertEqual(len(result['unpaired_responses']), 1)
        self.assertFalse(summarize([packet(6, request), packet(5, response, 6)])['exchanges'])

    def test_ambiguous_pdus_and_response_references_are_not_guessed(self):
        ambiguous = packet(1, bytes.fromhex('4b0220642401'))
        ambiguous['_source']['layers']['cip_raw'] = [ambiguous['_source']['layers']['cip_raw']] * 2
        response = packet(2, bytes.fromhex('cb000000'), 1)
        response['_source']['layers']['enip']['Command Specific Data']['enip.response_to'] = ['1', '3']
        result = summarize([ambiguous, response])
        self.assertEqual(result['decoded_messages'], 0)
        self.assertEqual(len(result['skipped_packets']), 2)

    def test_duplicate_frames_invalidate_the_original_pairing_candidate(self):
        request = packet(4, bytes.fromhex('4b0220642401'))
        response = packet(5, bytes.fromhex('cb000000'), 4)
        result = summarize([request, request, request, response])
        self.assertEqual(result['exchanges'], [])
        self.assertEqual(len(result['unpaired_responses']), 1)
        self.assertEqual(len(result['skipped_packets']), 2)

    def test_truncated_and_invalid_headers_do_not_become_successes(self):
        for raw in (b'', b'\x4b', b'\x4b\2\x20', b'\xCB\0\0',
                    b'\xCB\0\0\1', b'\xCB\1\0\0', b'\x4b\1\xFF\0'):
            result = summarize([packet(1, raw)])
            self.assertEqual(result['decoded_messages'], 0)
            self.assertEqual(len(result['skipped_packets']), 1)

    def test_symbols_and_data_are_absent_from_default_report(self):
        name = b'PrivateMachine'
        path = b'\x91' + bytes((len(name),)) + name
        raw = bytes((0x4D, len(path)//2)) + path + b'private-value'
        result = summarize([packet(4, raw)])
        report = json.dumps(result)
        self.assertNotIn(name.decode(), report)
        self.assertNotIn('private-value', report)
        self.assertNotIn('message_hex', report)
        self.assertTrue(result['unpaired_requests'][0]['symbolic_path'])

    def test_sixteen_bit_class_ids_and_zero_instances_are_preserved(self):
        description = describe(bytes.fromhex('030321001a03240001000100'))
        self.assertEqual((description['class_id'], description['instance']), (0x31A, 0))
        self.assertEqual(description['payload_bytes'], 4)

    def test_completed_inputs_are_preserved_and_changing_captures_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / 'capture.pcap'
            capture.write_bytes(b'original')
            with patch('tools.inspect_cip_capture.decode_capture', return_value=[]):
                result = inspect(capture, 'not-executed')
            self.assertTrue(result['input_unchanged'])
            self.assertEqual(capture.read_bytes(), b'original')
            def change(*_):
                capture.write_bytes(b'changed')
                return []
            with patch('tools.inspect_cip_capture.decode_capture', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'changed during analysis'):
                    inspect(capture, 'not-executed')


if __name__ == '__main__':
    unittest.main()
