"""Lazy ladder MVM/BTD references, preserved bits and transactional recovery."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_math_operands as fixtures
from logixlab.model import ModelError, Op


class BitTransferOperandTests(unittest.TestCase):
    setUp = fixtures.MathOperandTests.setUp
    checked = fixtures.MathOperandTests.checked
    snapshot = staticmethod(fixtures.MathOperandTests.snapshot)

    def engine(self, rungs=None, *, source='DINT', dest='DINT', value=0x12345678, index=99, mutate=None):
        def fields(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Masks',DataType='DINT',Dimensions='3',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
            if mutate:mutate(root)
        return fixtures.MathOperandTests.engine(self,rungs or ['XIC(StartPB)MVM(Inputs[Index],-1,Results[Index]);'],
                                               source=source,dest=dest,value=value,index=index,mutate=fields)

    def test_false_and_prescan_skip_invalid_source_mask_destination_indices(self):
        for text in ('MVM(Inputs[Index],Masks[Index],Results[Index]);','BTD(Inputs[Index],0,Results[Index],0,32);'):
            e=self.checked(['XIC(StartPB)'+text]);self.assertEqual(e.memory.read('Results'),[None]*3)
            reads=[];original=e.memory.read
            def read(ref,scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref,scope)
            with patch.object(e.memory,'read',side_effect=read):e.step()
            self.assertNotIn('Index',reads);self.assertNotIn('Inputs[Index]',reads);self.assertNotIn('Masks[Index]',reads)
            self.assertFalse(e.memory.structural);self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_prescan_run_entry_retains_unknown_alias_index_and_results(self):
        for text in ('MVM(Inputs[Index],-1,Results[Index]);','BTD(Inputs[Index],0,Results[Index],0,32);'):
            e=self.checked([text],index=None);e.enter_run()
            self.assertEqual(e.memory.read('Indices'),[None]);self.assertEqual(e.memory.read('Results'),[None]*3)
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_full_replacement_establishes_unknown_results_across_narrow_type_pairs(self):
        for source in ('SINT','INT','DINT'):
            for dest,bits in (('SINT',8),('INT',16),('DINT',32)):
                for text in ('MVM(Inputs[Index],-1,Results[Index]);',f'BTD(Inputs[Index],0,Results[Index],0,{bits});'):
                    e=self.checked(['XIC(StartPB)'+text],source=source,dest=dest,value=-1);e.step()
                    e.memory.write('Index',1);e.memory.write('Inputs[1]',-1);e.memory.write('StartPB',True);e.step()
                    expected={'SINT':255,'INT':65535,'DINT':4294967295}[source]
                    expected=int.from_bytes(expected.to_bytes(4,'little')[:bits//8],'little',signed=True)
                    self.assertEqual(e.memory.read('Results'),[None,expected,None],(source,dest,text))

    def test_partial_writes_require_old_destination_then_preserve_unselected_bits(self):
        for text in ('MVM(Inputs[Index],255,Results[Index]);','BTD(Inputs[Index],0,Results[Index],0,8);'):
            e=self.checked(['XIC(StartPB)'+text],index=1);e.step();e.memory.write('Inputs[1]',0x78);e.memory.write('StartPB',True)
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Results[1]',0x12345600);e.step();self.assertEqual(e.memory.read('Results'),[None,0x12345678,None])

    def test_dynamic_mask_is_required_before_selected_source_values_and_recovers(self):
        e=self.checked(['XIC(StartPB)MVM(Inputs[Index],Masks[Index],Results[Index]);'],index=1);e.step()
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Masks[1]',-1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',0x12345678);e.step();self.assertEqual(e.memory.read('Results'),[None,0x12345678,None])

    def test_zero_mask_skips_values_but_enabled_calls_still_check_addresses(self):
        e=self.checked(['XIC(StartPB)MVM(Inputs[Index],0,Results[Index]);']);e.step()
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Inputs'),[None]*3);self.assertEqual(e.memory.read('Results'),[None]*3)

    def test_each_actual_source_mask_destination_index_is_checked_when_enabled(self):
        for text in ('MVM(Inputs[Index],-1,Results[0]);','MVM(Source,Masks[Index],Results[0]);',
                     'MVM(Source,-1,Results[Index]);','BTD(Inputs[Index],0,Results[0],0,32);','BTD(Source,0,Results[Index],0,32);'):
            e=self.checked(['XIC(StartPB)'+text]);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Index',1);e.memory.write('Inputs[1]',12);e.memory.write('Masks[1]',-1);e.step()

    def test_static_fields_literal_bounds_types_permissions_and_shapes_remain_blocked(self):
        for text in ('MVM(Inputs,-1,Results[0]);','BTD(Source,0,Results,0,32);','MVM(StartPB,-1,Results[0]);',
                     'MVM(Source,Masks,Results[0]);','BTD(Source,Index,Results[0],0,8);',
                     'BTD(Source,0,Results[0],Index,8);','BTD(Source,0,Results[0],0,Index);',
                     'BTD(Source,-1,Results[0],0,8);','BTD(Source,32,Results[0],0,8);',
                     'BTD(Source,0,Results[0],32,8);','BTD(Source,0,Results[0],0,0);',
                     'MVM(2147483648,-1,Results[0]);','MVM(Source,16#1FFFFFFFF,Results[0]);',
                     'MVM(Inputs[Missing],-1,Results[0]);','BTD(Source,0,Results[99],0,32);'):
            self.assertTrue(self.engine(['AFI()'+text]).blockers,text)
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT','REAL'):
            self.assertTrue(self.engine(source=dtype,value=1).blockers,dtype)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_preflight_restores_prior_context_after_success_and_error(self):
        from logixlab import bit_transfer
        e=self.checked(index=0)
        for previous in (False,True):
            e.memory.structural=previous
            bit_transfer.preflight(e.memory,Op('BTD',['Inputs[Index]','0','Results[Index]','0','32']),'')
            self.assertEqual(e.memory.structural,previous)
            with self.assertRaises(ModelError):bit_transfer.preflight(e.memory,Op('BTD',['Source','32','Results[0]','0','8']),'')
            self.assertEqual(e.memory.structural,previous)
        e.memory.structural=False

    def test_alias_udt_member_overlap_and_neighbor_guards(self):
        def alias(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name in ('Word','Guard'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Packet1',TagType='Base',DataType='Packet')
            record=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(record,'DataValueMember',Name='Guard',DataType='DINT',Value='987')
            E.SubElement(tags,'Tag',Name='AliasResult',TagType='Alias',DataType='DINT',AliasFor='Packet1.Word')
        e=self.checked(['XIC(StartPB)MVM(Inputs[Index],-1,AliasResult);','XIC(StartPB)BTD(AliasResult,0,AliasResult,4,12);'],mutate=alias)
        e.memory.write('Index',1);e.memory.write('Inputs[1]',0x1234);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Packet1'),{'Word':0x2344,'Guard':987})
        self.assertEqual(e.memory.read('Results'),[None]*3);self.assertEqual(e.memory.read('Inputs'),[None,0x1234,None])

    def test_later_failure_restores_full_and_partial_writes_and_scheduler(self):
        e=self.checked(['XIC(StartPB)MVM(Inputs[Index],-1,Results[Index]);',
                        'XIC(StartPB)BTD(Inputs[Index],0,Results[Index],8,8);',
                        'XIC(StartPB)DIV(1,Inputs[2],SpeedCommand);'],index=1)
        e.memory.write('Inputs[1]',0x1234);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[2]',1);e.step();self.assertEqual(e.memory.read('Results'),[None,0x3434,None])

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['MVM(Value,-1,Buffer[Index])BTD(Value,0,Stack[0],0,32);'])
        queues.logic(root,['AFI()MVM(Value,-1,Buffer[Index])BTD(Value,0,Stack[0],0,32);'],name='EnableInFalse')
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
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(11,22))
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]')),(11,22))
        self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_other_controllers_keep_prior_validation_and_execution_path(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)
        e=self.checked(['MVM(Source,-1,Dest);'],index=0,mutate=old);e.step();self.assertEqual(e.memory.read('Dest'),0x12345678)
        report=self.checked().report()['bit_transfer'];self.assertFalse(report['native_math_status'])


if __name__=='__main__':unittest.main()
