"""Bounded constants in mixed-tag ladder limits and unchanged legacy relations."""
import unittest
from xml.etree import ElementTree as E

import test_mixed_relations as fixtures
from logixlab.model import ModelError


class ComparisonConstantTests(unittest.TestCase):
    setUp=fixtures.MixedRelationTests.setUp
    engine=fixtures.MixedRelationTests.engine
    checked=fixtures.MixedRelationTests.checked
    snapshot=staticmethod(fixtures.MixedRelationTests.snapshot)

    def test_all_type_pairs_three_constant_positions_and_dint_boundaries(self):
        unsigned={'USINT','UINT','UDINT','ULINT'}
        bounds={'SINT':(-128,127),'INT':(-32768,32767),'DINT':(-2147483648,2147483647),'USINT':(0,255),'UINT':(0,65535),'UDINT':(0,4294967295),'ULINT':(0,18446744073709551615),
                'LINT':(-9223372036854775808,9223372036854775807)}
        for a in fixtures.RANK:
            for b in fixtures.RANK:
                common=max((a,b),key=fixtures.RANK.index)
                for constant in (-2147483648,-1,0,2147483647):
                    for position in range(3):
                        with self.subTest(a=a,b=b,constant=constant,position=position):
                            args=['Source','Mask'];args.insert(position,str(constant))
                            wide=bool({a,b}&(unsigned|{'LINT'}))
                            allowed=not wide or ({a,b}<=fixtures.COVERS[common] and bounds[common][0]<=constant<=bounds[common][1])
                            e=self.engine(['LIM('+','.join(args)+')OTE(RunLatch);'],types=(a,b,'DINT'),values=(2,8,0))
                            self.assertEqual(not e.blockers,allowed)
                            if allowed:
                                values=[2,8];values.insert(position,constant);low,test,high=values
                                expected=low<=test<=high if low<=high else test>=low or test<=high
                                e.step();self.assertEqual(e.memory.read('RunLatch'),expected)
                                self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(2,8))

    def test_mixed_limits_inclusive_reversed_equal_and_radix_constants(self):
        for low,high,rows in [(2,8,[(1,False),(2,True),(8,True),(9,False)]),
                              (8,2,[(1,True),(2,True),(5,False),(8,True),(9,True)]),
                              (2,2,[(1,False),(2,True),(3,False)])]:
            for value,expected in rows:
                for constant,args,types,values in [(str(low),'CONST,Source,Mask',('LINT','DINT','DINT'),(value,high,0)),
                                                  (str(value),'Source,CONST,Mask',('LINT','DINT','DINT'),(low,high,0)),
                                                  (str(high),'Source,Mask,CONST',('LINT','DINT','DINT'),(low,value,0))]:
                    e=self.checked(['LIM('+args.replace('CONST',constant)+')OTE(RunLatch);'],types=types,values=values)
                    e.step();self.assertEqual(e.memory.read('RunLatch'),expected)
        for constant in ('16#7fff_ffff','2#1010','8#12','-16#8000_0000'):
            e=self.checked([f'LIM({constant},Source,Mask)OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(10,20,0));e.step()
            self.assertTrue(e.memory.read('RunLatch'))

    def test_exact_lint_and_ulint_values_with_mixed_constant_limits(self):
        for dtype,other,value,high in [('LINT','DINT',9007199254740993,2147483647),('ULINT','UDINT',18446744073709551615,4294967295)]:
            e=self.checked(['LIM(0,Source,Mask)OTE(RunLatch);'],types=(dtype,other,'DINT'),values=(value,high,0))
            e.step();self.assertFalse(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),value)
        e=self.checked(['LIM(0,Mask,Source)OTE(RunLatch);'],types=('LINT','UDINT','DINT'),values=(9007199254740993,4294967295,0))
        e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_skips_unknowns_indices_and_true_requires_each_source(self):
        for args in ('0,Values[Index],Mask','Values[Index],5,Mask','Mask,Values[Index],10'):
            e=self.checked(['XIC(StartPB)LIM('+args+')OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(0,10,0))
            e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'))
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',5);e.step()
            self.assertEqual(e.memory.read('RunLatch'),not args.startswith('Mask'))

    def test_known_test_does_not_hide_unknown_high_or_later_rollback(self):
        e=self.checked(['MOV(99,SpeedCommand);','LIM(Mask,0,Values[0])OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(0,10,0))
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',20);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_read_only_constant_tag_and_program_alias(self):
        def alias(root):
            root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='LINT',TagType='Alias',AliasFor='Source')
        e=self.checked(['LIM(-2,View,Mask)OTE(RunLatch);'],types=('LINT','UINT','DINT'),values=(-1,8,0),mutate=alias)
        before=(e.memory.read('Source'),e.memory.read('Mask'));e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),before)

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        fixtures.MixedRelationTests.aoi_logic(root)
        queues.logic(root,['LIM(-1,Stack[0],Buffer[Index])OTE(EnableOut);'])
        queues.logic(root,['AFI()LIM(-1,Stack[0],Buffer[Index])OTE(EnableOut);'],name='EnableInFalse')

    def test_aoi_unknown_sources_independent_coils_false_indices_and_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        for name in ('DriverA.Stack[0]','DriverB.Stack[0]'):e.memory.write(name,0)
        e.step();self.assertTrue(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'))
        e.memory.write('DriverA.Stack[0]',1);e.step();self.assertFalse(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step();e.memory.write('EnabledB',True);e.memory.write('DriverA.Stack[0]',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',2);e.step()
        self.assertTrue(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'));self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_constants_cannot_authorize_lossy_types_or_unsupported_immediates(self):
        for types in (('DINT','UDINT','DINT'),('LINT','ULINT','DINT'),('SINT','USINT','DINT')):
            for args in ('0,Source,Mask','Source,0,Mask','Source,Mask,0'):
                self.assertTrue(self.engine(['AFI()LIM('+args+')OTE(RunLatch);'],types=types,values=(1,1,0)).blockers)
        for constant in ('2147483648','-2147483649','16#ffff_ffff','1.0','TRUE','1LU','18446744073709551615UL'):
            for args in (f'{constant},Source,Mask',f'Source,{constant},Mask',f'Source,Mask,{constant}'):
                self.assertTrue(self.engine(['AFI()LIM('+args+')OTE(RunLatch);'],types=('LINT','DINT','DINT')).blockers)
        self.assertTrue(self.engine(['AFI()LIM(-1,Source,Mask)OTE(RunLatch);'],types=('ULINT','UDINT','DINT')).blockers)
        self.assertEqual(self.engine(['AFI()LIM(0,Source,Mask)OTE(RunLatch);'],types=('LINT','REAL','DINT')).blockers,[])
        self.assertTrue(self.engine(['AFI()LIM(1e39,Source,Mask)OTE(RunLatch);'],types=('LINT','REAL','DINT')).blockers)
        self.assertTrue(self.engine(['AFI()LIM(0,Values,Mask)OTE(RunLatch);'],types=('LINT','DINT','DINT')).blockers)

    def test_homogeneous_binary_narrow_meq_and_controller_profiles_remain_separate(self):
        for dtype in fixtures.RANK:
            for op in fixtures.RELATIONS:
                e=self.checked([f'{op}(Source,5)OTE(RunLatch);'],types=(dtype,)*3,values=(5,5,0));e.step()
                self.assertEqual(e.memory.read('RunLatch'),op in ('EQU','LEQ','GEQ'))
        self.assertTrue(self.engine(['EQU(Source,2147483648)OTE(RunLatch);'],types=('LINT',)*3).blockers)
        meq = self.checked(['MEQ(Source,Mask,0)OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(1 << 32,-1,0))
        meq.step()
        self.assertTrue(meq.memory.read('RunLatch'))
        self.assertTrue(self.engine(['LIM(0,Source,2147483647)OTE(RunLatch);'],types=('USINT',)*3).blockers)
        # Homogeneous USINT keeps its old representability restriction.
        for processor,revision in [('1756-L75','35'),('1756-L85E','34')]:
            def old(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',revision)
            self.assertTrue(self.engine(['LIM(0,Source,Mask)OTE(RunLatch);'],types=('LINT','DINT','DINT'),mutate=old).blockers)
        report=self.checked().report()['numeric_comparisons']['mixed_integer_ordering']
        self.assertIn('signed-DINT',report['constants']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
