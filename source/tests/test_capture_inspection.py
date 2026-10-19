"""Offline protocol evidence: conservative pairing, byte boundaries and privacy."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.inspect_cip_capture import describe, inspect, summarize
from test_signed_messages import request as signed_request, response as signed_response
from test_signed_batches import REQUEST as BATCH_REQUEST, RESPONSE as BATCH_RESPONSE, batch


def packet(frame, raw, reference=None, stream=0):
    layers = {'frame': {'frame.number': str(frame)}, 'tcp': {'tcp.stream': str(stream)},
              'cip_raw': [raw.hex(), 94, len(raw), 0, 1, 0], 'enip': {}}
    if reference is not None:
        layers['enip']['Command Specific Data'] = {'enip.response_to': str(reference)}
    return {'_source': {'layers': layers}}


class CaptureInspectionTests(unittest.TestCase):
    def test_batch_pair_exposes_ordered_children_and_partial_errors(self):
        report = summarize([packet(1, BATCH_REQUEST), packet(2, BATCH_RESPONSE, 1)])
        pair, = report['exchanges']
        self.assertEqual(report['format_version'], 3)
        for message in (pair['request'], pair['response']):
            envelope = message['signed_envelope']
            self.assertEqual(envelope['structure'], 'DECODED')
            self.assertEqual(envelope['integrity'], 'NOT VERIFIED')
            self.assertEqual(envelope['sequence'], 7)
            self.assertEqual(envelope['child_count'], 2)
            self.assertEqual([child['service'] for child in envelope['children']], [0x0E, 0x4C])
        self.assertEqual(pair['response']['status'], 0x1E)
        self.assertEqual([child['status'] for child in pair['response']['signed_envelope']['children']], [0, 6])
        self.assertEqual(pair['response']['signed_envelope']['children'][1]['additional_status'], [0x1234])

    def test_batch_privacy_and_nested_envelopes_stop_at_one_layer(self):
        name = b'PrivateMachine'
        path = b'\x91' + bytes((len(name),)) + name
        private_child = bytes((0x4D, len(path)//2)) + path + b'operator-private-value'
        raw = batch((private_child, BATCH_REQUEST))
        for include in (False, True):
            report = summarize([packet(1, raw)], include)
            children = report['unpaired_requests'][0]['signed_envelope']['children']
            self.assertTrue(children[0]['symbolic_path'])
            self.assertEqual(children[1]['service'], 0x38)
            self.assertNotIn('signed_envelope', children[1])
            if include:
                self.assertEqual(children[0]['message_hex'], private_child.hex())
            else:
                for private in (name.decode(), name.hex(), private_child.hex(), raw.hex(), 'operator-private-value'):
                    self.assertNotIn(private, json.dumps(report))

    def test_invalid_batch_children_do_not_expose_partial_decodes(self):
        raw = batch((bytes.fromhex('0e03200124013001'), b'\x0E\xFF'))
        report = summarize([packet(1, raw)])
        envelope = report['unpaired_requests'][0]['signed_envelope']
        self.assertEqual(envelope['structure'], 'UNSUPPORTED OR MALFORMED')
        self.assertNotIn('children', envelope)
        self.assertEqual(report['decoded_messages'], 1)
        self.assertFalse(report['skipped_packets'])
        for reply in (batch((b'\x8E\0\0\0',), response=True),
                      batch((b'\x8E\0\0\0', b'\xCC\0\0\0'), response=True, sequence=8)):
            report = summarize([packet(1, BATCH_REQUEST), packet(2, reply, 1)])
            envelope = report['exchanges'][0]['response']['signed_envelope']
            self.assertEqual(envelope['structure'], 'UNSUPPORTED OR MALFORMED')
            self.assertNotIn('children', envelope)

    def test_signed_pair_exposes_inner_fields_without_verifying_integrity(self):
        for service in (0x36, 0x37):
            result = summarize([packet(1, signed_request(service)), packet(2, signed_response(service), 1)])
            pair, = result['exchanges']
            for message in (pair['request'], pair['response']):
                envelope = message['signed_envelope']
                self.assertEqual(envelope['structure'], 'DECODED')
                self.assertEqual(envelope['integrity'], 'NOT VERIFIED')
                self.assertEqual(envelope['sequence'], 7)
                self.assertEqual(envelope['inner']['service'], 0x0E)
            self.assertEqual(pair['request']['signed_envelope']['inner']['attribute'], 1)
            self.assertEqual(pair['response']['signed_envelope']['inner']['status'], 0)
            self.assertEqual(result['signed_integrity'], 'NOT VERIFIED')
            self.assertEqual(result['studio_go_online'], 'NOT ASSESSED')

    def test_signed_reports_preserve_privacy_and_opt_in_raw_bytes(self):
        name = b'PrivateMachine'
        path = b'\x91' + bytes((len(name),)) + name
        inner = bytes((0x4D, len(path)//2)) + path + b'operator-private-value'
        raw = signed_request(0x37, inner)
        for include in (False, True):
            report = summarize([packet(1, raw)], include)
            nested = report['unpaired_requests'][0]['signed_envelope']['inner']
            self.assertTrue(nested['symbolic_path'])
            self.assertEqual('message_hex' in nested, include)
            if not include:
                text = json.dumps(report)
                for private in (name.decode(), name.hex(), 'operator-private-value', raw.hex()):
                    self.assertNotIn(private, text)
            else:
                self.assertEqual(nested['message_hex'], inner.hex())

    def test_malformed_and_unknown_envelopes_keep_outer_evidence(self):
        for raw in (signed_request()[:20], b'\x38'+signed_request()[1:],
                    signed_request(0x37, b'\x0E\1\xFF\0')):
            result = summarize([packet(1, raw)])
            self.assertEqual(result['decoded_messages'], 1)
            self.assertFalse(result['skipped_packets'])
            self.assertEqual(result['unpaired_requests'][0]['signed_envelope']['structure'],
                             'UNSUPPORTED OR MALFORMED')
        other_class = bytearray(signed_request()); other_class[3] = 3
        self.assertNotIn('signed_envelope', describe(bytes(other_class)))

    def test_signed_reply_requires_matching_counter_and_successful_wrapper(self):
        for raw in (signed_response(sequence=8), b'\xB6\0\x08\0'):
            result = summarize([packet(1, signed_request()), packet(2, raw, 1)])
            pair, = result['exchanges']
            self.assertEqual(pair['response']['signed_envelope']['structure'], 'UNSUPPORTED OR MALFORMED')
            self.assertNotIn('inner', pair['response']['signed_envelope'])

    def test_nested_signed_envelopes_stop_after_one_layer(self):
        message = describe(signed_request(0x37, signed_request()))
        self.assertEqual(message['signed_envelope']['inner']['service'], 0x36)
        self.assertNotIn('signed_envelope', message['signed_envelope']['inner'])

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
