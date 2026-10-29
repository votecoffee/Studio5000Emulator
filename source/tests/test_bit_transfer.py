"""Common bit packing, masks, declared widths and emulator fault boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class BitTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, rungs, *, types=('DINT', 'DINT', 'DINT'), values=(0, -1, 0), mutate=None):
        source = Path(__file__).resolve().parents[1] / 'samples/ConveyorDemo.L5X'
        root = E.parse(source).getroot()
        tags = root.find('./Controller/Tags')
        for name, dtype, value in zip(('Source', 'Mask', 'Dest'), types, values):
            tag = E.SubElement(tags, 'Tag', Name=name, DataType=dtype, TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=dtype, Value=str(value))
        content = root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
        content.clear()
        for number, text in enumerate(rungs):
            E.SubElement(E.SubElement(content, 'Rung', Number=str(number), Type='N'), 'Text').text = text
        if mutate: mutate(root)
        path = Path(self.tmp.name) / 'fixture.L5X'
        E.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        return Engine(Project(path))

    def checked(self, *args, **kwargs):
        engine = self.engine(*args, **kwargs)
        self.assertEqual(engine.blockers, [])
        return engine

    def test_mask_preserves_unselected_bits_and_source(self):
        e = self.checked(['MVM(Source,Mask,Dest);'], values=(0x12345678, 0x00ff00ff, 0x76543210))
        e.step()
        self.assertEqual(e.memory.read('Dest'), 0x76343278)
        self.assertEqual(e.memory.read('Source'), 0x12345678)
        self.assertEqual(e.memory.read('Mask'), 0x00ff00ff)

    def test_mvm_zero_extends_each_declared_width(self):
        cases = ((('SINT','DINT','DINT'), (-1,-1,0), 255),
                 (('INT','DINT','DINT'), (-1,-1,0), 65535),
                 (('DINT','SINT','DINT'), (0,-1,-1), -256),
                 (('DINT','INT','DINT'), (0,-1,-1), -65536),
                 (('SINT','SINT','INT'), (-1,-1,-32768), -32513),
                 (('DINT','DINT','SINT'), (0x123456,-1,0), 0x56))
        for types, values, expected in cases:
            with self.subTest(types=types):
                e = self.checked(['MVM(Source,Mask,Dest);'], types=types, values=values)
                e.step(); self.assertEqual(e.memory.read('Dest'), expected)

    def test_mask_literals_in_decimal_hex_octal_and_binary(self):
        for mask in ('255', '16#FF', '8#377', '2#1111_1111'):
            e = self.checked([f'MVM(Source,{mask},Dest);'], values=(0x1234,0,-1))
            e.step(); self.assertEqual(e.memory.read('Dest'), -204)
        for mask in ('-1', '16#FFFF_FFFF', '8#37777777777', '2#'+'1'*32):
            e = self.checked([f'MVM(Source,{mask},Dest);'], values=(-2147483648,0,7))
            e.step(); self.assertEqual(e.memory.read('Dest'), -2147483648)

    def test_full_replacement_establishes_unknown_destination(self):
        for rung in ('MVM(Source,-1,Dest);', 'BTD(Source,0,Dest,0,32);'):
            e = self.checked([rung], values=(1234,0,0))
            e.memory.values['dest'] = None
            e.step(); self.assertEqual(e.memory.read('Dest'), 1234)

    def test_partial_replacement_requires_preserved_destination_bits(self):
        for rung in ('MVM(Source,255,Dest);', 'BTD(Source,0,Dest,0,8);'):
            e = self.checked([rung], values=(1234,0,0))
            e.memory.values['dest'] = None
            with self.assertRaisesRegex(ModelError, 'Unknown'): e.step()
            self.assertIsNone(e.memory.values['dest'])
            self.assertEqual((e.scan_count,e.time_ms), (0,0))

    def test_zero_mask_is_noop_even_for_unknown_source_and_destination(self):
        e = self.checked(['MVM(Source,0,Dest);'])
        e.memory.values['source'] = e.memory.values['dest'] = None
        e.step(); self.assertIsNone(e.memory.values['dest'])

    def test_false_rung_and_prescan_leave_values_unchanged(self):
        e = self.checked(['AFI()MVM(Source,Mask,Dest);', 'AFI()BTD(Source,0,Dest,0,32);'], values=(17,-1,29))
        self.assertEqual(e.memory.read('Dest'),29)
        e.memory.values['source'] = None
        e.step(); self.assertEqual(e.memory.read('Dest'),29)

    def test_rung_out_continues_through_bit_transfers(self):
        e = self.checked(['MVM(Source,255,Dest)BTD(Source,0,Dest,8,8)OTE(RunLatch);'], values=(0x35,0,0))
        e.step(); self.assertTrue(e.memory.read('RunLatch')); self.assertEqual(e.memory.read('Dest'),0x3535)

    def test_btd_extracts_and_inserts_a_field(self):
        e = self.checked(['BTD(Source,4,Dest,12,8);'], values=(0x1234,0,-1))
        e.step(); self.assertEqual(e.memory.read('Dest'), -901121)
        self.assertEqual(e.memory.read('Source'),0x1234)

    def test_btd_overlap_uses_source_value_before_write(self):
        for rung, expected in (('BTD(Dest,0,Dest,4,12);',0x2344),
                               ('BTD(Dest,4,Dest,0,12);',0x1123)):
            e = self.checked([rung], values=(0,0,0x1234))
            e.step(); self.assertEqual(e.memory.read('Dest'),expected)

    def test_btd_zero_fill_past_source_and_discard_past_destination(self):
        e = self.checked(['BTD(Source,4,Dest,0,16);'], types=('SINT','DINT','DINT'),values=(-1,0,-1))
        e.step(); self.assertEqual(e.memory.read('Dest'),-65521)
        e = self.checked(['BTD(Source,0,Dest,4,32);'], types=('DINT','DINT','SINT'),values=(0x12345678,0,3))
        e.step(); self.assertEqual(e.memory.read('Dest'),-125)

    def test_btd_sign_bit_and_complete_width_all_sizes(self):
        for dtype,bits in (('SINT',8),('INT',16),('DINT',32)):
            e = self.checked([f'BTD(1,0,Dest,{bits-1},1);'], types=('DINT','DINT',dtype))
            e.step(); self.assertEqual(e.memory.read('Dest'),-(1<<(bits-1)))
            e = self.checked([f'BTD(Source,0,Dest,0,{bits});'], types=(dtype,'DINT',dtype),values=(-1,0,0))
            e.step(); self.assertEqual(e.memory.read('Dest'),-1)

    def test_btd_literal_source_accepts_32_bit_pattern(self):
        e = self.checked(['BTD(16#FEDC_BA98,24,Dest,0,8);'])
        e.step(); self.assertEqual(e.memory.read('Dest'),254)

    def test_btd_configuration_must_be_immediate_and_in_declared_bounds(self):
        for rung in ('BTD(Source,Mask,Dest,0,8);','BTD(Source,0,Dest,Mask,8);','BTD(Source,0,Dest,0,Mask);',
                     'BTD(Source,-1,Dest,0,8);','BTD(Source,32,Dest,0,8);','BTD(Source,0,Dest,32,8);',
                     'BTD(Source,0,Dest,0,0);','BTD(Source,0,Dest,0,33);','BTD(Source,0.0,Dest,0,8);',
                     'BTD(Source,TRUE,Dest,0,8);'):
            with self.subTest(rung=rung): self.assertTrue(self.engine([rung]).blockers)
        for dtype,bits in (('SINT',8),('INT',16)):
            self.assertTrue(self.engine([f'BTD(Source,{bits},Dest,0,1);'],types=(dtype,'DINT','DINT')).blockers)
            self.assertTrue(self.engine([f'BTD(Source,0,Dest,{bits},1);'],types=('DINT','DINT',dtype)).blockers)

    def test_rejects_wide_unsigned_real_bool_aggregate_and_constant_destinations(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT','REAL','BOOL'):
            for types in ((dtype,'DINT','DINT'),('DINT',dtype,'DINT'),('DINT','DINT',dtype)):
                self.assertTrue(self.engine(['MVM(Source,Mask,Dest);'],types=types).blockers)
            for types in ((dtype,'DINT','DINT'),('DINT','DINT',dtype)):
                self.assertTrue(self.engine(['BTD(Source,0,Dest,0,8);'],types=types).blockers)
        def constant(root): root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        for rung in ('MVM(Source,Mask,Dest);','BTD(Source,0,Dest,0,8);'):
            self.assertTrue(self.engine([rung],mutate=constant).blockers)
        for rung in ('MVM(Source,Mask,Source.0);','MVM(Source,Mask,3);','BTD(Source,0,TRUE,0,1);'):
            self.assertTrue(self.engine([rung]).blockers)

    def test_rejects_unbounded_and_noninteger_immediates_and_bad_arities(self):
        for source in ('4294967296','2147483648','-2147483649','16#100000000','1.0','TRUE'):
            self.assertTrue(self.engine([f'MVM({source},-1,Dest);']).blockers)
            self.assertTrue(self.engine([f'BTD({source},0,Dest,0,8);']).blockers)
        for rung in ('MVM(Source,Dest);','BTD(Source,0,Dest,0);'):
            self.assertTrue(self.engine([rung]).blockers)

    def test_aliases_arrays_udt_members_indirect_index_and_no_array_wrap(self):
        def aggregate(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Word',DataType='DINT',Dimension='0')
            tags=c.find('Tags')
            index=E.SubElement(tags,'Tag',Name='Index',DataType='DINT',TagType='Base')
            E.SubElement(E.SubElement(index,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            array=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Words',DataType='INT',Dimensions='2',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='INT',Dimensions='2')
            for i,value in enumerate((-1,1234)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
            structure=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(structure,'DataValueMember',Name='Word',DataType='DINT',Value='0')
            E.SubElement(tags,'Tag',Name='AliasWord',TagType='Alias',DataType='DINT',AliasFor='Packet1.Word')
        e=self.checked(['MVM(Words[Index],-1,AliasWord);','BTD(Source,0,Words[Index],12,32);'],values=(-1,0,0),mutate=aggregate)
        e.step();self.assertEqual(e.memory.read('Packet1.Word'),65535)
        self.assertEqual(e.memory.read('Words[0]'),-1);self.assertEqual(e.memory.read('Words[1]'),1234)
        for rung in ('MVM(Words,-1,Dest);','BTD(Source,0,Words,0,8);'):
            self.assertTrue(self.engine([rung],mutate=aggregate).blockers)

    def test_late_unknown_read_rolls_back_earlier_moves_and_scheduler(self):
        e=self.checked(['MVM(12,-1,Dest);','BTD(Source,0,SpeedCommand,0,32);'])
        e.memory.values['source']=None;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_mvm_and_btd_remain_rll_only(self):
        for text in ('MVM(Source,Mask,Dest);','BTD(Source,0,Dest,0,8);'):
            def structured(root):
                routine=root.find('./Controller/Programs/Program/Routines/Routine')
                routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
                E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
            self.assertTrue(any('Unsupported ST instruction' in b for b in self.engine([],mutate=structured).blockers))

    def test_aoi_inout_and_parameter_bindings_use_bit_transfers(self):
        import test_addons as fixtures
        fixture=fixtures.AddOnTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.body()[0].find('Text').text='MVM(Step,16#FF,Total)BTD(Step,0,Shared,8,8);'
        e=fixture.engine();self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('TotalA'),2);self.assertEqual(e.memory.read('SharedA'),522)
        self.assertEqual(e.memory.read('TotalB'),3);self.assertEqual(e.memory.read('SharedB'),788)

    def test_report_describes_scope_and_native_status_boundary(self):
        e=self.checked(['MVM(Source,Mask,Dest);'])
        report=e.report()['bit_transfer']
        self.assertEqual(report['instructions'],['BTD','MVM']);self.assertEqual(report['types'],['SINT','INT','DINT'])
        self.assertFalse(report['native_math_status']);self.assertFalse(report['native_fault_classification'])

    def test_bundled_bit_lab_values_and_supported_inventory(self):
        from logixlab.server import SAMPLES
        self.assertIn('BitLab',SAMPLES)
        path=Path(__file__).resolve().parents[1]/'samples/BitLab.L5X'
        e=Engine(Project(path));self.assertEqual(e.blockers,[]);e.step()
        expected=dict(Status=0x123400aa,Packed=0xedcc00aa,LowWord=0x00aa,HighByte=-19,
                      MixedMask=-171,Overlap=0x2344,Truncated=-15150,BitOK=True)
        expected['Packed']-=1<<32
        for ref,value in expected.items():self.assertEqual(e.memory.read(ref),value,ref)
        self.assertIn('MVM',e.report()['supported_instructions']);self.assertIn('BTD',e.report()['supported_instructions'])


if __name__ == '__main__': unittest.main()
