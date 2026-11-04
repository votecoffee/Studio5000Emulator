"""Integer BCD operators in ladder CMP, eager Boolean paths and scoped caches."""
import itertools
import unittest
from xml.etree import ElementTree as E

import test_cpt_bcd as fixtures
from logixlab.conditions import Condition
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class CmpBcdTests(unittest.TestCase):
    setUp=fixtures.CptBcdTests.setUp
    checked=fixtures.CptBcdTests.checked
    snapshot=staticmethod(fixtures.CptBcdTests.snapshot)
    fault=fixtures.CptBcdTests.fault
    packet=staticmethod(fixtures.CptBcdTests.packet)

    def engine(self,rungs=None,**options):
        return fixtures.CptBcdTests.engine(self,rungs or ['CMP(FRD(Source)=30)OTE(RunLatch);'],**options)

    def test_nine_numeric_tag_pairings_and_both_conversion_functions(self):
        for source,other in itertools.product(('SINT','INT','DINT'),repeat=2):
            for function,value,want in [('FRD',26,20),('TOD',21,33)]:
                e=self.checked([f'CMP({function}(Source)=Dest)OTE(RunLatch);'],source_type=source,dest_type=other,value=value);e.memory.write('Dest',want);e.step()
                self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),value);self.assertEqual(e.memory.read('Dest'),want)
                e.memory.write('Dest',want+1);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_six_relations_and_nested_arithmetic_patterns(self):
        cases=[('FRD(Source)=30',True),('FRD(Source)<>30',False),('FRD(Source)<31',True),('FRD(Source)<=30',True),('FRD(Source)>30',False),('FRD(Source)>=30',True),
               ('FRD(16#1A)=20',True),('(FRD(-1) AND 255)=169',True),('FRD(-2147483648)=80000000',True),('TOD(99999999)<0',True),('FRD(TOD(99999999))=99999999',True),
               ('(TOD(99999999) AND 7)=1',True),('FRD(TOD(Source+3))/2=22',True),('TRN(ABS(FRD(16#1234)-1235))=1',True),('(FRD(16#1234) MOD 100) OR (TOD(21) AND 7)=35',True)]
        for expression,want in cases:
            e=self.checked([f'CMP({expression})OTE(RunLatch);']);e.step();self.assertIs(e.memory.read('RunLatch'),want,expression)

    def test_signed_narrow_sources_promote_before_eight_nibble_comparison(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['CMP(FRD(Source)=166666665)OTE(RunLatch);'],source_type=dtype,value=-1);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),-1)

    def test_boolean_tags_negation_and_composition_retain_numeric_types(self):
        for expression,want in [('!StartPB&&(TOD(Source)>0)',True),('StartPB||(FRD(Source)=30)',True),('(FRD(Source)=30) AND StartPB',False),
                                ('(FRD(Source)=30) XOR StartPB',True),('NOT StartPB AND (TOD(Source)>0)',True),('StartPB=(FRD(Source)<>30)',True)]:
            e=self.checked([f'CMP({expression})OTE(RunLatch);']);e.step();self.assertIs(e.memory.read('RunLatch'),want,expression)

    def test_false_prescan_unknowns_and_selected_values_remain_lazy(self):
        e=self.checked(['XIC(StartPB)CMP(FRD(Inputs[Index])=21)OTE(RunLatch);'],index=99);e.enter_run();e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',33);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('Inputs[1]',34);e.step();self.assertFalse(e.memory.read('RunLatch'));self.assertIsNone(e.memory.read('Results')[0])
        e.memory.write('StartPB',False);e.memory.write('Index',99);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_logical_results_and_zero_masks_do_not_hide_required_arguments(self):
        for expression,want in [('(1=1)||(FRD(Inputs[Index])=0)',True),('(1=2)&&(FRD(Inputs[Index])=0)',False),('(1=1)^^(FRD(Inputs[Index])=0)',True),('(FRD(Inputs[Index]) AND 0)=0',True)]:
            e=self.checked([f'CMP({expression})OTE(RunLatch);']);self.fault(e,'Unknown');e.memory.write('Inputs[1]',33);e.step();self.assertIs(e.memory.read('RunLatch'),want)
        e=self.checked(['CMP((1=1)||(TOD(Source)=0))OTE(RunLatch);'],value=-1);self.fault(e,'qualified')

    def test_ranges_intermediates_division_and_later_faults_are_atomic(self):
        for expression,value,text in [('TOD(Source)=0',-1,'qualified'),('TOD(Source)=0',100000000,'qualified'),('FRD(Source*2)>0',1073741824,'overflow'),
                                      ('TOD(Source+1)=0',2147483647,'overflow'),('TOD(Source/Divisor)>0',42,'zero'),('FRD(2147483648)>0',42,'overflow')]:
            e=self.checked(['MOV(99,SpeedCommand);',f'CMP({expression})OTE(RunLatch);'],value=value,divisor=0);self.fault(e,text)
        e=self.checked(['CMP(FRD(Source)=30)OTE(RunLatch);','DIV(1,LateDivisor,SpeedCommand);']);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('Source',33);e.memory.write('LateDivisor',0);self.fault(e,'zero');self.assertTrue(e.memory.read('RunLatch'));e.memory.write('LateDivisor',1);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_alias_udt_members_nested_indices_and_constant_sources(self):
        e=self.checked(['CMP(FRD(Selected)=21)OTE(RunLatch);'],mutate=self.packet);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet.Guard'),777)
        e=self.checked(['CMP(FRD(Inputs[FRD(TOD(Index))])=21)OTE(RunLatch);']);e.memory.write('Inputs[1]',33);e.step();self.assertTrue(e.memory.read('RunLatch'))
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
        e=self.checked(mutate=constant);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),42)

    def aoi(self,dtype='SINT'):
        f=fixtures.CptBcdTests();f.setUp();self.addCleanup(f.doCleanups);original=f.aoi(dtype);root=E.parse(original.project.path).getroot()
        import test_aoi_queues as queues
        queues.logic(root,['CMP(FRD(TOD(Value))=Value)MOV(Value,Buffer[Index]);','CMP((FRD(Value) AND 255)>0)MOV(Value,Stack[Index]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(original.project.path))

    def test_warm_aoi_copied_inputs_conditional_writes_and_binding_rollback(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.aoi(dtype);self.assertEqual(e.blockers,[]);e.step();self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[2]')),(21,34,21,34))
            e.memory.write('ValueA',0);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[1]'),0);self.assertEqual(e.memory.read('DriverA.Stack[1]'),21)

    def test_scoped_parser_cache_keeps_st_and_direct_conditions_separate(self):
        expression='FRD(Source)>0';e=self.checked([f'CMP({expression})OTE(RunLatch);']);e.step();self.assertIn((expression,True,True,True),e.extensions.conditions)
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):e.extensions.condition(expression,allow_wide=True)
        with self.assertRaisesRegex(ModelError,'Unsupported expression function'):Condition(expression)
        for code in ('IF FRD(Source)>0 THEN Dest:=1; END_IF;','IF TOD(Source)>0 THEN Dest:=1; END_IF;'):
            self.assertTrue(self.engine(code,st=True).blockers)
        import test_file_search as files
        f=files.FileSearchTests();f.setUp();self.addCleanup(f.doCleanups)
        for function in ('FRD','TOD'):
            e=f.checked([f'CMP({function}(Incoming)>0)OTE(RunLatch);',f'FSC(Ctl,?,?,ALL,{function}(Incoming)>0);']);e.step();self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),0)

    @staticmethod
    def text_tag(root):
        tags=root.find('./Controller/Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='TextValue',DataType='STRING',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='STRING')
        E.SubElement(obj,'DataValueMember',Name='LEN',DataType='DINT',Value='1');arr=E.SubElement(obj,'ArrayMember',Name='DATA',DataType='SINT',Dimensions='82');E.SubElement(arr,'Element',Index='[0]',Value='65')

    def test_real_wide_string_numeric_bool_and_malformed_forms_stay_guarded(self):
        for dtype in ('BOOL','REAL','LREAL','LINT','USINT','UINT','UDINT','ULINT'):
            for function in ('FRD','TOD'):
                self.assertTrue(self.engine([f'AFI()CMP({function}(Source)>0)OTE(RunLatch);'],source_type=dtype,value=1).blockers,(dtype,function))
        for expression in ('FRD(Source)>0.0','TOD(Source+0.5)>0','FRD(Source)+SQR(4.0)>0','TOD(Source)**2.0>0','FRD(StartPB)>0','FRD(Source)=StartPB','TOD(1L)>0','FRD(Source,1)>0'):
            self.assertTrue(self.engine([f'AFI()CMP({expression})OTE(RunLatch);']).blockers,expression)
        e=self.engine(['AFI()CMP((TextValue=TextValue)&&(FRD(Source)>0))OTE(RunLatch);'],mutate=self.text_tag);self.assertEqual(e.memory.string('TextValue'),'A');self.assertTrue(e.blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()CMP(FRD(Source)>0)OTE(RunLatch);'],mutate=old).blockers)

    def test_report_records_boolean_composition_and_native_boundaries(self):
        d=self.checked().report()['integer_expression_execution'];self.assertEqual(d['bcd_cmp']['functions'],['FRD','TOD']);self.assertTrue(d['bcd_cmp']['boolean_composition']);self.assertFalse(d['bcd_cmp']['native_runtime_parity']);self.assertEqual(d['bcd_cpt']['functions'],['FRD','TOD'])


if __name__=='__main__':unittest.main()
