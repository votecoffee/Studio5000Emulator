"""Identity Flash_LEDs timing, transport and application-state boundaries."""
import copy
import struct
import tempfile
import unittest
from logixlab.server import Application
from logixlab.ethernetip import Endpoint
from test_ethernetip import Client, fo, request


FLASH = bytes.fromhex('4b0220012401')


class DeviceLocatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'NetworkLab'})
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e').start(); self.app.endpoint = self.endpoint
        self.now = 100.0; self.endpoint._locator_clock = lambda: self.now
        self.client = Client(self.endpoint.port); self.client.register()

    def tearDown(self): self.client.close(); self.app.close(); self.tmp.cleanup()

    def cip(self, raw):
        status, response = self.client.cip(raw); self.assertEqual(status, 0); return response

    def flash(self, seconds): return self.cip(FLASH + bytes((seconds,)))

    def locator(self): return self.app.connectivity()['locator']

    def test_readonly_endpoint_accepts_identification_without_writing_tags(self):
        before = copy.deepcopy(self.app.engine.memory.values); source = self.app.engine.project.sha256
        self.assertEqual(self.flash(30), b'\xCB\0\0\0')
        state = self.locator(); self.assertTrue(state['active']); self.assertEqual(state['remaining_ms'], 30000)
        self.assertEqual(state['elapsed_ms'], 0); self.assertTrue(state['request_id'])
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.app.engine.project.sha256, source)
        self.assertEqual(self.cip(request(0x4D, 'Command', struct.pack('<HHi', 0xC4, 1, 7)))[2], 0x0F)

    def test_zero_stop_request_succeeds_before_during_and_after_identification(self):
        self.assertEqual(self.cip(bytes.fromhex('4b022001240100')), b'\xCB\0\0\0')
        self.assertFalse(self.locator()['active'])
        self.flash(9); self.assertTrue(self.locator()['active'])
        self.assertEqual(self.flash(0)[2], 0); self.assertFalse(self.locator()['active'])
        self.now += 1000; self.assertFalse(self.locator()['active'])
        self.assertEqual(self.flash(0)[2], 0)

    def test_expiry_uses_elapsed_real_time_and_does_not_need_a_scan(self):
        self.flash(9); self.now = 108.25
        self.assertEqual(self.locator()['remaining_ms'], 750)
        self.assertEqual(self.locator()['elapsed_ms'], 8250)
        self.assertEqual(self.app.engine.scan_count, 0)
        self.now = 109; self.assertFalse(self.locator()['active'])
        self.assertEqual(self.locator()['remaining_ms'], 0)

    def test_minimum_and_maximum_durations_are_supported(self):
        for seconds in (9, 255):
            self.assertEqual(self.flash(seconds)[2], 0)
            self.assertEqual(self.locator()['remaining_ms'], seconds * 1000)

    def test_new_request_replaces_remaining_time_and_has_a_new_identifier(self):
        self.flash(255); old = self.locator()['request_id']; self.now += 5
        self.flash(9); state = self.locator()
        self.assertEqual((state['remaining_ms'], state['elapsed_ms']), (9000, 0))
        self.assertNotEqual(state['request_id'], old)
        self.now += 1; self.flash(255); self.assertEqual(self.locator()['remaining_ms'], 255000)

    def test_durations_one_through_eight_are_rejected_without_replacing_the_timer(self):
        self.flash(30); before = self.locator()
        for seconds in range(1, 9):
            self.assertEqual(self.flash(seconds), b'\xCB\0\3\0')
            self.assertEqual(self.locator(), before)

    def test_missing_and_trailing_data_do_not_change_an_active_request(self):
        self.flash(30); before = self.locator()
        for payload, status in ((b'', 0x13), (b'\x09\0', 0x15)):
            self.assertEqual(self.cip(FLASH + payload)[2], status)
            self.assertEqual(self.locator(), before)

    def test_wrong_instances_attributes_and_symbolic_paths_do_not_trigger_locator(self):
        requests = (bytes.fromhex('4b022001240009'), bytes.fromhex('4b022001240209'),
                    bytes.fromhex('4b0320012401300109'), request(0x4B, 'Command', b'\x09'))
        for raw in requests:
            self.assertNotEqual(self.cip(raw)[2], 0)
            self.assertFalse(self.locator()['active'])

    def test_unconnected_send_slot_zero_wraps_the_flash_leds_reply(self):
        child = FLASH + b'\x09'
        raw = bytes.fromhex('5202200624010a05') + struct.pack('<H', len(child)) + child + b'\0\1\0\1\0'
        self.assertEqual(self.cip(raw), b'\xCB\0\0\0')
        self.assertTrue(self.locator()['active'])

    def test_connected_replay_does_not_restart_or_extend_the_timer(self):
        opened = self.cip(fo()); connection = struct.unpack_from('<I', opened, 4)[0]
        status, first = self.client.cip(FLASH + b'\x1E', connection, 7)
        self.assertEqual((status, first), (0, b'\xCB\0\0\0')); old = self.locator()['request_id']
        self.now += 10
        self.assertEqual(self.client.cip(FLASH + b'\x1E', connection, 7), (0, first))
        self.assertEqual(self.locator()['request_id'], old)
        self.assertEqual(self.locator()['remaining_ms'], 20000)
        self.assertEqual(self.client.cip(FLASH + b'\x09', connection, 8), (0, first))
        self.assertEqual(self.locator()['remaining_ms'], 9000)

    def test_multiple_service_children_can_start_and_stop_identification(self):
        first, second = FLASH + b'\x1E', FLASH + b'\0'
        payload = struct.pack('<3H', 2, 6, 6 + len(first)) + first + second
        response = self.cip(bytes.fromhex('0a0220022401') + payload)
        self.assertEqual(response[2], 0); self.assertFalse(self.locator()['active'])
        self.assertEqual(self.endpoint.counts['locator'], 2)

    def test_scans_and_tag_edits_do_not_change_the_locator_timer(self):
        self.flash(30); before = self.locator()
        self.app.command('write', {'tag': 'Command', 'value': 7}); self.app.command('step', {})
        self.assertEqual(self.app.engine.memory.read('Observed'), 7)
        self.assertEqual(self.locator(), before)

    def test_model_reset_preserves_device_identification_and_invalidates_old_session(self):
        self.flash(30); before = self.locator(); self.app.command('reset', {})
        self.assertEqual(self.locator(), before)
        self.assertEqual(self.client.cip(FLASH + b'\0')[0], 0x64)
        self.assertEqual(self.locator(), before)

    def test_endpoint_stop_clears_identification_and_a_new_endpoint_starts_idle(self):
        self.flash(30); self.endpoint.stop(); self.assertFalse(self.locator()['active'])
        other = Endpoint(self.app, 0, False).start()
        try: self.assertFalse(other.state()['locator']['active'])
        finally: other.stop()
        self.app.endpoint = None
        self.assertEqual(self.app.connectivity()['locator'], {'active': False, 'remaining_ms': 0, 'elapsed_ms': 0, 'request_id': None})

    def test_trace_records_valid_locator_requests_with_no_payload_data_side_effects(self):
        self.flash(9); self.flash(0)
        events = self.endpoint.state(True)['events']
        self.assertEqual([e['duration_seconds'] for e in events if e['kind'] == 'locator'], [9, 0])
        replies = [e for e in events if e['kind'] == 'cip' and e['service'] == '0x4B']
        self.assertEqual([e['status'] for e in replies], [0, 0])
        self.assertEqual(self.endpoint.state()['unsupported'], [])


if __name__ == '__main__': unittest.main()
