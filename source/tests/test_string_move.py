"""Ladder string MOV, quoted RLL operands and transactional writes."""
import copy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_string_operations as fixtures
from logixlab.model import ModelError


class StringMoveTests(unittest.TestCase):
    setUp = fixtures.StringOperationTests.setUp
    engine = fixtures.StringOperationTests.engine
    checked = fixtures.StringOperationTests.checked

    @staticmethod
    def short_destination(root):
        controller = root.find('Controller')
        dtype = E.SubElement(controller.find('DataTypes'), 'DataType', Name='ShortText', Family='NoFamily', Class='User')
        members = E.SubElement(dtype, 'Members')
        E.SubElement(members, 'Member', Name='LEN', DataType='DINT', Dimension='0')
        E.SubElement(members, 'Member', Name='DATA', DataType='SINT', Dimension='4')
        tag = E.SubElement(controller.find('Tags'), 'Tag', Name='Short', TagType='Base', DataType='ShortText')
        fixtures.string_data(E.SubElement(tag, 'Data', Format='Decorated'), 'WXYZ', 4, 'ShortText')

    @staticmethod
    def string_rows(root):
        tags = root.find('./Controller/Tags')
        tag = E.SubElement(tags, 'Tag', Name='Rows', TagType='Base', DataType='STRING', Dimensions='2')
        E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='STRING', Dimensions='2')

    def test_short_and_long_string_writes_roll_back_without_copying_array(self):
        for length in (5, 70):
            with self.subTest(length=length):
                e = self.checked(['MOV(SourceA,Rows[1]);', 'XIC(StartPB)CPT(SpeedCommand,1/0);'],
                                 mutate=self.string_rows)
                e.memory.write_string('SourceA', 'ÿ' * length)
                e.memory.write('Rows[1].DATA[81]', 77)
                e.memory.write('StartPB', True)
                before = copy.deepcopy(e.memory.values['rows'])
                with patch.object(e.memory, '_remember', wraps=e.memory._remember) as remember:
                    with self.assertRaisesRegex(ModelError, 'zero'):
                        e.step()
                self.assertFalse({'rows', 'sourcea'} & {call.args[0] for call in remember.call_args_list})
                self.assertEqual(e.memory.values['rows'], before)
                e.memory.write('StartPB', False)
                e.step()
                self.assertEqual(e.memory.string('Rows[1]'), 'ÿ' * length)
                self.assertEqual(e.memory.read('Rows[1].DATA[81]'), 77)
                self.assertIsNone(e.memory.values['rows'][1]['DATA'][80])
                self.assertEqual(e.memory.values['rows'][0], before[0])

    def test_clipping_consumes_only_the_copied_prefix_and_retains_the_source(self):
        engine = self.checked(['MOV(SourceA,Short)XIC(S:V)OTE(RunLatch);'], mutate=self.short_destination)
        source = engine.memory.values['sourcea']
        source['DATA'][7] = None
        before = copy.deepcopy(source)
        engine.step()
        self.assertEqual(engine.memory.string('Short'), 'ABC1')
        self.assertTrue(engine.memory.read('RunLatch'))
        self.assertEqual(source, before)
        source['DATA'][2] = None
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'unknown active DATA'):
            engine.step()
        self.assertEqual(engine.memory.values, before)

    def test_clipped_literal_sets_overflow_and_fitting_literal_clears_it(self):
        engine = self.checked([
            "MOV('ABCDE',Short)[XIC(S:V)OTE(RunLatch),MOV('XY',Short)XIO(S:V)OTE(MotorRunning)];",
        ], mutate=self.short_destination)
        engine.step()
        self.assertEqual(engine.memory.string('Short'), 'XY')
        self.assertTrue(engine.memory.read('RunLatch'))
        self.assertTrue(engine.memory.read('MotorRunning'))

    def test_short_and_empty_moves_preserve_destination_tail_bytes(self):
        engine = self.checked(['MOV(SourceB,Short);'], mutate=self.short_destination)
        engine.step()
        self.assertEqual(engine.memory.string('Short'), 'XY')
        self.assertEqual(engine.memory.read('Short.DATA'), [88,89,89,90])
        engine.memory.write('SourceB', '')
        engine.step()
        self.assertEqual(engine.memory.read('Short.LEN'), 0)
        self.assertEqual(engine.memory.read('Short.DATA'), [88,89,89,90])

    def test_literal_punctuation_escape_and_parallel_rung_delimiters(self):
        engine = self.checked(["[MOV('Line [1], (ready); $'OK$' $$ $FF$I',Dest),MOV('',SourceB)];"])
        engine.step()
        self.assertEqual(engine.memory.string('Dest'), "Line [1], (ready); 'OK' $ ÿ\n")
        self.assertEqual(engine.memory.string('SourceB'), '')

    def test_alias_to_same_string_and_custom_destination(self):
        def tags(root):
            self.short_destination(root)
            E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Alias', TagType='Alias',
                         DataType='STRING', AliasFor='SourceA')
        engine = self.checked(['MOV(SourceA,Alias);','MOV(Alias,Short);','MOV(Short,Dest);'], mutate=tags)
        engine.step()
        self.assertEqual(engine.memory.string('Alias'), 'ABC123ABC')
        self.assertEqual(engine.memory.string('Dest'), 'ABC1')

    def test_false_and_prescan_skip_bad_index_and_later_fault_rolls_back(self):
        engine = self.checked(['XIC(StartPB)MOV(SourceB,Dest);','XIC(StartPB)MOV(SourceA,Rows[Index]);'],
                              mutate=self.string_rows)
        engine.memory.write('Index', 99)
        engine.step()
        self.assertEqual(engine.memory.string('Dest'), 'TAIL')
        engine.memory.write('StartPB', True)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        engine.memory.write('Index', 1)
        engine.step()
        self.assertEqual(engine.memory.string('Rows[1]'), 'ABC123ABC')
        self.assertEqual(engine.memory.string('Dest'), 'XY')
        self.assertIsNone(engine.memory.read('Rows[0]')['LEN'])

    def test_invalid_types_malformed_literals_and_permissions_block_even_when_false(self):
        for call in ("MOV('bad $Q',Dest)", "MOV('first' 'second',Dest)", "MOV('open,Dest)", "MOV('λ',Dest)",
                     'MOV(1,Dest)', 'MOV(SourceA,Result)', 'CLR(Dest)'):
            with self.subTest(call=call):
                self.assertTrue(self.engine(['AFI()'+call+';']).blockers)
        def read_only(root):
            root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()MOV(SourceA,Dest);'], mutate=read_only).blockers)
        def legacy(root):
            root.find('Controller').set('MajorRev', '34')
        self.assertTrue(self.engine(['AFI()MOV(SourceA,Dest);'], mutate=legacy).blockers)
