"""Logical CONTROL, transitional shifts, bounded FIFO pairs and member access."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.control_operations import FLAGS, default
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def control_data(parent, length, position=0, **flags):
    obj=E.SubElement(parent,'Structure',DataType='CONTROL')
    for name,value in dict(default(),LEN=length,POS=position,**flags).items():
        E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL' if name in FLAGS else 'DINT',Value=str(int(value)))
    return obj


class ControlOperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,rungs,*,length=33,position=0,words=(0,0,7),queue=(0,0,0,999),dtype='DINT',mutate=None):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        tag=E.SubElement(tags,'Tag',Name='Ctl',DataType='CONTROL',TagType='Base')
        control_data(E.SubElement(tag,'Data',Format='Decorated'),length,position)
        for name,kind,values in (('Words','DINT',words),('Queue',dtype,queue)):
            tag=E.SubElement(tags,'Tag',Name=name,DataType=kind,TagType='Base',Dimensions=str(len(values)))
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=kind,Dimensions=str(len(values)))
            for i,value in enumerate(values):E.SubElement(data,'Element',Index=f'[{i}]',Value=str(value))
        for name,kind,value in (('Incoming',dtype,11),('Outgoing',dtype,99),('BitIn','BOOL',1)):
            tag=E.SubElement(tags,'Tag',Name=name,DataType=kind,TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=kind,Value=str(value))
        content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent');content.clear()
        for i,text in enumerate(rungs):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'fixture.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_control_schema_preserves_saved_values_and_member_types(self):
        e=self.checked(['NOP();'],length=47,position=8)
        self.assertEqual(e.memory.read('Ctl'),default()|dict(LEN=47,POS=8))
        self.assertNotIn('CONTROL',e.project.data_only_types)
        for name in FLAGS:self.assertEqual(e.memory.resolve('Ctl.'+name)[2],'BOOL')
        for name in ('LEN','POS'):self.assertEqual(e.memory.resolve('Ctl.'+name)[2],'DINT')

    def test_left_shift_crosses_words_preserves_partial_word_and_next_word(self):
        e=self.checked(['BSL(Words[0],Ctl,BitIn,?);'],words=(-2147483648,0x12345678,7))
        e.step();self.assertEqual(e.memory.read('Words'),[1,0x12345679,7])
        self.assertTrue(e.memory.read('Ctl.EN'));self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertFalse(e.memory.read('Ctl.UL'));self.assertEqual(e.memory.read('Ctl.POS'),33)

    def test_right_shift_crosses_words_preserves_partial_word_and_next_word(self):
        e=self.checked(['BSR(Words[0],Ctl,BitIn,?);'],words=(1,0x12345679,7))
        e.step();self.assertEqual(e.memory.read('Words'),[-2147483648,0x12345679,7])
        self.assertTrue(e.memory.read('Ctl.UL'));self.assertEqual(e.memory.read('Ctl.POS'),33)

    def test_shift_runs_once_per_edge_and_false_resets_status(self):
        e=self.checked(['XIC(StartPB)BSL(Words[0],Ctl,BitIn,?);'],length=8)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Words[0]'),1)
        e.step();self.assertEqual(e.memory.read('Words[0]'),1)
        e.memory.write('StartPB',False);e.step()
        self.assertFalse(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Words[0]'),3)

    def test_shift_prescan_clears_enable_done_error_position_but_retains_data_ul(self):
        def flags(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure')
            for n in ('EN','DN','ER','UL'):obj.find(f'DataValueMember[@Name="{n}"]').set('Value','1')
        e=self.checked(['BSL(Words[0],Ctl,BitIn,?);'],length=8,position=5,words=(123,0,7),mutate=flags)
        self.assertEqual(e.memory.read('Words[0]'),123);self.assertTrue(e.memory.read('Ctl.UL'))
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[False,False,False,0])
        e.step();self.assertEqual(e.memory.read('Words[0]'),247)

    def test_shift_zero_and_negative_length_status_paths(self):
        for instruction in ('BSL','BSR'):
            e=self.checked([f'{instruction}(Words[0],Ctl,BitIn,?);'],length=0,words=(123,0,7))
            e.step();self.assertEqual(e.memory.read('Words[0]'),123)
            self.assertTrue(e.memory.read('Ctl.DN'));self.assertTrue(e.memory.read('Ctl.UL'));self.assertEqual(e.memory.read('Ctl.POS'),0)
            e=self.checked([f'{instruction}(Words[0],Ctl,BitIn,?);'],length=-3)
            e.memory.write('Ctl.POS',7);e.step()
            self.assertTrue(e.memory.read('Ctl.ER'));self.assertFalse(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),7)

    def test_shift_source_bit_from_array_uses_value_before_shift(self):
        e=self.checked(['BSL(Words[0],Ctl,Words[0].31,?);'],length=32,words=(-2147483648,17,7))
        e.step();self.assertEqual(e.memory.read('Words'),[1,17,7]);self.assertTrue(e.memory.read('Ctl.UL'))

    def test_shift_bounds_resource_limit_and_late_fault_roll_back_everything(self):
        for length in (97,131073):
            e=self.checked(['BSL(Words[0],Ctl,BitIn,?);'],length=length);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))
        e=self.checked(['BSL(Words[0],Ctl,BitIn,?);','DIV(1,0,SpeedCommand);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_unknown_length_and_array_words_remain_unknown_on_failed_step(self):
        for name in ('Ctl.LEN','Words[0]'):
            e=self.checked(['BSL(Words[0],Ctl,BitIn,?);'])
            if name=='Ctl.LEN':e.memory.values['ctl']['LEN']=None
            else:e.memory.values['words'][0]=None
            before=copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError,'unknown|Unknown'):e.step()
            self.assertEqual(e.memory.values,before)

    def test_res_control_retains_len_clears_all_flags_and_position(self):
        e=self.checked(['RES(Ctl);'],length=47,position=8)
        e.memory.values['ctl'].update(dict.fromkeys(FLAGS,True));e.step()
        self.assertEqual(e.memory.read('Ctl'),default()|dict(LEN=47))

    def test_false_res_retains_control_and_zero_fill_is_explicitly_bounded(self):
        e=self.checked(['AFI()RES(Ctl);'],length=47,position=8);before=copy.deepcopy(e.memory.read('Ctl'));e.step()
        self.assertEqual(e.memory.read('Ctl'),before)
        e=self.checked(['FLL(0,Ctl,1);'],length=47,position=8);e.step();self.assertEqual(e.memory.read('Ctl'),default())
        e=self.checked(['FLL(0,Ctl,1);']);e.memory.values['ctl']['EN']=None;e.step()
        self.assertIs(e.memory.read('Ctl.EN'),False)

    def paired(self,**kwargs):
        return self.checked(['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);','XIC(PartSensor)FFU(Queue[0],Outgoing,Ctl,?,?);'],length=3,**kwargs)

    @staticmethod
    def pulse(e,tag,value=None):
        e.memory.write(tag,False);e.step()
        if value is not None:e.memory.write('Incoming',value)
        e.memory.write(tag,True);e.step()

    def test_fifo_prescan_prevents_first_scan_load_or_unload(self):
        def enable(root):
            for name in ('StartPB','PartSensor'):root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/DataValue').set('Value','1')
        e=self.paired(mutate=enable);self.assertTrue(e.memory.read('Ctl.EN'));self.assertTrue(e.memory.read('Ctl.EU'))
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertEqual(e.memory.read('Outgoing'),99)
        self.assertEqual(e.memory.read('Queue'),[0,0,0,999])

    def test_fifo_order_edges_full_empty_and_unused_elements(self):
        e=self.paired();e.step()
        for value in (11,22,33):self.pulse(e,'StartPB',value)
        self.assertEqual(e.memory.read('Queue'),[11,22,33,999]);self.assertEqual(e.memory.read('Ctl.POS'),3)
        self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EM'))
        self.pulse(e,'StartPB',44);self.assertEqual(e.memory.read('Queue'),[11,22,33,999])
        e.memory.write('StartPB',False)
        for value in (11,22,33):
            self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),value)
        self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertTrue(e.memory.read('Ctl.EM'));self.assertFalse(e.memory.read('Ctl.DN'))
        self.assertEqual(e.memory.read('Queue'),[0,0,0,999])
        self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),0)

    def test_fifo_held_true_does_not_repeat_and_latches_are_independent(self):
        e=self.paired();e.step();e.memory.write('StartPB',True);e.step()
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('PartSensor',True);e.step();self.assertEqual(e.memory.read('Outgoing'),11)
        self.assertEqual(e.memory.read('Ctl.POS'),0);e.step();self.assertEqual(e.memory.read('Outgoing'),11)
        self.assertTrue(e.memory.read('Ctl.EN'));self.assertTrue(e.memory.read('Ctl.EU'))

    def test_fifo_same_scan_load_unload_obeys_rung_order(self):
        e=self.paired();e.step();e.memory.write('StartPB',True);e.memory.write('PartSensor',True);e.step()
        self.assertEqual(e.memory.read('Outgoing'),11);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_fifo_selected_offset_region_stays_inside_array(self):
        e=self.checked(['XIC(StartPB)FFL(Incoming,Queue[1],Ctl,?,?);','XIC(PartSensor)FFU(Queue[1],Outgoing,Ctl,?,?);'],length=2,queue=(77,0,0,999))
        e.step();self.pulse(e,'StartPB',11);self.pulse(e,'StartPB',22);e.memory.write('StartPB',False)
        self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),11)
        self.assertEqual(e.memory.read('Queue'),[77,22,0,999])

    def test_fifo_numeric_types_keep_matching_declared_values(self):
        for dtype,value in (('SINT',-12),('INT',-1234),('DINT',123456),('REAL',1.25)):
            e=self.paired(dtype=dtype,queue=(0,0,0,0));e.step();self.pulse(e,'StartPB',value)
            e.memory.write('StartPB',False);self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),value)

    def test_fifo_invalid_length_or_negative_pos_sets_empty_and_done_without_io(self):
        for length,position in ((0,0),(-1,0),(3,-1)):
            e=self.checked(['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);'],length=length,position=position)
            e.step();e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.DN'));self.assertTrue(e.memory.read('Ctl.EM'))
            self.assertEqual(e.memory.read('Queue'),[0,0,0,999])

    def test_fifo_pos_beyond_len_and_array_bounds_faults_are_transactional(self):
        for length,position in ((3,4),(5,0)):
            e=self.checked(['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);'],length=length,position=position)
            e.step();e.memory.write('StartPB',True);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before)

    def test_fifo_unload_unknown_data_rolls_back_prior_rungs_and_control(self):
        e=self.checked(['MOV(7,SpeedCommand);','XIC(PartSensor)FFU(Queue[0],Outgoing,Ctl,?,?);'],length=3,position=1)
        e.step();e.memory.values['queue'][1]=None;e.memory.write('PartSensor',True);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_neutral_operands_types_and_source_control_overlap_stay_explicit(self):
        for text in ('BSL(Words[0],Ctl,BitIn,33);','FFL(Incoming,Queue[0],Ctl,3,0);',
                     'BSR(Words[0],Ctl,1,?);','BSL(Words[0],Ctl,Ctl.UL,?);','BSL(Incoming,Ctl,BitIn,?);',
                     'BSL(Queue[Incoming],Ctl,BitIn,?);','FFU(Queue[0],Queue[1],Ctl,?,?);',
                     'BSL(Words[0],SourceA,BitIn,?);','FFL(BitIn,Queue[0],Ctl,?,?);',
                     'BSL(Words[0],Words[0].0,BitIn,?);','BSL(BitIn,Ctl,BitIn,?);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Ctl"]').set('Constant','true')
        self.assertTrue(self.engine(['BSL(Words[0],Ctl,BitIn,?);'],mutate=constant).blockers)

    def test_control_arrays_udt_members_alias_and_member_boundary(self):
        def record(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='ShiftRecord',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='State',DataType='CONTROL',Dimension='0')
            E.SubElement(members,'Member',Name='Bits',DataType='DINT',Dimension='2')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Record',DataType='ShiftRecord',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ShiftRecord')
            state=control_data(obj,33);state.tag='StructureMember';state.set('Name','State')
            array=E.SubElement(obj,'ArrayMember',Name='Bits',DataType='DINT',Dimensions='2')
            for i,value in enumerate((-2147483648,0)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ControlAlias',DataType='CONTROL',TagType='Alias',AliasFor='Record.State')
        e=self.checked(['BSL(Record.Bits[0],ControlAlias,BitIn,?);'],mutate=record);e.step()
        self.assertEqual(e.memory.read('Record.Bits'),[1,1]);self.assertEqual(e.memory.read('Record.State.POS'),33)
        e=self.checked(['BSL(Record.Bits[0],ControlAlias,BitIn,?);'],mutate=record)
        e.memory.write('Record.State.LEN',65)
        with self.assertRaises(ModelError):e.step()

    def test_alias_and_indirect_start_arrays_and_st_calls_remain_blocked(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ArrayAlias',DataType='DINT',TagType='Alias',AliasFor='Words[0]')
        self.assertTrue(self.engine(['BSL(ArrayAlias,Ctl,BitIn,?);'],mutate=alias).blockers)
        def structured(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine')
            routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='FFL(Incoming,Queue[0],Ctl,0,0);'
        self.assertTrue(self.engine([],mutate=structured).blockers)

    def test_control_array_element_retains_other_control_instances(self):
        def controls(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='States',DataType='CONTROL',TagType='Base',Dimensions='2')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='CONTROL',Dimensions='2')
            for i,length in enumerate((17,33)):control_data(E.SubElement(array,'Element',Index=f'[{i}]'),length)
        e=self.checked(['BSL(Words[0],States[1],BitIn,?);'],mutate=controls);e.step()
        self.assertEqual(e.memory.read('States[0]'),default()|dict(LEN=17))
        self.assertEqual(e.memory.read('States[1].POS'),33)

    def test_omitted_control_fields_remain_unknown_until_specific_initialization(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="FD"]'))
        e=self.checked(['NOP();'],mutate=missing)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.memory.read('Ctl.FD')
        e=self.checked(['RES(Ctl);'],mutate=missing);e.step();self.assertIs(e.memory.read('Ctl.FD'),False)

    def test_full_control_wire_layout_withheld_but_atomic_members_readable(self):
        from logixlab.server import Application
        from logixlab.ethernetip import Endpoint, Session
        from test_ethernetip import request
        e=self.checked(['NOP();'],length=47,position=8)
        app=Application(Path(self.tmp.name)/'app');self.addCleanup(app.close);app.engine=e
        endpoint=Endpoint(app,0,True);self.addCleanup(endpoint.stop)
        session=Session(handle=1,generation=app.generation)
        reply=endpoint.router.handle(request(0x4c,'Ctl.LEN',struct.pack('<H',1)),session)
        self.assertEqual(reply[2],0);self.assertEqual(reply[-4:],struct.pack('<i',47))
        whole=endpoint.router.handle(request(0x4c,'Ctl',struct.pack('<H',1)),session)
        self.assertNotEqual(whole[2],0)
        self.assertFalse(e.report()['control_operations']['native_control_layout'])

    def test_bundled_control_lab_exposes_common_models_without_data_only_types(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('ControlLab',names)
        e=Engine(Project(SAMPLES/'ControlLab.L5X'));self.assertEqual(e.blockers,[])
        self.assertEqual(e.project.data_only_types,set());e.step()
        e.memory.write('ShiftRight',True);e.step()
        self.assertEqual(e.memory.read('RightBits'),[-2147483648,0x12345679,999])
        self.assertTrue(e.memory.read('RightControl.UL'))


if __name__=='__main__':unittest.main()
