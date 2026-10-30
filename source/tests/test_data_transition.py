"""DTR comparisons, prescan/false writes, bindings and transactional faults."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
import test_bit_transfer as fixtures

SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def rungs(content, logic):
    for child in list(content):content.remove(child)
    for index, text in enumerate(logic):
        E.SubElement(E.SubElement(content, 'Rung', Number=str(index), Type='N'), 'Text').text = text


def scalar(parent, name, dtype, value):
    tag = E.SubElement(parent, 'Tag', Name=name, DataType=dtype, TagType='Base')
    E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=dtype, Value=str(value))
    return tag


class DataTransitionTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    engine = fixtures.BitTransferTests.engine
    checked = fixtures.BitTransferTests.checked

    def test_prescan_replaces_saved_reference_with_masked_source(self):
        e = self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'], values=(0x1234, 255, 99))
        self.assertEqual(e.memory.read('Dest'), 0x34)
        self.assertEqual(e.memory.read('Source'), 0x1234)
        self.assertFalse(e.memory.read('RunLatch'));e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_change_pulses_once_for_rising_and_falling_data(self):
        e = self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'])
        for source, changed in ((1,True),(1,False),(3,True),(2,True),(0,True),(0,False)):
            e.memory.write('Source', source);e.step()
            self.assertIs(e.memory.read('RunLatch'), changed);self.assertEqual(e.memory.read('Dest'), source)

    def test_unselected_source_bits_do_not_trigger(self):
        e = self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'], values=(0x12, 15, 0))
        e.memory.write('Source', 0x32);e.step();self.assertFalse(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Dest'), 2);self.assertEqual(e.memory.read('Source'), 0x32)

    def test_comparison_uses_complete_reference_without_masking_it(self):
        e = self.checked(['DTR(Source,15,Dest)OTE(RunLatch);'], values=(2,-1,0))
        e.memory.write('Dest', 0x12);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Dest'), 2);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_mask_changes_are_compared_with_prior_reference(self):
        e = self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'], values=(255,15,0))
        e.memory.write('Mask', 255);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Dest'), 255);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_false_rung_still_updates_reference_and_clears_output(self):
        e = self.checked(['AFI()DTR(Source,Mask,Dest)OTE(RunLatch);'])
        e.memory.write('Source', 37);e.memory.write('RunLatch', True);e.step()
        self.assertEqual(e.memory.read('Dest'), 37);self.assertFalse(e.memory.read('RunLatch'))
        event = next(x for x in e.trace[0]['events'] if x['instruction']=='DTR')
        self.assertIs(event['in'], False);self.assertIs(event['out'], False)

    def test_reenable_does_not_pulse_for_changes_already_seen_on_false_rung(self):
        e = self.checked(['XIC(StartPB)DTR(Source,Mask,Dest)OTE(RunLatch);'])
        e.memory.write('Source', 7);e.step();self.assertEqual(e.memory.read('Dest'), 7)
        e.memory.write('StartPB', True);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('Source', 8);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_zero_mask_clears_reference_and_detects_manual_reference_change(self):
        e = self.checked(['DTR(Source,0,Dest)OTE(RunLatch);'], values=(123,-1,77))
        self.assertEqual(e.memory.read('Dest'), 0);e.memory.write('Dest', 1);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Dest'), 0)
        e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_sign_bit_and_all_bits_are_stored_as_signed_dint(self):
        for source, mask, result in ((-1,-1,-1),(-1,-2147483648,-2147483648),(-2147483648,-1,-2147483648),(-1,2147483647,2147483647)):
            e = self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'], values=(0,mask,0))
            e.memory.write('Source', source);e.step();self.assertTrue(e.memory.read('RunLatch'))
            self.assertEqual(e.memory.read('Dest'), result)

    def test_signed_and_radix_source_and_mask_immediates(self):
        for value in ('-1','16#FFFF_FFFF','8#37777777777','2#'+'1'*32):
            e = self.checked([f'DTR({value},{value},Dest)OTE(RunLatch);'])
            self.assertEqual(e.memory.read('Dest'), -1);e.memory.write('Dest', 0);e.step()
            self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Dest'), -1)

    def test_invalid_immediates_and_operand_counts_are_rejected(self):
        for value in ('TRUE','1.0','2147483648','-2147483649','16#100000000'):
            for logic in (f'DTR({value},Mask,Dest);',f'DTR(Source,{value},Dest);'):
                self.assertTrue(self.engine([logic]).blockers, logic)
        for logic in ('DTR(Source,Dest);','DTR(Source,Mask,Dest,Source);','DTR(Source,Mask,1);'):
            self.assertTrue(self.engine([logic]).blockers)

    def test_non_dint_types_and_bit_references_are_rejected(self):
        for dtype in ('BOOL','SINT','INT','REAL','LINT','USINT','UINT','UDINT','ULINT'):
            for index in range(3):
                types=['DINT']*3;types[index]=dtype
                self.assertTrue(self.engine(['DTR(Source,Mask,Dest);'],types=types).blockers,(dtype,index))
        for logic in ('DTR(Source.0,Mask,Dest);','DTR(Source,Mask.0,Dest);','DTR(Source,Mask,Dest.0);'):
            self.assertTrue(self.engine([logic]).blockers)

    def test_aggregate_operand_is_not_a_scalar(self):
        for operand in ('Source','Mask','Dest'):
            def mutate(root):
                t=root.find(f'./Controller/Tags/Tag[@Name="{operand}"]');t.set('Dimensions','2')
                d=t.find('Data');d.clear();a=E.SubElement(d,'Array',DataType='DINT',Dimensions='2')
                for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]',Value='0')
                d.set('Format','Decorated')
            self.assertTrue(self.engine(['DTR(Source,Mask,Dest);'],mutate=mutate).blockers)

    def test_constant_reference_is_rejected_even_on_false_rung(self):
        def mutate(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()DTR(Source,Mask,Dest);'],mutate=mutate).blockers)

    def test_constant_source_and_mask_are_allowed(self):
        def mutate(root):
            for name in ('Source','Mask'):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
        e=self.checked(['DTR(Source,Mask,Dest);'],values=(5,3,0),mutate=mutate)
        self.assertEqual(e.memory.read('Dest'),1)

    def test_overlapping_source_and_reference_use_prewrite_values(self):
        e=self.checked(['DTR(Source,255,Source)OTE(RunLatch);'],values=(0x1234,-1,0))
        self.assertEqual(e.memory.read('Source'),0x34)
        e.memory.write('Source',0x1234);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Source'),0x34);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_overlapping_mask_and_reference_use_prewrite_values(self):
        e=self.checked(['DTR(Source,Dest,Dest)OTE(RunLatch);'],values=(0xf0,-1,255))
        self.assertEqual(e.memory.read('Dest'),0xf0)
        e.memory.write('Dest',0xaa);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Dest'),0xa0)

    def array_tags(self,root):
        tags=root.find('./Controller/Tags');scalar(tags,'Index','DINT',0)
        tag=E.SubElement(tags,'Tag',Name='Words',DataType='DINT',Dimensions='3',TagType='Base')
        a=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
        for i,value in enumerate((77,88,999)):E.SubElement(a,'Element',Index=f'[{i}]',Value=str(value))
        E.SubElement(tags,'Tag',Name='ReferenceAlias',TagType='Alias',AliasFor='Words[0]')

    def test_array_dynamic_reference_and_alias_preserve_other_elements(self):
        e=self.checked(['DTR(Source,Mask,Words[Index])OTE(RunLatch);'],mutate=self.array_tags)
        self.assertEqual(e.memory.read('ReferenceAlias'),0)
        e.memory.write('Index',1);e.memory.write('Source',4);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Words'),[0,4,999])
        e.memory.write('Index',0);e.step();self.assertEqual(e.memory.read('ReferenceAlias'),4)
        self.assertEqual(e.memory.read('Words[2]'),999)

    def test_dynamic_source_and_mask_are_reselected_each_scan(self):
        e=self.checked(['DTR(Words[Index],Mask,Dest)OTE(RunLatch);'],mutate=self.array_tags)
        self.assertEqual(e.memory.read('Dest'),77)
        e.memory.write('Index',1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Dest'),88);self.assertEqual(e.memory.read('Words'),[77,88,999])

    def test_alias_reference_is_writable(self):
        e=self.checked(['DTR(Source,Mask,ReferenceAlias)OTE(RunLatch);'],mutate=self.array_tags)
        e.memory.write('Source',12);e.step();self.assertEqual(e.memory.read('Words'),[12,88,999])

    def test_program_local_reference_and_explicit_scope(self):
        def mutate(root):scalar(root.find('./Controller/Programs/Program/Tags'),'LocalReference','DINT',99)
        e=self.checked(['DTR(Source,Mask,LocalReference)OTE(RunLatch);'],mutate=mutate)
        self.assertEqual(e.memory.read('Program:MainProgram.LocalReference'),0)
        e.memory.write('Source',5);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Program:MainProgram.LocalReference'),5)

    def test_dint_members_of_an_explicit_udt_are_scalar_operands(self):
        def mutate(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name in ('Source','Mask','Reference'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='PacketData',DataType='Packet',TagType='Base')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Packet')
            for name,value in (('Source',19),('Mask',15),('Reference',99)):
                E.SubElement(data,'DataValueMember',Name=name,DataType='DINT',Value=str(value))
        e=self.checked(['DTR(PacketData.Source,PacketData.Mask,PacketData.Reference)OTE(RunLatch);'],mutate=mutate)
        self.assertEqual(e.memory.read('PacketData.Reference'),3)
        e.memory.write('PacketData.Source',20);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('PacketData'),{'Source':20,'Mask':15,'Reference':4})

    def test_runtime_indirect_bounds_failure_rolls_back_even_on_false_rung(self):
        e=self.checked(['AFI()DTR(Words[Index],Mask,Dest);'],mutate=self.array_tags)
        e.memory.write('Index',3);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scan_count,0)

    def test_parallel_branches_keep_separate_reference_words(self):
        def mutate(root):scalar(root.find('./Controller/Tags'),'SecondReference','DINT',0)
        e=self.checked(['[DTR(Source,Mask,Dest),DTR(Source,Mask,SecondReference)]OTE(RunLatch);'],mutate=mutate)
        e.memory.write('Source',6);e.step();events=[x for x in e.trace[0]['events'] if x['instruction']=='DTR']
        self.assertEqual([x['out'] for x in events],[True,True]);self.assertTrue(e.memory.read('RunLatch'))
        e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_repeated_use_of_one_reference_observes_sequential_writes(self):
        e=self.checked(['[DTR(Source,Mask,Dest),DTR(Source,Mask,Dest)]OTE(RunLatch);'])
        e.memory.write('Source',6);e.step();events=[x for x in e.trace[0]['events'] if x['instruction']=='DTR']
        self.assertEqual([x['out'] for x in events],[True,False])

    def test_shared_reference_with_different_sources_is_not_hidden_one_shot(self):
        e=self.checked(['DTR(Source,-1,Dest)OTE(RunLatch);','DTR(Mask,-1,Dest)OTE(MotorRunning);'],values=(10,20,0))
        for _ in range(2):
            e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertTrue(e.memory.read('MotorRunning'))
            self.assertEqual(e.memory.read('Dest'),20)

    def test_required_unknown_source_or_mask_faults_even_on_false_or_zero_mask(self):
        for prefix in ('','AFI()'):
            for unknown in ('source','mask'):
                e=self.checked([prefix+'DTR(Source,Mask,Dest);']);e.memory.values[unknown]=None
                before=copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
                self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))
        e=self.checked(['AFI()DTR(Source,0,Dest);']);e.memory.values['source']=None
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()

    def test_unknown_reference_faults_when_comparison_requires_it(self):
        e=self.checked(['DTR(Source,Mask,Dest);']);e.memory.values['dest']=None
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertIsNone(e.memory.values['dest'])

    def test_false_scan_establishes_unknown_reference(self):
        e=self.checked(['AFI()DTR(Source,Mask,Dest);']);e.memory.values['dest']=None
        e.memory.write('Source',42);e.step();self.assertEqual(e.memory.read('Dest'),42)

    def test_deferred_preview_preserves_saved_values_until_run_prescan(self):
        initial=self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'],values=(25,15,99))
        e=Engine(initial.project,defer_prescan=True);self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('Dest'),99);self.assertEqual(e.prescan_count,0)
        e.enter_run();self.assertEqual(e.memory.read('Dest'),9);self.assertEqual(e.prescan_count,1)
        e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_each_run_entry_reprimes_without_advancing_scan_or_time(self):
        e=self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);']);e.step();e.memory.write('Source',123)
        before=(e.scan_count,e.time_ms);e.enter_run();self.assertEqual((e.scan_count,e.time_ms),before)
        self.assertEqual(e.memory.read('Dest'),123);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_run_prescan_can_establish_unknown_reference(self):
        e=self.checked(['DTR(Source,Mask,Dest);'],values=(13,7,0));e.memory.values['dest']=None
        e.enter_run();self.assertEqual(e.memory.read('Dest'),5)

    def test_routine_harness_uses_selected_routines_prescan_and_execution(self):
        source=self.checked(['DTR(Source,Mask,Dest)OTE(RunLatch);'],values=(5,3,99))
        e=Engine(source.project,'routine','MainProgram/MainRoutine');self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('Dest'),1);e.memory.write('Source',6);e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Dest'),2)

    def test_uncalled_routine_is_lexically_prescanned_but_not_normally_executed(self):
        def mutate(root):
            routines=root.find('./Controller/Programs/Program/Routines')
            r=E.SubElement(routines,'Routine',Name='Unused',Type='RLL')
            rungs(E.SubElement(r,'RLLContent'),['DTR(Source,Mask,Dest);'])
        e=self.checked(['NOP();'],values=(5,3,99),mutate=mutate)
        self.assertEqual(e.memory.read('Dest'),1);e.memory.write('Source',2);e.step()
        self.assertEqual(e.memory.read('Dest'),1)

    def test_late_prescan_failure_rolls_back_prior_reference_writes(self):
        e=self.checked(['DTR(Source,Mask,Dest);','OTE(RunLatch);'])
        e.memory.write('Source',9);e.memory.write('Dest',37);before=copy.deepcopy(e.memory.values)
        count=e.prescan_count;e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.prescan_count,count)

    def test_unknown_prescan_source_rolls_back_and_preserves_old_reference(self):
        e=self.checked(['DTR(Source,Mask,Dest);']);e.memory.values['source']=None;e.memory.write('Dest',37)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Prescan.*Unknown'):e.enter_run()
        self.assertEqual(e.memory.values,before)

    def test_late_scan_fault_rolls_back_reference_and_recovers_pulse_once(self):
        e=self.checked(['DTR(Source,-1,Dest)OTE(RunLatch);','DIV(1,Mask,DisplayedPartCount);'],values=(0,1,0))
        e.memory.write('Source',12);e.memory.write('Mask',0);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'divide by zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))
        e.memory.write('Mask',1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Dest'),12);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_disabled_mcr_false_scans_dtr_reference_and_reenable_has_no_stale_pulse(self):
        e=self.checked(['XIC(StartPB)MCR();','DTR(Source,Mask,Dest)OTE(RunLatch);','MCR();'])
        e.memory.write('Source',11);e.step();self.assertEqual(e.memory.read('Dest'),11)
        self.assertFalse(e.memory.read('RunLatch'));self.assertTrue(e.trace[1]['mcr_forced_false'])
        e.memory.write('StartPB',True);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('Source',12);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_dtr_side_effect_is_rejected_in_mcr_opening_conditions(self):
        self.assertTrue(self.engine(['DTR(Source,Mask,Dest)MCR();','NOP();','MCR();']).blockers)

    def aoi_engine(self, false_routine=False):
        root=E.parse(SAMPLES/'AOILab.L5X').getroot()
        d=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="LabAccumulator"]')
        d.set('ExecutePrescan','false')
        rungs(d.find('./Routines/Routine[@Name="Logic"]/RLLContent'),['DTR(Step,-1,Shared)OTE(EnableOut);','MOV(Shared,Total);'])
        if false_routine:rungs(d.find('./Routines/Routine[@Name="EnableInFalse"]/RLLContent'),['AFI()DTR(Step,-1,Shared);','MOV(Shared,Total);'])
        path=Path(self.tmp.name)/'aoi.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        e=Engine(Project(path));self.assertEqual(e.blockers,[]);return e

    def test_aoi_prescan_and_inout_references_are_independent_per_instance(self):
        e=self.aoi_engine();self.assertEqual(e.memory.read('SharedA'),2);self.assertEqual(e.memory.read('SharedB'),3)
        e.step();self.assertFalse(e.memory.read('AccumulatorA.EnableOut'));self.assertFalse(e.memory.read('AccumulatorB.EnableOut'))
        e.memory.write('StepA',7);e.step();self.assertTrue(e.memory.read('AccumulatorA.EnableOut'))
        self.assertFalse(e.memory.read('AccumulatorB.EnableOut'));self.assertEqual(e.memory.read('SharedA'),7)
        self.assertEqual(e.memory.read('SharedB'),3)

    def test_aoi_enable_in_false_routine_can_update_dtr_reference(self):
        e=self.aoi_engine(True);e.memory.write('EnableA',False);e.memory.write('StepA',8);e.step()
        self.assertEqual(e.memory.read('SharedA'),8);self.assertFalse(e.memory.read('AccumulatorA.EnableOut'))
        e.memory.write('EnableA',True);e.step();self.assertFalse(e.memory.read('AccumulatorA.EnableOut'))

    def test_other_controller_profiles_and_st_calls_are_blocked(self):
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def mutate(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(['DTR(Source,Mask,Dest);'],mutate=mutate).blockers)
        def st(root):
            r=root.find('./Controller/Programs/Program/Routines/Routine');r.set('Type','ST');r.remove(r.find('RLLContent'))
            E.SubElement(E.SubElement(r,'STContent'),'Line',Number='0').text='DTR(Source,Mask,Dest);'
        self.assertTrue(self.engine([],mutate=st).blockers)

    def test_report_describes_true_false_prescan_and_qualification(self):
        e=self.checked(['DTR(Source,Mask,Dest);']);report=e.report()['data_transition']
        self.assertEqual(report['instructions'],['DTR']);self.assertEqual(report['language'],'RLL')
        self.assertFalse(report['native_runtime_parity']);self.assertIn('false_scan',report);self.assertIn('prescan',report)

    def test_routine_replacement_preview_does_not_prime_active_or_candidate_values(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked(['NOP();'],values=(4,-1,99));e.step()
        logic=['DTR(Source,Mask,Dest)OTE(RunLatch);'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId='1'),'TextIOI').text=logic[0]
        source=decode(container(E.tostring(xml,encoding='utf-8')))
        candidate,_=prepare(e,source,tuple(logic),'MainProgram',0)
        self.assertEqual(e.memory.read('Dest'),99);self.assertEqual(candidate.memory.read('Dest'),99)
        candidate.step();self.assertTrue(candidate.memory.read('RunLatch'));self.assertEqual(candidate.memory.read('Dest'),4)
        self.assertEqual(e.memory.read('Dest'),99)
