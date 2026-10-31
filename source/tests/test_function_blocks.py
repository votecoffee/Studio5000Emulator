"""FBD selector graphs, typed wires, lifecycle and whole-advance rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.fbd_select import SCHEMAS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


class FunctionBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLES/'SelectorLab.L5X').getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'fbd.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode,'MainProgram/SelectSignals' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e):e.step(10);return e.memory.read('MultiplexedOutput')

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="SelectSignals"]/FBDContent/Sheet')

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    def test_manual_automatic_selection_and_chained_graph(self):
        e=self.checked();self.assertEqual(self.step(e),10);self.assertEqual(e.memory.read('SelectedOutput'),10)
        e.memory.write('ManualMode',True);self.assertEqual(self.step(e),25)
        e.memory.write('ManualValue',-3.5);self.assertEqual(self.step(e),-3.5)
        self.assertEqual([t['detail'] for t in e.trace if t.get('language')=='FBD'],['SEL','MUX'])

    def test_mux_each_one_based_channel_and_unconnected_pins(self):
        e=self.checked()
        for channel,value in enumerate((10,25,30,40,50,60,70,80),1):
            e.memory.write('Channel',channel);self.assertEqual(self.step(e),value)
            self.assertEqual(e.memory.read('SelectorStatus'),0)

    def test_invalid_mux_first_enabled_call_uses_zero_not_saved_output(self):
        e=self.checked();e.memory.write('Channel',0);e.memory.write('ChannelChoice.Out',123)
        self.assertEqual(self.step(e),0);self.assertEqual(e.memory.read('SelectorStatus'),3)
        self.assertTrue(e.memory.read('ChannelChoice.InstructFault'));self.assertTrue(e.memory.read('ChannelChoice.SelectorInv'))

    def test_invalid_selectors_hold_internal_output_and_recover(self):
        e=self.checked();e.memory.write('Channel',5);self.assertEqual(self.step(e),50)
        for channel in (-2147483648,-1,0,9,2147483647):
            e.memory.write('Channel',channel);e.memory.write('ChannelChoice.Out',999)
            self.assertEqual(self.step(e),50);self.assertEqual(e.memory.read('SelectorStatus'),3)
        e.memory.write('Channel',8);self.assertEqual(self.step(e),80);self.assertEqual(e.memory.read('SelectorStatus'),0)

    def test_disabled_blocks_preserve_outputs_status_and_hidden_state(self):
        e=self.checked();self.step(e);e.memory.write('Channel',0);self.step(e)
        e.memory.write('BlockEnable',False);e.memory.write('ManualValue',88);e.memory.write('ManualMode',True)
        before=copy.deepcopy(e.last_timer);self.assertEqual(self.step(e),10)
        self.assertEqual(e.last_timer,before);self.assertEqual(e.memory.read('SelectorStatus'),3)
        self.assertFalse(e.memory.read('Choice.EnableOut'));self.assertFalse(e.memory.read('ChannelChoice.EnableIn'))
        e.memory.write('BlockEnable',True);self.assertEqual(self.step(e),10);self.assertEqual(e.memory.read('SelectedOutput'),88)

    def test_prescan_only_clears_enables_and_disabled_start_does_not_initialize_history(self):
        e=self.checked();e.memory.write('BlockEnable',False);e.memory.write('ChannelChoice.Out',91)
        self.assertEqual(self.step(e),91);self.assertEqual(e.last_timer,{})
        e.memory.write('BlockEnable',True);e.memory.write('Channel',0);self.assertEqual(self.step(e),0)

    def test_unwired_enable_is_true_after_prescan(self):
        def unwire(root):
            sheet=self.sheet(root)
            for w in list(sheet.findall('Wire')):
                if w.get('ToParam')=='EnableIn':sheet.remove(w)
        e=self.checked(unwire);self.assertFalse(e.memory.read('Choice.EnableIn'))
        e.memory.write('BlockEnable',False);self.assertEqual(self.step(e),10);self.assertTrue(e.memory.read('Choice.EnableIn'))

    def test_skipped_jsr_retains_history_and_resumes_selection(self):
        e=self.checked();self.step(e);before=copy.deepcopy(e.last_timer);e.memory.write('ExecuteGraph',False)
        e.memory.write('ManualMode',True);self.assertEqual(self.step(e),10);self.assertEqual(e.last_timer,before)
        self.assertFalse(any(t.get('language')=='FBD' for t in e.trace))
        e.memory.write('ExecuteGraph',True);self.assertEqual(self.step(e),25)

    def test_run_entry_resets_internal_hold_but_does_not_scan_outputs(self):
        e=self.checked();self.step(e);e.memory.write('Channel',0);e.enter_run()
        self.assertEqual(e.memory.read('MultiplexedOutput'),10);self.assertFalse(e.memory.read('Choice.EnableOut'))
        self.assertEqual(self.step(e),0)

    def test_unknown_unselected_input_propagates_without_false_coercion(self):
        e=self.checked();self.unknown(e,'ManualValue');self.assertEqual(self.step(e),10)
        e.memory.write('ManualMode',True);before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)
        e.memory.write('ManualValue',12);self.assertEqual(self.step(e),12)

    def test_unknown_selected_mux_input_faults_and_disabled_inputs_may_be_unknown(self):
        e=self.checked();self.unknown(e,'ChannelChoice.In8');e.memory.write('Channel',8)
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
        e.memory.write('BlockEnable',False);self.assertEqual(self.step(e),0)

    def test_unknown_enable_and_selector_fault_when_consumed(self):
        for tag in ('BlockEnable','ManualMode','Channel'):
            e=self.checked();self.unknown(e,tag)
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)

    def test_unknown_unwired_unused_analog_value_is_allowed(self):
        e=self.checked();self.unknown(e,'ChannelChoice.In8');self.assertEqual(self.step(e),10)

    def test_unknown_disabled_output_cannot_be_published_as_known(self):
        e=self.checked();self.unknown(e,'Choice.Out');e.memory.write('BlockEnable',False)
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)

    def test_late_ladder_fault_rolls_back_block_outputs_and_history(self):
        e=self.checked();self.step(e);e.memory.write('ManualMode',True);e.memory.write('FaultDivisor',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scheduler_description()),before)
        e.memory.write('ManualValue',99);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e),99)

    def test_typed_literals_and_direct_reference_to_output_wire(self):
        def direct(root):
            sheet=self.sheet(root)
            for child in list(sheet):sheet.remove(child)
            E.SubElement(sheet,'IRef',ID='1',Operand='-3.5');E.SubElement(sheet,'ORef',ID='2',Operand='SelectedOutput')
            E.SubElement(sheet,'Wire',FromID='1',FromParam='In',ToID='2',ToParam='Out')
        e=self.checked(direct);self.step(e);self.assertEqual(e.memory.read('SelectedOutput'),-3.5)

    def test_dependencies_override_id_and_xml_order_with_stable_ties(self):
        def reorder(root):
            sheet=self.sheet(root)
            for child in sheet:
                for attribute in ('ID','FromID','ToID'):
                    value=child.get(attribute)
                    if value=='10':child.set(attribute,'100')
                    elif value=='20':child.set(attribute,'0')
            sheet[:]=reversed(list(sheet))
        e=self.checked(reorder);self.assertEqual(self.step(e),10)
        self.assertEqual([t['number'] for t in e.trace if t.get('language')=='FBD'],['100','0'])

    def test_late_oref_failure_rolls_back_earlier_blocks_and_leaves_no_partial_outputs(self):
        e=self.checked();self.unknown(e,'ChannelChoice.Status');e.memory.write('BlockEnable',False)
        before=copy.deepcopy((e.memory.values,e.last_timer))
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_work_budget_covers_nodes_and_wires(self):
        e=self.checked(mode='routine');before=copy.deepcopy((e.memory.values,e.last_timer))
        e.instruction_limit=10
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer),before)
        e.instruction_limit=100;self.assertEqual(self.step(e),10)

    def test_routine_harness_and_periodic_tasks_execute_graph(self):
        e=self.checked(mode='routine');self.assertEqual(self.step(e),10)
        def periodic(root):
            task=root.find('./Controller/Tasks/Task');task.set('Type','Periodic');task.set('Rate','10')
        self.assertEqual(self.step(self.checked(periodic)),10)

    def test_program_local_alias_static_array_and_nested_udt_record(self):
        def nesting(root):
            tags=root.find('./Controller/Tags');choice=tags.find('Tag[@Name="Choice"]');tags.remove(choice)
            root.find('./Controller/Programs/Program/Tags').append(choice)
            E.SubElement(tags,'Tag',Name='ChoiceAlias',TagType='Alias',AliasFor='Program:MainProgram.Choice')
            self.sheet(root).find('Block[@Type="SEL"]').set('Operand','ChoiceAlias')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Cell',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Select',DataType='MULTIPLEXER',Dimension='0')
            mux=tags.find('Tag[@Name="ChannelChoice"]');structure=mux.find('Data/Structure');tags.remove(mux)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',DataType='Cell',TagType='Base',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='Cell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='Cell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Select');obj.append(item)
            self.sheet(root).find('Block[@Type="MUX"]').set('Operand','Cells[1].Select')
        e=self.checked(nesting);self.assertEqual(self.step(e),10);e.memory.write('Channel',0);self.assertEqual(self.step(e),10)
        self.assertEqual(e.memory.read('Cells[0].Select.Out'),0)

    def test_records_member_types_aliases_and_report(self):
        e=self.checked()
        for name,dtype in (('Choice','SELECT'),('ChannelChoice','MULTIPLEXER')):
            self.assertNotIn(dtype,e.project.data_only_types)
            self.assertEqual(default(dtype)['EnableIn'],True)
            for member,kind in SCHEMAS[dtype].items():self.assertEqual(e.memory.resolve(name+'.'+member)[2],kind)
        e.memory.write('ChannelChoice.SelectorInv',True);self.assertEqual(e.memory.read('ChannelChoice.Status'),2)
        report=e.report()['function_blocks'];self.assertEqual(report['instructions'],['ABS','ADD','BAND','BNOT','BOR','BXOR','CTUD','DERV','DFF','DIV','EQU','ESEL','GEQ','GRT','HLL','INTG','JKFF','LEQ','LES','LIM','MAXC','MINC','MUL','MUX','NEG','NEQ','OSFI','OSRI','RESD','RLIM','RTOR','SCL','SEL','SETD','SNEG','SSUM','SUB','TOFR','TONR','UPDN']);self.assertFalse(report['native_runtime_parity'])
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))

    def test_profiles_and_st_ladder_forms_remain_blocked(self):
        for version,cpu in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',cpu)
            self.assertTrue(self.engine(profile).blockers)
        for text in ('SEL(Choice);','MUX(ChannelChoice);'):
            def st(root):logic(root.find('.//Routine[@Name="SelectSignals"]'),[text])
            self.assertTrue(self.engine(st).blockers)

    def test_malformed_graphs_are_blocked_before_prescan(self):
        def cases(root,kind):
            sheet=self.sheet(root);block=sheet.find('Block');wire=sheet.find('Wire')
            if kind=='duplicate':block.set('ID','1')
            elif kind=='missing':wire.set('FromID','999')
            elif kind=='badpin':wire.set('ToParam','Out')
            elif kind=='direction':wire.set('FromID','30');wire.set('FromParam','Out')
            elif kind=='twodrivers':sheet.append(copy.deepcopy(wire))
            elif kind=='type':wire.set('FromID','3')
            elif kind=='unconnected':sheet.remove(sheet.find('Wire[@ToID="30"]'))
            elif kind=='unknownblock':block.set('Type','PID')
            elif kind=='attributes':block.set('ExecutionOrder','0')
            elif kind=='nodechild':E.SubElement(block,'Array',Name='Storage',Operand='ManualValue')
            elif kind=='visible':block.set('VisiblePins','NotAPin')
            elif kind=='id':block.set('ID','-1')
            elif kind=='coords':block.set('X','10001')
            elif kind=='cycle':
                wire.set('FromID','20');wire.set('FromParam','Out')
            elif kind=='feedback':E.SubElement(sheet,'FeedbackWire',FromID='20',FromParam='Out',ToID='10',ToParam='In1')
            elif kind=='connector':E.SubElement(sheet,'ICon',ID='99',Name='A')
            elif kind=='function':E.SubElement(sheet,'Function',ID='99',Type='ADD')
        for kind in ('duplicate','missing','badpin','direction','twodrivers','type','unconnected','unknownblock','attributes','nodechild','visible','id','coords','cycle','feedback','connector','function'):
            with self.subTest(kind=kind):self.assertTrue(self.engine(lambda root:cases(root,kind)).blockers)

    def test_missing_protected_multiple_sheet_and_edit_variants_block(self):
        for kind in ('missing','protected','multisheet','edits','twoorig'):
            def mutate(root):
                routine=root.find('.//Routine[@Name="SelectSignals"]');content=routine.find('FBDContent')
                if kind=='missing':routine.remove(content)
                elif kind=='protected':E.SubElement(routine,'EncryptedContent')
                elif kind=='multisheet':content.append(copy.deepcopy(content[0]))
                elif kind=='edits':content.set('OnlineEditType','PendingEdits')
                else:routine.append(copy.deepcopy(content))
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_overlaps_implicit_feedback_and_indirect_references_block(self):
        for kind in ('record','recordalias','oref','readwrite','backingread','indirect','constant','wrongtype','redefined'):
            def mutate(root):
                sheet=self.sheet(root);tags=root.find('./Controller/Tags')
                if kind=='record':sheet.find('Block[@Type="MUX"]').set('Operand','Choice')
                elif kind=='recordalias':
                    E.SubElement(tags,'Tag',Name='Alias',TagType='Alias',AliasFor='Choice');node=copy.deepcopy(sheet.find('Block'));node.set('ID','99');node.set('Operand','Alias');sheet.append(node)
                elif kind=='oref':sheet.find('ORef[@ID="31"]').set('Operand','SelectedOutput')
                elif kind=='readwrite':sheet.find('ORef[@ID="30"]').set('Operand','AutomaticValue')
                elif kind=='backingread':sheet.find('IRef').set('Operand','Choice.Out')
                elif kind=='indirect':sheet.find('IRef').set('Operand','Values[Channel]')
                elif kind=='constant':tags.find('Tag[@Name="Choice"]').set('Constant','true')
                elif kind=='wrongtype':sheet.find('IRef').set('Operand','Choice')
                else:
                    members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SELECT',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Out',DataType='REAL',Dimension='0')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_unsupported_fbd_in_aoi_is_a_blocker(self):
        def aoi(root):
            defs=root.find('./Controller/AddOnInstructionDefinitions');a=E.SubElement(defs,'AddOnInstructionDefinition',Name='Bad',Revision='1.0');p=E.SubElement(a,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(a,'LocalTags');routine=copy.deepcopy(root.find('.//Routine[@Name="SelectSignals"]'));routine.set('Name','Logic');E.SubElement(a,'Routines').append(routine)
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='BadInstance',DataType='Bad',TagType='Base')
            root.find('.//Routine[@Name="MainRoutine"]/RLLContent/Rung/Text').text='Bad(BadInstance);'
        self.assertTrue(self.engine(aoi).blockers)

    def event_engine(self,fault=False):
        def event(root):
            main=root.find('.//Routine[@Name="MainRoutine"]');logic(main,['JSR(SelectSignals,0); EVENT(SampleEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');lines=['AutomaticValue:=99;']
            if fault:lines.append('GuardResult:=1/FaultDivisor;')
            logic(routine,lines);task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='SampleEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_failure_rolls_back_fbd_and_scheduler(self):
        e=self.event_engine(True);e.memory.write('FaultDivisor',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e),10);self.assertEqual(self.step(e),99)

    def test_fbd_event_task_uses_shared_backing_record_and_output_history(self):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(SelectSignals,0); Channel:=0; EVENT(SampleEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='SelectSignals',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            E.SubElement(p,'Routines').append(copy.deepcopy(root.find('.//Routine[@Name="SelectSignals"]')))
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='SampleEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);e.memory.write('Channel',4);self.assertEqual(self.step(e),40)
        self.assertEqual(e.memory.read('SelectorStatus'),3)
        self.assertEqual(len([t for t in e.trace if t.get('language')=='FBD']),4)

    def test_enableout_wire_drives_downstream_enable(self):
        def enable(root):
            wire=self.sheet(root).find('Wire[@ToID="20"][@ToParam="EnableIn"]');wire.set('FromID','10');wire.set('FromParam','EnableOut')
        e=self.checked(enable);self.step(e);e.memory.write('BlockEnable',False);e.memory.write('Channel',8)
        self.assertEqual(self.step(e),10);self.assertFalse(e.memory.read('ChannelChoice.EnableOut'))

    def test_float32_rounding_signed_zero_and_nonfinite_faults(self):
        import math
        e=self.checked();e.memory.write('AutomaticValue',-0.0);self.assertLess(math.copysign(1,self.step(e)),0)
        e.memory.write('AutomaticValue',16777217);self.assertEqual(self.step(e),16777216)
        key,parts,_=e.memory.resolve('AutomaticValue');e.memory.store(key,parts,float('nan'))
        with self.assertRaisesRegex(ModelError,'Nonfinite'):self.step(e)

    def test_deferred_prescan_preview_retains_saved_enables_until_run(self):
        e=self.checked(defer=True);self.assertTrue(e.memory.read('Choice.EnableIn'));self.assertFalse(e.memory.read('Choice.EnableOut'))
        e.enter_run();self.assertFalse(e.memory.read('Choice.EnableIn'));self.assertEqual(self.step(e),10)

    def test_node_and_wire_admission_limits_are_explicit(self):
        def too_many(root):
            sheet=self.sheet(root)
            for i in range(600):E.SubElement(sheet,'IRef',ID=str(i+100),Operand='AutomaticValue')
        self.assertTrue(any('limit' in b for b in self.engine(too_many).blockers))

    def test_empty_sheet_and_nested_reference_content_block(self):
        def empty(root):
            sheet=self.sheet(root)
            for child in list(sheet):sheet.remove(child)
        self.assertTrue(self.engine(empty).blockers)
        def nested(root):E.SubElement(self.sheet(root).find('IRef'),'Expression').text='AutomaticValue+1'
        self.assertTrue(self.engine(nested).blockers)

    def test_detached_ladder_replacement_preserves_graph_output_history(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);e.memory.write('Channel',0);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(SelectSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual((candidate.project.instruction_counts['SEL'],candidate.project.instruction_counts['MUX']),(1,1))
        import hashlib,json
        content=[(key,r.kind,r.diagram if r.kind=='FBD' else [x['text'] for x in r.rungs]) for key,r in sorted(candidate.project.routines.items())]
        self.assertEqual(candidate.project.runtime_logic_sha256,hashlib.sha256(json.dumps(content,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(self.step(candidate),10)


if __name__=='__main__':unittest.main()
