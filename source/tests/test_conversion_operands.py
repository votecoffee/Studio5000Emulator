"""Lazy ladder FRD/TOD/SWPB indices, unknown results and atomic recovery."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_math_operands as fixtures
from logixlab.model import ModelError, Op

CASES = {'FRD':(0x1234,1234),'TOD':(1234,0x1234),'SWPB':(0x12345678,0x78563412)}


def instruction(name, source='Inputs[Index]', dest='Results[Index]', order='REVERSE'):
    return name+'('+','.join((source,order,dest) if name=='SWPB' else (source,dest))+')'


class ConversionOperandTests(unittest.TestCase):
    setUp = fixtures.MathOperandTests.setUp
    checked = fixtures.MathOperandTests.checked
    snapshot = staticmethod(fixtures.MathOperandTests.snapshot)

    def engine(self, rungs=None, *, source='DINT', dest='DINT', value=1234, index=99, mutate=None):
        return fixtures.MathOperandTests.engine(self,rungs or ['XIC(StartPB)FRD(Inputs[Index],Results[Index]);'],
                                               source=source,dest=dest,value=value,index=index,mutate=mutate)

    def test_false_and_prescan_skip_unknown_values_and_invalid_indices_for_all_three(self):
        for name in CASES:
            e=self.checked(['XIC(StartPB)'+instruction(name)+';']);self.assertEqual(e.memory.read('Results'),[None]*3)
            reads=[];original=e.memory.read
            def read(ref,scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref,scope)
            with patch.object(e.memory,'read',side_effect=read):e.step()
            self.assertNotIn('Index',reads);self.assertNotIn('Inputs[Index]',reads)
            self.assertFalse(e.memory.structural);self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_prescan_run_entry_retains_unknown_alias_index_and_results(self):
        for name in CASES:
            e=self.checked([instruction(name)+';'],index=None);e.enter_run()
            self.assertEqual(e.memory.read('Indices'),[None]);self.assertEqual(e.memory.read('Results'),[None]*3)
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_each_required_unknown_source_faults_then_full_result_is_established(self):
        for name,(value,expected) in CASES.items():
            e=self.checked(['MOV(99,SpeedCommand);','XIC(StartPB)'+instruction(name)+';'],index=1);e.step()
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[1]',value);e.step();self.assertEqual(e.memory.read('Results'),[None,expected,None])

    def test_all_fifteen_supported_type_and_order_forms_keep_existing_calculations(self):
        cases=[]
        for source in ('SINT','INT','DINT'):cases.append(('TOD',source,'DINT',99,'REVERSE',0x99))
        for dest in ('SINT','INT','DINT'):cases.append(('FRD','DINT',dest,0x99,'REVERSE',99))
        for order,expected in (('REVERSE',0x78563412),('WORD',0x56781234),('HIGHLOW',0x34127856)):
            cases.append(('SWPB','DINT','DINT',0x12345678,order,expected))
            for dest in ('INT','DINT'):cases.append(('SWPB','INT',dest,0x12ab,order,-21742))
        self.assertEqual(len(cases),15)
        for name,source,dest,value,order,expected in cases:
            e=self.checked(['XIC(StartPB)'+instruction(name,order=order)+';'],source=source,dest=dest,value=value);e.step()
            e.memory.write('Index',1);e.memory.write('Inputs[1]',value);e.memory.write('StartPB',True);e.step()
            self.assertEqual(e.memory.read('Results'),[None,expected,None],(name,source,dest,order))

    def test_actual_source_and_destination_indices_are_required_only_when_reached(self):
        for name in CASES:
            for source,dest in (('Inputs[Index]','Results[0]'),('Source','Results[Index]')):
                e=self.checked(['XIC(StartPB)'+instruction(name,source=source,dest=dest)+';']);e.step()
                e.memory.write('StartPB',True);before=self.snapshot(e)
                with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
                self.assertEqual(self.snapshot(e),before)
                e.memory.write('Index',1);e.memory.write('Inputs[1]',1234);e.step()

    def test_tod_and_frd_range_failures_are_deferred_until_true_then_recover(self):
        for name,source,dest,value,retry,expected in (('TOD','DINT','DINT',-1,1234,0x1234),
                                                    ('TOD','DINT','DINT',100000000,1234,0x1234),
                                                    ('FRD','DINT','SINT',0x128,0x127,127),
                                                    ('FRD','DINT','INT',0x32768,0x32767,32767)):
            e=self.checked(['MOV(99,SpeedCommand);','XIC(StartPB)'+instruction(name)+';'],source=source,dest=dest,index=1)
            e.memory.write('Inputs[1]',value);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[1]',retry);e.step();self.assertEqual(e.memory.read('Results'),[None,expected,None])

    def test_static_type_shape_reference_literal_order_and_permission_guards_remain(self):
        for text in ('FRD(Inputs,Results[0]);','TOD(Source,Results);','FRD(StartPB,Results[0]);',
                     'SWPB(1234,WORD,Results[0]);','SWPB(Source,Index,Results[0]);','SWPB(Source,HIGH/LOW,Results[0]);',
                     'FRD(2147483648,Results[0]);','TOD(1.0,Results[0]);','TOD(Inputs[Missing],Results[0]);',
                     'FRD(Inputs[Source/2],Results[0]);','FRD(Source,Results[99]);'):
            self.assertTrue(self.engine(['AFI()'+text]).blockers,text)
        for source,dest in (('SINT','DINT'),('INT','DINT'),('USINT','DINT'),('UINT','DINT'),('REAL','DINT'),('DINT','BOOL')):
            self.assertTrue(self.engine(source=source,dest=dest,value=1).blockers,(source,dest))
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_preflight_restores_prior_context_after_success_or_failure(self):
        from logixlab import numeric_conversions
        e=self.checked(index=0)
        for previous in (False,True):
            e.memory.structural=previous
            self.assertEqual(numeric_conversions.preflight(e.memory,Op('FRD',['Inputs[Index]','Results[Index]']),''),32)
            self.assertEqual(e.memory.structural,previous)
            with self.assertRaises(ModelError):numeric_conversions.preflight(e.memory,Op('SWPB',['Source','Index','Results[0]']),'')
            self.assertEqual(e.memory.structural,previous)
        e.memory.structural=False

    def test_unknown_udt_member_alias_full_writes_overlap_and_neighbor_guards(self):
        def aliases(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name in ('Word','Guard'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base')
            record=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(record,'DataValueMember',Name='Guard',DataType='DINT',Value='987')
            E.SubElement(tags,'Tag',Name='AliasWord',TagType='Alias',DataType='DINT',AliasFor='Packet1.Word')
        e=self.checked(['XIC(StartPB)FRD(Inputs[Index],AliasWord);','XIC(StartPB)TOD(AliasWord,Results[Index]);',
                        'XIC(StartPB)SWPB(Results[Index],WORD,Results[Index]);'],mutate=aliases)
        e.memory.write('Index',1);e.memory.write('Inputs[1]',0x1234);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Packet1'),{'Word':1234,'Guard':987});self.assertEqual(e.memory.read('Results'),[None,0x12340000,None])

    def test_later_failure_restores_conversion_swapped_values_and_scheduler(self):
        e=self.checked(['XIC(StartPB)TOD(Inputs[Index],Results[Index]);',
                        'XIC(StartPB)SWPB(Results[Index],WORD,Results[2]);','XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);'],index=1)
        e.memory.write('Inputs[1]',1234);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[2]',1);e.step();self.assertEqual(e.memory.read('Results'),[None,0x1234,0x12340000])

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['TOD(Value,Buffer[Index])SWPB(Value,REVERSE,Stack[0]);'])
        queues.logic(root,['AFI()TOD(Value,Buffer[Index])SWPB(Value,REVERSE,Stack[0]);'],name='EnableInFalse')
        for name in ('IndexA','IndexB'):root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/DataValue').set('Value','999')
        for name in ('DriverA','DriverB'):
            arr=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]')
            arr.remove(arr.find('Element[@Index="[0]"]'))

    def test_aoi_saved_invalid_indices_unknown_local_inout_and_binding_recovery(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic)
        e.memory.write('EnabledA',False);e.memory.write('EnabledB',False);e.step()
        e.memory.write('EnabledA',True);e.memory.write('EnabledB',True);e.memory.write('IndexA',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(0x11,0x22))
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]')),(0x0b000000,0x16000000))
        self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_st_swpb_false_branch_unknown_index_and_true_recovery_keep_existing_rules(self):
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='IF StartPB THEN SWPB(Inputs[Index],WORD,Results[Index]); END_IF;'
        e=self.checked(index=None,mutate=st);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);e.memory.write('Inputs[1]',0x1234);e.step();self.assertEqual(e.memory.read('Results'),[None,0x12340000,None])


if __name__=='__main__':unittest.main()
