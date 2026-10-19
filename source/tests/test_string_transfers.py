"""Explicit user LEN/DATA structures: exact layout and access preservation."""
import base64
import copy
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.server import Application
from logixlab.ethernetip import Endpoint, Session
from test_ethernetip import request


def fixture(len_access='Read/Write', data_access='Read/Write'):
    root = E.Element('RSLogix5000Content', SchemaRevision='1.0', SoftwareRevision='35.01', TargetType='Controller', ContainsContext='false')
    controller = E.SubElement(root, 'Controller', Name='StringWireLab', ProcessorType='1756-L85E', MajorRev='35', MinorRev='11')
    types = E.SubElement(controller, 'DataTypes')
    text = E.SubElement(types, 'DataType', Name='UserText', Class='User', Family='NoFamily')
    members = E.SubElement(text, 'Members')
    E.SubElement(members, 'Member', Name='LEN', DataType='DINT', Dimension='0', ExternalAccess=len_access)
    E.SubElement(members, 'Member', Name='DATA', DataType='SINT', Dimension='9', ExternalAccess=data_access)
    record = E.SubElement(types, 'DataType', Name='TextRecord', Class='User', Family='NoFamily')
    members = E.SubElement(record, 'Members')
    E.SubElement(members, 'Member', Name='Sequence', DataType='DINT')
    E.SubElement(members, 'Member', Name='Text', DataType='UserText')
    tags = E.SubElement(controller, 'Tags')
    def value(parent, text, sequence=None):
        outer = E.SubElement(parent, 'Structure', DataType='TextRecord' if sequence is not None else 'UserText')
        if sequence is not None:
            E.SubElement(outer, 'DataValueMember', Name='Sequence', DataType='DINT', Value=str(sequence))
            outer = E.SubElement(outer, 'StructureMember', Name='Text', DataType='UserText')
        E.SubElement(outer, 'DataValueMember', Name='LEN', DataType='DINT', Value=str(len(text)))
        array = E.SubElement(outer, 'ArrayMember', Name='DATA', DataType='SINT', Dimensions='9')
        for i, byte in enumerate(text + b'\0' * (9-len(text))):
            E.SubElement(array, 'Element', Index=f'[{i}]', Value=str(byte if byte < 128 else byte-256))
    for name, dtype, dimension, access in [('Text', 'UserText', '0', 'Read/Write'),
             ('Texts', 'UserText', '2', 'Read/Write'), ('Record', 'TextRecord', '0', 'Read/Write'),
             ('Readonly', 'UserText', '0', 'Read Only')]:
        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype, Dimensions=dimension, ExternalAccess=access)
        data = E.SubElement(tag, 'Data', Format='Decorated')
        if dimension == '2':
            array = E.SubElement(data, 'Array', DataType=dtype, Dimensions='2')
            for i, text in enumerate((b'alpha', b'\xff\x80')):
                value(E.SubElement(array, 'Element', Index=f'[{i}]'), text)
        else:
            value(data, b'abc', 7 if dtype == 'TextRecord' else None)
    return E.tostring(root, encoding='utf-8')


def encoded(text, length=None):
    return struct.pack('<i', len(text) if length is None else length) + text + b'\0' * (12-len(text))


class StringTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.load()

    def load(self, **access):
        self.app.command('load', {'name': 'StringWireLab.L5X', 'content': base64.b64encode(fixture(**access)).decode()})
        self.endpoint = Endpoint(self.app, 0, True)
        self.router = self.endpoint.router
        self.session = Session(handle=1, generation=self.app.generation)

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def read(self, name='Text', count=1, offset=None, limit=480):
        data = struct.pack('<H', count) + (struct.pack('<I', offset) if offset is not None else b'')
        return self.router.handle(request(0x52 if offset is not None else 0x4C, name, data), self.session, limit=limit)

    def write(self, payload, name='Text', count=1, offset=None, dtype='UserText', handle=None):
        template = self.router.templates().for_type(dtype)
        data = struct.pack('<HHH', 0x02A0, template.handle if handle is None else handle, count)
        if offset is not None: data += struct.pack('<I', offset)
        return self.router.handle(request(0x53 if offset is not None else 0x4D, name, data + payload), self.session)

    def test_imported_explicit_string_layout_and_values(self):
        template = self.router.templates().for_type('UserText')
        self.assertEqual((template.size, template.alignment), (16, 4))
        self.assertEqual([(m.name, m.offset, m.count) for m in template.members], [('LEN', 0, 1), ('DATA', 4, 9)])
        self.assertEqual(self.read()[8:], encoded(b'abc'))
        self.assertEqual(self.read('Texts', 2)[8:], encoded(b'alpha') + encoded(b'\xff\x80'))
        symbols = {s['name']: s for s in self.router.symbols()}
        self.assertEqual(symbols['Texts']['dimensions'], [2, 0, 0])
        self.assertEqual(symbols['Texts']['type'], symbols['Text']['type'] | 0x2000)

    def test_nested_string_and_array_writes(self):
        self.assertEqual(self.read('Record')[8:], struct.pack('<i', 7) + encoded(b'abc'))
        self.assertEqual(self.write(encoded(b'new'), 'Record.Text')[2], 0)
        self.assertEqual(self.app.engine.memory.string('Record.Text'), 'new')
        payload = encoded(b'first') + encoded(b'second')
        self.assertEqual(self.write(payload, 'Texts', count=2)[2], 0)
        self.assertEqual(self.read('Texts', 2)[8:], payload)

    def test_fragmented_read_and_write_cross_record_boundary(self):
        original = encoded(b'alpha') + encoded(b'\xff\x80')
        pieces = []
        for offset in range(0, 32, 5):
            response = self.read('Texts', 2, offset, 13)
            self.assertEqual(response[2], 6 if offset+5 < 32 else 0)
            pieces.append(response[8:])
        self.assertEqual(b''.join(pieces), original)
        self.assertEqual(self.write(b'\0'*4 + struct.pack('<i', 3), 'Texts', count=2, offset=12)[2], 0)
        self.assertEqual(self.app.engine.memory.read('Texts[1].LEN'), 3)
        self.assertEqual(self.write(b'X', 'Texts', count=2, offset=20)[2], 0)
        self.assertEqual(self.app.engine.memory.read('Texts[1].DATA[0]'), 88)

    def test_split_unknown_length_rejects_without_changing_data(self):
        self.app.engine.memory.values['text']['LEN'] = None
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write(b'\0Z', offset=3)[2], 0x0C)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_read_only_len_applies_to_atomic_and_whole_writes(self):
        self.load(len_access='Read Only')
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write(encoded(b'blocked'))[2], 0x0F)
        atomic = request(0x4D, 'Text.LEN', struct.pack('<HHi', 0xC4, 1, 2))
        self.assertEqual(self.router.handle(atomic, self.session)[2], 0x0F)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.write(b'Z', offset=4)[2], 0)
        self.assertEqual(self.app.engine.memory.string('Text'), 'Zbc')

    def test_read_only_data_rejects_partial_and_whole_writes_atomically(self):
        self.load(data_access='Read Only')
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write(encoded(b'blocked'))[2], 0x0F)
        self.assertEqual(self.write(b'Z', offset=4)[2], 0x0F)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_padding_wrong_handles_and_read_only_tags_preserve_memory(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.write(encoded(b'new')[:-1]+b'\1')[2], 9)
        template = self.router.templates().for_type('UserText')
        self.assertEqual(self.write(encoded(b'new'), handle=template.handle ^ 1)[2], 0xFF)
        self.assertEqual(self.write(encoded(b'new'), 'Readonly')[2], 0x0F)
        self.assertEqual(self.app.engine.memory.values, before)

    def test_unknown_backing_bytes_are_not_invented(self):
        self.app.engine.memory.values['text']['DATA'][8] = None
        self.assertEqual(self.read()[2], 0x0C)
        self.assertEqual(self.write(encoded(b'known'))[2], 0)
        self.assertEqual(self.read()[8:], encoded(b'known'))

    def test_invalid_len_is_transferred_as_dint_and_string_execution_stays_guarded(self):
        self.assertEqual(self.write(encoded(b'abc', 10))[2], 0)
        self.assertEqual(self.read()[8:], encoded(b'abc', 10))
        from logixlab.model import ModelError
        with self.assertRaises(ModelError): self.app.engine.memory.string('Text')

    def test_private_members_prevent_whole_type_advertisement(self):
        self.load(data_access='None')
        self.assertIsNone(self.router.templates().for_type('UserText'))
        self.assertNotIn('Text', {s['name'] for s in self.router.symbols()})
        self.assertEqual(self.read()[2], 8)
        self.assertEqual(self.read('Text.DATA[0]')[2], 0x0F)

    def test_builtin_string_remains_explicitly_unsupported(self):
        self.app.command('demo', {'sample': 'TextLab'})
        self.endpoint = Endpoint(self.app, 0, False)
        self.router = self.endpoint.router
        self.session = Session(handle=1, generation=self.app.generation)
        self.assertEqual(self.read('Message')[2], 8)
        project = self.app.engine.project
        project.udts['string'] = E.fromstring('<DataType Name="STRING" Class="User" Family="NoFamily"><Members>'
            '<Member Name="LEN" DataType="DINT"/><Member Name="DATA" DataType="SINT" Dimension="9"/></Members></DataType>')
        self.router._catalog = None
        self.assertIsNone(self.router.templates().for_type('STRING'))
        self.assertEqual(self.read('Message')[2], 8)

    def test_nonscalar_length_definition_is_not_advertised(self):
        length = self.app.engine.project.udts['usertext'].find('./Members/Member')
        length.set('Dimension', '2')
        self.router._catalog = None
        self.assertIsNone(self.router.templates().for_type('UserText'))
        self.assertNotIn('Text', {s['name'] for s in self.router.symbols()})


if __name__ == '__main__':
    unittest.main()
