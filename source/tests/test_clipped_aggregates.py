"""Logical record/string clipping, captured windows and complete ST effects."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_aggregate_copy as copies
import test_aggregate_fill as fills
from test_numeric_copy import logic
from logixlab.model import ModelError


class ClippedAggregateTests(unittest.TestCase):
    setUp=copies.AggregateCopyTests.setUp
    fields=staticmethod(copies.AggregateCopyTests.fields)
    engine=copies.AggregateCopyTests.engine
    checked=copies.AggregateCopyTests.checked
    snapshot=staticmethod(copies.AggregateCopyTests.snapshot)
    assert_cell_zero=fills.AggregateFillTests.assert_cell_zero

    def fault(self,e,expected):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,expected):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_cop_and_cps_clip_at_the_shorter_remaining_source_or_destination(self):
        for op in ('COP','CPS'):
            e=self.checked([f'{op}(Records[2],CopyRecords[0],100000);']);before=copy.deepcopy(e.memory.values);e.step()
            self.assertEqual(e.memory.read('CopyRecords')[0],before['records'][2]);self.assertEqual(e.memory.read('CopyRecords')[1:],before['copyrecords'][1:])
            e=self.checked([f'{op}(Records[0],CopyRecords[2],100000);']);e.memory.write('Records[0].Count',11);before=copy.deepcopy(e.memory.values);e.step()
            self.assertEqual(e.memory.read('CopyRecords')[2]['Count'],11);self.assertEqual(e.memory.read('CopyRecords')[:2],before['copyrecords'][:2])

    def test_all_basic_record_and_string_fills_clip_and_establish_unknown_tail_only(self):
        for name in ('Records','Timers','Counters','Controls','Texts','CustomTexts'):
            e=self.checked([f'FLL(0,{name}[2],100000);']);before=copy.deepcopy(e.memory.read(name));e.step()
            self.assertEqual(e.memory.read(name)[:2],before[:2])
            if name=='Records':self.assert_cell_zero(e.memory.read(name)[2])
            elif name in ('Texts','CustomTexts'):self.assertEqual(e.memory.string(name+'[2]'),'');self.assertTrue(all(v==0 for v in e.memory.read(name)[2]['DATA']))
            else:self.assertEqual(e.memory.read(name)[2],e.project.default(e.memory.resolve(name)[2]))

    def test_all_basic_record_and_string_copies_clip_and_keep_complete_logical_unknowns(self):
        for name in ('Records','Timers','Counters','Controls','Texts','CustomTexts'):
            for op in ('COP','CPS'):
                e=self.checked([f'{op}({name}[2],Copy{name}[1],100000);']);before=copy.deepcopy(e.memory.read(name));guard=copy.deepcopy(e.memory.read('Copy'+name));e.step()
                self.assertEqual(e.memory.read('Copy'+name)[1],before[2]);self.assertEqual(e.memory.read('Copy'+name)[0],guard[0]);self.assertEqual(e.memory.read('Copy'+name)[2],guard[2])

    def test_scalar_record_targets_clip_to_one_and_own_independent_storage(self):
        def solo(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Solo',DataType='FillCell',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FillCell')
        for op in ('COP','CPS'):
            e=self.checked([f'{op}(Records[2],Solo,100000);'],solo);e.step();self.assertEqual(e.memory.read('Solo.Count'),777)
            e.memory.write('Solo.Count',9);self.assertEqual(e.memory.read('Records[2].Count'),777)
        e=self.checked(['FLL(0,Solo,100000);'],solo);e.step();self.assert_cell_zero(e.memory.read('Solo'))

    @staticmethod
    def matrix(root):
        tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Grid',DataType='FillCell',TagType='Base',Dimensions='2,2');array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='FillCell',Dimensions='2,2')
        for i,value in enumerate((101,11,22,33)):
            record=E.SubElement(E.SubElement(array,'Element',Index=f'[{i//2},{i%2}]'),'Structure',DataType='FillCell');E.SubElement(record,'DataValueMember',Name='Count',DataType='DINT',Value=str(value))

    def test_multidimensional_windows_are_row_major_and_clipped(self):
        e=self.checked(['CPS(Grid[0,1],CopyRecords[1],100000);'],self.matrix);e.step();self.assertEqual([r['Count'] for r in e.memory.read('CopyRecords')],[None,11,22]);self.assertEqual(e.memory.read('Grid[1,1].Count'),33)
        e=self.checked(['FLL(0,Grid[1,0],100000);'],self.matrix);e.step();self.assertEqual([r['Count'] for row in e.memory.read('Grid') for r in row],[101,11,0,0])

    @staticmethod
    def members(root):
        members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Box'),'Members');E.SubElement(members,'Member',Name='Cells',DataType='FillCell',Dimension='3');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
        tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Boxed',DataType='Box',TagType='Base');record=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Box');E.SubElement(record,'ArrayMember',Name='Cells',DataType='FillCell',Dimensions='3');E.SubElement(record,'DataValueMember',Name='Guard',DataType='DINT',Value='999')
        E.SubElement(root.find('./Controller/Tags'),'Tag',Name='View',DataType='FillCell',TagType='Alias',AliasFor='Boxed.Cells')

    def test_member_aliases_clip_without_crossing_sibling_members(self):
        e=self.checked(['COP(Records[2],View[1],100000);','FLL(0,View[2],100000);'],self.members);e.step()
        self.assertEqual(e.memory.read('Boxed.Cells[1].Count'),777);self.assertIsNone(e.memory.read('Boxed.Cells')[0]['Count']);self.assert_cell_zero(e.memory.read('Boxed.Cells[2]'));self.assertEqual(e.memory.read('Boxed.Guard'),999)

    def test_lengths_indices_and_forward_overlap_are_captured_before_stores(self):
        e=self.checked(['COP(Records[0],Records[1],Records[1].Count);']);e.memory.write('Records[0].Count',7);e.memory.write('Records[1].Count',100000);e.step();self.assertEqual([r['Count'] for r in e.memory.read('Records')],[7,7,7])
        e=self.checked(['CPS(Records[0],Records[Records[1].Count],100000);']);e.memory.write('Records[0].Count',7);e.memory.write('Records[1].Count',1);e.step();self.assertEqual([r['Count'] for r in e.memory.read('Records')],[7,7,7])
        e=self.checked(['FLL(Records[1].Count,Records[0],Records[0].Count);']);e.memory.write('Records[0].Count',100000);e.memory.write('Records[1].Count',0);e.step()
        for row in e.memory.read('Records'):self.assert_cell_zero(row)

    def test_zero_length_skips_record_values_but_not_required_addresses(self):
        e=self.checked(['COP(Records[SourceIndex],CopyRecords[Index],0);']);self.fault(e,'outside bounds');e.memory.write('SourceIndex',0);e.memory.write('Index',0);before=copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values,before)
        e=self.checked(['FLL(Zeros[SourceIndex],Records[Index],0);']);self.fault(e,'outside bounds');e.memory.write('Index',0);e.step();self.assertIsNone(e.memory.read('Records')[0]['Count'])

    def test_requested_size_does_not_charge_work_for_elements_beyond_the_clip(self):
        for text in ('COP(Records[2],CopyRecords[2],100000);','CPS(Records[2],CopyRecords[2],100000);','FLL(0,Records[2],100000);'):
            e=self.checked([text]);e.instruction_limit=100;e.step();self.assertEqual(e.scan_count,1)
            e=self.checked([text]);e.instruction_limit=10;self.fault(e,'scalar-member budget')

    @staticmethod
    def st(root,text):
        routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST');logic(routine,[text])

    def test_st_copy_effects_respect_source_clipping_and_protect_actual_target_members(self):
        for op in ('COP','CPS'):
            text=f'FOR SpeedCommand:=0 TO CopyRecords[2].Count DO {op}(Records[2],CopyRecords[1],100000); END_FOR;'
            e=self.checked([],lambda root:self.st(root,text));e.memory.write('CopyRecords[2].Count',2);e.step();self.assertEqual(e.memory.read('SpeedCommand'),3);self.assertEqual(e.memory.read('CopyRecords[1].Count'),777)
            bad=text.replace('TO CopyRecords[2].Count','TO CopyRecords[1].Count');self.assertTrue(any('bounds/step' in b for b in self.engine([],lambda root:self.st(root,bad)).blockers))

    def test_st_fill_effects_protect_clipped_tail_and_zero_length_is_empty(self):
        text='FOR SpeedCommand:=0 TO Records[2].Count DO FLL(0,Records[1],100000); END_FOR;'
        self.assertTrue(any('bounds/step' in b for b in self.engine([],lambda root:self.st(root,text)).blockers))
        text='FOR SpeedCommand:=0 TO Records[2].Count DO FLL(Zeros[SourceIndex],Records[1],0); END_FOR;'
        e=self.checked([],lambda root:self.st(root,text));e.memory.write('Records[2].Count',2);e.step();self.assertEqual(e.memory.read('SpeedCommand'),3);self.assertIsNone(e.memory.read('Records')[1]['Count'])

    def test_dynamic_copy_and_fill_effects_conservatively_cover_the_member(self):
        for text in ('FOR SpeedCommand:=0 TO CopyRecords[2].Count DO CPS(Records[SourceIndex],CopyRecords[1],1); END_FOR;',
                     'FOR SpeedCommand:=0 TO Records[2].Count DO FLL(0,Records[Index],Lengths[0]); END_FOR;'):
            self.assertTrue(any('bounds/step' in b for b in self.engine([],lambda root:self.st(root,text)).blockers))

    @staticmethod
    def clipped_aoi(root):
        copies.AggregateCopyTests.aoi_logic(root)
        for node in root.findall('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="FillWorker"]/Routines/Routine/RLLContent/Rung/Text'):node.text=node.text.replace(',1);',',100000);')

    def test_aoi_inout_local_clips_and_later_fault_roll_back_bindings(self):
        e=self.checked(['XIC(EnabledA)FillWorker(First,Records,IndexA);','XIC(EnabledB)FillWorker(Second,Records,IndexB);','DIV(1,SpeedSetpoint,SpeedCommand);'],self.clipped_aoi)
        e.memory.write('IndexB',1)
        for i,value in enumerate((11,22,33)):e.memory.write(f'Records[{i}].Count',value)
        e.memory.write('SpeedSetpoint',0);self.fault(e,'zero');e.memory.write('SpeedSetpoint',1);e.step()
        self.assertEqual([r['Count'] for r in e.memory.read('Records')],[11,22,33]);self.assertEqual([r['Count'] for r in e.memory.read('First.LocalCells')],[11,22]);self.assertEqual(e.memory.read('Second.LocalCells')[1]['Count'],22)

    def test_reports_keep_logical_clipping_separate_from_native_byte_layouts(self):
        e=self.checked(['NOP();']);report=e.report()
        for name in ('aggregate_copy','aggregate_fill'):
            self.assertTrue(report[name]['clipping']);self.assertIn('logical',report[name]['clipping_boundary']);self.assertFalse(report[name]['native_runtime_parity'])
