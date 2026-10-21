"""Offline protocol evidence: conservative pairing, byte boundaries and privacy."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools.inspect_cip_capture import CaptureDecode, describe, field_packets, inspect, summarize
from logixlab.ethernetip import CIPError, decode_path
from test_signed_messages import request as signed_request, response as signed_response
from test_signed_batches import REQUEST as BATCH_REQUEST, RESPONSE as BATCH_RESPONSE, batch


def packet(frame, raw, reference=None, stream=0):
    layers = {'frame': {'frame.number': str(frame)}, 'tcp': {'tcp.stream': str(stream)},
              'cip_raw': [raw.hex(), 94, len(raw), 0, 1, 0], 'enip': {}}
    if reference is not None:
        layers['enip']['Command Specific Data'] = {'enip.response_to': str(reference)}
    return {'_source': {'layers': layers}}


class CaptureInspectionTests(unittest.TestCase):
    def test_time_sync_layouts_decode_plain_signed_and_batch_replies(self):
        query = bytes.fromhex('030220432401020001000300')
        answer = bytes.fromhex('8300060001000100000000')
        pairs = [(query, answer),
                 (signed_request(0x36, query), signed_response(0x36, answer)),
                 (batch((query,)), batch((answer,), response=True))]
        for request, response in pairs:
            with self.subTest(request=request.hex()):
                result = summarize([packet(1, request), packet(2, response, 1)])
                pair, = result['exchanges']
                decoded = pair['response']
                if 'signed_envelope' in decoded:
                    envelope = decoded['signed_envelope']
                    decoded = envelope.get('inner') or envelope['children'][0]
                layout = decoded['time_sync_attribute_list']
                self.assertTrue(layout['partial'])
                self.assertEqual(layout['remaining_attributes'], [3])
                self.assertEqual(layout['attributes'][0]['value_bytes'], 1)
                self.assertNotIn('data_hex', layout['attributes'][0])
                self.assertEqual(result['signed_integrity'], 'NOT VERIFIED')

    def test_bad_clock_layout_keeps_exchange_and_does_not_guess_field_boundaries(self):
        query = bytes.fromhex('03022043240101001500')
        answer = bytes.fromhex('8300000001001500000004000000')+b'ab'
        result = summarize([packet(1, query), packet(2, answer, 1)])
        pair, = result['exchanges']
        self.assertEqual(pair['response']['status'], 0)
        layout = pair['response']['time_sync_attribute_list']
        self.assertEqual(layout['structure'], 'UNSUPPORTED OR MALFORMED')
        self.assertNotIn('attributes', layout)
        self.assertFalse(result['skipped_packets'])

    def test_batch_pair_exposes_ordered_children_and_partial_errors(self):
        report = summarize([packet(1, BATCH_REQUEST), packet(2, BATCH_RESPONSE, 1)])
        pair, = report['exchanges']
        self.assertEqual(report['format_version'], 4)
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

    def test_scoped_object_path_keeps_order_without_claiming_a_flat_target(self):
        path = bytes.fromhex('206524032100770124003009')
        raw = bytes((0x0E, len(path)//2)) + path
        request = describe(raw)
        self.assertIsNone(request['class_id'])
        self.assertIsNone(request['instance'])
        self.assertIsNone(request['attribute'])
        self.assertEqual(request['object_path'], [
            dict(class_id=0x65, instance=3, attribute=None, symbolic_path=False),
            dict(class_id=0x177, instance=0, attribute=9, symbolic_path=False)])
        # Offline inspection does not broaden the live endpoint's path grammar.
        with self.assertRaises(CIPError):
            decode_path(path)

    def test_scoped_requests_pair_inside_single_and_batch_wrappers(self):
        inner = bytes.fromhex('0304206524032077240501000900')
        for raw, response in (
                (inner, b'\x83\0\x08\0'),
                (signed_request(0x36, inner), signed_response(0x36, b'\x83\0\x08\0')),
                (signed_request(0x37, inner), signed_response(0x37, b'\x83\0\x08\0')),
                (batch((inner,)), batch((b'\x83\0\x08\0',), response=True))):
            report = summarize([packet(1, raw), packet(2, response, 1)])
            pair, = report['exchanges']
            envelope = pair['request'].get('signed_envelope')
            decoded = (envelope.get('inner') or envelope['children'][0]) if envelope else pair['request']
            self.assertEqual(len(decoded['object_path']), 2)
            self.assertEqual(decoded['requested_attributes'], [9])
            self.assertFalse(report['skipped_packets'])
            self.assertEqual(report['signed_integrity'], 'NOT VERIFIED')

    def test_scoped_symbol_names_and_payload_values_stay_private(self):
        name = b'Private0Machine'
        path = b'\x20\x65\x24\3\x20\x77\x24\5\x91' + bytes((len(name),)) + name + b'\0'
        raw = bytes((0x4C, len(path)//2)) + path + b'private-value'
        result = describe(raw)
        self.assertTrue(result['symbolic_path'])
        self.assertTrue(result['object_path'][-1]['symbolic_path'])
        text = json.dumps(result)
        for value in (name.decode(), name.hex(), raw.hex(), 'private-value'):
            self.assertNotIn(value, text)
        self.assertEqual(describe(raw, True)['message_hex'], raw.hex())

    def test_malformed_or_ambiguous_scopes_still_reject_the_request(self):
        paths = ('206520772405', '20652403240320772405',
                 '20652403300120772405', '206524032077',
                 '2065240322007700', '20652403210177012405',
                 '206524032077240591ff', '206524032077240530013002')
        for path in paths:
            raw = bytes.fromhex(path)
            self.assertEqual(len(raw) % 2, 0)
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    describe(bytes((0x0E, len(raw)//2)) + raw)

    def test_scope_count_and_wide_logical_segments_are_bounded(self):
        scope = bytes.fromhex('220034120000260078560000')
        path = scope * 16
        raw = bytes((0x0E, len(path)//2)) + path
        scopes = describe(raw)['object_path']
        self.assertEqual(len(scopes), 16)
        self.assertEqual(scopes[-1]['class_id'], 0x1234)
        self.assertEqual(scopes[-1]['instance'], 0x5678)
        path += scope
        with self.assertRaisesRegex(ValueError, 'scope limit'):
            describe(bytes((0x0E, len(path)//2)) + path)

    def test_attribute_list_ids_are_structural_and_preserve_order_and_duplicates(self):
        prefix = b'\x03\2\x20\x65\x24\3'
        raw = prefix + struct.pack('<4H', 3, 9, 13, 9)
        message = describe(raw)
        self.assertEqual(message['requested_attributes'], [9, 13, 9])
        self.assertNotIn('message_hex', message)
        self.assertNotIn('attribute_values', message)
        for payload in (b'', b'\1', b'\1\0', b'\0\0\1\0', struct.pack('<H', 257)+b'\1\0'*257):
            self.assertNotIn('requested_attributes', describe(prefix + payload))
        self.assertEqual(describe(prefix + b'\0\0')['requested_attributes'], [])
        bound = describe(prefix + struct.pack('<H', 256) + b'\1\0'*256)
        self.assertEqual(len(bound['requested_attributes']), 256)
        self.assertNotIn('requested_attributes', describe(b'\x83\0\0\0' + raw[6:]))

    def test_completed_inputs_are_preserved_and_changing_captures_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / 'capture.pcap'
            capture.write_bytes(b'original')
            with patch('tools.inspect_cip_capture.decode_capture', return_value=CaptureDecode([], 3)):
                result = inspect(capture, 'not-executed')
            self.assertTrue(result['input_unchanged'])
            self.assertEqual(result['limits']['input_frames_read'], 3)
            self.assertFalse(result['limits']['packet_bound_reached'])
            self.assertEqual(capture.read_bytes(), b'original')
            def change(*_):
                capture.write_bytes(b'changed')
                return CaptureDecode([], 0)
            with patch('tools.inspect_cip_capture.decode_capture', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'changed during analysis'):
                    inspect(capture, 'not-executed')

    def test_compact_fields_count_non_cip_frames_and_pair_late_exchanges(self):
        fields = (b'1\t\t\t\n50001\t2\t\t0e:03:20:01:24:01:30:01\n'
                  b'50002\t2\t50001\t8e:00:00:00:01:00\n50003\t\t\t\n')
        decoded = field_packets(io.BytesIO(fields))
        self.assertEqual(decoded.input_frames, 4)
        result = summarize(decoded.packets)
        self.assertEqual(result['cip_packets'], 2)
        pair, = result['exchanges']
        self.assertEqual(pair['request']['frame'], 50001)
        self.assertEqual(pair['response']['status'], 0)
        self.assertFalse(result['skipped_packets'])

    def test_compact_fields_keep_multiple_pdus_and_references_ambiguous(self):
        fields = (b'1\t0\t\t0e03200124013001,0e03200124013002\n'
                  b'2\t0\t1,3\t8e0000000100\n'
                  b'3\t0\t\tprivate-invalid-hex\n')
        result = summarize(field_packets(io.BytesIO(fields)).packets)
        self.assertFalse(result['exchanges'])
        self.assertEqual(len(result['skipped_packets']), 3)
        self.assertNotIn('private-invalid-hex', json.dumps(result))

    def test_compact_field_framing_and_bounds_reject_invalid_extraction(self):
        for fields in (b'1\t\t\n', b'\xff\t\t\t\n', b'0\t\t\t\n',
                       b'bad\t\t\t\n', b'1\t\t\t\textra\n'):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                field_packets(io.BytesIO(fields))
        with patch('tools.inspect_cip_capture.MAX_LINE', 12):
            with self.assertRaisesRegex(ValueError, 'line exceeds'):
                field_packets(io.BytesIO(b'1\t0\t\t' + b'00' * 12))
        with patch('tools.inspect_cip_capture.PACKET_LIMIT', 2):
            with self.assertRaisesRegex(ValueError, 'packet bound'):
                field_packets(io.BytesIO(b'1\t\t\t\n2\t\t\t\n3\t\t\t\n'))

    def test_hitting_input_bound_is_explicit_even_without_cip_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / 'capture.pcap'
            capture.write_bytes(b'original')
            with patch('tools.inspect_cip_capture.PACKET_LIMIT', 2), patch(
                    'tools.inspect_cip_capture.decode_capture', return_value=CaptureDecode([], 2)):
                result = inspect(capture, 'not-executed')
            self.assertTrue(result['limits']['packet_bound_reached'])
            self.assertEqual(result['limits']['capture_completeness'], 'NOT ASSESSED')


if __name__ == '__main__':
    unittest.main()
