"""DELETE consumes retained text, with unknown-data and transaction boundaries."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_string_operations as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class DeleteWindowTests(unittest.TestCase):
    setUp = fixtures.StringOperationTests.setUp
    engine = fixtures.StringOperationTests.engine
    checked = fixtures.StringOperationTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.addons.instances,
                              e.scan_count, e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def fault(self, e, pattern):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, pattern):
            e.step()
        self.assertEqual(self.snapshot(e), before)

    @staticmethod
    def unknown(e, first, count, ref='sourcea'):
        e.memory.values[ref]['DATA'][first:first + count] = [None] * count

    def test_middle_unknown_window_is_removed_in_ladder_and_st(self):
        for st in (False, True):
            e = self.checked('DELETE(SourceA,3,4,Dest);', st=st)
            self.unknown(e, 3, 3)
            e.step()
            self.assertEqual(e.memory.string('Dest'), 'ABCABC')
            self.assertEqual(e.memory.values['sourcea']['DATA'][3:6], [None] * 3)

    def test_unknown_prefix_suffix_and_entire_text_can_be_removed(self):
        for first, count, expected in ((0, 3, '123ABC'), (6, 3, 'ABC123'), (0, 9, '')):
            e = self.checked([f'DELETE(SourceA,{count},{first + 1},Dest);'])
            self.unknown(e, first, count)
            e.step()
            self.assertEqual(e.memory.string('Dest'), expected)
            self.assertEqual(e.memory.values['sourcea']['LEN'], 9)

    def test_full_deletion_establishes_unknown_len_and_preserves_backing_data(self):
        e = self.checked(['DELETE(SourceA,9,1,Dest);'])
        self.unknown(e, 0, 9)
        original = copy.deepcopy(e.memory.values['dest']['DATA'])
        e.memory.values['dest']['LEN'] = None
        e.memory.values['dest']['DATA'][7] = None
        original[7] = None
        e.step()
        self.assertEqual(e.memory.string('Dest'), '')
        self.assertEqual(e.memory.values['dest']['DATA'], original)

    def test_retained_prefix_and_suffix_unknowns_fault_and_retry(self):
        for index in (0, 8):
            e = self.checked(['MOV(77,SpeedCommand);', 'DELETE(SourceA,3,4,Dest);'])
            self.unknown(e, 3, 3)
            self.unknown(e, index, 1)
            self.fault(e, 'unknown active DATA')
            e.memory.values['sourcea']['DATA'][index] = 65
            e.step()
            self.assertEqual(e.memory.string('Dest'), 'ABCABA' if index == 8 else 'ABCABC')

    def test_alias_destination_uses_original_retained_bytes(self):
        def alias(root):
            E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Alias', TagType='Alias', AliasFor='SourceA')
        e = self.checked(['DELETE(SourceA,3,4,Alias);'], mutate=alias)
        self.unknown(e, 3, 3)
        e.step()
        self.assertEqual(e.memory.string('SourceA'), 'ABCABC')
        self.assertEqual(e.memory.values['sourcea']['DATA'][6:9], [65, 66, 67])

    def test_nul_and_high_retained_bytes_preserve_unsigned_byte_values(self):
        e = self.checked(['DELETE(SourceA,2,3,Dest);'])
        e.memory.write('SourceA', 'A\0xx\xffZ')
        self.unknown(e, 2, 2)
        e.step()
        self.assertEqual(e.memory.string('Dest'), 'A\0\xffZ')

    def test_result_capacity_is_checked_after_removal_and_rolls_back(self):
        e = self.checked(['MOV(77,SpeedCommand);', 'DELETE(SourceA,Qty,4,Record.Text);'],
                         mutate=fixtures.StringOperationTests.custom_strings)
        e.memory.write('SourceA', 'ABC' + 'x' * 20 + 'DEF')
        self.unknown(e, 3, 20)
        e.memory.write('Qty', 20)
        e.step()
        self.assertEqual(e.memory.string('Record.Text'), 'ABCDEF')
        e.memory.write('SourceA', 'A' * 26)
        e.memory.write('Qty', 1)
        self.fault(e, 'capacity')

    def test_invalid_ranges_lengths_and_required_unknown_metadata_still_fault(self):
        for tag, value in (('Start', 0), ('Start', 83), ('Start', 10), ('Qty', 0), ('Qty', -1), ('Qty', 10),
                           ('Start', None), ('Qty', None), ('SourceA.LEN', -1), ('SourceA.LEN', 83), ('SourceA.LEN', None)):
            with self.subTest(tag=tag, value=value):
                e = self.checked(['DELETE(SourceA,Qty,Start,Dest);'])
                if value is None:
                    key, parts, _ = e.memory.resolve(tag)
                    e.memory.store(key, parts, None)
                else:
                    e.memory.write(tag, value)
                self.fault(e, 'DELETE|LEN|Unknown')

    def test_false_ladder_and_unreached_st_skip_unknown_metadata(self):
        for st, text in ((False, 'AFI()DELETE(SourceA,Qty,Start,Dest);'),
                         (True, 'IF FALSE THEN DELETE(SourceA,Qty,Start,Dest); END_IF;')):
            e = self.checked(text, st=st)
            e.memory.values['sourcea']['LEN'] = None
            e.memory.values['qty'] = None
            e.memory.values['start'] = None
            e.step()
            self.assertEqual(e.memory.string('Dest'), 'TAIL')

    def test_selected_udt_destinations_and_aliases_use_live_indices(self):
        e = self.checked(['XIC(StartPB)DELETE(Texts[Index],2,3,Record.Text);'],
                         mutate=fixtures.StringOperationTests.custom_strings)
        neighbor = copy.deepcopy(e.memory.values['texts'][1])
        e.memory.write('Index', 99)
        e.step()
        e.memory.write('StartPB', True)
        self.fault(e, 'outside bounds')
        e.memory.write('Index', 0)
        e.memory.write('Texts[0]', 'ABxxCD')
        e.memory.values['texts'][0]['DATA'][2:4] = [None, None]
        e.step()
        self.assertEqual(e.memory.string('Record.Text'), 'ABCD')
        self.assertEqual(e.memory.values['texts'][1], neighbor)

    @staticmethod
    def aoi(root, st):
        controller = root.find('Controller')
        definition = E.SubElement(controller.find('AddOnInstructionDefinitions'), 'AddOnInstructionDefinition',
                                  Name='TextDelete', Class='Standard', ExecutePrescan='false',
                                  ExecutePostscan='false', ExecuteEnableInFalse='false')
        params = E.SubElement(definition, 'Parameters')
        fields = [('EnableIn', 'BOOL', 'Input', 'false'), ('EnableOut', 'BOOL', 'Output', 'false'),
                  ('Buffer', 'STRING', 'InOut', 'true'), ('Result', 'STRING', 'InOut', 'true'),
                  ('Position', 'DINT', 'Input', 'true'), ('Amount', 'DINT', 'Input', 'true')]
        for name, dtype, usage, required in fields:
            E.SubElement(params, 'Parameter', Name=name, DataType=dtype, Usage=usage,
                         Required=required, Visible=required, TagType='Base')
        E.SubElement(definition, 'LocalTags')
        routine = E.SubElement(E.SubElement(definition, 'Routines'), 'Routine', Name='Logic', Type='ST' if st else 'RLL')
        content = E.SubElement(routine, 'STContent' if st else 'RLLContent')
        parent = content if st else E.SubElement(content, 'Rung', Number='0', Type='N')
        E.SubElement(parent, 'Line' if st else 'Text', **({'Number': '0'} if st else {})).text = 'DELETE(Buffer,Amount,Position,Result);'
        tag = E.SubElement(controller.find('Tags'), 'Tag', Name='Instance', DataType='TextDelete', TagType='Base')
        obj = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='TextDelete')
        for name, dtype, value in [('EnableIn', 'BOOL', 0), ('EnableOut', 'BOOL', 0), ('Position', 'DINT', 1), ('Amount', 'DINT', 3)]:
            E.SubElement(obj, 'DataValueMember', Name=name, DataType=dtype, Value=str(value))

    def test_aoi_ladder_st_bindings_and_late_fault_rollback(self):
        for st in (False, True):
            e = self.checked(['TextDelete(Instance,SourceA,Dest,4,3);', 'DIV(1,Count,SpeedCommand);'],
                             mutate=lambda root: self.aoi(root, st))
            self.unknown(e, 3, 3)
            self.fault(e, 'zero')
            e.memory.write('Count', 1)
            e.step()
            self.assertEqual(e.memory.string('Dest'), 'ABCABC')
            self.assertEqual(e.memory.read('Instance.Position'), 4)
            self.assertTrue(e.memory.read('Instance.EnableOut'))

    def test_sample_and_report_expose_the_retained_window_contract(self):
        e = Engine(Project(fixtures.SAMPLES / 'StringLab.L5X'))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.string('DeleteResult'), 'old')
        e.memory.write('DeleteWindow', True)
        e.step()
        self.assertEqual(e.memory.string('DeleteResult'), 'ABCD')
        self.assertEqual(e.memory.read('DeleteResult.DATA[31]'), 33)
        e.memory.write('DeleteQty', 3)
        self.fault(e, 'unknown active DATA')
        e.memory.write('DeleteQty', 4)
        e.step()
        report = e.report()['string_operations']['delete']
        self.assertIn('removed', report['reads'])
        self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
