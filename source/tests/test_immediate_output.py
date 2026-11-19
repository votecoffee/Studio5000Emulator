"""IOT captures instruction-time data at a committed boundary."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from logixlab.model import ModelError
from logixlab.server import Application

SAMPLE = Path(__file__).resolve().parents[1] / 'samples/ModuleStatusLab.L5X'


def add_local_bridge(modules):
    bridge = ET.SubElement(modules, 'Module', Name='LineBridge', CatalogNumber='1756-EN2TR',
                           Vendor='1', ProductType='12', ParentModule='Local',
                           ParentModPortId='1', Inhibited='false', MajorFault='false')
    ports = ET.SubElement(bridge, 'Ports')
    ET.SubElement(ports, 'Port', Id='1', Address='6', Type='ICP', Upstream='true')
    ET.SubElement(ports, 'Port', Id='2', Type='Ethernet', Upstream='false')
    return bridge.get('Name')


def select_output_tag(root, name):
    tag = ET.SubElement(root.find('./Controller/Tags'), 'Tag', Name=name,
                        TagType='Base', DataType='DINT')
    ET.SubElement(ET.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='0')
    text = root.find('.//Routine[@Name="Main"]/RLLContent/Rung[@Number="16"]/Text')
    text.text = text.text.replace('Local:2:O', name)


class ImmediateOutputTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = Application(tmp.name)
        self.addCleanup(self.app.close)

    def load(self, mutate=None):
        if mutate is None:
            state = self.app.command('demo',{'sample':'ModuleStatusLab'})
        else:
            root = ET.parse(SAMPLE).getroot()
            mutate(root)
            state = self.app.command('load',{'name':'IOTTest.L5X','content':base64.b64encode(ET.tostring(root)).decode()})
        return state

    def write(self, name, value):
        return self.app.command('write',{'tag':name,'value':value})

    def step(self):
        return self.app.command('step',{'count':1,'dt':10})

    def connection(self, state, *, module='RackOutput', **extra):
        return self.app.command('module-connection',dict(module=module,state=state,
                                                       project_generation=self.app.generation,**extra))

    def open_output(self):
        self.write('ModeCommand',1)
        self.write('ApplyMode',True)
        self.connection('running')

    def snapshot(self):
        return json.loads(self.app.device_io.snapshot()[1])

    @staticmethod
    def named_output(root, *, bridged=False, address='192.0.2.99'):
        modules = root.find('./Controller/Modules')
        parent = add_local_bridge(modules) if bridged else 'Local'
        remote = ET.SubElement(modules, 'Module', Name='NetworkOutput', CatalogNumber='1732E-OB16M12',
                               Vendor='1', ProductType='7', ParentModule=parent, ParentModPortId='2',
                               Inhibited='false', MajorFault='false')
        ET.SubElement(ET.SubElement(remote, 'Ports'), 'Port', Id='1', Address=address,
                      Type='Ethernet', Upstream='true')
        select_output_tag(root, 'NetworkOutput:O')

    @staticmethod
    def remote_rack_output(root, *, bridged=False, tag_slot=5):
        modules = root.find('./Controller/Modules')
        adapter = modules.find('Module[@Name="RemoteRack"]')
        if bridged:
            adapter.set('ParentModule', add_local_bridge(modules))
            # The extra local slot hop also lengthens the sample's GSV Path read.
            path = root.find('./Controller/Tags/Tag[@Name="RemotePath"]')
            path.set('Dimensions', '20')
            path.find('./Data/Array').set('Dimensions', '20')
        module = ET.SubElement(modules, 'Module', Name='RemoteCoils', CatalogNumber='1756-OB16D',
                               Vendor='1', ProductType='7', ParentModule='RemoteRack',
                               ParentModPortId='1', Inhibited='false', MajorFault='false')
        ET.SubElement(ET.SubElement(module, 'Ports'), 'Port', Id='1', Address='5',
                      Type='ICP', Upstream='true')
        select_output_tag(root, f'RemoteRack:{tag_slot}:O')

    def test_remote_rack_slot_captures_child_output_and_tracks_upstream_state(self):
        for bridged in (False, True):
            with self.subTest(bridged=bridged):
                self.assertEqual(self.load(lambda root: self.remote_rack_output(root, bridged=bridged))['blockers'], [])
                self.write('SendImmediate', True)
                self.connection('running', module='RemoteRack')
                self.assertEqual(self.step()['immediate_outputs'], [])
                self.connection('running', module='RemoteCoils')
                self.assertEqual(self.step()['immediate_outputs'], [])  # Adapter is still inhibited.
                self.write('RackModeCommand', 0)
                self.write('ApplyRackMode', True)
                captured = self.step()['immediate_outputs']
                self.assertEqual(captured, [
                    dict(module='RemoteCoils', tag='RemoteRack:5:O', value=17, sequence=1, scan=3, simulation_ms=30)])
                self.assertEqual(self.snapshot()['immediate_outputs'], captured)
                self.assertEqual(self.app.engine.memory.read('RemoteRack:5:O'), 29)

                blocked_module = 'LineBridge' if bridged else 'RemoteRack'
                self.connection('faulted', module=blocked_module, fault_code=5, fault_info=0)
                self.write('OutputCommand', 45)
                self.assertEqual(self.step()['immediate_outputs'], captured)
                self.connection('running', module=blocked_module)
                self.assertEqual(self.step()['immediate_outputs'], [
                    captured[0] | dict(value=45, sequence=2, scan=5, simulation_ms=50)])

    def test_remote_output_cannot_match_a_local_slot_or_ambiguous_rack_slot(self):
        state = self.load(lambda root: self.remote_rack_output(root, tag_slot=2))
        self.assertTrue(any('IOT requires' in blocker for blocker in state['blockers']), state['blockers'])

        # Adding a second child to rack slot 5 invalidates both slot routes.
        def duplicate(root):
            self.remote_rack_output(root)
            modules = root.find('./Controller/Modules')
            sibling = ET.fromstring(ET.tostring(modules.find('Module[@Name="RemoteCoils"]')))
            sibling.set('Name', 'DuplicateCoils')
            modules.append(sibling)

        state = self.load(duplicate)
        self.assertTrue(any('IOT requires' in blocker for blocker in state['blockers']), state['blockers'])

    def test_named_ipv4_outputs_require_running_path_and_retain_sample_when_blocked(self):
        for bridged in (False, True):
            with self.subTest(bridged=bridged):
                self.assertEqual(self.load(lambda root: self.named_output(root, bridged=bridged))['blockers'], [])
                self.write('SendImmediate', True)
                self.assertEqual(self.step()['immediate_outputs'], [])
                self.connection('running', module='NetworkOutput')
                captured = self.step()['immediate_outputs']
                self.assertEqual(captured, [
                    dict(module='NetworkOutput', tag='NetworkOutput:O', value=17, sequence=1, scan=2, simulation_ms=20)])
                self.assertEqual(self.snapshot()['immediate_outputs'], captured)
                self.assertEqual(self.app.engine.memory.read('NetworkOutput:O'), 29)

                blocked_module = 'LineBridge' if bridged else 'NetworkOutput'
                self.connection('faulted', module=blocked_module, fault_code=5, fault_info=0)
                self.write('OutputCommand', 45)
                self.assertEqual(self.step()['immediate_outputs'], captured)
                self.connection('running', module=blocked_module)
                self.assertEqual(self.step()['immediate_outputs'], [
                    captured[0] | dict(value=45, sequence=2, scan=4, simulation_ms=40)])

    def test_named_output_rejects_invalid_or_ambiguous_ipv4_route(self):
        for address in ('invalid', '192.0.2.42'):
            state = self.load(lambda root: self.named_output(root, address=address))
            self.assertTrue(any('IOT requires' in blocker for blocker in state['blockers']), state['blockers'])

    def test_open_output_captures_earlier_value_and_retains_sequence(self):
        self.assertEqual(self.load()['blockers'],[])
        self.write('SendImmediate',True)
        self.connection('running')
        self.assertEqual(self.step()['immediate_outputs'],[])  # Rack is inhibited.
        self.open_output()
        state = self.step()
        sample = dict(module='RackOutput',tag='Local:2:O',value=17,sequence=1,scan=2,simulation_ms=20)
        self.assertEqual(state['immediate_outputs'],[sample])
        self.assertEqual(self.snapshot()['immediate_outputs'],[sample])
        self.assertEqual(self.app.engine.memory.read('Local:2:O'),29)

        self.write('OutputCommand',45)
        self.write('SendImmediate',False)
        self.assertEqual(self.step()['immediate_outputs'],[sample])
        self.connection('faulted',fault_code=5,fault_info=0)
        self.write('SendImmediate',True)
        self.assertEqual(self.step()['immediate_outputs'],[sample])
        self.connection('running')
        retry = self.step()['immediate_outputs']
        self.assertEqual(retry,[sample | dict(value=45,sequence=2,scan=5,simulation_ms=50)])
        self.assertEqual(self.app.command('reset',{})['immediate_outputs'],[])
        self.assertNotIn('immediate_outputs',self.snapshot())

    def test_late_fault_rolls_back_new_output_and_keeps_published_sample(self):
        def add_fault(root):
            routine = root.find('.//Routine[@Name="Main"]/RLLContent')
            rung = ET.SubElement(routine,'Rung',Number='17',Type='N')
            ET.SubElement(rung,'Text').text = 'XIC(ReadModule)DIV(1,0,OutputCommand);'

        self.assertEqual(self.load(add_fault)['blockers'],[])
        self.open_output()
        self.write('SendImmediate',True)
        before = self.step()['immediate_outputs']
        self.write('OutputCommand',45)
        self.write('ReadModule',True)
        with self.assertRaisesRegex(ModelError,'Scan rolled back'):
            self.step()
        self.assertEqual(self.app.engine.scan_count,1)
        self.assertEqual(self.snapshot()['immediate_outputs'],before)
        self.assertEqual(self.app.engine.memory.read('Local:2:O'),29)

    def test_multiple_sends_keep_only_the_last_committed_image(self):
        def configure(root):
            text = root.find('.//Routine[@Name="Main"]/RLLContent/Rung[@Number="16"]/Text')
            text.text = ('XIC(SendImmediate)MOV(17,Local:2:O)IOT(Local:2:O)'
                         'MOV(21,Local:2:O)IOT(Local:2:O)MOV(29,Local:2:O);')

        self.assertEqual(self.load(configure)['blockers'],[])
        self.open_output()
        self.write('SendImmediate',True)
        state = self.step()
        self.assertEqual(state['immediate_outputs'],[
            dict(module='RackOutput',tag='Local:2:O',value=21,sequence=2,scan=1,simulation_ms=10)])
        self.assertEqual(self.snapshot()['immediate_outputs'],state['immediate_outputs'])
        self.assertEqual(self.app.engine.memory.read('Local:2:O'),29)

    def test_flat_record_and_array_images_are_copied_with_exact_values(self):
        def configure(root, record):
            tag = root.find('.//Tag[@Name="Local:2:O"]')
            decorated = tag.find('Data')
            decorated.clear()
            decorated.set('Format','Decorated')
            text = root.find('.//Routine[@Name="Main"]/RLLContent/Rung[@Number="16"]/Text')
            if record:
                tag.set('DataType','TestOutput')
                dtype = ET.SubElement(root.find('./Controller/DataTypes'),'DataType',
                                      Name='TestOutput',Family='NoFamily',Class='User')
                members = ET.SubElement(dtype,'Members')
                for name,kind in [('Value','DINT'),('Valid','BOOL')]:
                    ET.SubElement(members,'Member',Name=name,DataType=kind,Dimension='0',Hidden='false')
                obj = ET.SubElement(decorated,'Structure',DataType='TestOutput')
                ET.SubElement(obj,'DataValueMember',Name='Value',DataType='DINT',Value='7')
                ET.SubElement(obj,'DataValueMember',Name='Valid',DataType='BOOL',Value='1')
                target = 'Local:2:O.Value'
            else:
                tag.set('Dimensions','2')
                obj = ET.SubElement(decorated,'Array',DataType='DINT',Dimensions='2')
                ET.SubElement(obj,'Element',Index='[0]',Value='7')
                ET.SubElement(obj,'Element',Index='[1]',Value='8')
                target = 'Local:2:O[0]'
            text.text = f'XIC(SendImmediate)IOT(Local:2:O)MOV(29,{target});'

        for record,expected in ((True,{'Value':7,'Valid':True}),(False,[7,8])):
            with self.subTest(record=record):
                self.assertEqual(self.load(lambda root:configure(root,record))['blockers'],[])
                self.open_output()
                self.write('SendImmediate',True)
                self.assertEqual(self.step()['immediate_outputs'][0]['value'],expected)
                self.assertEqual(self.snapshot()['immediate_outputs'][0]['value'],expected)

    def test_unqualified_operand_and_unknown_output_guard(self):
        def logic(root, text):
            root.find('.//Routine[@Name="Main"]/RLLContent/Rung[@Number="16"]/Text').text = text

        for tag in ('OutputCommand','Local:2:O.0','Local:3:O'):
            state = self.load(lambda root:logic(root,f'AFI()IOT({tag});'))
            self.assertTrue(any('IOT requires' in blocker or 'IOT output slot' in blocker for blocker in state['blockers']))
        self.assertEqual(self.load(lambda root:logic(root,'XIC(SendImmediate)IOT(Local:2:O);'))['blockers'],[])
        self.open_output()
        self.write('SendImmediate',True)
        self.app.engine.memory.values['local:2:o'] = None
        with self.assertRaisesRegex(ModelError,'IOT output contains unknown data'):
            self.step()
        self.assertNotIn('immediate_outputs',self.snapshot())
