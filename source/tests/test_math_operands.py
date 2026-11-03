"""Structural preflight and reached-value checks for standalone ladder math."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
from logixlab.model import ModelError

CASES = {'SQR':(-16,4),'LN':(1,0),'LOG':(100,2),'DEG':(0,0),'RAD':(0,0),
         'SIN':(0,0),'COS':(0,1),'TAN':(0,0),'ASN':(0,0),'ACS':(1,0),'ATN':(0,0),'XPY':(2,8)}


def instruction(name, source='Inputs[Index]', dest='Results[Index]', exponent='3'):
    return name+'('+','.join((source,exponent,dest) if name=='XPY' else (source,dest))+')'


class MathOperandTests(unittest.TestCase):
    setUp = fixtures.NumericStorageTests.setUp
    checked = fixtures.NumericStorageTests.checked
    snapshot = staticmethod(fixtures.NumericStorageTests.snapshot)

    def engine(self, rungs=None, *, source='REAL', dest='REAL', value=4, index=99, mutate=None):
        def fields(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Index"]')
            if index is None:
                tags=root.find('./Controller/Tags');tags.remove(tag)
                array=E.SubElement(tags,'Tag',Name='Indices',DataType='DINT',Dimensions='1',TagType='Base')
                E.SubElement(E.SubElement(array,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='1')
                E.SubElement(tags,'Tag',Name='Index',DataType='DINT',TagType='Alias',AliasFor='Indices[0]')
            else:tag.find('Data/DataValue').set('Value',str(index))
            if mutate:mutate(root)
        return fixtures.NumericStorageTests.engine(self,rungs or ['XIC(StartPB)SQR(Inputs[Index],Results[Index]);'],
                                                   source=source,dest=dest,value=value,mutate=fields)

    def test_all_twelve_false_instructions_skip_invalid_indices_and_unknown_values(self):
        for name in CASES:
            e=self.checked(['XIC(StartPB)'+instruction(name)+';']);self.assertEqual(e.memory.read('Results'),[None]*3)
            reads=[];original=e.memory.read
            def read(ref,scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref,scope)
            with patch.object(e.memory,'read',side_effect=read):e.step()
            self.assertNotIn('Index',reads);self.assertNotIn('Inputs[Index]',reads)
            self.assertFalse(e.memory.structural);self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_all_twelve_prescan_and_run_entry_retain_unknown_indices_and_results(self):
        for name in CASES:
            e=self.checked([instruction(name)+';'],index=None);self.assertEqual(e.memory.read('Indices'),[None])
            e.enter_run();self.assertEqual((e.scan_count,e.time_ms),(0,0))
            self.assertEqual(e.memory.read('Indices'),[None]);self.assertEqual(e.memory.read('Results'),[None]*3)
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_all_twelve_reached_unknown_sources_fault_then_establish_selected_results(self):
        for name,(value,expected) in CASES.items():
            e=self.checked(['MOV(99,SpeedCommand);','XIC(StartPB)'+instruction(name)+';'],index=1)
            e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[1]',value);e.step();self.assertEqual(e.memory.read('Results'),[None,float(expected),None],name)

    def test_each_narrow_source_destination_type_combination_uses_structural_indices(self):
        for source in ('SINT','INT','DINT','REAL'):
            for dest in ('SINT','INT','DINT','REAL'):
                e=self.checked(source=source,dest=dest,index=99);e.step();e.memory.write('Index',1)
                e.memory.write('Inputs[1]',-16);e.memory.write('StartPB',True);e.step()
                self.assertEqual(e.memory.read('Results'),[None,4,None],(source,dest))

    def test_actual_source_and_destination_indices_are_checked_only_when_reached(self):
        for text in ('SQR(Inputs[Index],Results[0]);','SQR(Source,Results[Index]);'):
            e=self.checked(['XIC(StartPB)'+text]);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Index',1);e.memory.write('Inputs[1]',4);e.step()
            self.assertEqual(e.memory.read('Results[0]' if 'Results[0]' in text else 'Results[1]'),2.0)

    def test_xpy_requires_both_inputs_when_enabled_and_skips_both_when_false(self):
        e=self.checked(['XIC(StartPB)XPY(Inputs[Index],Inputs[2],Results[Index]);']);e.step()
        e.memory.write('StartPB',True);e.memory.write('Index',0);e.memory.write('Inputs[0]',2);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[2]',3);e.step();self.assertEqual(e.memory.read('Results'),[8.0,None,None])

    def test_alias_udt_member_and_dynamic_destination_preserve_unwritten_unknowns(self):
        def alias(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='REAL',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Packet1',TagType='Base',DataType='Packet')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ResultAlias',TagType='Alias',DataType='REAL',AliasFor='Packet1.Value')
        e=self.checked(['XIC(StartPB)SQR(Inputs[Index],ResultAlias);'],mutate=alias);e.step()
        e.memory.write('Index',1);e.memory.write('Inputs[1]',-16);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Packet1.Value'),4.0);self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_static_type_shape_permission_index_grammar_and_literal_guards_remain(self):
        for text in ('SQR(Inputs,Results[0]);','SQR(Source,Results);','SQR(StartPB,Results[0]);',
                     'SQR(Inputs[Missing],Results[0]);','SQR(Inputs[Source],Results[0]);',
                     'SQR(Inputs[Index/2],Results[0]);','XPY(Source,2147483648,Results[0]);',
                     'LN(1e40,Results[0]);','SQR(Source,Results[99]);'):
            self.assertTrue(self.engine(['AFI()'+text]).blockers,text)
        for dtype in ('BOOL','LINT','USINT','UINT','UDINT','ULINT'):
            self.assertTrue(self.engine(dest=dtype).blockers,dtype)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_preflight_restores_prior_structural_context_after_success_or_error(self):
        from logixlab import real_math
        from logixlab.model import Op
        e=self.checked(index=0)
        for previous in (False,True):
            e.memory.structural=previous
            real_math.preflight(e.memory,Op('SQR',['Inputs[Index]','Results[Index]']),'')
            self.assertEqual(e.memory.structural,previous)
            with self.assertRaises(ModelError):real_math.preflight(e.memory,Op('SQR',['Missing','Results[0]']),'')
            self.assertEqual(e.memory.structural,previous)
        e.memory.structural=False

    def test_reached_domain_and_range_faults_roll_back_then_retry(self):
        for name,value,retry in (('LN',0,1),('LOG',-1,100),('ASN',2,0),('ACS',-2,1),('XPY',-2,4)):
            text=instruction(name,exponent='0.5')
            e=self.checked(['MOV(99,SpeedCommand);','XIC(StartPB)'+text+';'],index=1)
            e.memory.write('Inputs[1]',value);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[1]',retry);e.step();self.assertIsNotNone(e.memory.read('Results[1]'))
        e=self.checked(['XIC(StartPB)SQR(Inputs[Index],Results[Index]);'],dest='SINT',index=1)
        e.memory.write('Inputs[1]',40000);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'overflow'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',25);e.step();self.assertEqual(e.memory.read('Results[1]'),5)

    def test_later_fault_restores_established_math_results_values_and_scheduler(self):
        e=self.checked(['XIC(StartPB)SQR(Inputs[Index],Results[Index]);','XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);'],index=0)
        e.memory.write('Inputs[0]',-16);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[2]',1);e.step();self.assertEqual(e.memory.read('Results'),[4.0,None,None])

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['SQR(Value,Buffer[Index])XPY(Value,1,Stack[0]);'])
        queues.logic(root,['AFI()SQR(Value,Buffer[Index])XPY(Value,1,Stack[0]);'],name='EnableInFalse')
        for name in ('IndexA','IndexB'):root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/DataValue').set('Value','999')
        for name in ('DriverA','DriverB'):
            arr=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]')
            arr.remove(arr.find('Element[@Index="[0]"]'))

    def test_aoi_saved_invalid_indices_unknown_local_results_and_binding_recovery(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic)
        e.memory.write('EnabledA',False);e.memory.write('EnabledB',False);e.step()
        e.memory.write('EnabledA',True);e.memory.write('EnabledB',True);e.memory.write('IndexA',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(3,5))
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]')),(11,22))
        self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)


if __name__=='__main__':unittest.main()
