"""Bounded mixed CPT/CMP arithmetic with explicit common-type intermediates."""
import unittest
from xml.etree import ElementTree as E

import test_calculation_selection as fixtures
import test_mixed_relations as relations
from logixlab.model import ModelError


class MixedExpressionMathTests(unittest.TestCase):
    setUp=fixtures.CalculationSelectionTests.setUp
    snapshot=staticmethod(fixtures.CalculationSelectionTests.snapshot)

    def engine(self,rungs,*,types=('LINT','DINT','LINT'),values=(7,3,0),mutate=None):
        def fields(root):
            for name,value in zip(('Source','Mask','Dest'),values):root.find('./Controller/Tags/Tag[@Name="'+name+'"]/Data/DataValue').set('Value',str(value))
            if mutate:mutate(root)
        return fixtures.CalculationSelectionTests.engine(self,rungs,types=types,mutate=fields)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    def test_400_mixed_source_destination_sets_and_five_binary_operators(self):
        def flags(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Flags',DataType='BOOL',Dimensions='5',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='5')
        rungs=[f'CPT(Dest,Source{op}Mask)EQU(Dest,{expected})OTE(Flags[{i}]);' for i,(op,expected) in enumerate([('+',8),('-',4),('*',12),('/',3),(' MOD ',0)])]
        sets=0
        for a in relations.RANK:
            for b in relations.RANK:
                if a==b or {a,b}<={'SINT','INT','DINT'}:continue
                common=max((a,b),key=relations.RANK.index)
                for dest in relations.RANK:
                    with self.subTest(a=a,b=b,dest=dest):
                        sets+=1;e=self.engine(rungs,types=(a,b,dest),values=(6,2,0),mutate=flags)
                        allowed=dest==common and {a,b}<=relations.COVERS[common];self.assertEqual(not e.blockers,allowed)
                        if allowed:
                            e.step();self.assertEqual(e.memory.read('Flags'),[True]*5);self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(6,2))
        self.assertEqual(sets,400)

    def test_exact_nested_signed_quotient_remainder_and_unsigned_values(self):
        for expr,expected in [('Source+Mask',9007199254740996),('Source-Mask',9007199254740990),
                              ('Source*Mask',27021597764222979),('(Source+Mask)/2',4503599627370498)]:
            e=self.checked(['CPT(Dest,'+expr+');'],values=(9007199254740993,3,0));e.step();self.assertEqual(e.memory.read('Dest'),expected)
        for a,b,q,r in [(-9223372036854775808,3,-3074457345618258602,-2),(7,-3,-2,1),(-7,3,-2,-1)]:
            for expr,expected in [('Source/Mask',q),('Source MOD Mask',r)]:
                e=self.checked(['CPT(Dest,'+expr+');'],values=(a,b,0));e.step();self.assertEqual(e.memory.read('Dest'),expected)
        e=self.checked(['CPT(Dest,Source-Mask);'],types=('ULINT','UDINT','ULINT'),values=(18446744073709551615,3,0));e.step();self.assertEqual(e.memory.read('Dest'),18446744073709551612)

    def test_unary_and_abs_require_the_common_tag_type_in_their_subtree(self):
        for expr,expected in [('-Source+Mask',10),('+Source+Mask',-4),('ABS(Source)+Mask',10),('ABS(Source*Mask)',21)]:
            e=self.checked(['CPT(Dest,'+expr+');'],values=(-7,3,0));e.step();self.assertEqual(e.memory.read('Dest'),expected)
        for expr in ('Source+(-Mask)','Source+ABS(Mask)','Source+(1+2)+Mask','Source+(Mask+1)','(Mask*Mask)+Source'):
            self.assertTrue(self.engine(['AFI()CPT(Dest,'+expr+');']).blockers,expr)

    def test_cmp_arithmetic_composes_with_eager_boolean_conditions(self):
        e=self.checked(['CMP((Source/Mask=2)&&(Source MOD Mask=1))OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['CMP((Source+Mask>Source)&&StartPB)OTE(RunLatch);']);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['CMP((-Source)>Mask)OTE(RunLatch);'],values=(-7,3,0));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_indices_required_unknowns_and_full_mixed_cpt_writes(self):
        e=self.checked(['XIC(StartPB)CPT(Results[OutputIndex],Values[Index]+Mask);']);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('OutputIndex',0);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',9007199254740993);e.step();self.assertEqual(e.memory.read('Results'),[9007199254740996,None,None])

    def test_zero_multiplier_true_or_and_divisor_do_not_hide_required_data(self):
        for rung in ('CPT(Results[0],Values[0]*0+Mask);','CMP((1=1)||(Values[0]/Mask>0))OTE(RunLatch);'):
            e=self.checked(['MOV(99,SpeedCommand);',rung]);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',7);e.step()
            if rung.startswith('CPT'):self.assertEqual(e.memory.read('Results'),[3,None,None])
            else:self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['MOV(99,SpeedCommand);','CMP((1=1)||(Source/Mask>0))OTE(RunLatch);'],values=(7,0,0));before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Mask',3);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_each_intermediate_overflow_underflow_and_recovery_roll_back(self):
        cases=[(('LINT','DINT','LINT'),9223372036854775807,1,'Source+Mask'),
               (('LINT','DINT','LINT'),-9223372036854775808,1,'Source-Mask'),
               (('LINT','DINT','LINT'),4611686018427387904,2,'Source*Mask'),
               (('LINT','DINT','LINT'),-9223372036854775808,-1,'Source/Mask'),
               (('ULINT','UDINT','ULINT'),0,1,'Source-Mask'),
               (('LINT','DINT','LINT'),-9223372036854775808,0,'ABS(Source)+Mask'),
               (('LINT','DINT','LINT'),9223372036854775807,1,'(Source+Mask)-Mask')]
        for types,a,b,expr in cases:
            e=self.checked(['MOV(99,SpeedCommand);','CPT(Results[0],'+expr+');'],types=types,values=(a,b,0));before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Source',1 if types[0]=='ULINT' else 0);e.step();self.assertIsNotNone(e.memory.read('Results[0]'));self.assertIsNone(e.memory.read('Results')[1])

    def test_read_only_alias_and_constant_udt_sources_preserve_guard_members(self):
        def fields(root):
            root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='LINT',TagType='Alias',AliasFor='Source')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name,dtype in [('Value','LINT'),('Guard','DINT')]:E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
            rec=E.SubElement(E.SubElement(E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base',Constant='true'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            for name,dtype,value in [('Value','LINT','9007199254740993'),('Guard','DINT','987')]:E.SubElement(rec,'DataValueMember',Name=name,DataType=dtype,Value=value)
        e=self.checked(['CPT(Results[0],View+Mask);','CPT(Results[1],Packet1.Value+Mask);'],values=(9007199254740993,3,0),mutate=fields);e.step()
        self.assertEqual(e.memory.read('Results'),[9007199254740996,9007199254740996,None]);self.assertEqual(e.memory.read('Source'),9007199254740993);self.assertEqual(e.memory.read('Packet1'),{'Value':9007199254740993,'Guard':987})

    @staticmethod
    def aoi_logic(root):
        import test_mixed_relations as common
        import test_aoi_queues as queues
        common.MixedRelationTests.aoi_logic(root)
        queues.logic(root,['CPT(Stack[0],Stack[3]+Buffer[Index])CMP((Stack[0]>Buffer[Index])&&!Load)OTE(EnableOut);'])
        queues.logic(root,['AFI()CPT(Stack[0],Stack[3]+Buffer[Index])CMP((Stack[0]>Buffer[Index])&&!Load)OTE(EnableOut);'],name='EnableInFalse')
        array=root.find('./Controller/Tags/Tag[@Name="BufferA"]/Data/Array');array.remove(array.find('Element[@Index="[1]"]'))

    def test_aoi_full_local_results_independence_indices_and_binding_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('BufferA[1]',1);e.step();self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]')),(778,777))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step();e.memory.write('EnabledB',True);e.memory.write('BufferA[1]',5);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',2);e.step();self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]')),(782,777));self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_self_read_result_stays_unknown_until_it_is_initialized(self):
        e=self.checked(['CPT(Results[0],Results[0]+Mask);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Results[0]',5);e.step();self.assertEqual(e.memory.read('Results'),[8,None,None])

    def test_unqualified_types_destinations_operators_and_permissions_stay_blocked(self):
        for types in [('LINT','DINT','DINT'),('LINT','ULINT','LINT'),('DINT','UINT','LINT')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,Source+Mask);'],types=types,values=(1,1,0)).blockers)
        for expr in ('Source AND Mask','(NOT Source)+Mask','SQR(Source)+Mask','Source**2+Mask','Source+Mask+2147483648','Source+Mask+1.0','Source+Mask+1U'):
            self.assertTrue(self.engine(['AFI()CPT(Dest,'+expr+');']).blockers,expr)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()CPT(Results[0],Source+Mask);'],mutate=constant).blockers)

    def test_constants_and_profile_gates_remain_explicit(self):
        for expr,values,expected in [('Source+Mask-(-2147483648)',(-2147483648,0,0),0),('Source+Mask+16#7fff_ffff',(0,0,0),2147483647)]:
            e=self.checked(['CPT(Dest,'+expr+');'],values=values);e.step();self.assertEqual(e.memory.read('Dest'),expected)
        self.assertTrue(self.engine(['CPT(Dest,Source+Mask+(-1));'],types=('ULINT','UDINT','ULINT')).blockers)
        for processor,revision in [('1756-L75','35'),('1756-L85E','34')]:
            def target(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',revision)
            self.assertTrue(self.engine(['AFI()CPT(Dest,Source+Mask);'],mutate=target).blockers)
        report=self.checked(['CPT(Dest,Source+Mask);']).report()['wide_ladder_expressions'];self.assertTrue(report['mixed_numeric_types']);self.assertEqual(report['mixed_integer_arithmetic']['instructions'],['CPT','CMP','FAL','FSC']);self.assertFalse(report['mixed_integer_arithmetic']['native_runtime_parity'])


if __name__=='__main__':unittest.main()
