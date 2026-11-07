"""FBC/DDT canonical storage, indirect sampling and transactional bounds."""
import copy
import unittest
from xml.etree import ElementTree as E
import test_file_bit_compare as fixtures
from logixlab.model import ModelError


class BitDiagnosticReferenceTests(unittest.TestCase):
    setUp=fixtures.FileBitCompareTests.setUp
    instruction=fixtures.FileBitCompareTests.instruction
    checked=fixtures.FileBitCompareTests.checked

    @staticmethod
    def tags(root):
        tags=root.find('./Controller/Tags')
        for name in ('Index','ResultIndex'):
            tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
        for name,target,kind in [('SourceView','Source','DINT'),('ReferenceView','Reference','DINT'),('ResultView','Result','DINT'),('SourceChain','Source[0]','DINT'),('Cursor','Compare.POS','DINT'),('OutputCursor','ResultControl.POS','DINT'),('ControlView','Compare','CONTROL')]:E.SubElement(tags,'Tag',Name=name,DataType=kind,TagType='Alias',AliasFor=target)

    def engine(self,logic=None,*,mutate=None,**kwargs):
        def refs(root):
            self.tags(root)
            if mutate:mutate(root)
        return fixtures.FileBitCompareTests.engine(self,logic,mutate=refs,**kwargs)

    def snapshot(self,e):return copy.deepcopy((e.memory.values,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def indirect(self,name='FBC'):
        return self.instruction(name,source='SourceView[Index]',reference='ReferenceView[Index]',result='ResultView[ResultIndex]')

    def test_alias_chains_and_indirect_starts_retain_bit_offsets_and_wrap(self):
        e=self.checked([self.instruction(source='SourceChain',reference='ReferenceView[Index]',result='ResultView[ResultIndex]')+';']);e.step();self.assertEqual(e.memory.read('Result'),[32,39,31,999])

    def test_false_held_and_saved_done_calls_skip_live_indices(self):
        for state in ('false','held','done'):
            e=self.checked(['XIC(Enable)'+self.indirect()+';']);e.memory.values['index']=None;e.memory.values['resultindex']=None
            if state=='false':e.memory.write('Enable',False)
            elif state=='held':e.memory.write('Compare.EN',True)
            else:e.memory.write('Compare.DN',True)
            e.step();self.assertEqual(e.memory.read('Result'),[-1,-1,-1,999])

    def test_invalid_compare_state_skips_source_indices(self):
        for length,position in ((0,0),(-1,0),(40,-1)):
            e=self.checked([self.indirect('DDT')+';'],length=length,position=position);e.memory.values['index']=None;e.step();self.assertTrue(e.memory.read('Compare.ER'))

    def test_reached_source_and_reference_indices_fail_atomically(self):
        for operand in ('Source[Index]','Reference[Index]'):
            for bad in (None,999,-1):
                args=dict(source=operand) if operand.startswith('Source') else dict(reference=operand)
                e=self.checked([self.instruction('DDT',**args)+';']);e.memory.values['index']=bad;before=self.snapshot(e)
                with self.assertRaises(ModelError):e.step()
                self.assertEqual(self.snapshot(e),before)

    def test_no_mismatch_does_not_consume_result_index_or_state(self):
        for bad in (None,999):
            e=self.checked([self.indirect()+';'],reference=(-2147483615,129,888));e.memory.values['resultindex']=bad;e.memory.values['resultcontrol']['DN']=None;e.memory.write('ResultControl.LEN',0)
            e.step();self.assertTrue(e.memory.read('Compare.DN'));self.assertEqual(e.memory.read('Result'),[-1,-1,-1,999])

    def test_bad_result_index_faults_only_when_recording(self):
        e=self.checked([self.indirect('DDT')+';']);e.memory.write('ResultIndex',999);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_result_start_is_frozen_before_ddt_learning_changes_its_index(self):
        e=self.checked([self.instruction('DDT',result='Result[Reference[0]]')+';'],length=2,source=(3,0,999),reference=(0,0,888));e.step()
        self.assertEqual(e.memory.read('Result'),[0,1,-1,999]);self.assertEqual(e.memory.read('Reference[0]'),3)

    def test_result_start_is_frozen_before_result_writes_change_its_index(self):
        e=self.checked([self.instruction(result='Result[Result[0]]')+';'],source=(-2147483616,1,999),result=(0,-1,-1,-1,999));e.step()
        self.assertEqual(e.memory.read('Result'),[5,31,32,-1,999])

    def test_source_reference_windows_are_frozen_before_result_writes(self):
        e=self.checked([self.instruction(source='Source[Result[0]]',reference='Reference[Result[0]]')+';'],capacity=1,result=(0,-1,-1,999));e.step()
        self.assertEqual(e.memory.read('Result'),[39,-1,-1,999])

    def test_result_window_is_reselected_on_next_one_mismatch_edge(self):
        e=self.checked(['XIC(Enable)'+self.indirect('DDT')+';'],one=True,result=(-1,-1,-1,-1,999));e.step();e.memory.write('Enable',False);e.step();e.memory.write('ResultIndex',1);e.memory.write('Enable',True);e.step()
        self.assertEqual(e.memory.read('Result'),[0,-1,5,-1,999]);self.assertEqual(e.memory.read('Compare.POS'),6)

    @staticmethod
    def packet(root,array=False):
        c=root.find('Controller');dt=E.SubElement(c.find('DataTypes'),'DataType',Name='DiagnosticPacket',Family='NoFamily',Class='User');members=E.SubElement(dt,'Members')
        for name,kind,dim in [('Source','DINT','3'),('Reference','DINT','3'),('Result','DINT','4'),('Compare','CONTROL','0'),('Output','CONTROL','0')]:E.SubElement(members,'Member',Name=name,DataType=kind,Dimension=dim)
        tags=c.find('Tags');tag=E.SubElement(tags,'Tag',Name='Packets' if array else 'Packet1',DataType='DiagnosticPacket',TagType='Base',**({'Dimensions':'2'} if array else {}));data=E.SubElement(tag,'Data',Format='Decorated')
        parents=[E.SubElement(data,'Structure',DataType='DiagnosticPacket')]
        if array:
            data.clear();data.set('Format','Decorated');rows=E.SubElement(data,'Array',DataType='DiagnosticPacket',Dimensions='2');parents=[E.SubElement(E.SubElement(rows,'Element',Index=f'[{i}]'),'Structure',DataType='DiagnosticPacket') for i in range(2)]
        for obj in parents:
            for name,original,kind in [('Source','Source','Array'),('Reference','Reference','Array'),('Result','Result','Array'),('Compare','Compare','Structure'),('Output','ResultControl','Structure')]:
                member=copy.deepcopy(tags.find(f'Tag[@Name="{original}"]/Data/{kind}'));member.tag=kind+'Member';member.set('Name',name);obj.append(member)

    def test_disjoint_packet_members_and_control_records_share_one_base(self):
        for name in ('FBC','DDT'):
            e=self.checked([self.instruction(name,source='Packet1.Source[0]',reference='Packet1.Reference[0]',result='Packet1.Result[0]',compare='Packet1.Compare',output='Packet1.Output')+';'],mutate=self.packet);e.step()
            self.assertEqual(e.memory.read('Packet1.Result'),[32,39,31,999]);self.assertEqual(e.memory.read('Packet1.Reference[0]'),-2147483615 if name=='DDT' else 0)

    def test_out_of_bounds_control_alias_loads_but_prescan_rejects_actual_overlap(self):
        def setup(root):
            self.packet(root, array=True)
            tags = root.find('./Controller/Tags')
            tags.find('./Tag[@Name="ResultIndex"]/Data/DataValue').set('Value', '2')
            E.SubElement(tags, 'Tag', Name='OutputView', DataType='CONTROL', TagType='Alias',
                         AliasFor='Packets[ResultIndex].Compare')

        for name in ('FBC', 'DDT'):
            with self.subTest(instruction=name):
                instruction = self.instruction(name, compare='Packets[0].Compare', output='OutputView')
                engine = self.checked([instruction + ';'], mutate=setup, flags={'EN': True, 'DN': True, 'FD': True})
                self.assertEqual(engine.memory.read('Packets'), engine.project.initial['packets'])
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('ResultIndex', 0)
                before = self.snapshot(engine)
                with self.assertRaisesRegex(ModelError, 'Prescan rolled back.*distinct storage'):
                    engine.enter_run()
                self.assertEqual(self.snapshot(engine), before)

    def test_deferred_control_address_still_checks_shape_permissions_and_data_roles(self):
        def setup(root):
            self.packet(root, array=True)
            tags = root.find('./Controller/Tags')
            tags.find('./Tag[@Name="ResultIndex"]/Data/DataValue').set('Value', '2')

        for arguments, message in (
            (dict(output='Packets[2].Output'), 'outside bounds'),
            (dict(output='Packets[-1].Output'), 'outside bounds'),
            (dict(output='Packets[1 + 1].Output'), 'outside bounds'),
            (dict(output='Packets[ResultIndex].Source[0]'), 'writable CONTROL'),
            (dict(output='Packets[ResultIndex].Output', result='Source[2]'), 'distinct array/member'),
        ):
            with self.subTest(arguments=arguments):
                engine = self.engine([self.instruction(**arguments) + ';'], mutate=setup)
                self.assertTrue(any(message in blocker for blocker in engine.blockers), engine.blockers)

        def read_only(root):
            setup(root)
            root.find('./Controller/Tags/Tag[@Name="Packets"]').set('Constant', 'true')

        engine = self.engine([self.instruction(output='Packets[ResultIndex].Output') + ';'], mutate=read_only)
        self.assertTrue(any('Read-only destination' in blocker for blocker in engine.blockers))

    def test_actual_source_reference_overlap_is_checked_after_parent_selection(self):
        e=self.checked([self.instruction('DDT',source='Packets[Index].Source[0]',reference='Packets[1].Source[0]')+';'],mutate=lambda root:self.packet(root,True));e.memory.write('Index',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'distinct array/member'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_actual_result_overlap_is_checked_when_first_mismatch_needs_it(self):
        e=self.checked([self.instruction(source='Packets[1].Source[0]',result='Packets[Index].Source[0]')+';'],mutate=lambda root:self.packet(root,True));e.memory.write('Index',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'distinct array/member'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_same_array_writable_roles_remain_blocked_even_for_disjoint_starts(self):
        for args in (dict(result='Source[2]'),dict(name='DDT',reference='Source[1]'),dict(output='ControlView')):
            self.assertTrue(self.engine([self.instruction(**args)+';']).blockers)

    def test_control_pos_dependencies_in_all_array_roles_are_blocked(self):
        for args in (dict(source='Source[Cursor]'),dict(reference='Reference[Compare.POS]'),dict(result='Result[OutputCursor]')):
            self.assertTrue(any('CONTROL.POS' in b for b in self.engine([self.instruction(**args)+';']).blockers))

    def test_read_only_alias_inputs_supported_but_writable_roles_blocked(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Reference"]').set('Constant','true')
        e=self.checked([self.indirect()+';'],mutate=constant);e.step();self.assertEqual(e.memory.read('Result[0]'),32)
        self.assertTrue(self.engine([self.indirect('DDT')+';'],mutate=constant).blockers)

    def test_limits_precede_live_indices_and_result_capacity_is_lazy(self):
        e=self.checked([self.indirect()+';'],length=4097);e.memory.values['index']=None
        with self.assertRaisesRegex(ModelError,'4096-bit'):e.step()
        e=self.checked([self.indirect('DDT')+';'],capacity=4097);e.memory.values['resultindex']=None
        with self.assertRaisesRegex(ModelError,'4096-element'):e.step()

    def test_late_failure_restores_learning_results_controls_and_time(self):
        e=self.checked([self.indirect('DDT')+';','DIV(1,FaultDivisor,GuardResult);']);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('Reference')[:2],[-2147483615,129])


if __name__=='__main__':unittest.main()
