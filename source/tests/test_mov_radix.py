"""MOV radix constants use DINT patterns before numeric destination conversion."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
import test_file_bcd as snapshots
from logixlab.model import ModelError, Project, literal
from logixlab.numeric_storage import typed_literal
from logixlab.runtime import Engine


class MovRadixTests(unittest.TestCase):
    setUp = fixtures.NumericStorageTests.setUp
    engine = fixtures.NumericStorageTests.engine
    checked = fixtures.NumericStorageTests.checked
    snapshot = staticmethod(snapshots.FileBcdTests.snapshot)
    fault = snapshots.FileBcdTests.fault

    def test_short_constants_are_zero_filled_in_all_three_bases(self):
        for text, expected in [('16#FFFF', 65535), ('8#1234', 668), ('2#1010', 10),
                               ('16#7FFFFFFF', 2147483647), ('16#0000FFFF', 65535)]:
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest='DINT')
            e.step(); self.assertEqual(e.memory.read('Results'), [None, expected, None])

    def test_bit_31_selects_the_signed_dint_value(self):
        for base in (2, 8, 16):
            for value in (0x80000000, 0x80000001, 0xfffffffe, 0xffffffff):
                digits = format(value, {2:'b', 8:'o', 16:'x'}[base])
                e = self.checked([f'MOV({base}#{digits},Results[1]);'], dest='DINT')
                e.step(); self.assertEqual(e.memory.read('Results[1]'), value - (1 << 32))

    def test_source_pattern_converts_to_all_ten_numeric_destination_types(self):
        expected = {'SINT':-1, 'INT':-1, 'DINT':-1, 'LINT':-1,
                    'USINT':255, 'UINT':65535, 'UDINT':4294967295,
                    'ULINT':18446744073709551615, 'REAL':-1.0, 'LREAL':-1.0}
        for base, dest in itertools.product((2, 8, 16), expected):
            digits = format(0xffffffff, {2:'b', 8:'o', 16:'X'}[base])
            e = self.checked([f'MOV({base}#{digits},Results[1]);'], dest=dest)
            e.step(); self.assertEqual(e.memory.read('Results'), [None, expected[dest], None])
            self.assertIs(type(e.memory.read('Results[1]')), float if dest in ('REAL','LREAL') else int)

    def test_signed_widening_differs_from_unsigned_decimal_source(self):
        e = self.checked(['MOV(16#FFFFFFFF,Results[0]);', 'MOV(4294967295U,Results[1]);'], dest='LINT')
        e.step(); self.assertEqual(e.memory.read('Results'), [-1, 4294967295, None])

    def test_integer_to_real_rounding_follows_dint_source_precision(self):
        for dest, expected in [('REAL',2147483648.0), ('LREAL',2147483647.0)]:
            e = self.checked(['MOV(16#7FFFFFFF,Results[1]);'], dest=dest)
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_grouping_leading_zeroes_and_hexadecimal_case(self):
        for text, expected in [('16#ffff ffff',-1), ('16#0000_FfFf',65535),
                               ('2#1000_0000 0000_0000 0000_0000 0000_0000',-2147483648),
                               ('8#37 777 777 777',-1), ('16#00000000000000000000',0)]:
            self.assertEqual(typed_literal(text), ('DINT',expected))
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest='LINT')
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_overwide_patterns_are_structurally_blocked_on_false_rungs(self):
        for text in ('16#100000000','8#40000000000','2#1'+'0'*32):
            e = self.engine(['AFI()MOV(' + text + ',Results[1]);'])
            self.assertTrue(e.blockers, text); self.assertIn('32-bit', str(e.blockers))

    def test_invalid_digits_and_excluded_suffix_expression_forms_stay_blocked(self):
        for text in ('2#2','8#8','16#G','16#','16#___','16#FFLU','16#FFFFFFFFLL',
                     '16#FF+1','(16#FF)','DINT#16#FF','+16#FF','2147483648'):
            self.assertTrue(self.engine(['AFI()MOV(' + text + ',Results[1]);']).blockers, text)

    def test_false_and_prescan_skip_unknown_data_and_invalid_destination_indices(self):
        e = self.checked(['XIC(StartPB)MOV(16#FFFFFFFF,Results[Index]);'], dest='LINT')
        e.memory.values['source'] = None; e.memory.write('Index',999); e.step()
        self.assertEqual(e.memory.read('Results'), [None]*3)
        e.memory.write('StartPB',True); self.fault(e,'outside bounds')
        e.memory.write('Index',1); e.step(); self.assertEqual(e.memory.read('Results'), [None,-1,None])

    def test_late_fault_restores_prior_writes_and_scan_history(self):
        e = self.checked(['MOV(16#FFFFFFFF,Results[1]);','DIV(1,Index,Dest);'], dest='DINT')
        self.fault(e,'zero'); e.memory.write('Index',1); e.step()
        self.assertEqual(e.memory.read('Results'), [None,-1,None])

    def test_alias_udt_members_preserve_their_unwritten_guards(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='LINT',Dimension='0')
            record=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(record,'DataValueMember',Name='Guard',DataType='LINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['MOV(16#FFFF FFFF,AliasValue);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(-1,777))

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        import test_lreal_results as results
        results.LrealResultTests.aoi_fields(root,'LINT')
        queues.logic(root,['MOV(16#FFFFFFFF,Buffer[Index]);','MOV(16#FFFF,Item);','MOV(16#80000000,Stack[Index]);'])
        queues.logic(root,['AFI()MOV(16#FFFFFFFF,Stack[Index]);'],name='EnableInFalse')

    def test_warm_aoi_inout_output_local_values_and_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.checked(self.aoi_fields);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('ItemA'),e.memory.read('DriverA.Stack[1]')),(-1,65535,-2147483648.0))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),-1)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_controller_and_firmware_gates_preserve_legacy_contracts(self):
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()MOV(16#FFFFFFFF,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_constant_destinations_and_other_consumers_do_not_widen(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()MOV(16#FFFFFFFF,Results[1]);'],mutate=constant).blockers)
        for text in ('FLL(16#FFFFFFFF,Results[1],1);','CLR(16#FFFFFFFF);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for text in ('CPT(Results[1],16#FFFFFFFF);','MOV(1,Results[16#FFFFFFFF]);'):
            self.fault(self.checked([text]),'DINT overflow')
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_report_describes_bounded_radix_source_scope(self):
        row=self.checked().report()['numeric_storage']['radix_mov_literals']
        self.assertEqual((row['bases'],row['source_type'],row['bits']),([2,8,16],'DINT',32))
        self.assertFalse(row['native_runtime_parity'])

    def test_sample_qualifies_selection_conversion_and_atomic_retry(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('RadixSelected'),[None,None,903])
        e.memory.write('RadixEnabled',True);e.step()
        for name,value in [('RadixSigned',-1),('RadixZeroFilled',65535),('RadixSignExtended',-2147483648),('RadixUnsigned',(1<<64)-1),('RadixReal',2147483648.0)]:self.assertEqual(e.memory.read(name),value)
        self.assertEqual(e.memory.read('RadixSelected'),[-1,None,903])
        e.memory.write('RadixIndex',1);e.memory.write('RadixLateDivisor',0);self.fault(e,'zero')
        e.memory.write('RadixLateDivisor',1);e.step();self.assertEqual(e.memory.read('RadixSelected'),[-1,-1,903])
        e.memory.write('RadixEnabled',False);e.memory.write('RadixIndex',999);e.step()


if __name__=='__main__':unittest.main()
