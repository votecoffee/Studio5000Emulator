"""Mixed integer CMP relations, Boolean composition and structural selection."""
import unittest
from xml.etree import ElementTree as E

import test_mixed_relations as fixtures
from logixlab.model import ModelError


class MixedConditionTests(unittest.TestCase):
    setUp=fixtures.MixedRelationTests.setUp
    engine=fixtures.MixedRelationTests.engine
    checked=fixtures.MixedRelationTests.checked
    snapshot=staticmethod(fixtures.MixedRelationTests.snapshot)

    def test_all_64_tag_type_pairs_six_relations_and_three_value_orders(self):
        def flags(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Flags',DataType='BOOL',Dimensions='6',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='6')
        rungs=[f'CMP(Source{op}Mask)OTE(Flags[{i}]);' for i,op in enumerate(('=','<>','<','<=','>','>='))]
        for a in fixtures.RANK:
            for b in fixtures.RANK:
                with self.subTest(a=a,b=b):
                    common=max((a,b),key=fixtures.RANK.index);allowed={a,b}<=fixtures.COVERS[common]
                    e=self.engine(rungs,types=(a,b,'DINT'),values=(3,5,0),mutate=flags)
                    self.assertEqual(not e.blockers,allowed)
                    if allowed:
                        for av,bv,expected in [(3,5,[False,True,True,True,False,False]),(5,3,[False,True,False,False,True,True]),(5,5,[True,False,False,True,False,True])]:
                            e.memory.write('Source',av);e.memory.write('Mask',bv);e.step();self.assertEqual(e.memory.read('Flags'),expected)
                            self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(av,bv))

    def test_symbolic_word_boolean_operators_and_boolean_equality(self):
        rows=[('(Source>Mask)&&StartPB',False,True),('(Source>Mask)||StartPB',True,True),
              ('(Source>Mask)^^StartPB',True,False),('!(Source<Mask)',True,True),('NOT (Source<Mask)',True,True),
              ('(Source>Mask) AND StartPB',False,True),('(Source>Mask) OR StartPB',True,True),
              ('(Source>Mask) XOR StartPB',True,False),('(Source>Mask)=StartPB',False,True),('(Source>Mask)<>StartPB',True,False)]
        for expr,off,on in rows:
            with self.subTest(expr=expr):
                e=self.checked(['CMP('+expr+')OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(10,5,0));e.step();self.assertEqual(e.memory.read('RunLatch'),off)
                e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('RunLatch'),on)

    def test_exact_adjacent_signed_unsigned_and_bounded_constants(self):
        e=self.checked(['CMP((Source>Mask)&&(Source<Dest))OTE(RunLatch);'],types=('LINT','DINT','LINT'),values=(9007199254740993,2147483647,9007199254740994))
        e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),9007199254740993)
        for types,values,expr in [(('LINT','UDINT','DINT'),(4294967295,4294967295,0),'(Source=Mask)&&(Mask>=0)'),
                                   (('ULINT','UDINT','DINT'),(18446744073709551615,4294967295,0),'(Source>Mask)&&(Mask>=0)'),
                                   (('LINT','DINT','DINT'),(-2147483648,-7,0),'(Source=-2147483648)&&(Mask<0)'),
                                   (('INT','USINT','DINT'),(-1,255,0),'(Source<Mask)&&(Source=-1)')]:
            e=self.checked(['CMP('+expr+')OTE(RunLatch);'],types=types,values=values);before=tuple(e.memory.read(t) for t in ('Source','Mask'))
            e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(tuple(e.memory.read(t) for t in ('Source','Mask')),before)

    def test_false_skips_indices_and_eager_logic_requires_unknown_right_side(self):
        for left,op in [('1=1','||'),('1=2','&&'),('1=1','^^'),('1=1','OR')]:
            e=self.checked(['ADD(SpeedCommand,1,SpeedCommand);',f'XIC(StartPB)CMP(({left}){op}(Values[Index]>Mask))OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(0,7,0))
            e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',8);e.step();self.assertEqual(e.memory.read('RunLatch'),op in ('||','OR'))
            self.assertFalse(e.memory.structural)

    def test_complete_expression_tag_ranges_cannot_be_relaxed_by_values_or_constants(self):
        for types in [('DINT','UDINT','DINT'),('LINT','ULINT','DINT'),('SINT','USINT','DINT')]:
            self.assertTrue(self.engine(['AFI()CMP((Source=Mask)||(Source=0))OTE(RunLatch);'],types=types,values=(1,1,0)).blockers)
        # An actual third LINT tag supplies a common type that covers both byte ranges.
        e=self.checked(['CMP((Source<Mask)&&(Dest>=0))OTE(RunLatch);'],types=('SINT','USINT','LINT'),values=(-1,255,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_constant_tags_program_alias_and_udt_members_are_read_only(self):
        def fields(root):
            root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='LINT',TagType='Alias',AliasFor='Source')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LINT',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            rec=E.SubElement(E.SubElement(E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base',Constant='true'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            for name,dtype,value in [('Value','LINT','65535'),('Guard','DINT','987')]:E.SubElement(rec,'DataValueMember',Name=name,DataType=dtype,Value=value)
        e=self.checked(['CMP((View=Mask)&&(Packet1.Value=Mask))OTE(RunLatch);'],types=('LINT','UINT','DINT'),values=(65535,65535,0),mutate=fields)
        before=self.snapshot(e)[0];e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet1'),{'Value':65535,'Guard':987});self.assertEqual(e.memory.read('Source'),65535)

    def test_homogeneous_unknown_imports_now_receive_structural_cmp_preflight(self):
        e=self.checked(['XIC(StartPB)CMP(Values[Index]>Mask)OTE(RunLatch);'],types=('LINT','LINT','LINT'),values=(0,7,0))
        e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);e.memory.write('Values[0]',8);e.step();self.assertTrue(e.memory.read('RunLatch'))

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        fixtures.MixedRelationTests.aoi_logic(root)
        queues.logic(root,['CMP((Stack[0]>=Buffer[Index])&&!Load)OTE(EnableOut);'])
        queues.logic(root,['AFI()CMP((Stack[0]>=Buffer[Index])&&!Load)OTE(EnableOut);'],name='EnableInFalse')

    def test_aoi_unknown_inputs_independence_false_indices_and_later_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        for name in ('DriverA.Stack[0]','DriverB.Stack[0]'):e.memory.write(name,0)
        e.step();self.assertTrue(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'))
        e.memory.write('BufferA[1]',1);e.step();self.assertFalse(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step();e.memory.write('EnabledB',True);e.memory.write('BufferA[1]',-1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',2);e.step();self.assertTrue(e.memory.read('DriverA.EnableOut'));self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_arithmetic_bitwise_functions_shapes_and_unbounded_literals_remain_blocked(self):
        for expr in ('Source+Mask>0','Source/Mask=1','(Source AND Mask)>0','(NOT Source)=Mask','-Source<Mask',
                     'ABS(Source)>Mask','Source>Mask>Dest','Source>RunLatch','Values>Mask','Source>2147483648','Source>1.0','Source>1L'):
            e=self.engine(['AFI()CMP('+expr+')OTE(RunLatch);'],types=('LINT','DINT','DINT'));self.assertTrue(e.blockers,expr);self.assertFalse(e.memory.structural)
        self.assertTrue(self.engine(['CMP((Source>Mask)&&(Mask>-1))OTE(RunLatch);'],types=('ULINT','UDINT','DINT')).blockers)
        self.assertTrue(self.engine(['AFI()CMP(Source>Mask)OTE(RunLatch);'],types=('LINT','REAL','DINT')).blockers)

    def test_cpt_st_legacy_homogeneous_and_controller_boundaries_remain_separate(self):
        self.assertTrue(self.engine(['AFI()CPT(Dest,Source+Mask);'],types=('LINT','DINT','LINT')).blockers)
        e=self.checked(['CMP((Source AND Mask)>0)OTE(RunLatch);'],types=('LINT',)*3,values=(7,3,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        for processor,revision in [('1756-L75','35'),('1756-L85E','34')]:
            def old(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',revision)
            self.assertTrue(self.engine(['CMP(Source>Mask)OTE(RunLatch);'],types=('LINT','DINT','DINT'),mutate=old).blockers)
        report=e.report()['wide_ladder_expressions']['mixed_integer_comparisons'];self.assertEqual(report['instructions'],['CMP']);self.assertEqual(report['types'],fixtures.RANK);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
