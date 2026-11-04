"""Structural numeric CPT/CMP preflight and reached expression transactions."""
import unittest
from xml.etree import ElementTree as E

import test_numeric_comparisons as fixtures
from logixlab.model import ModelError

TYPES=['SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT','REAL']


class CalculationSelectionTests(unittest.TestCase):
    setUp=fixtures.NumericComparisonTests.setUp
    snapshot=staticmethod(fixtures.NumericComparisonTests.snapshot)

    def engine(self,rungs,*,dtype='DINT',types=None,mutate=None):
        types=types or (dtype,)*3
        def fields(root):
            tags=root.find('./Controller/Tags')
            result=E.SubElement(tags,'Tag',Name='Results',DataType=types[2],Dimensions='3',TagType='Base')
            E.SubElement(E.SubElement(result,'Data',Format='Decorated'),'Array',DataType=types[2],Dimensions='3')
            out=E.SubElement(tags,'Tag',Name='OutputIndex',DataType='DINT',TagType='Base')
            E.SubElement(E.SubElement(out,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='999')
            if mutate:mutate(root)
        return fixtures.NumericComparisonTests.engine(self,rungs,types=types,values=(0,2,0),mutate=fields)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    def test_cpt_all_nine_types_skip_false_indices_and_establish_unknown_results(self):
        for dtype in TYPES:
            with self.subTest(dtype=dtype):
                e=self.checked(['XIC(StartPB)CPT(Results[OutputIndex],Values[Index]+Mask);'],dtype=dtype)
                e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
                e.memory.write('OutputIndex',0);e.memory.write('StartPB',True);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
                self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
                self.assertEqual(self.snapshot(e),before);value=5.25 if dtype=='REAL' else 5;e.memory.write('Values[0]',value);e.step()
                self.assertEqual(e.memory.read('Results'),[value+2,None,None]);self.assertEqual(e.memory.read('Values'),[value,None,None]);self.assertFalse(e.memory.structural)

    def test_cmp_all_nine_types_clear_false_coils_and_consume_eager_right_operand(self):
        for dtype in TYPES:
            e=self.checked(['XIC(StartPB)CMP((1=1)||(Values[Index]>Mask))OTE(RunLatch);'],dtype=dtype)
            e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',5.25 if dtype=='REAL' else 5);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_unknown_index_and_literal_only_cpt_destination_are_lazy(self):
        def unknown(root):
            tag=root.find('./Controller/Tags/Tag[@Name="OutputIndex"]');tag.set('Dimensions','3');tag.remove(tag.find('Data'))
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
        e=self.checked(['XIC(StartPB)CPT(Results[OutputIndex[0]],1+2*3);'],mutate=unknown);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('OutputIndex[0]',1);e.step();self.assertEqual(e.memory.read('Results'),[None,7,None])

    def test_known_zero_cpt_multiplier_and_false_cmp_left_do_not_fold_unknowns(self):
        for rung in ('CPT(Results[0],Values[0]*0);','CMP((1=2)&&(Values[0]>Mask))OTE(RunLatch);'):
            e=self.checked(['MOV(99,SpeedCommand);',rung]);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',5);e.step();self.assertFalse(e.memory.read('RunLatch'))
            if rung.startswith('CPT'):self.assertEqual(e.memory.read('Results'),[0,None,None])

    def test_later_fault_restores_new_values_coils_unknown_siblings_and_schedule(self):
        e=self.checked(['MOV(99,SpeedCommand);','CPT(Results[0],Values[0]+Mask);','CMP((1=1)||(Dest/Source>0))OTE(RunLatch);'])
        e.memory.write('Values[0]',5);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Source',1);e.step();self.assertEqual(e.memory.read('Results'),[7,None,None]);self.assertTrue(e.memory.read('RunLatch'))

    def test_alias_constant_sources_and_unknown_udt_results_keep_guards(self):
        def fields(root):
            root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='InputView',DataType='DINT',TagType='Alias',AliasFor='Values')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='OutputView',DataType='DINT',TagType='Alias',AliasFor='Results')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name in ('Result','Guard'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='987')
        e=self.checked(['XIC(StartPB)CPT(OutputView[OutputIndex],InputView[Index]+Source);','XIC(StartPB)CPT(Packet1.Result,InputView[Index]+Mask);'],mutate=fields)
        e.step();self.assertEqual(e.memory.read('Packet1'),{'Result':None,'Guard':987})
        for tag,value in [('Index',0),('OutputIndex',1),('Values[0]',5),('StartPB',True)]:e.memory.write(tag,value)
        e.step();self.assertEqual(e.memory.read('Results'),[None,5,None]);self.assertEqual(e.memory.read('Packet1'),{'Result':7,'Guard':987});self.assertEqual(e.memory.read('Source'),0)

    def test_unknown_bool_cmp_is_lazy_and_whole_bool_array_stays_blocked(self):
        def flags(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Flags',DataType='BOOL',Dimensions='3',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='3')
        e=self.checked(['XIC(StartPB)CMP((1=1)||Flags[Index])OTE(RunLatch);'],mutate=flags);e.step();e.memory.write('StartPB',True);e.memory.write('Index',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Flags[0]',False);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(self.engine(['AFI()CMP(Flags=StartPB)OTE(RunLatch);'],mutate=flags).blockers)

    def test_unknown_packed_bits_and_system_first_scan_keep_bool_reference_semantics(self):
        e=self.checked(['XIC(StartPB)CMP(Values[0].[Index]||S:FS)OTE(RunLatch);'])
        e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'bit selection'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',1);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertFalse(e.memory.structural)

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['CPT(Stack[0],Buffer[Index]+Value)CMP(Stack[0]>Buffer[Index])OTE(EnableOut);'])
        queues.logic(root,['AFI()CPT(Stack[0],Buffer[Index]+Value)CMP(Stack[0]>Buffer[Index])OTE(EnableOut);'],name='EnableInFalse')
        for instance in ('DriverA','DriverB'):
            array=root.find('./Controller/Tags/Tag[@Name="'+instance+'"]/Data/Structure/ArrayMember[@Name="Stack"]');array.remove(array.find('Element[@Index="[0]"]'))
        array=root.find('./Controller/Tags/Tag[@Name="BufferA"]/Data/Array');array.remove(array.find('Element[@Index="[1]"]'))

    def test_aoi_unknown_sources_full_local_writes_false_indices_and_binding_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('BufferA[1]',5);e.step();self.assertEqual(e.memory.read('DriverA.Stack[0]'),16);self.assertEqual(e.memory.read('DriverB.Stack[0]'),22)
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step();e.memory.write('EnabledB',True);e.memory.write('ValueA',99);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',2);e.step();self.assertEqual(e.memory.read('DriverA.Stack[0]'),104);self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_shapes_permissions_index_grammar_and_existing_type_rules_remain_blockers(self):
        for rung in ('CPT(Results,Source+Mask);','CPT(Results[0],Values);','CPT(Results[0],StartPB);','CPT(Results[0],Values[999]);',
                     'CPT(Results[0],Values[Index MOD 2]);','CPT(Results[0],Missing+1);','CMP(Values>Mask)OTE(RunLatch);'):
            e=self.engine(['AFI()'+rung]);self.assertTrue(e.blockers,rung);self.assertFalse(e.memory.structural)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()CPT(Results[Index],Source+Mask);'],mutate=constant).blockers)
        self.assertTrue(self.engine(['AFI()CPT(Results[0],Source+(Mask+1));'],types=('LINT','DINT','LINT')).blockers)
        self.assertTrue(self.engine(['AFI()CPT(Results[0],Source+2147483648);'],dtype='LINT').blockers)

    def test_other_targets_direct_evaluators_and_file_consumers_do_not_gain_this_preflight(self):
        for processor,revision in [('1756-L75','35'),('1756-L85E','34')]:
            def old(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',revision)
            self.assertTrue(self.engine(['AFI()CPT(Results[Index],Values[Index]+Mask);'],mutate=old).blockers)
        e=self.checked(['AFI()CPT(Results[0],Values[0]+Mask);'])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.extensions.expression('Values[0]+Mask').validate(e.memory,'MainProgram','DINT')
        report=e.report()['integer_expression_execution']['ladder_selection'];self.assertEqual(report['instructions'],['CPT','CMP']);self.assertEqual(set(report['types']),set(TYPES));self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
