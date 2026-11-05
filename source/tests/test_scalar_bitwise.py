"""Declared-width ladder bitwise operations, lazy values and rollback."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_scalar_math as fixtures
from logixlab.model import ModelError

OPS = ('AND','OR','XOR','NOT')


def instruction(name, source='Source', other='Mask', dest='Results[1]'):
    return name+'('+','.join((source,dest) if name=='NOT' else (source,other,dest))+')'


class ScalarBitwiseTests(unittest.TestCase):
    setUp = fixtures.ScalarMathTests.setUp
    checked = fixtures.ScalarMathTests.checked
    snapshot = staticmethod(fixtures.ScalarMathTests.snapshot)

    def engine(self, rungs=None, *, source='SINT', other='DINT', dest='DINT', value=-1, mask=256, mutate=None):
        def fields(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Mask"]');tag.set('DataType',other)
            node=tag.find('Data/DataValue');node.set('DataType',other);node.set('Value',str(mask))
            if mutate:mutate(root)
        return fixtures.ScalarMathTests.engine(self,rungs or ['OR(Source,Mask,Results[1]);'],source=source,dest=dest,value=value,mutate=fields)

    def test_mixed_negative_sources_are_zero_extended_in_both_orders(self):
        cases=(('SINT','DINT',-1,256,(0,511,511)),('DINT','SINT',256,-1,(0,511,511)),
               ('INT','DINT',-1,65536,(0,131071,131071)),('DINT','INT',65536,-1,(0,131071,131071)),
               ('SINT','INT',-1,256,(0,511,511)),('INT','SINT',256,-1,(0,511,511)))
        for source,other,a,b,results in cases:
            for name,expected in zip(OPS,results):
                with self.subTest(source=source,other=other,op=name):
                    e=self.checked([instruction(name)+';'],source=source,other=other,value=a,mask=b);e.step()
                    self.assertEqual(e.memory.read('Results'),[None,expected,None])

    def test_all_eighty_one_binary_declared_width_combinations(self):
        # Both sources are -1. These explicit bit-pattern results distinguish
        # source zero extension from host negative-integer sign extension.
        patterns={('SINT','SINT'):(255,255,0),('SINT','INT'):(255,65535,65280),
                  ('SINT','DINT'):(255,4294967295,4294967040),('INT','SINT'):(255,65535,65280),
                  ('INT','INT'):(65535,65535,0),('INT','DINT'):(65535,4294967295,4294901760),
                  ('DINT','SINT'):(255,4294967295,4294967040),('DINT','INT'):(65535,4294967295,4294901760),
                  ('DINT','DINT'):(4294967295,4294967295,0)}
        for (source,other),results in patterns.items():
            for dest in ('SINT','INT','DINT'):
                for name,pattern in zip(OPS,results):
                    e=self.checked([instruction(name)+';'],source=source,other=other,dest=dest,mask=-1);e.step()
                    size={'SINT':1,'INT':2,'DINT':4}[dest]
                    expected=int.from_bytes(pattern.to_bytes(4,'little')[:size],'little',signed=True)
                    self.assertEqual(e.memory.read('Results[1]'),expected,(source,other,dest,name))

    def test_not_zero_extends_before_widening_and_keeps_low_bits_when_narrowing(self):
        for source,dest,value,expected in (('SINT','SINT',-1,0),('SINT','INT',-1,-256),('SINT','DINT',-1,-256),
                                           ('INT','SINT',-1,0),('INT','INT',-1,0),('INT','DINT',-1,-65536),
                                           ('DINT','SINT',-1,0),('DINT','INT',-1,0),('DINT','DINT',-1,0),
                                           ('DINT','SINT',255,0),('DINT','SINT',256,-1),('DINT','INT',65536,-1),
                                           ('DINT','SINT',0x12345678,-121),('DINT','INT',0x12345678,-22137)):
            e=self.checked(['NOT(Source,Results[1]);'],source=source,dest=dest,value=value);e.step()
            self.assertEqual(e.memory.read('Results[1]'),expected,(source,dest,value))

    def test_full_dint_radix_patterns_and_decimal_immediates(self):
        for literal in ('-1','16#FFFF_FFFF','8#37777777777','2#'+'1'*32):
            e=self.checked([f'AND(Source,{literal},Results[0]);',f'NOT({literal},Results[1]);']);e.step()
            self.assertEqual(e.memory.read('Results'),[255,0,None])
        e=self.checked(['OR(-1,Source,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),-1)

    def test_invalid_immediates_types_shapes_and_constants_are_blocked_even_false(self):
        for text in ('OR(Source,2147483648,Results[0]);','AND(Source,-2147483649,Results[0]);',
                     'NOT(16#1FFFFFFFF,Results[0]);','NOT(1e40,Results[0]);','OR(StartPB,1,Results[0]);',
                     'NOT(Source,Results);','OR(Inputs,Mask,Results[0]);','NOT(Missing,Results[0]);'):
            self.assertTrue(self.engine(['AFI()'+text]).blockers,text)
        self.assertTrue(self.engine(dest='BOOL').blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()NOT(Source,Results[0]);'],mutate=constant).blockers)

    def test_real_bitwise_rounds_before_combining_and_converts_real_results(self):
        cases=(
            ('AND','REAL','DINT','DINT',-1.5,3,2),
            ('OR','SINT','REAL','DINT',-1,-0.5,255),
            ('XOR','REAL','REAL','INT',3.5,-1.5,-6),
            ('NOT','REAL','DINT','SINT',-1.5,0,1),
            ('NOT','REAL','DINT','REAL',3.5,0,-5.0),
            ('OR','DINT','DINT','REAL',16777217,0,16777216.0),
            ('OR','REAL','DINT','DINT',-2147483648.0,1,-2147483647),
        )
        for name,source,other,dest,value,mask,expected in cases:
            with self.subTest(name=name,source=source,other=other,dest=dest,value=value):
                e=self.checked([instruction(name)+';'],source=source,other=other,dest=dest,value=value,mask=mask)
                e.step()
                actual=e.memory.read('Results[1]')
                self.assertEqual(actual,expected)
                self.assertIs(type(actual),type(expected))
        e=self.checked(['AND(3.5,7,Results[0]);','XOR(2.5,1.5,Results[1]);','NOT(-2.5,Results[2]);'])
        e.step()
        self.assertEqual(e.memory.read('Results'),[4,0,1])

    def test_real_bitwise_invalid_values_are_lazy_and_roll_back_prior_writes(self):
        e=self.checked(['NOT(-1.0,Results[0]);','XIC(StartPB)AND(Inputs[Index],7,Results[Index]);'],source='REAL')
        e.memory.write('Index',99)
        e.step()
        self.assertEqual(e.memory.read('Results'),[0,None,None])
        e.memory.write('Results[0]',99)
        e.memory.write('StartPB',True)
        for index,value,reason in ((99,None,'outside bounds'),(1,None,'Unknown'),(1,2147483647.0,'DINT overflow')):
            e.memory.write('Index',index)
            if value is not None:e.memory.write('Inputs[1]',value)
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,reason):
                e.step()
            self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',7.5)
        e.step()
        self.assertEqual(e.memory.read('Results'),[0,0,None])

    def test_lreal_bitwise_preserves_lint_bits_and_converts_floating_results(self):
        base=1 << 53
        cases=(
            ('AND','LREAL','LINT','LINT',base+2,base+3,base+2),
            ('OR','LREAL','DINT','LINT',base,-1,base+0xFFFFFFFF),
            ('XOR','LINT','LREAL','LINT',base+1,3.5,base+5),
            ('NOT','LREAL','DINT','LINT',base,0,-base-1),
            ('NOT','LREAL','DINT','LREAL',base,0,-float(base)),
            ('AND','LREAL','REAL','LINT',-1.5,-1.5,0xFFFFFFFE),
            ('OR','DINT','DINT','LREAL',-1,0,4294967295.0),
            ('OR','LREAL','DINT','REAL',(1 << 40)+1,0,float(1 << 40)),
            ('OR','LREAL','DINT','LINT',-(1 << 63),1,-(1 << 63)+1),
        )
        for name,source,other,dest,value,mask,expected in cases:
            with self.subTest(name=name,source=source,other=other,dest=dest,value=value):
                e=self.checked([instruction(name)+';'],source=source,other=other,dest=dest,value=value,mask=mask)
                e.step()
                actual=e.memory.read('Results[1]')
                self.assertEqual(actual,expected)
                self.assertIs(type(actual),type(expected))
        e=self.checked(['AND(3.5L,7,Results[0]);','XOR(2.5l,1.5L,Results[1]);','NOT(-2.5L,Results[2]);'])
        e.step()
        self.assertEqual(e.memory.read('Results'),[4,0,1])

    def test_lreal_bitwise_guards_unsigned_sources_for_floating_destinations(self):
        self.assertTrue(self.engine(source='ULINT',dest='LREAL',value=1).blockers)
        self.assertTrue(self.engine(['AFI()OR(1.0L,1UL,Results[0]);'],dest='REAL').blockers)
        self.assertTrue(self.engine(['AFI()NOT(1e309L,Results[0]);']).blockers)

    def test_lreal_bitwise_overflow_rolls_back_and_skipped_call_does_not_read(self):
        e=self.checked(['OR(4.0L,1,Results[0]);','XIC(StartPB)NOT(Inputs[Index],Results[Index]);'],source='LREAL',dest='LINT')
        e.memory.write('Index',99)
        e.step()
        self.assertEqual(e.memory.read('Results'),[5,None,None])
        e.memory.write('Results[0]',99)
        e.memory.write('StartPB',True)
        e.memory.write('Index',1)
        e.memory.write('Inputs[1]',float(1 << 63))
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'LINT overflow'):
            e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',2.5)
        e.step()
        self.assertEqual(e.memory.read('Results'),[5,-3,None])

    def test_false_and_prescan_skip_unknown_sources_results_and_dynamic_indices(self):
        for name in OPS:
            e=self.checked(['XIC(StartPB)'+instruction(name,source='Inputs[Index]',dest='Results[Index]')+';'])
            self.assertEqual(e.memory.read('Results'),[None]*3);e.memory.write('Index',999);reads=[];original=e.memory.read
            def read(ref,scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref,scope)
            with patch.object(e.memory,'read',side_effect=read):e.step()
            self.assertNotIn('Index',reads);self.assertNotIn('Inputs[Index]',reads);self.assertFalse(e.memory.structural)
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Index',1);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[1]',-1);e.step()
            self.assertEqual(e.memory.read('Results'),[None,{'AND':0,'OR':511,'XOR':511,'NOT':-256}[name],None])

    def test_all_binary_sources_remain_required_even_with_zero_mask(self):
        for name in OPS[:3]:
            for source,other in (('Inputs[0]','0'),('0','Inputs[0]')):
                e=self.checked([instruction(name,source=source,other=other)+';']);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
                self.assertEqual(self.snapshot(e),before)
                e.memory.write('Inputs[0]',-1);e.step()

    def test_full_writes_do_not_read_old_results_and_aliases_preserve_siblings(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ResultAlias',DataType='DINT',TagType='Alias',AliasFor='Results[1]')
        e=self.checked(['OR(Source,Mask,ResultAlias);','NOT(Results[1],Results[1]);'],mutate=alias);e.step()
        self.assertEqual(e.memory.read('Results'),[None,-512,None]);self.assertEqual(e.memory.read('Source'),-1)
        e=self.checked(['NOT(Source,Source);'],source='SINT');e.step();self.assertEqual(e.memory.read('Source'),0)

    def test_actual_destination_index_is_required_only_when_enabled(self):
        e=self.checked(['XIC(StartPB)NOT(Source,Results[Index]);']);e.memory.write('Index',999);e.step()
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',2);e.step();self.assertEqual(e.memory.read('Results'),[None,None,-256])

    def test_later_failure_restores_bitwise_values_unknowns_and_scheduler(self):
        e=self.checked(['OR(Source,Mask,Results[0]);','NOT(Source,Results[1]);','DIV(1,Inputs[0],SpeedCommand);'])
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[0]',1);e.step();self.assertEqual(e.memory.read('Results'),[511,-256,None])

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['AND(Value,16#FF,Buffer[Index])NOT(Value,Stack[0]);'])
        queues.logic(root,['AFI()AND(Value,16#FF,Buffer[Index])NOT(Value,Stack[0]);'],name='EnableInFalse')
        for name in ('DriverA','DriverB'):
            arr=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]')
            arr.remove(arr.find('Element[@Index="[0]"]'))

    def test_aoi_unknown_inout_local_results_and_late_binding_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('DriverA.Stack[0]')),(11,-12))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step()
        e.memory.write('EnabledB',True);e.memory.write('ValueA',-1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step();self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('DriverA.Stack[0]')),(255,0))
        self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_homogeneous_wide_rules_and_other_controller_path_are_unchanged(self):
        e=self.checked(['NOT(Source,Results[0]);','XOR(Source,Mask,Results[1]);'],source='ULINT',other='ULINT',dest='ULINT',value=9007199254740993,mask=1)
        e.step();self.assertEqual(e.memory.read('Results')[:2],[18437736874454810622,9007199254740992])
        self.assertTrue(self.engine(['ADD(Source,Mask,Results[1]);'],source='LINT',other='DINT').blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        e=self.checked(['OR(Source,Mask,Dest);'],mutate=old);e.step();self.assertEqual(e.memory.read('Dest'),-1)
        report=self.checked().report()['scalar_math']['bitwise'];self.assertFalse(report['native_precision'])


if __name__=='__main__':unittest.main()
