"""ST/FBD explicit-target moves, dynamic fields and preservation boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_bit_moves import SCHEMAS,default
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/TargetMoveLab.L5X'
PINS={'Source':'Word','SourceBit':'SourceOffset','Length':'BitCount','DestBit':'DestinationOffset','Target':'BaseWord'}


class TargetBitMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="GraphMoves"]/FBDContent/Sheet')

    def engine(self,lines=None,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if lines is not None:logic(root.find('.//Routine[@Name="TextMoves"]'),lines)
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'moves.L5X';E.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/MainRoutine' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def settings(e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    @staticmethod
    def corrupt(e,ref,value=None):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,value)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def field(self,language):
        e=self.checked(['BTDT(TextField);'] if language=='ST' else None)
        self.settings(e,ExecuteGraph=language=='FBD',ExecuteText=language=='ST');return e

    def configure(self,e,language,**values):
        self.settings(e,**{('TextField.'+pin if language=='ST' else PINS[pin]):value for pin,value in values.items()})

    @staticmethod
    def result(e,language):return e.memory.read(('TextField' if language=='ST' else 'GraphField')+'.Dest')

    def test_default_st_and_fbd_chains_match(self):
        e=self.checked();e.step(10)
        self.assertEqual((e.memory.read('TextFieldValue'),e.memory.read('GraphFieldValue')),(0x236700aa,0x236700aa))
        self.assertEqual((e.memory.read('TextOutput'),e.memory.read('GraphOutput')),(0x23670078,0x23670078));self.assertTrue(e.memory.read('TextEnabled'));self.assertTrue(e.memory.read('GraphEnabled'));self.assertEqual(e.last_timer,{})

    def test_full_word_replacement_and_signed_patterns_in_both_languages(self):
        for language in ('ST','FBD'):
            e=self.field(language)
            for source in (0,-1,-2147483648,2147483647,0x12345678):
                self.configure(e,language,Source=source,SourceBit=0,Length=32,DestBit=0,Target=123);e.step(10);self.assertEqual(self.result(e,language),source)

    def test_source_offset_and_destination_alignment(self):
        for language in ('ST','FBD'):
            e=self.field(language);self.configure(e,language,Source=0x12345678,SourceBit=4,Length=8,DestBit=16,Target=0x230000aa);e.step(10);self.assertEqual(self.result(e,language),0x236700aa)
            self.configure(e,language,SourceBit=8,DestBit=0);e.step(10);self.assertEqual(self.result(e,language),0x23000056)

    def test_sign_bit_extraction_zero_extension_and_signed_destination(self):
        for language in ('ST','FBD'):
            e=self.field(language);self.configure(e,language,Source=-2147483648,SourceBit=31,Length=1,DestBit=0,Target=0);e.step(10);self.assertEqual(self.result(e,language),1)
            self.configure(e,language,Source=1,SourceBit=0,DestBit=31);e.step(10);self.assertEqual(self.result(e,language),-2147483648)

    def test_destination_excess_is_clipped_without_word_wrap(self):
        for language in ('ST','FBD'):
            e=self.field(language);self.configure(e,language,Source=15,SourceBit=0,Length=8,DestBit=30,Target=0x12345678);e.step(10);self.assertEqual(self.result(e,language),0xd2345678-(1<<32))

    def test_source_excess_zero_fill_is_an_explicit_software_policy(self):
        for language in ('ST','FBD'):
            e=self.field(language);self.configure(e,language,Source=-2147483648,SourceBit=31,Length=8,DestBit=0,Target=-1);e.step(10);self.assertEqual(self.result(e,language),-255)

    def test_every_single_bit_position(self):
        for language in ('ST','FBD'):
            e=self.field(language)
            for bit in range(32):
                self.configure(e,language,Source=-1,SourceBit=bit,Length=1,DestBit=bit,Target=0);e.step(10)
                self.assertEqual(self.result(e,language),(1<<bit) if bit<31 else -2147483648)

    def test_explicit_target_replaces_old_destination_and_keeps_inputs(self):
        for language in ('ST','FBD'):
            e=self.field(language);self.configure(e,language,Source=0x67,SourceBit=0,Length=8,DestBit=8,Target=0x120000aa);e.step(10)
            ref='TextField' if language=='ST' else 'GraphField';self.settings(e,**{ref+'.Dest':-1});self.configure(e,language,Target=0x230000bb);e.step(10)
            self.assertEqual(self.result(e,language),0x230067bb);self.assertEqual(e.memory.read(ref+'.Source'),0x67);self.assertEqual(e.memory.read(ref+'.Target'),0x230000bb)

    def test_st_mvmt_uses_existing_masks_and_signed_results(self):
        e=self.checked(['MVMT(TextMask);']);self.settings(e,ExecuteGraph=False)
        for source,mask,target,result in ((170,15,240,250),(-1,0,123,123),(-2147483648,-1,123,-2147483648),(0,-2147483648,-1,2147483647)):
            self.settings(e,**{'TextMask.Source':source,'TextMask.Mask':mask,'TextMask.Target':target});e.step(10);self.assertEqual(e.memory.read('TextMask.Dest'),result)

    def test_btdt_ranges_reject_invalid_parameters_and_roll_back(self):
        for language in ('ST','FBD'):
            for pin,value in (('SourceBit',-1),('SourceBit',32),('DestBit',-1),('DestBit',32),('Length',0),('Length',33)):
                e=self.field(language);self.configure(e,language,**{pin:value});before=self.snapshot(e)
                with self.subTest(language=language,pin=pin,value=value),self.assertRaisesRegex(ModelError,'BTDT '+pin+' must'):e.step(10)
                self.assertEqual(self.snapshot(e),before)

    def test_every_btdt_required_input_must_be_known(self):
        for language in ('ST','FBD'):
            for pin in PINS:
                e=self.field(language);self.corrupt(e,'TextField.'+pin if language=='ST' else PINS[pin]);before=self.snapshot(e)
                with self.subTest(language=language,pin=pin),self.assertRaisesRegex(ModelError,'BTDT '+pin+' is unknown'):e.step(10)
                self.assertEqual(self.snapshot(e),before)

    def test_full_replacement_still_requires_known_target(self):
        for language in ('ST','FBD'):
            e=self.field(language);self.configure(e,language,SourceBit=0,Length=32,DestBit=0);self.corrupt(e,'TextField.Target' if language=='ST' else 'BaseWord')
            with self.assertRaisesRegex(ModelError,'Target is unknown'):e.step(10)

    def test_mvmt_unknowns_and_zero_mask_remain_strict_in_st(self):
        for pin in ('Source','Mask','Target'):
            e=self.checked(['MVMT(TextMask);']);self.settings(e,ExecuteGraph=False,**{'TextMask.Mask':0});self.corrupt(e,'TextMask.'+pin)
            with self.assertRaisesRegex(ModelError,'MVMT '+pin+' is unknown'):e.step(10)

    def test_corrupt_btdt_values_reject_bool_float_string_and_range(self):
        for pin in PINS:
            for value in (True,1.0,'1',1<<31):
                e=self.field('ST');self.corrupt(e,'TextField.'+pin,value)
                with self.subTest(pin=pin,value=value),self.assertRaisesRegex(ModelError,'signed DINT'):e.step(10)

    def test_st_reached_calls_ignore_stored_false_enables(self):
        e=self.checked();self.settings(e,BlockEnable=False)
        for name in ('TextField','TextMask'):self.settings(e,**{name+'.EnableIn':False})
        e.step(10);self.assertTrue(e.memory.read('TextEnabled'));self.assertEqual(e.memory.read('TextOutput'),0x23670078);self.assertFalse(e.memory.read('GraphEnabled'))

    def test_fbd_disabled_and_each_language_skip_are_independent(self):
        e=self.checked();e.step(10);self.settings(e,BlockEnable=False,Word=0,BaseWord=0);e.step(10)
        self.assertEqual(e.memory.read('TextOutput'),0);self.assertEqual(e.memory.read('GraphOutput'),0x23670078)
        self.settings(e,ExecuteText=False,BlockEnable=True,Word=-1,SourceOffset=0,BitCount=32,DestinationOffset=0,Mask=-1);e.step(10)
        self.assertEqual(e.memory.read('TextOutput'),0);self.assertEqual(e.memory.read('GraphOutput'),-1)

    def test_disabled_graph_skips_unknown_inputs(self):
        e=self.checked();e.step(10);self.settings(e,ExecuteText=False,BlockEnable=False)
        for tag in PINS.values():self.corrupt(e,tag)
        e.step(10);self.assertEqual(e.memory.read('GraphOutput'),0x23670078);self.assertFalse(e.memory.read('GraphEnabled'))

    def test_unwired_graph_enables_execute(self):
        def unwire(root):
            for wire in list(self.sheet(root).findall('Wire')):
                if wire.get('ToParam')=='EnableIn':self.sheet(root).remove(wire)
        e=self.checked(mutate=unwire);self.settings(e,BlockEnable=False);e.step(10);self.assertEqual(e.memory.read('GraphOutput'),0x23670078);self.assertTrue(e.memory.read('GraphEnabled'))

    def test_prescan_and_run_clear_enables_but_retain_dest(self):
        def saved(root):
            for obj in root.findall('./Controller/Tags/Tag/Data/Structure'):
                obj.find('DataValueMember[@Name="EnableOut"]').set('Value','1');obj.find('DataValueMember[@Name="Dest"]').set('Value','99')
        e=self.checked(mutate=saved)
        for name in ('TextField','TextMask','GraphField','GraphMask'):self.assertFalse(e.memory.read(name+'.EnableOut'));self.assertEqual(e.memory.read(name+'.Dest'),99)
        e.step(10);dest=e.memory.read('TextField.Dest');e.enter_run();self.assertEqual(e.memory.read('TextField.Dest'),dest);self.assertFalse(e.memory.read('TextField.EnableOut'));self.assertEqual(e.last_timer,{})

    def test_defaults_types_and_missing_saved_parameter(self):
        self.assertEqual(default('FBD_BIT_FIELD_DISTRIBUTE')['Length'],0)
        def missing(root):
            self.sheet(root).remove(self.sheet(root).find('Wire[@ToID="100"][@ToParam="Length"]'));obj=root.find('./Controller/Tags/Tag[@Name="GraphField"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="Length"]'))
        e=self.checked(mutate=missing);self.settings(e,ExecuteText=False);self.assertNotIn('FBD_BIT_FIELD_DISTRIBUTE',e.project.data_only_types)
        for pin,kind in SCHEMAS['FBD_BIT_FIELD_DISTRIBUTE'].items():self.assertEqual(e.memory.resolve('GraphField.'+pin)[2],kind)
        with self.assertRaisesRegex(ModelError,'Length is unknown'):e.step(10)

    def test_st_for_write_effects_protect_record_bound_dependencies(self):
        e=self.engine(['FOR GuardResult:=0 TO TextField.Length DO BTDT(TextField); END_FOR;'])
        self.assertTrue(any('FOR body cannot modify tags used by its bounds/step' in p for p in e.blockers),e.blockers)
        e=self.checked(['FOR GuardResult:=0 TO 2 DO BTDT(TextField); MVMT(TextMask); END_FOR;']);e.step(10);self.assertTrue(e.memory.read('TextMask.EnableOut'))

    def test_aoi_inout_binding_executes_typed_bitfield(self):
        def aoi(root):
            a=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='BitMover',Revision='1.0');p=E.SubElement(a,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='FBD_BIT_FIELD_DISTRIBUTE',Usage='InOut',Required='true',Visible='true');E.SubElement(a,'LocalTags');logic(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='ST'),['BTDT(State);'])
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='BitMover',TagType='Base');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='BitMover')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['BitMover(Instance,TextField);'],mutate=aoi);self.settings(e,**{'TextField.Source':0x12345678,'TextField.Target':0x230000aa});e.step(10);self.assertEqual(e.memory.read('TextField.Dest'),0x236700aa)

    def test_local_alias_and_nested_array_record(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="GraphMask"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag);E.SubElement(tags,'Tag',Name='LocalMask',TagType='Alias',AliasFor='Program:MainProgram.GraphMask');self.sheet(root).find('Block[@Type="MVMT"]').set('Operand','LocalMask')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='BitCell',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Field',DataType='FBD_BIT_FIELD_DISTRIBUTE',Dimension='0')
            tag=tags.find('Tag[@Name="GraphField"]');obj=tag.find('Data/Structure');tags.remove(tag);arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='BitCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='BitCell',Dimensions='2')
            for i in range(2):
                cell=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='BitCell');item=copy.deepcopy(obj);item.tag='StructureMember';item.set('Name','Field');cell.append(item)
            self.sheet(root).find('Block[@Type="BTDT"]').set('Operand','Cells[1].Field')
        e=self.checked(mutate=nested);e.step(10);self.assertEqual(e.memory.read('GraphOutput'),0x23670078);self.assertEqual(e.memory.read('Cells[0].Field.Dest'),0)

    def test_profile_constant_redefinition_types_and_rll_forms_stay_blocked(self):
        for kind in ('profile','version','constant','record','redefined','wire','function','rll'):
            def mutate(root):
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='version':root.find('Controller').set('MajorRev','34')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="TextField"]').set('Constant','true')
                elif kind=='record':self.sheet(root).find('Block[@Type="BTDT"]').set('Operand','GraphMask')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_BIT_FIELD_DISTRIBUTE',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Dest',DataType='DINT',Dimension='0')
                elif kind=='wire':self.sheet(root).find('IRef[@ID="1"]').set('Operand','BlockEnable')
                elif kind=='function':self.sheet(root).find('Block').tag='Function'
                else:root.find('.//Routine[@Name="MainRoutine"]/RLLContent/Rung/Text').text='BTDT(TextField);'
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate=mutate).blockers)

    def test_late_fault_restores_both_languages_and_retry(self):
        e=self.checked();e.step(10);self.settings(e,Word=0,BaseWord=0,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step(10)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1);e.step(10);self.assertEqual((e.memory.read('TextOutput'),e.memory.read('GraphOutput')),(0,0))

    def test_periodic_and_routine_harness(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        for e in (self.checked(mutate=periodic),self.checked(mode='routine',defer=True)):e.step(10);self.assertEqual(e.memory.read('TextOutput'),e.memory.read('GraphOutput'))

    def event_engine(self,fault=False):
        def event(root):
            body=root.find('.//Routine[@Name="MainRoutine"]/RLLContent');E.SubElement(E.SubElement(body,'Rung',Number='5',Type='N'),'Text').text='EVENT(BitMoveEvent);'
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventMoves',Class='Standard',Disabled='false');E.SubElement(p,'Tags');routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventMoves',Type='ST');logic(routine,['BTDT(TextField); MVMT(TextMask);']+(['GuardResult:=1/SourceOffset;'] if fault else []))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='BitMoveEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(mutate=event)

    def test_event_calls_have_no_hidden_move_history(self):
        e=self.event_engine();e.step(10);self.assertEqual(e.memory.read('TextField.Dest'),0x236700aa);self.assertEqual(e.last_timer,{})

    def test_event_fault_restores_earlier_field_and_mask_updates(self):
        e=self.event_engine(True);e.step(10);self.settings(e,SourceOffset=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step(10)
        self.assertEqual(self.snapshot(e),before)

    def test_budget_failure_rolls_back(self):
        e=self.checked();e.instruction_limit=10;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):e.step(10)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_preserves_move_results(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();e.step(10);before=self.snapshot(e);texts=['JSR(TextMoves,0);','JSR(GraphMoves,0);'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0);self.assertEqual(self.snapshot(e),before);candidate.step(10);self.assertEqual(candidate.memory.read('TextOutput'),candidate.memory.read('GraphOutput'));self.assertEqual(candidate.project.instruction_counts['BTDT'],2)

    def test_report_and_dispatch_inventories(self):
        e=self.checked();p=e.report();self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(106,29));self.assertEqual(len(p['function_blocks']['instructions']),63)
        self.assertEqual(p['st_bit_moves']['instructions'],['BTDT','MVMT']);self.assertEqual(p['function_blocks']['blocks']['bit_moves'],p['st_bit_moves']);self.assertFalse(p['st_bit_moves']['native_runtime_parity'])


if __name__=='__main__':unittest.main()
