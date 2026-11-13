"""FIND captures its active suffix, with explicit unknown and rollback limits."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_string_operations as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class FindWindowTests(unittest.TestCase):
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

    def test_ladder_and_st_search_after_unknown_prefix_with_original_positions(self):
        for st in (False, True):
            for start, result in ((4, 7), (7, 7), (8, 0)):
                e = self.checked('FIND(SourceA,Search,Start,Result);', st=st)
                e.memory.write('Start', start)
                self.unknown(e, 0, start - 1)
                with self.assertRaisesRegex(ModelError, 'unknown active DATA'):
                    e.memory.string('SourceA')
                original = copy.deepcopy(e.memory.values['sourcea'])
                e.memory.values['result'] = None
                e.step()
                self.assertEqual(e.memory.read('Result'), result)
                self.assertEqual(e.memory.values['sourcea'], original)

    def test_valid_start_beyond_active_len_consumes_no_source_data(self):
        for start in (10, 82):
            e = self.checked(['FIND(SourceA,Search,Start,Result);'])
            self.unknown(e, 0, 82)
            e.memory.write('Start', start)
            e.step()
            self.assertEqual(e.memory.read('Result'), 0)
            self.assertTrue(all(byte is None for byte in e.memory.values['sourcea']['DATA']))

    def test_complete_suffix_is_required_even_after_an_earlier_match_and_retries(self):
        e = self.checked(['MOV(77,SpeedCommand);', 'FIND(SourceA,Search,4,Result);'])
        self.unknown(e, 0, 3)
        e.memory.write('Search', '123')
        self.unknown(e, 8, 1)
        self.fault(e, 'unknown active DATA')
        e.memory.values['sourcea']['DATA'][8] = ord('C')
        e.step()
        self.assertEqual(e.memory.read('Result'), 4)
        self.assertEqual(e.memory.read('SpeedCommand'), 77)

    def test_search_data_is_required_even_without_a_source_suffix(self):
        for start in (7, 82):
            e = self.checked(['MOV(77,SpeedCommand);', 'FIND(SourceA,Search,Start,Result);'])
            e.memory.write('Start', start)
            self.unknown(e, 0, start - 1)
            self.unknown(e, 1, 1, 'search')
            self.fault(e, 'unknown active DATA')
            e.memory.values['search']['DATA'][1] = ord('B')
            e.step()
            self.assertEqual(e.memory.read('Result'), 7 if start == 7 else 0)

    def test_unknown_invalid_and_empty_metadata_still_fault_atomically(self):
        for ref, value in (('Start', 0), ('Start', 83), ('Start', None),
                           ('SourceA.LEN', -1), ('SourceA.LEN', 83), ('SourceA.LEN', None),
                           ('SourceA.LEN', 0), ('Search.LEN', 0), ('Search.LEN', 83), ('Search.LEN', None)):
            with self.subTest(ref=ref, value=value):
                e = self.checked(['MOV(77,SpeedCommand);', 'FIND(SourceA,Search,Start,Result);'])
                e.memory.write('Start', 7)
                self.unknown(e, 0, 6)
                key, parts, _ = e.memory.resolve(ref)
                e.memory.store(key, parts, value)
                self.fault(e, '(?i)unknown|nonempty|capacity')

    def test_nul_high_bytes_case_and_overlap_keep_byte_positions(self):
        e = self.checked(['FIND(SourceA,Search,3,Result);'])
        e.memory.write('SourceA', 'xxA\0\xffZ')
        e.memory.write('Search', '\0\xff')
        self.unknown(e, 0, 2)
        e.step()
        self.assertEqual(e.memory.read('Result'), 4)
        e.memory.write('Search', 'a')
        e.step()
        self.assertEqual(e.memory.read('Result'), 0)
        e.memory.write('SourceA', 'xxABABA')
        e.memory.write('Search', 'ABA')
        self.unknown(e, 0, 2)
        e.step()
        self.assertEqual(e.memory.read('Result'), 3)

    def test_custom_strings_indirect_selection_and_udt_aliases(self):
        for source, storage in (('Texts[Index]', ('texts', 0)), ('Alias', ('record', 'Text'))):
            e = self.checked([f'XIC(StartPB)FIND({source},Search,7,Result);'],
                             mutate=fixtures.StringOperationTests.custom_strings)
            e.memory.write('Index', 99)
            e.step()
            if source.startswith('Texts'):
                e.memory.write('StartPB', True)
                self.fault(e, 'outside bounds')
                e.memory.write('Index', 0)
            ref = 'Texts[0]' if source.startswith('Texts') else 'Record.Text'
            e.memory.write(ref, 'ABC123ABC')
            obj = e.memory.values[storage[0]][storage[1]]
            obj['DATA'][:6] = [None] * 6
            neighbor = copy.deepcopy(e.memory.values['texts'][1])
            e.memory.write('StartPB', True)
            e.step()
            self.assertEqual(e.memory.read('Result'), 7)
            self.assertEqual(e.memory.values['texts'][1], neighbor)

    def test_result_aliases_source_len_only_after_original_text_is_captured(self):
        e = self.checked(['FIND(SourceA,Search,7,SourceA.LEN);'])
        self.unknown(e, 0, 6)
        data = copy.deepcopy(e.memory.values['sourcea']['DATA'])
        e.step()
        self.assertEqual(e.memory.read('SourceA.LEN'), 7)
        self.assertEqual(e.memory.values['sourcea']['DATA'], data)

    def test_narrow_result_overflow_preserves_source_and_previous_advance(self):
        def narrow(root):
            tags = root.find('./Controller/Tags')
            result = tags.find('Tag[@Name="Result"]')
            result.set('DataType', 'SINT');result.find('Data/DataValue').set('DataType', 'SINT')
            members = E.SubElement(E.SubElement(root.find('./Controller/DataTypes'), 'DataType',
                                               Name='LongText', Class='User', Family='NoFamily'), 'Members')
            E.SubElement(members, 'Member', Name='LEN', DataType='DINT', Dimension='0')
            E.SubElement(members, 'Member', Name='DATA', DataType='SINT', Dimension='160')
            source = tags.find('Tag[@Name="SourceA"]');source.set('DataType', 'LongText')
            data = source.find('Data');data.clear();data.set('Format', 'Decorated')
            fixtures.string_data(data, 'X' * 129 + 'ABC', 160, 'LongText')
        e = self.checked(['MOV(77,SpeedCommand);', 'FIND(SourceA,Search,130,Result);'], mutate=narrow)
        self.unknown(e, 0, 129)
        self.fault(e, 'overflow')

    @staticmethod
    def aoi(root, st):
        c = root.find('Controller')
        definition = E.SubElement(c.find('AddOnInstructionDefinitions'), 'AddOnInstructionDefinition',
                                  Name='TextFind', Class='Standard', ExecutePrescan='false',
                                  ExecutePostscan='false', ExecuteEnableInFalse='false')
        params = E.SubElement(definition, 'Parameters')
        for name, dtype, usage, required in (
                ('EnableIn', 'BOOL', 'Input', 'false'), ('EnableOut', 'BOOL', 'Output', 'false'),
                ('Buffer', 'STRING', 'InOut', 'true'), ('Needle', 'STRING', 'InOut', 'true'),
                ('Position', 'DINT', 'Input', 'true'), ('Match', 'DINT', 'Output', 'true')):
            E.SubElement(params, 'Parameter', Name=name, DataType=dtype, Usage=usage,
                         Required=required, Visible=required, TagType='Base')
        E.SubElement(definition, 'LocalTags')
        routine = E.SubElement(E.SubElement(definition, 'Routines'), 'Routine', Name='Logic', Type='ST' if st else 'RLL')
        content = E.SubElement(routine, 'STContent' if st else 'RLLContent')
        parent = content if st else E.SubElement(content, 'Rung', Number='0', Type='N')
        E.SubElement(parent, 'Line' if st else 'Text', **({'Number': '0'} if st else {})).text = 'FIND(Buffer,Needle,Position,Match);'
        tag = E.SubElement(c.find('Tags'), 'Tag', Name='Instance', DataType='TextFind', TagType='Base')
        obj = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='TextFind')
        for name, dtype, value in [('EnableIn', 'BOOL', 0), ('EnableOut', 'BOOL', 0), ('Position', 'DINT', 1), ('Match', 'DINT', 99)]:
            E.SubElement(obj, 'DataValueMember', Name=name, DataType=dtype, Value=str(value))

    def test_aoi_ladder_st_bindings_and_late_fault_rollback(self):
        for st in (False, True):
            e = self.checked(['TextFind(Instance,SourceA,Search,Start,Result);', 'DIV(1,Count,SpeedCommand);'],
                             mutate=lambda root:self.aoi(root, st))
            e.memory.write('Start', 7)
            self.unknown(e, 0, 6)
            self.fault(e, 'zero')
            e.memory.write('Count', 1)
            e.step()
            self.assertEqual(e.memory.read('Result'), 7)
            self.assertEqual(e.memory.read('Instance.Position'), 7)
            self.assertTrue(e.memory.read('Instance.EnableOut'))

    def test_false_prescan_and_skipped_st_branch_do_not_consume_unknowns(self):
        for st, logic in ((False, 'AFI()FIND(SourceA,Search,Start,Result);'),
                          (True, 'IF FALSE THEN FIND(SourceA,Search,Start,Result); END_IF;')):
            e = self.checked(logic, st=st)
            e.memory.values['sourcea']['LEN'] = None
            e.memory.values['search']['LEN'] = None
            e.memory.values['start'] = None
            e.step()
            self.assertEqual(e.memory.read('Result'), 99)
        e = self.checked(['FIND(SourceA,Search,Start,Result);'])
        self.assertEqual(e.scan_count, 0)
        self.assertEqual(e.prescan_count, 1)

    def test_public_sample_and_report_expose_the_suffix_contract(self):
        e = Engine(Project(fixtures.SAMPLES / 'StringLab.L5X'))
        self.assertEqual(e.blockers, [])
        e.step();self.assertEqual(e.memory.read('FindResult'), 99)
        e.memory.write('FindWindow', True)
        for start, result in ((5, 5), (6, 7), (9, 0), (32, 0)):
            e.memory.write('FindStart', start);e.step()
            self.assertEqual(e.memory.read('FindResult'), result)
        e.memory.write('FindStart', 1);self.fault(e, 'unknown active DATA')
        e.memory.write('FindStart', 5);e.step()
        self.assertEqual(e.memory.read('FindResult'), 5)
        profile = e.report()['string_operations']['find']
        self.assertIn('earlier source', profile['reads'])
        self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
