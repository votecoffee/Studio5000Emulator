"""Numeric copy selection without saved lengths/indices, preserving byte rules."""
import copy
import struct
import unittest
from xml.etree import ElementTree as E

import test_numeric_copy as fixtures
import test_aoi_queues as queues
from logixlab.model import ModelError
from logixlab.numeric_copy import FORMATS,SIZES


class CopySelectionTests(unittest.TestCase):
    setUp=fixtures.NumericCopyTests.setUp

    @staticmethod
    def fields(root):
        tags=root.find('./Controller/Tags')
        for name in ('Index','OutputIndex'):fixtures.tag(tags,name,'DINT',99)
        t=E.SubElement(tags,'Tag',Name='Lengths',DataType='DINT',TagType='Base',Dimensions='3')
        E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
        for name in ('Src','Dst'):
            array=tags.find(f'Tag[@Name="{name}"]/Data/Array')
            for child in list(array):array.remove(child)

    def engine(self,lines,*,mutate=None,**kwargs):
        def fields(root):
            self.fields(root)
            if mutate:mutate(root)
        return fixtures.NumericCopyTests.engine(self,lines,mutate=fields,**kwargs)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.scheduler_description(),e.trace))

    def test_both_calls_skip_false_unknown_lengths_and_indices_then_require_actual_values(self):
        for op in ('COP','CPS'):
            e=self.checked([f'XIC(StartPB){op}(Src[Index],Dst[OutputIndex],Lengths[0]);']);e.step();self.assertEqual(e.memory.read('Dst'),[None]*3)
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Lengths[0]',1);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);e.memory.write('OutputIndex',0);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'known integer'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Src[0]',1065353216);e.step();self.assertEqual(e.memory.read('Dst'),[1.0,None,None])

    def test_all_nine_numeric_types_copy_exact_bytes_and_full_unknown_roundtrip(self):
        values={'SINT':-2,'INT':-1234,'DINT':-123456,'LINT':-9007199254740993,'USINT':254,'UINT':65000,'UDINT':4000000000,'ULINT':18446744073709551613,'REAL':1.25}
        for op in ('COP','CPS'):
            for dtype,value in values.items():
                with self.subTest(op=op,dtype=dtype):
                    e=self.checked([f'XIC(StartPB){op}(Src[Index],Dst[OutputIndex],Lengths[0]);',f'XIC(StartPB){op}(Dst[OutputIndex],Src[1],1);'],source_type=dtype,source=[0]*3,dest_type='SINT',dest=[0]*12,dest_dims=(12,))
                    e.memory.write('Index',0);e.memory.write('OutputIndex',1);e.memory.write('Lengths[0]',SIZES[dtype]);e.memory.write('Src[0]',value);e.memory.write('StartPB',True);e.step()
                    raw=struct.pack('<'+FORMATS[dtype],value);expected=[x if x<128 else x-256 for x in raw]
                    self.assertEqual(e.memory.read('Dst')[1:1+len(raw)],expected);self.assertIsNone(e.memory.read('Dst')[0]);self.assertIsNone(e.memory.read('Dst')[-1]);self.assertEqual(e.memory.read('Src')[1],value);self.assertIsNone(e.memory.read('Src')[2])

    def test_prescan_skips_enabled_unknown_lengths_values_and_indices(self):
        for op in ('COP','CPS'):
            e=self.checked([f'{op}(Src[Index],Dst[OutputIndex],Lengths[0]);']);self.assertEqual(e.prescan_count,1);self.assertEqual(e.scan_count,0);self.assertEqual(e.memory.read('Dst'),[None]*3)

    def test_zero_length_still_checks_addresses_but_reads_no_numeric_values(self):
        e=self.checked(['COP(Src[Index],Dst[OutputIndex],Lengths[0]);']);e.memory.write('Lengths[0]',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);e.memory.write('OutputIndex',0);e.step();self.assertEqual(e.memory.read('Src'),[None]*3);self.assertEqual(e.memory.read('Dst'),[None]*3)

    def test_clipping_partial_preservation_and_late_fault_restore_all_writes(self):
        e=self.checked(['COP(Src[Index],Dst[OutputIndex],Lengths[0]);'],source_type='SINT',dest_type='DINT');e.memory.write('Index',0);e.memory.write('OutputIndex',0);e.memory.write('Lengths[0]',100000)
        for i,value in enumerate([1,2,3]):e.memory.write(f'Src[{i}]',value)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Partial numeric-copy destination'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Dst[0]',0x11223344);e.step();self.assertEqual(e.memory.read('Dst'),[0x11030201,None,None])
        e=self.checked(['COP(Src[0],Dst[0],Lengths[0]);','DIV(1,SpeedSetpoint,SpeedCommand);']);e.memory.write('Lengths[0]',1);e.memory.write('Src[0]',1065353216);e.memory.write('SpeedSetpoint',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Dst'),[1.0,None,None])

    def test_matching_unknowns_and_indirect_overlap_retain_forward_propagation(self):
        e=self.checked(['COP(Src[Index],Dst[OutputIndex],Lengths[0]);'],dest_type='DINT');e.memory.write('Index',0);e.memory.write('OutputIndex',0);e.memory.write('Lengths[0]',3);e.step();self.assertEqual(e.memory.read('Dst'),[None]*3)
        e=self.checked(['CPS(Src[Index],Src[OutputIndex],Lengths[0]);'],dest_type='DINT');e.memory.write('Index',0);e.memory.write('OutputIndex',1);e.memory.write('Lengths[0]',100000);e.memory.write('Src[0]',7);e.step();self.assertEqual(e.memory.read('Src'),[7,7,7])

    def test_dynamic_alias_starts_and_lengths_are_not_used_for_static_transfer_limits(self):
        def alias(root):E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='DINT',TagType='Alias',AliasFor='Src[Index]')
        e=self.checked(['XIC(StartPB)COP(View,Dst[OutputIndex],Lengths[0]);'],mutate=alias);e.step();e.memory.write('Index',0);e.memory.write('OutputIndex',0);e.memory.write('Lengths[0]',1);e.memory.write('Src[0]',1065353216);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Dst'),[1.0,None,None])

    def test_indirect_alias_clipping_defers_actual_transfer_cap_until_reached(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='View',DataType='DINT',TagType='Alias',AliasFor='Src[Index]')
        e=self.checked(['XIC(StartPB)COP(View,Dst[0],32769);'],source=[0]*8193,source_dims=(8193,),dest_type='SINT',dest=[0]*32769,dest_dims=(32769,),mutate=alias)
        e.step();e.memory.write('StartPB',True);e.memory.write('Index',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'32768 bytes'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',8192);e.memory.write('Src[8192]',1);e.step();self.assertEqual(e.memory.read('Dst')[:5],[1,0,0,0,None])

    @staticmethod
    def aoi_logic(root):
        queues.logic(root,['XIC(Load)COP(Buffer[Index],Stack[0],Value);'])
        queues.logic(root,['NOP();'],'EnableInFalse')
        root.find('.//LocalTag[@Name="Stack"]').set('DataType','REAL')
        for node in root.findall('./Controller/Tags/Tag/Data/Structure/ArrayMember[@Name="Stack"]'):
            node.set('DataType','REAL')
            for child in list(node):node.remove(child)

    def test_aoi_unknown_local_outputs_false_indices_and_later_binding_rollback(self):
        q=queues.AOIQueueTests();q.setUp();self.addCleanup(q.doCleanups);e=q.checked(self.aoi_logic)
        for tag,value in [('Load',True),('ValueA',1),('ValueB',1),('IndexA',1),('IndexB',99)]:e.memory.write(tag,value)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',2);e.step()
        for driver,buffer,index in [('DriverA','BufferA',1),('DriverB','BufferB',2)]:self.assertEqual(e.memory.read(driver+'.Stack')[0],struct.unpack('<f',struct.pack('<i',e.memory.read(buffer)[index]))[0]);self.assertIsNone(e.memory.read(driver+'.Stack')[1])
        e.memory.write('EnabledB',False);e.memory.write('IndexB',99);e.step();self.assertFalse(e.memory.read('DriverB.EnableOut'))
        e.memory.write('EnabledB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_static_length_types_permissions_indices_and_older_profiles_remain_bounded(self):
        for length in ('-1','100001','1.0','StartPB','Src','Lengths','Src[0]/2'):
            self.assertTrue(self.engine([f'AFI()COP(Src[0],Dst[0],{length});']).blockers,length)
        for text in ('COP(Src[99],Dst[0],1);','COP(Src[0].0,Dst[0],1);','COP(Src[0],Dst[0],1);'):
            def mutate(root):root.find('./Controller/Tags/Tag[@Name="Dst"]').set('Constant','true')
            e=self.engine(['AFI()'+text],mutate=mutate);self.assertTrue(e.blockers);self.assertFalse(e.memory.structural)
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()COP(Src[Index],Dst[OutputIndex],Lengths[0]);'],mutate=older).blockers)

    def test_existing_st_calls_share_selection_without_new_syntax(self):
        e=self.checked(['IF StartPB THEN COP(Src[Index],Dst[OutputIndex],Lengths[0]); END_IF;'],st=True);e.step();e.memory.write('Index',0);e.memory.write('OutputIndex',0);e.memory.write('Lengths[0]',1);e.memory.write('Src[0]',1065353216);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Dst'),[1.0,None,None]);self.assertIn('Structural',e.report()['numeric_copy']['selection'])


if __name__=='__main__':unittest.main()
