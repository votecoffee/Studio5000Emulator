"""Numeric byte images, clipped regions, partial writes and transaction boundaries."""
import copy
import itertools
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def tag(parent,name,dtype,value,*,dims=None):
    t=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype)
    data=E.SubElement(t,'Data',Format='Decorated')
    if dims is None:E.SubElement(data,'DataValue',DataType=dtype,Value=str(value))
    else:
        t.set('Dimensions',','.join(map(str,dims)));a=E.SubElement(data,'Array',DataType=dtype,Dimensions=','.join(map(str,dims)))
        for indices,item in zip(itertools.product(*(range(d) for d in dims)),value,strict=True):
            E.SubElement(E.SubElement(a,'Element',Index='['+','.join(map(str,indices))+']'),'DataValue',DataType=dtype,Value=str(item))
    return t


class NumericCopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,source_type='DINT',source=None,dest_type='REAL',dest=None,source_dims=(3,),dest_dims=(3,),mutate=None,st=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        tag(tags,'Src',source_type,[1065353216,1073741824,-1071644672] if source is None else source,dims=source_dims)
        tag(tags,'Dst',dest_type,[0,0,0] if dest is None else dest,dims=dest_dims)
        tag(tags,'Length','DINT',3)
        routine=root.find('./Controller/Programs/Program/Routines/Routine');lines=lines if lines is not None else ['COP(Src[0],Dst[0],3);']
        if st:logic(routine,lines)
        else:
            content=routine.find('RLLContent');content.clear()
            for i,text in enumerate(lines):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'copy.L5X';E.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
        return Engine(Project(p))

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_real_dint_bit_patterns_are_reinterpreted_in_both_languages(self):
        for instruction in ('COP','CPS'):
            for st in (False,True):
                e=self.checked([instruction+'(Src[0],Dst[0],3);'],st=st);e.step()
                self.assertEqual(e.memory.read('Dst'),[1,2,-2.5])

    def test_real_to_integer_uses_bits_instead_of_numeric_conversion(self):
        e=self.checked(source_type='REAL',source=[1,2,-2.5],dest_type='DINT');e.step()
        self.assertEqual(e.memory.read('Dst'),[1065353216,1073741824,-1071644672])

    def test_signed_unsigned_images_cover_every_integer_width(self):
        cases=(('SINT',-1,'USINT',255),('USINT',255,'SINT',-1),('INT',-2,'UINT',65534),('UINT',65535,'INT',-1),
               ('DINT',-2,'UDINT',4294967294),('UDINT',2147483648,'DINT',-2147483648),
               ('LINT',-2,'ULINT',18446744073709551614),('ULINT',9223372036854775808,'LINT',-9223372036854775808))
        for source_type,value,dest_type,expected in cases:
            e=self.checked(['CPS(Src,Dst,1);'],source_type=source_type,source=value,source_dims=None,dest_type=dest_type,dest=0,dest_dims=None)
            with self.subTest(source=source_type,dest=dest_type):e.step();self.assertEqual(e.memory.read('Dst'),expected)

    def test_destination_element_width_determines_transfer_size(self):
        e=self.checked(['COP(Src[0],Dst[0],2);'],source=[0x12345678],source_dims=(1,),dest_type='INT',dest=[0,0],dest_dims=(2,));e.step()
        self.assertEqual(e.memory.read('Dst'),[0x5678,0x1234])
        e=self.checked(['COP(Src[0],Dst,1);'],source_type='INT',source=[0x5678,0x1234],source_dims=(2,),dest_type='DINT',dest=0,dest_dims=None);e.step()
        self.assertEqual(e.memory.read('Dst'),0x12345678)

    def test_little_endian_signed_bytes_can_build_real_values(self):
        e=self.checked(['COP(Src[0],Dst[0],2);'],source_type='SINT',source=[0,0,-128,63,0,0,32,-64],source_dims=(8,),dest=[0,0],dest_dims=(2,));e.step()
        self.assertEqual(e.memory.read('Dst'),[1,-2.5])

    def test_source_end_clip_preserves_uncopied_destination_bytes(self):
        e=self.checked(['COP(Src[0],Dst[0],20);'],source_type='SINT',source=[1,2,3,4,5],source_dims=(5,),dest_type='DINT',dest=[0,0x11223344,0x55667788]);e.step()
        self.assertEqual(e.memory.read('Dst'),[0x04030201,0x11223305,0x55667788])

    def test_destination_end_and_source_start_offsets_clip_correctly(self):
        e=self.checked(['COP(Src[1],Dst[1],20);'],source_type='SINT',source=[9,1,2,3,4,5],source_dims=(6,),dest_type='INT',dest=[99,0,0]);e.step()
        self.assertEqual(e.memory.read('Dst'),[99,0x0201,0x0403])

    def test_partial_wide_destination_preserves_upper_half(self):
        e=self.checked(['CPS(Src,Dst,1);'],source_type='REAL',source=1,source_dims=None,dest_type='ULINT',dest=0x1122334400000000,dest_dims=None);e.step()
        self.assertEqual(e.memory.read('Dst'),0x112233443f800000)

    def test_partial_source_element_does_not_copy_its_remaining_bytes(self):
        e=self.checked(['COP(Src,Dst,1);'],source_type='ULINT',source=0x112233443f800000,source_dims=None,dest_type='REAL',dest=0,dest_dims=None);e.step()
        self.assertEqual(e.memory.read('Dst'),1)

    def test_full_overwrite_establishes_unknown_destination(self):
        e=self.checked();e.memory.values['dst']=[None]*3;e.step();self.assertEqual(e.memory.read('Dst'),[1,2,-2.5])

    def test_partial_overwrite_requires_known_preserved_bytes(self):
        e=self.checked(['COP(Src,Dst,1);'],source_type='SINT',source=1,source_dims=None,dest_type='DINT',dest=0,dest_dims=None)
        e.memory.values['dst']=None
        with self.assertRaisesRegex(ModelError,'Partial numeric-copy destination'):e.step()
        self.assertEqual((e.memory.values['dst'],e.time_ms),(None,0))

    def test_unknown_mixed_source_faults_but_same_type_unknowns_propagate(self):
        e=self.checked();e.memory.values['src'][1]=None;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'known integer'):e.step()
        self.assertEqual(e.memory.values,before)
        e=self.checked(dest_type='DINT');e.memory.values['src'][1]=None;e.step();self.assertIsNone(e.memory.read('Dst')[1])

    def test_nonfinite_real_bit_image_rejects_the_whole_advance(self):
        for invalid in (0x7fc00000,0x7f800000,-8388608):
            e=self.checked(['MOV(99,SpeedCommand);','COP(Src[0],Dst[0],3);'],source=[1065353216,invalid,1073741824])
            before=copy.deepcopy(e.memory.values)
            with self.subTest(image=invalid),self.assertRaisesRegex(ModelError,'Nonfinite'):e.step()
            self.assertEqual((e.memory.values,e.time_ms),(before,0))

    def test_signed_zero_roundtrips_through_its_integer_image(self):
        e=self.checked(['COP(Src,Dst,1);'],source_type='REAL',source=-0.0,source_dims=None,dest_type='DINT',dest=0,dest_dims=None);e.step()
        self.assertEqual(e.memory.read('Dst'),-2147483648)

    def test_same_type_overlap_propagates_forward_and_copies_backward(self):
        for instruction in ('COP','CPS'):
            e=self.checked([instruction+'(Src[0],Src[1],20);'],source=[1,2,3]);e.step();self.assertEqual(e.memory.read('Src'),[1,1,1])
            e=self.checked([instruction+'(Src[1],Src[0],20);'],source=[1,2,3]);e.step();self.assertEqual(e.memory.read('Src'),[2,3,3])

    def test_aliased_overlap_uses_the_same_resolved_region(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='AliasSrc',TagType='Alias',AliasFor='Src')
        e=self.checked(['COP(AliasSrc[0],Src[1],2);'],source=[1,2,3],mutate=alias);e.step();self.assertEqual(e.memory.read('Src'),[1,1,1])

    def test_multidimensional_arrays_copy_row_major_from_selected_offsets(self):
        e=self.checked(['COP(Src[0,1,0],Dst[0,1],3);'],source=[0,0,1065353216,1073741824,-1071644672,0,0,0],source_dims=(2,2,2),dest=[0]*6,dest_dims=(2,3));e.step()
        self.assertEqual(e.memory.read('Dst'),[[0,1,2],[-2.5,0,0]])

    def test_zero_length_reads_no_values_and_changes_nothing(self):
        e=self.checked(['COP(Src[0],Dst[0],0);']);e.memory.values['src']=[None]*3;e.step();self.assertEqual(e.memory.read('Dst'),[0,0,0])

    def test_huge_requested_length_clips_to_small_actual_regions(self):
        e=self.checked(['COP(Src,Dst,100000);'],source=1065353216,source_dims=None,dest=0,dest_dims=None);e.step();self.assertEqual(e.memory.read('Dst'),1)

    def test_dynamic_lengths_recompute_and_negative_fault_rolls_back(self):
        e=self.checked(['MOV(99,SpeedCommand);','COP(Src[0],Dst[0],Length);']);e.memory.write('Length',1);e.step();self.assertEqual(e.memory.read('Dst'),[1,0,0])
        e.memory.write('Length',-1);before=copy.deepcopy((e.memory.values,e.time_ms,e.scan_count,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'length'):e.step()
        self.assertEqual((e.memory.values,e.time_ms,e.scan_count,e.scheduler_description()),before)

    def test_false_rung_and_prescan_do_not_copy(self):
        e=self.checked(['XIC(StartPB)COP(Src[0],Dst[0],3);']);e.step();self.assertEqual(e.memory.read('Dst'),[0,0,0])
        e.memory.write('StartPB',True);e.step();e.memory.write('Dst[0]',9);e.enter_run();self.assertEqual(e.memory.read('Dst')[0],9)

    def test_byte_budget_failure_restores_all_prior_writes(self):
        e=self.checked(['MOV(99,SpeedCommand);','COP(Src[0],Dst[0],3);']);e.instruction_limit=5;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'byte budget'):e.step()
        self.assertEqual((e.memory.values,e.time_ms),(before,0))

    def test_transfer_cap_applies_to_actual_bytes(self):
        e=self.checked(['COP(Src[0],Dst[0],32768);'],source=[0]*8192,source_dims=(8192,),dest_type='SINT',dest=[0]*32768,dest_dims=(32768,));e.step()
        self.assertEqual(len(e.memory.read('Dst')),32768)
        e=self.engine(['COP(Src[0],Dst[0],32769);'],source=[0]*8193,source_dims=(8193,),dest_type='SINT',dest=[0]*32769,dest_dims=(32769,))
        self.assertTrue(any('32768 bytes' in problem for problem in e.blockers))

    def test_readonly_source_is_allowed_and_constant_destination_blocks(self):
        def source_constant(root):root.find('./Controller/Tags/Tag[@Name="Src"]').set('Constant','true')
        e=self.checked(mutate=source_constant);e.step();self.assertEqual(e.memory.read('Dst'),[1,2,-2.5])
        def dest_constant(root):root.find('./Controller/Tags/Tag[@Name="Dst"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=dest_constant).blockers)

    def test_bits_literals_and_aggregate_mismatches_are_blocked(self):
        for text in ('COP(Src[0].0,Dst[0],1);','COP(1,Dst[0],1);','COP(Src[0],StartPB,1);','COP(StationTimer,Dst[0],1);'):
            self.assertTrue(self.engine([text]).blockers)

    def test_other_profiles_keep_legacy_matching_copy_and_block_mixed_forms(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)
            e=self.engine(['COP(Src[0],Src[1],2);'],source=[1,2,3],mutate=profile)
            if version=='34':self.assertTrue(any('Revision 34' in b for b in e.blockers))
            else:self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Src'),[1,1,1])
            self.assertFalse(e.report()['numeric_copy']['available'])

    def test_report_exposes_byte_contract_without_adding_dispatch_entries(self):
        e=self.checked();profile=e.report()['numeric_copy'];self.assertTrue(profile['available']);self.assertFalse(profile['native_runtime_parity'])
        self.assertEqual((profile['endianness'],profile['types']),('little',['DINT','INT','LINT','REAL','SINT','UDINT','UINT','ULINT','USINT']))
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))

    def test_program_local_and_aoi_inout_arrays_use_resolved_regions(self):
        def setup(root):
            tags=root.find('./Controller/Tags');t=tags.find('./Tag[@Name="Src"]');tags.remove(t);root.find('./Controller/Programs/Program/Tags').append(t)
            E.SubElement(tags,'Tag',Name='AliasSrc',TagType='Alias',AliasFor='Program:MainProgram.Src')
            a=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='ConvertBlock',Revision='1.0');p=E.SubElement(a,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            for name,dtype in (('Input','DINT'),('Output','REAL')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType=dtype,Dimensions='3',Usage='InOut',Required='true',Visible='true')
            E.SubElement(a,'LocalTags');logic(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='ST'),['COP(Input[0],Output[0],3);'])
            t=E.SubElement(tags,'Tag',Name='Instance',DataType='ConvertBlock',TagType='Base');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='ConvertBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['ConvertBlock(Instance,AliasSrc,Dst);'],mutate=setup,st=True);e.step();self.assertEqual(e.memory.read('Dst'),[1,2,-2.5])
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[]);h.step();self.assertEqual(h.memory.read('Dst'),[1,2,-2.5])

    def test_nested_record_member_arrays_copy_within_member_boundaries(self):
        def nested(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='PacketCell',Class='User',Family='NoFamily'),'Members')
            for name,dtype,dimension in (('Bytes','SINT','5'),('Words','DINT','3'),('Sentinel','DINT','0')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension=dimension)
            tags=root.find('./Controller/Tags');t=E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='PacketCell',Dimensions='2');arr=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='PacketCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='PacketCell')
                for name,dtype,values in (('Bytes','SINT',[1,2,3,4,5]),('Words','DINT',[0,0x11223344,99])):
                    a=E.SubElement(obj,'ArrayMember',Name=name,DataType=dtype,Dimensions=str(len(values)))
                    for j,value in enumerate(values):E.SubElement(a,'Element',Index=f'[{j}]',Value=str(value))
                E.SubElement(obj,'DataValueMember',Name='Sentinel',DataType='DINT',Value='77')
        e=self.checked(['COP(Cells[1].Bytes[0],Cells[1].Words[0],100);'],mutate=nested);e.step()
        self.assertEqual(e.memory.read('Cells[1].Words'),[0x04030201,0x11223305,99]);self.assertEqual(e.memory.read('Cells[1].Sentinel'),77)
        self.assertEqual(e.memory.read('Cells[0].Words'),[0,0x11223344,99])

    def test_st_for_guards_every_copied_element_and_dynamic_extent(self):
        for text in ('FOR SpeedCommand:=0 TO Dst[1] DO COP(Src[0],Dst[0],2); END_FOR;',
                     'FOR SpeedCommand:=0 TO Dst[2] DO COP(Src[0],Dst[0],Length); END_FOR;',
                     'FOR SpeedCommand:=0 TO Dst[1] DO COP(Src[0],Dst[Index],1); END_FOR;'):
            self.assertTrue(self.engine([text],dest_type='DINT',st=True).blockers)
        e=self.checked(['FOR SpeedCommand:=0 TO Dst[2] DO COP(Src[0],Dst[0],1); END_FOR;'],dest_type='DINT',st=True);e.step()

    def test_st_for_guard_includes_partially_modified_destination_element(self):
        e=self.engine(['FOR SpeedCommand:=0 TO Dst[1] DO COP(Src[0],Dst[0],20); END_FOR;'],source_type='SINT',source=[1,2,3,4,5],source_dims=(5,),dest_type='DINT',st=True)
        self.assertTrue(any('bounds/step' in b for b in e.blockers))

    def test_late_fault_restores_tags_time_and_scheduler_after_raw_copy(self):
        e=self.checked(['COP(Src[0],Dst[0],3);','DIV(1,SpeedSetpoint,SpeedCommand);']);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.time_ms,e.scan_count,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.time_ms,e.scan_count,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Dst'),[1,2,-2.5])

    def test_event_reads_copied_values_and_fault_rolls_back_both_tasks(self):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='CopyEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');logic(routine,['CPS(Dst[0],Src[0],3); SpeedCommand:=1/SpeedSetpoint;'])
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='CopyEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='CopyEvent')
        e=self.checked(['COP(Src[0],Dst[0],3); EVENT(CopyEventTask);'],mutate=event,st=True);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.time_ms,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('Dst'),[1,2,-2.5])

    def test_detached_routine_replacement_does_not_execute_or_lose_copied_values(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();e.step();before=copy.deepcopy(e.memory.values)
        neutral=['CPS(Src[0],Dst[0],3);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf-8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual(e.memory.values,before);self.assertEqual(candidate.memory.values,before)
        candidate.memory.write('Src[0]',1077936128);candidate.step();self.assertEqual(candidate.memory.read('Dst'),[3,2,-2.5])


if __name__=='__main__':unittest.main()
