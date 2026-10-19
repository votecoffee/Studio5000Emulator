"""Controller cache-comparison contract and project/session lifecycle checks."""
import base64
import copy
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.server import Application
from logixlab.model import ModelError
from logixlab.ethernetip import Endpoint, Session, symbol_path
from test_ethernetip import Client, request


ATTRIBUTES = (1, 2, 3, 4, 10)
WIDTHS = {1: 2, 2: 2, 3: 4, 4: 4, 10: 4}
OBJECT_PATH = b'\x20\xAC\x24\1'
REVISION_REQUEST = b'\x03\2' + OBJECT_PATH + struct.pack('<6H', 5, *ATTRIBUTES)


def revision_values(response):
    assert response[:4] == b'\x83\0\0\0', response.hex()
    count = struct.unpack_from('<H', response, 4)[0]; pos = 6; result = {}
    for _ in range(count):
        attribute, status = struct.unpack_from('<HH', response, pos); pos += 4
        assert status == 0, (attribute, status)
        width = WIDTHS[attribute]; result[attribute] = response[pos:pos + width]; pos += width
    assert pos == len(response)
    return result


class CatalogRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'LayoutLab'})
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e').start()
        self.app.endpoint = self.endpoint; self.clients = []; self.client = self.fresh_client()
        self.source = Path(__file__).resolve().parents[1] / 'samples/LayoutLab.L5X'

    def tearDown(self):
        for client in self.clients: client.close()
        self.app.close(); self.tmp.cleanup()

    def fresh_client(self):
        client = Client(self.endpoint.port); client.register(); self.clients.append(client)
        return client

    def cip(self, raw, client=None):
        status, result = (client or self.client).cip(raw)
        self.assertEqual(status, 0); return result

    def revision(self, client=None):
        return revision_values(self.cip(REVISION_REQUEST, client))

    def load(self, data):
        return self.app.command('load', {'name': 'catalog.L5X', 'content': base64.b64encode(data).decode('ascii')})

    def test_documented_attribute_widths_and_single_list_reads_agree(self):
        listed = self.revision(); self.assertEqual(tuple(listed), ATTRIBUTES)
        self.assertEqual([len(v) for v in listed.values()], [2, 2, 4, 4, 4])
        for attribute, value in listed.items():
            raw = b'\x0E\3' + OBJECT_PATH + bytes((0x30, attribute))
            self.assertEqual(self.cip(raw), b'\x8E\0\0\0' + value)
        long_path = b'\x03\3\x20\xAC\x25\0\1\0' + struct.pack('<6H', 5, *ATTRIBUTES)
        self.assertEqual(revision_values(self.cip(long_path)), listed)

    def test_reordered_and_duplicate_attribute_requests_preserve_response_order(self):
        attrs = (10, 1, 4, 10, 2, 3); before = self.revision()
        response = self.cip(b'\x03\2' + OBJECT_PATH + struct.pack('<7H', 6, *attrs))
        self.assertEqual(response[:6], b'\x83\0\0\0\6\0'); pos = 6
        for attribute in attrs:
            self.assertEqual(struct.unpack_from('<HH', response, pos), (attribute, 0)); pos += 4
            self.assertEqual(response[pos:pos + WIDTHS[attribute]], before[attribute]); pos += WIDTHS[attribute]
        self.assertEqual(pos, len(response))

    def test_runtime_edits_scans_and_reports_leave_revision_unchanged(self):
        before = self.revision()
        self.app.command('write', {'tag': 'Records[0].Count', 'value': 777})
        self.app.command('step', {}); self.app.command('snapshot', {}); self.app.command('report', {})
        self.app.command('settings', {'converter': ''})
        self.assertEqual(self.app.engine.memory.read('Observed'), 777)
        self.assertEqual(self.revision(), before)

    def test_network_writes_do_not_change_revision_tokens(self):
        before = self.revision()
        raw = request(0x4D, 'Records[0].Count', struct.pack('<HHi', 0xC4, 1, 456))
        self.assertEqual(self.cip(raw)[2], 0)
        self.assertEqual(self.app.engine.memory.read('Records[0].Count'), 456)
        self.assertEqual(self.revision(), before)

    def test_same_source_import_preserves_tokens_but_invalidates_old_sessions(self):
        before = self.revision(); self.load(self.source.read_bytes())
        self.assertEqual(self.client.cip(REVISION_REQUEST)[0], 0x64)
        self.assertEqual(self.revision(self.fresh_client()), before)

    def test_changed_tag_source_changes_tokens_and_requires_fresh_catalog(self):
        before = self.revision(); tree = E.parse(self.source)
        tag = E.SubElement(tree.find('./Controller/Tags'), 'Tag', Name='Added', TagType='Base', DataType='DINT', ExternalAccess='Read/Write')
        E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='42')
        self.load(E.tostring(tree.getroot(), encoding='utf-8'))
        self.assertEqual(self.client.cip(request(0x4C, 'Records[0].Count', b'\1\0'))[0], 0x64)
        fresh = self.fresh_client(); self.assertNotEqual(self.revision(fresh), before)
        self.assertEqual(self.cip(request(0x4C, 'Added', b'\1\0'), fresh)[4:], struct.pack('<Hi', 0xC4, 42))

    def test_initial_data_only_import_also_conservatively_invalidates_tokens(self):
        before = self.revision(); tree = E.parse(self.source)
        tree.find('./Controller/Tags/Tag[@Name="Observed"]/Data/DataValue').set('Value', '9')
        self.load(E.tostring(tree.getroot(), encoding='utf-8'))
        self.assertNotEqual(self.revision(self.fresh_client()), before)

    def test_reset_and_scope_change_preserve_tokens_and_require_reconnect(self):
        before = self.revision()
        for action, data in (('reset', {}), ('configure', {'mode': 'routine', 'routine': 'MainProgram/MainRoutine'})):
            old = self.client; self.app.command(action, data)
            self.assertEqual(old.cip(REVISION_REQUEST)[0], 0x64)
            self.client = self.fresh_client(); self.assertEqual(self.revision(), before)

    def test_failed_import_preserves_project_tokens_and_live_session(self):
        old = self.app.engine; before = self.revision()
        with self.assertRaises(E.ParseError): self.load(b'<invalid')
        self.assertIs(self.app.engine, old); self.assertFalse(self.app.busy)
        self.assertEqual(self.revision(), before)

    def test_incompatible_import_keeps_live_profile_and_revision(self):
        old = self.app.engine; before = self.revision(); tree = E.parse(self.source)
        tree.find('Controller').set('ProcessorType', '1756-L83E')
        with self.assertRaises(ModelError): self.load(E.tostring(tree.getroot(), encoding='utf-8'))
        self.assertIs(self.app.engine, old); self.assertFalse(self.app.busy)
        self.assertEqual(self.revision(), before)

    def test_busy_import_rejects_metadata_until_existing_project_is_available(self):
        before = self.revision(); self.app.busy = True
        try: self.assertEqual(self.cip(REVISION_REQUEST)[2], 0x10)
        finally: self.app.busy = False
        self.assertEqual(self.revision(), before)

    def test_state_token_matches_wire_values_and_is_not_a_native_signature(self):
        metadata = self.endpoint.state()['catalog_revision']; values = self.revision()
        self.assertEqual(bytes.fromhex(metadata['token']), b''.join(values[a] for a in ATTRIBUTES))
        self.assertFalse(metadata['native_firmware_signature'])
        self.endpoint.stop(); self.assertIsNone(self.endpoint.state()['catalog_revision'])
        self.app.endpoint = None; self.assertIsNone(self.app.connectivity()['catalog_revision'])

    def test_different_identity_profiles_have_the_same_source_bound_revision(self):
        other = Endpoint(self.app, 0, False, 'research').start(); client = Client(other.port)
        try:
            client.register(); status, response = client.cip(REVISION_REQUEST)
            self.assertEqual(status, 0); self.assertEqual(revision_values(response), self.revision())
        finally: client.close(); other.stop()

    def test_unknown_attributes_return_per_attribute_errors_and_known_values(self):
        before = self.revision(); memory = copy.deepcopy(self.app.engine.memory.values)
        response = self.cip(b'\x03\2' + OBJECT_PATH + struct.pack('<4H', 3, 1, 99, 10))
        self.assertEqual(response[:4], b'\x83\0\x0A\0')
        self.assertEqual(response[4:], struct.pack('<HHH', 3, 1, 0) + before[1] + struct.pack('<HHHH', 99, 0x14, 10, 0) + before[10])
        self.assertEqual(self.cip(b'\x0E\3' + OBJECT_PATH + b'\x30\xFF')[2], 0x14)
        self.assertEqual(self.app.engine.memory.values, memory)

    def test_malformed_lists_and_paths_preserve_tokens_and_memory(self):
        before = self.revision(); memory = copy.deepcopy(self.app.engine.memory.values)
        for payload in (b'', b'\0\0', b'\1\0', b'\1\0\1\0x', struct.pack('<H', 33) + b'\1\0'*33):
            self.assertNotEqual(self.cip(b'\x03\2' + OBJECT_PATH + payload)[2], 0)
        for path in (b'\x20\xAC', b'\x20\xAC\x24\2', OBJECT_PATH + symbol_path('Extra'), OBJECT_PATH + b'\x28\0'):
            self.assertNotEqual(self.cip(b'\x03' + bytes((len(path)//2,)) + path + b'\1\0\1\0')[2], 0)
        self.assertEqual(self.revision(), before); self.assertEqual(self.app.engine.memory.values, memory)

    def test_unsupported_controller_services_are_rejected_without_mutation(self):
        memory = copy.deepcopy(self.app.engine.memory.values); before = self.revision()
        for service in (1, 0x10, 0x4B, 0x4D, 0x55):
            self.assertEqual(self.cip(bytes((service, 2)) + OBJECT_PATH)[2], 8)
        self.assertEqual(self.revision(), before); self.assertEqual(self.app.engine.memory.values, memory)

    def test_metadata_and_tag_read_can_share_a_multiple_service_packet(self):
        children = [REVISION_REQUEST, request(0x4C, 'Records[0].Count', b'\1\0')]
        body = struct.pack('<HHH', 2, 6, 6 + len(children[0])) + b''.join(children)
        response = self.cip(b'\x0A\2\x20\2\x24\1' + body)
        self.assertEqual(response[2], 0)
        count, first, second = struct.unpack_from('<3H', response, 4); self.assertEqual(count, 2)
        self.assertEqual(revision_values(response[4 + first:4 + second]), self.revision())
        self.assertEqual(response[4 + second:], b'\xCC\0\0\0' + struct.pack('<Hi', 0xC4, 100))

    def test_small_reply_limit_rejects_oversized_attribute_list(self):
        response = self.endpoint.router.handle(REVISION_REQUEST, Session(), limit=16)
        self.assertEqual(response, b'\x83\0\x1B\0')

    def test_native_class_revision_request_and_common_inventory(self):
        # Exact class-level revision request seen during the native SDK probe.
        self.assertEqual(self.cip(bytes.fromhex('030220ac240001000100')),
                         bytes.fromhex('830000000100010000000100'))
        for attribute in (1, 2, 3):
            single = b'\x0E\3\x20\xAC\x24\0' + bytes((0x30, attribute))
            self.assertEqual(self.cip(single), b'\x8E\0\0\0\1\0')
        extended = b'\x03\3\x20\xAC\x25\0\0\0' + struct.pack('<4H', 3, 1, 2, 3)
        self.assertEqual(self.cip(extended), b'\x83\0\0\0' + struct.pack('<10H', 3, 1, 0, 1, 2, 0, 1, 3, 0, 1))

    def test_class_attributes_preserve_order_and_per_attribute_errors(self):
        path = b'\x20\xAC\x24\0'
        response = self.cip(b'\x03\2' + path + struct.pack('<5H', 4, 3, 99, 1, 3))
        self.assertEqual(response, b'\x83\0\x0A\0' + struct.pack('<12H', 4, 3, 0, 1, 99, 0x14, 1, 0, 1, 3, 0, 1))
        self.assertEqual(self.cip(b'\x0E\3' + path + b'\x30\x0A')[2], 0x14)

    def test_class_reads_do_not_change_tokens_values_or_instance_attributes(self):
        token = self.revision(); memory = copy.deepcopy(self.app.engine.memory.values)
        for attribute in (1, 2, 3):
            self.cip(b'\x0E\3\x20\xAC\x24\0' + bytes((0x30, attribute)))
        self.assertEqual(self.revision(), token)
        self.assertEqual(self.app.engine.memory.values, memory)
        self.assertEqual(self.cip(b'\x0E\3' + OBJECT_PATH + b'\x30\x0A')[4:], token[10])

    def test_class_malformed_reads_and_writes_are_rejected_without_mutation(self):
        token = self.revision(); memory = copy.deepcopy(self.app.engine.memory.values)
        path = b'\x20\xAC\x24\0'
        for payload in (b'', b'\0\0', b'\1\0', b'\1\0\1\0x'):
            self.assertNotEqual(self.cip(b'\x03\2' + path + payload)[2], 0)
        self.assertEqual(self.cip(b'\x0E\3' + path + b'\x30\1x')[2], 0x15)
        self.assertEqual(self.cip(b'\x10\3' + path + b'\x30\1\2\0')[2], 8)
        for service in (1, 0x4B, 0x4D, 0x55):
            self.assertEqual(self.cip(bytes((service, 2)) + path)[2], 8)
        for extra in (symbol_path('Extra'), b'\x28\0'):
            malformed = path + extra
            self.assertEqual(self.cip(b'\x03' + bytes((len(malformed)//2,)) + malformed + b'\1\0\1\0')[2], 4)
        self.assertEqual(self.revision(), token); self.assertEqual(self.app.engine.memory.values, memory)


if __name__ == '__main__': unittest.main()
