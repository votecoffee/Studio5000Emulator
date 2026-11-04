"""Finite binary64 COP/CPS byte images, clipped windows and rollback."""
import math
import struct
import unittest
from xml.etree import ElementTree as E

import test_numeric_copy as copies
import test_lreal_math as basic
import test_lreal_advanced as advanced
from logixlab.model import Project
from logixlab.runtime import Engine

FORMATS={'SINT':'b','INT':'h','DINT':'i','LINT':'q','USINT':'B','UINT':'H','UDINT':'I','ULINT':'Q','REAL':'f','LREAL':'d'}


class LrealCopyTests(unittest.TestCase):
    setUp=copies.NumericCopyTests.setUp
    engine=copies.NumericCopyTests.engine
    checked=copies.NumericCopyTests.checked
    snapshot=staticmethod(basic.LrealMathTests.snapshot)
    fault=basic.LrealMathTests.fault

    def scalar(self,instruction='COP',*,value=1.0000000000000002,source_type='LREAL',dest_type='ULINT',dest=0,extra=()):
        return self.checked([instruction+'(Src,Dst,1);',*extra],source_type=source_type,source=value,source_dims=None,dest_type=dest_type,dest=dest,dest_dims=None)

    def test_all_numeric_type_pairs_involving_lreal_copy_eight_bytes_in_both_languages(self):
        raw=bytes(range(1,9))
        for source in FORMATS:
            for dest in FORMATS:
                if 'LREAL' not in (source,dest):continue
                source_values=[v[0] for v in struct.iter_unpack('<'+FORMATS[source],raw)]
                expected=[v[0] for v in struct.iter_unpack('<'+FORMATS[dest],raw)]
                for instruction in ('COP','CPS'):
                    for st in (False,True):
                        with self.subTest(source=source,dest=dest,instruction=instruction,st=st):
                            e=self.checked([f'{instruction}(Src[0],Dst[0],{len(expected)});'],source_type=source,source=source_values,source_dims=(len(source_values),),dest_type=dest,dest=[0]*len(expected),dest_dims=(len(expected),),st=st)
                            e.memory.values['dst']=[None]*len(expected);e.step();self.assertEqual(e.memory.read('Dst'),expected)

    def test_finite_precision_signed_zero_subnormal_and_extreme_images_round_trip(self):
        for value in (1.0000000000000002,-0.0,5e-324,-5e-324,1e308,-1e308):
            for instruction in ('COP','CPS'):
                image=struct.unpack('<Q',struct.pack('<d',value))[0]
                e=self.scalar(instruction,value=value);e.step();self.assertEqual(e.memory.read('Dst'),image)
                e=self.scalar(instruction,value=image,source_type='ULINT',dest_type='LREAL');e.step();self.assertEqual(struct.pack('<d',e.memory.read('Dst')),struct.pack('<d',value))

    def test_destination_element_count_controls_size_and_clipping_preserves_upper_bytes(self):
        e=self.scalar(source_type='DINT',value=1,dest_type='LREAL',dest=1.0);e.step();self.assertEqual(e.memory.read('Dst'),1.0000000000000002)
        e=self.scalar(value=1.0000000000000002,dest_type='DINT');e.step();self.assertEqual(e.memory.read('Dst'),1)
        e=self.checked(['COP(Src[0],Dst[0],100000);'],source_type='LREAL',source=[1.0],source_dims=(1,),dest_type='DINT',dest=[99,99,99]);e.step();self.assertEqual(e.memory.read('Dst'),[0,1072693248,99])

    def test_partial_destination_requires_old_bytes_full_write_establishes_unknown(self):
        e=self.scalar(source_type='DINT',value=1,dest_type='LREAL');e.memory.values['dst']=None;self.fault(e,'Partial numeric-copy destination')
        e=self.scalar(value=0x3ff0000000000001,source_type='ULINT',dest_type='LREAL');e.memory.values['dst']=None;e.step();self.assertEqual(e.memory.read('Dst'),1.0000000000000002)

    def test_same_type_unknowns_and_forward_backward_overlap_retain_logical_rules(self):
        for instruction in ('COP','CPS'):
            e=self.checked([instruction+'(Src[0],Dst[0],3);'],source_type='LREAL',source=[1,2,3],dest_type='LREAL');e.memory.values['src'][1]=None;e.step();self.assertEqual(e.memory.read('Dst'),[1.0,None,3.0])
            e=self.checked([instruction+'(Src[0],Src[1],2);'],source_type='LREAL',source=[1.0000000000000002,2,3]);e.step();self.assertEqual(e.memory.read('Src'),[1.0000000000000002]*3)
            e=self.checked([instruction+'(Src[1],Src[0],2);'],source_type='LREAL',source=[1,2,3]);e.step();self.assertEqual(e.memory.read('Src'),[2.0,3.0,3.0])

    def test_nonfinite_images_roll_back_all_outputs_and_task_timing(self):
        for image in (0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000001):
            e=self.checked(['MOV(99,SpeedCommand);','CPS(Src[0],Dst[0],3);'],source_type='ULINT',source=[0x3ff0000000000000,image,0x4000000000000000],dest_type='LREAL');self.fault(e,'Nonfinite LREAL')
        e=self.scalar();e.memory.values['src']=float('inf');self.fault(e,'Nonfinite LREAL')
        # A partial low-word patch retains the finite destination's upper bytes.
        e=self.scalar(source_type='DINT',value=1,dest_type='LREAL',dest=math.nextafter(math.inf,0));e.step();self.assertTrue(math.isfinite(e.memory.read('Dst')))

    def test_false_prescan_zero_length_and_live_unknown_indices_are_lazy(self):
        def controls(root):copies.tag(root.find('./Controller/Tags'),'Index','DINT',99)
        e=self.checked(['XIC(StartPB)COP(Src[Index],Dst[Index],Length);'],source_type='LREAL',source=[1,2,3],mutate=controls)
        e.memory.values['length']=None;e.enter_run();e.step();e.memory.write('StartPB',True);self.fault(e,'Unknown')
        e.memory.write('Length',1);self.fault(e,'outside bounds');e.memory.write('Index',1);e.memory.values['src'][1]=None;self.fault(e,'known numeric')
        e.memory.write('Length',0);e.step();self.assertEqual(e.memory.read('Dst'),[0.0]*3)
        e.memory.write('Index',99);self.fault(e,'outside bounds')

    def test_late_fault_recovers_and_preserves_exact_images(self):
        e=self.scalar(extra=['DIV(1,SpeedSetpoint,SpeedCommand);']);e.memory.write('SpeedSetpoint',0);self.fault(e,'zero')
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Dst'),0x3ff0000000000001)

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups);e=helper.aoi();root=E.parse(e.project.path).getroot()
        advanced.queues.logic(root,['COP(Stack[0],Buffer[Index],2);','CPS(Buffer[Index],Stack[0],2);'])
        E.ElementTree(root).write(e.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(e.project.path))

    def test_aoi_local_inout_arrays_and_warm_state_binding_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.step();e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(9.0,4.0));self.assertEqual(e.memory.frames['@AOI:drivera']['buffer'],('BufferA',''))

    def test_st_for_protects_integer_bounds_for_lreal_sources_and_allows_lreal_targets(self):
        e=self.engine(['FOR SpeedCommand:=0 TO Dst[1] DO COP(Src[0],Dst[0],2); END_FOR;'],source_type='LREAL',source=[1,2,3],dest_type='DINT',st=True)
        self.assertTrue(any('bounds/step' in b for b in e.blockers))
        e=self.checked(['FOR SpeedCommand:=0 TO 1 DO COP(Src[0],Dst[0],1); END_FOR;'],source_type='DINT',source=[1,2,3],dest_type='LREAL',st=True);e.step()
        self.assertEqual(struct.pack('<d',e.memory.read('Dst[0]')),struct.pack('<ii',1,2))

    def test_static_budget_permission_and_length_guards_are_unchanged(self):
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Dst"]').set('Constant','true')
        self.assertTrue(self.engine(source_type='LREAL',source=[1,2,3],dest_type='LREAL',mutate=readonly).blockers)
        self.assertTrue(self.engine(['COP(Src[0],Dst[0],1.0);'],source_type='LREAL',source=[1,2,3]).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(source_type='LREAL',source=[1,2,3],dest_type='LREAL',mutate=old).blockers)
        e=self.scalar();e.budget=0
        # Advance resets its budget; directly exercise a byte copy with a depleted budget.
        from logixlab import numeric_copy
        spec=numeric_copy.plan(e,type('Op',(),{'args':('Src','Dst','1')})(),'MainProgram',1)
        before=self.snapshot(e)
        with self.assertRaisesRegex(basic.ModelError,'budget'):numeric_copy.execute(e,spec)
        self.assertEqual(self.snapshot(e),before)

    def test_report_lists_ten_formats_and_keeps_native_limits(self):
        d=self.scalar().report()['numeric_copy'];self.assertEqual(len(d['types']),10);self.assertIn('LREAL',d['types']);self.assertEqual(d['endianness'],'little');self.assertFalse(d['native_runtime_parity'])
