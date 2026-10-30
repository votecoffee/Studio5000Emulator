"""Declared aggregate FIFO/LIFO copies retain fields, bounds and rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/RecordLab.L5X'


class RecordQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,logic=None,mutate=None):
        root=E.parse(SAMPLE).getroot()
        if logic is not None:
            content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent');content.clear()
            for i,text in enumerate(logic):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'records.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def pulse(self,e,gate):
        e.memory.write(gate,False);e.step();e.memory.write(gate,True);e.step()

    def part(self,e,id,name=None):
        e.memory.write('IncomingPart.Id',id);e.memory.write('IncomingPart.Lot',9007199254740993+id)
        e.memory.write('IncomingPart.Accepted',id%2==1);e.memory.write_string('IncomingPart.Name',name or 'PART-'+str(id))
        e.memory.write('IncomingPart.Readings[0]',id+.25);e.memory.write('IncomingPart.Readings[1]',-id-.5)
        return copy.deepcopy(e.memory.read('IncomingPart'))

    def test_record_lab_is_registered_and_has_explicit_types(self):
        from logixlab.server import SAMPLES
        self.assertIn('RecordLab',SAMPLES);e=self.checked();self.assertEqual(e.project.data_only_types,set())
        e.step();self.assertEqual(e.memory.read('PartControl.POS'),0);self.assertEqual(e.memory.read('PartQueue[3].Id'),999)

    def test_fifo_returns_whole_records_in_insertion_order(self):
        e=self.checked();values=[]
        for id in (11,22,33):values.append(self.part(e,id));self.pulse(e,'LoadPart')
        self.assertEqual(e.memory.read('PartControl.POS'),3);self.assertTrue(e.memory.read('PartControl.DN'))
        for expected in values:
            self.pulse(e,'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart'),expected)
        self.assertEqual(e.memory.read('PartControl.POS'),0);self.assertTrue(e.memory.read('PartControl.EM'))
        self.assertEqual(e.memory.read('PartQueue[3].Id'),999)

    def test_lifo_returns_whole_records_in_reverse_order(self):
        e=self.checked();values=[]
        for id in (11,22,33):values.append(self.part(e,id));self.pulse(e,'PushPart')
        for expected in reversed(values):
            self.pulse(e,'PopPart');self.assertEqual(e.memory.read('PoppedPart'),expected)
        self.assertEqual(e.memory.read('StackControl.POS'),0);self.assertEqual(e.memory.read('PartStack[3].Id'),888)

    def test_loaded_record_is_detached_from_later_source_edits(self):
        e=self.checked();expected=self.part(e,11);self.pulse(e,'LoadPart');self.part(e,22)
        self.assertEqual(e.memory.read('PartQueue[0]'),expected)
        e.memory.write_string('IncomingPart.Name','CHANGED');self.assertEqual(e.memory.string('PartQueue[0].Name'),'PART-11')

    def test_unloaded_record_is_detached_from_shifted_storage(self):
        e=self.checked();expected=self.part(e,11);self.pulse(e,'LoadPart');self.part(e,22);self.pulse(e,'LoadPart')
        self.pulse(e,'UnloadPart');e.memory.write('PartQueue[0].Id',777);e.memory.write('PartQueue[0].Readings[0]',999)
        self.assertEqual(e.memory.read('OutgoingPart'),expected)

    def test_fifo_shifts_entire_configured_region_and_clears_last_record(self):
        e=self.checked();e.step();e.memory.write('PartQueue[0].Id',11);e.memory.write('PartQueue[1].Id',22);e.memory.write('PartQueue[2].Id',33)
        e.memory.write('PartControl.POS',1);self.pulse(e,'UnloadPart')
        self.assertEqual([e.memory.read(f'PartQueue[{i}].Id') for i in range(4)],[22,33,0,999])
        self.assertEqual(e.memory.read('PartQueue[2]'),e.project.default('PartRecord'))

    def test_lifo_zeroes_only_popped_record(self):
        e=self.checked();self.part(e,11);self.pulse(e,'PushPart');self.part(e,22);self.pulse(e,'PushPart')
        first=copy.deepcopy(e.memory.read('PartStack[0]'));self.pulse(e,'PopPart')
        self.assertEqual(e.memory.read('PartStack[0]'),first);self.assertEqual(e.memory.read('PartStack[1]'),e.project.default('PartRecord'))
        self.assertEqual(e.memory.read('PoppedPart.Id'),22)

    def test_empty_unloads_establish_typed_zero_records(self):
        e=self.checked();e.memory.write('OutgoingPart.Id',123);e.memory.write('PoppedPart.Id',456)
        self.pulse(e,'UnloadPart');self.pulse(e,'PopPart')
        for name in ('OutgoingPart','PoppedPart'):
            self.assertEqual(e.memory.read(name),e.project.default('PartRecord'));self.assertIs(e.memory.read(name+'.Accepted'),False)
            self.assertIs(type(e.memory.read(name+'.Readings[0]')),float)

    def test_custom_string_fifo_preserves_len_and_all_backing_bytes(self):
        e=self.checked();e.memory.write_string('IncomingText','A$');e.memory.write('IncomingText.DATA[15]',-1)
        expected=copy.deepcopy(e.memory.read('IncomingText'));self.pulse(e,'LoadText')
        e.memory.write_string('IncomingText','SECOND');self.pulse(e,'LoadText');self.pulse(e,'UnloadText')
        self.assertEqual(e.memory.read('OutgoingText'),expected);self.assertEqual(e.memory.string('OutgoingText'),'A$')
        self.assertEqual(e.memory.string('TextQueue[0]'),'SECOND');self.assertEqual(e.memory.string('TextQueue[3]'),'KEEP')

    def test_builtin_string_type_and_lifo_are_supported(self):
        def builtin(root):
            for tag in root.findall('./Controller/Tags/Tag'):
                if tag.get('DataType')!='LabelText':continue
                tag.set('DataType','STRING')
                for node in tag.iter():
                    if node.get('DataType')=='LabelText':node.set('DataType','STRING')
                    if node.tag=='ArrayMember' and node.get('Name')=='DATA':
                        node.set('Dimensions','82')
                        for i in range(16,82):E.SubElement(node,'Element',Index=f'[{i}]',Value='0')
        e=self.checked(['XIC(LoadText)LFL(IncomingText,TextQueue[0],TextControl,?,?);','XIC(UnloadText)LFU(TextQueue[0],OutgoingText,TextControl,?,?);'],mutate=builtin)
        self.pulse(e,'LoadText');self.pulse(e,'UnloadText');self.assertEqual(e.memory.string('OutgoingText'),'ALPHA')
        self.assertEqual(e.memory.read('TextQueue[0]'),e.project.default('STRING'))

    def test_empty_string_unload_zeroes_entire_backing_array(self):
        e=self.checked();e.memory.write_string('OutgoingText','OLD');e.memory.write('OutgoingText.DATA[15]',99)
        self.pulse(e,'UnloadText');self.assertEqual(e.memory.read('OutgoingText'),{'LEN':0,'DATA':[0]*16})

    def test_unknown_record_members_and_backing_bytes_remain_unknown(self):
        e=self.checked();e.memory.values['incomingpart']['Lot']=None;e.memory.values['incomingpart']['Name']['DATA'][15]=None
        expected=copy.deepcopy(e.memory.read('IncomingPart'));self.pulse(e,'LoadPart');self.pulse(e,'UnloadPart')
        self.assertEqual(e.memory.read('OutgoingPart'),expected)
        with self.assertRaises(ModelError):e.memory.read('OutgoingPart.Lot')
        self.assertEqual(e.memory.string('OutgoingPart.Name'),'PART-A')

    def test_copy_does_not_interpret_unknown_active_string_bytes(self):
        e=self.checked();e.memory.values['incomingtext']['DATA'][0]=None
        self.pulse(e,'LoadText');self.pulse(e,'UnloadText');self.assertIsNone(e.memory.read('OutgoingText')['DATA'][0])
        with self.assertRaises(ModelError):e.memory.string('OutgoingText')

    def test_string_record_copy_does_not_repair_an_invalid_len(self):
        e=self.checked();e.memory.write('IncomingText.LEN',99);self.pulse(e,'LoadText');self.pulse(e,'UnloadText')
        self.assertEqual(e.memory.read('OutgoingText.LEN'),99)
        with self.assertRaises(ModelError):e.memory.string('OutgoingText')

    def test_unknown_whole_record_faults_and_rolls_back(self):
        e=self.checked();e.step();e.memory.values['incomingpart']=None;e.memory.write('LoadPart',True)
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)

    def test_full_load_and_held_edges_do_not_overwrite_data(self):
        e=self.checked()
        for id in (1,2,3):self.part(e,id);self.pulse(e,'LoadPart')
        before=copy.deepcopy(e.memory.read('PartQueue'));self.part(e,4);e.step();self.pulse(e,'LoadPart')
        self.assertEqual(e.memory.read('PartQueue'),before);self.assertEqual(e.memory.read('PartControl.POS'),3)

    def test_prescan_prevents_initial_transfer_until_false_rearms(self):
        def enabled(root):root.find('./Controller/Tags/Tag[@Name="LoadPart"]/Data/DataValue').set('Value','1')
        e=self.checked(mutate=enabled);e.step();self.assertEqual(e.memory.read('PartControl.POS'),0)
        self.pulse(e,'LoadPart');self.assertEqual(e.memory.read('PartControl.POS'),1)

    def test_res_retains_queued_records_and_clears_only_control_progress(self):
        e=self.checked();self.pulse(e,'LoadPart');before=copy.deepcopy(e.memory.read('PartQueue'))
        from logixlab.control_operations import reset
        reset(e.memory,'PartControl','MainProgram')
        self.assertEqual(e.memory.read('PartControl.POS'),0);self.assertEqual(e.memory.read('PartQueue'),before)

    def test_load_can_snapshot_a_source_element_in_its_own_queue(self):
        e=self.checked(['XIC(LoadPart)FFL(PartQueue[0],PartQueue[0],PartControl,?,?);'])
        e.memory.write('PartQueue[0].Id',71);e.memory.write('PartControl.POS',1);self.pulse(e,'LoadPart')
        self.assertEqual(e.memory.read('PartQueue[1].Id'),71);e.memory.write('PartQueue[0].Id',72)
        self.assertEqual(e.memory.read('PartQueue[1].Id'),71)

    def test_scalar_record_aliases_are_supported(self):
        def alias(root):
            tags=root.find('./Controller/Tags')
            for name,target in (('SourceAlias','IncomingPart'),('DestAlias','OutgoingPart')):E.SubElement(tags,'Tag',Name=name,TagType='Alias',DataType='PartRecord',AliasFor=target)
        e=self.checked(['XIC(LoadPart)FFL(SourceAlias,PartQueue[0],PartControl,?,?);','XIC(UnloadPart)FFU(PartQueue[0],DestAlias,PartControl,?,?);'],mutate=alias)
        self.pulse(e,'LoadPart');self.pulse(e,'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart'),e.memory.read('IncomingPart'))

    def test_program_local_record_source_uses_its_scope(self):
        def local(root):
            source=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="IncomingPart"]'));source.set('Name','LocalPart')
            root.find('./Controller/Programs/Program/Tags').append(source)
        e=self.checked(['XIC(LoadPart)FFL(LocalPart,PartQueue[0],PartControl,?,?);'],mutate=local)
        self.pulse(e,'LoadPart');self.assertEqual(e.memory.read('PartQueue[0]'),e.memory.read('LocalPart','MainProgram'))

    def test_selected_start_offset_respects_region_and_guard(self):
        e=self.checked(['XIC(LoadPart)FFL(IncomingPart,PartQueue[1],PartControl,?,?);'])
        e.memory.write('PartControl.LEN',2);self.pulse(e,'LoadPart');self.part(e,102);self.pulse(e,'LoadPart')
        self.assertEqual([e.memory.read(f'PartQueue[{i}].Id') for i in range(4)],[0,101,102,999])

    def test_bounds_and_late_faults_restore_complete_records_control_and_schedule(self):
        for failure in ('bounds','later'):
            e=self.checked();e.step();e.memory.write('LoadPart',True)
            e.memory.write('PartControl.LEN',5) if failure=='bounds' else e.memory.write('FaultDivisor',0)
            before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule);self.assertEqual((e.scan_count,e.time_ms),(1,10))
            e.memory.write('PartControl.LEN',3);e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('PartQueue[0].Id'),101)

    def test_false_and_full_rungs_do_not_read_unknown_source(self):
        e=self.checked();e.step();e.memory.values['incomingpart']=None;e.step()
        e.memory.write('PartControl.POS',3);e.memory.write('LoadPart',True);e.step();self.assertEqual(e.memory.read('PartControl.POS'),3)

    def test_unload_establishes_an_unknown_whole_destination(self):
        e=self.checked();self.pulse(e,'LoadPart');e.memory.values['outgoingpart']=None;self.pulse(e,'UnloadPart')
        self.assertEqual(e.memory.read('OutgoingPart'),e.memory.read('IncomingPart'))
        self.assertTrue(any(row['tag']=='OutgoingPart.Id' and row['before'] is None and row['after']==101 for row in e.changes))

    def test_declared_string_and_record_type_mismatches_are_blocked(self):
        for logic in (['FFL(IncomingPart,TextQueue[0],TextControl,?,?);'],['FFU(PartQueue[0],OutgoingText,PartControl,?,?);'],
                      ['FFL(IncomingText,PartQueue[0],PartControl,?,?);'],["FFL('ABC',TextQueue[0],TextControl,?,?);"]):
            self.assertTrue(self.engine(logic).blockers,logic)
        def other(root):
            dtype=copy.deepcopy(root.find('./Controller/DataTypes/DataType[@Name="LabelText"]'));dtype.set('Name','OtherText');root.find('./Controller/DataTypes').append(dtype)
            root.find('./Controller/Tags/Tag[@Name="IncomingText"]').set('DataType','OtherText')
        self.assertTrue(self.engine(mutate=other).blockers)

    def test_unload_destination_cannot_share_queue_base_tag(self):
        self.assertTrue(self.engine(['FFU(PartQueue[0],PartQueue[3],PartControl,?,?);']).blockers)

    def test_alias_and_dynamic_array_starts_remain_blocked(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='QueueAlias',TagType='Alias',DataType='PartRecord',AliasFor='PartQueue[0]')
        self.assertTrue(self.engine(['FFL(IncomingPart,QueueAlias,PartControl,?,?);'],alias).blockers)
        self.assertTrue(self.engine(['FFL(IncomingPart,PartQueue[GuardResult],PartControl,?,?);']).blockers)

    def test_wrong_firmware_or_controller_profile_is_blocked(self):
        for field,value in (('MajorRev','34'),('ProcessorType','1756-L75'),('ProcessorType','5069-L340ERM')):
            self.assertTrue(self.engine(mutate=lambda root:root.find('Controller').set(field,value)).blockers)

    def test_st_fifo_calls_stay_blocked(self):
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='FFL(IncomingPart,PartQueue[0],PartControl,?,?);'
        self.assertTrue(self.engine(mutate=st).blockers)

    def test_report_describes_typed_payloads_without_native_layout_claim(self):
        row=self.checked().report()['control_operations'];self.assertIn('UDT',row['fifo']);self.assertIn('unknown',row['aggregate_values'])
        self.assertFalse(row['native_control_layout']);self.assertFalse(row['native_fault_classification'])

    def holder(self,root):
        members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='QueueHolder',Class='User'),'Members')
        for name,dtype,dim in (('Queue','PartRecord','4'),('State','CONTROL','0')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension=dim)
        obj=E.SubElement(E.SubElement(E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Holder',TagType='Base',DataType='QueueHolder'),'Data',Format='Decorated'),'Structure',DataType='QueueHolder')
        for tag,kind,name in (('PartQueue','ArrayMember','Queue'),('PartControl','StructureMember','State')):
            node=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="'+tag+'"]/Data')[0]);node.tag=kind;node.set('Name',name);obj.append(node)

    def test_udt_array_member_with_separate_control_respects_its_boundary(self):
        e=self.checked(['XIC(LoadPart)FFL(IncomingPart,Holder.Queue[0],PartControl,?,?);'],self.holder)
        self.pulse(e,'LoadPart');self.assertEqual(e.memory.read('Holder.Queue[0].Id'),101);self.assertEqual(e.memory.read('Holder.Queue[3].Id'),999)
        e.memory.write('LoadPart',False);e.step();e.memory.write('PartControl.LEN',5);e.memory.write('LoadPart',True);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_aggregate_array_control_cannot_share_base_tag(self):
        e=self.engine(['FFL(IncomingPart,Holder.Queue[0],Holder.State,?,?);'],self.holder)
        self.assertTrue(e.blockers);self.assertIn('cannot share a base tag',str(e.blockers))

    def test_control_storage_cannot_be_nested_inside_payload(self):
        for owner,logic in (('IncomingPart','FFL(IncomingPart,PartQueue[0],IncomingPart.State,?,?);'),
                            ('OutgoingPart','FFU(PartQueue[0],OutgoingPart,OutgoingPart.State,?,?);')):
            def overlap(root):
                E.SubElement(root.find('./Controller/DataTypes/DataType[@Name="PartRecord"]/Members'),'Member',Name='State',DataType='CONTROL',Dimension='0')
                node=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="PartControl"]/Data/Structure'));node.tag='StructureMember';node.set('Name','State')
                root.find('./Controller/Tags/Tag[@Name="'+owner+'"]/Data/Structure').append(node)
            e=self.engine([logic],overlap);self.assertTrue(e.blockers)

    def test_decorated_only_records_remain_blocked(self):
        def opaque(root):
            types=root.find('./Controller/DataTypes');types.remove(types.find('DataType[@Name="PartRecord"]'))
        e=self.engine(mutate=opaque);self.assertTrue(e.blockers)

    def test_operational_record_members_require_separate_qualification(self):
        def timer(root):E.SubElement(root.find('./Controller/DataTypes/DataType[@Name="PartRecord"]/Members'),'Member',Name='TimerState',DataType='TIMER',Dimension='0')
        self.assertTrue(self.engine(mutate=timer).blockers)

    def test_nested_explicit_udt_with_full_unsigned_width_is_copied_and_cleared(self):
        def nested(root):
            types=root.find('./Controller/DataTypes');members=E.SubElement(E.SubElement(types,'DataType',Name='PartDetails',Class='User'),'Members')
            for name,dtype in (('Sequence','ULINT'),('Code','USINT')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
            E.SubElement(types.find('DataType[@Name="PartRecord"]/Members'),'Member',Name='Details',DataType='PartDetails',Dimension='0')
            obj=E.SubElement(root.find('./Controller/Tags/Tag[@Name="IncomingPart"]/Data/Structure'),'StructureMember',Name='Details',DataType='PartDetails')
            for name,dtype,value in (('Sequence','ULINT',18446744073709551615),('Code','USINT',255)):
                E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
        e=self.checked(mutate=nested);self.pulse(e,'LoadPart');self.pulse(e,'UnloadPart')
        self.assertEqual(e.memory.read('OutgoingPart.Details'),{'Sequence':18446744073709551615,'Code':255})
        self.assertEqual(e.memory.read('PartQueue[2].Details'),{'Sequence':0,'Code':0})

    def test_readonly_queue_or_output_is_blocked_without_transfer(self):
        for name in ('PartQueue','OutgoingPart'):
            self.assertTrue(self.engine(mutate=lambda root:root.find('./Controller/Tags/Tag[@Name="'+name+'"]').set('Constant','true')).blockers)


if __name__=='__main__':unittest.main()
