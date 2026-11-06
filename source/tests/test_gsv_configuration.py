"""Typed source-bound GSV settings, language bindings and rollback."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
import test_string_operations as strings


def scalar(tags,name,dtype,value=-7):
    tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base')
    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))


def device_buffer(root, *, dtype='SINT', count=36, constant=False):
    dims=str(count)
    tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='DeviceBytes',DataType=dtype,
                     TagType='Base',Dimensions=dims,Constant=str(constant).lower())
    array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions=dims)
    for i in (0,count-1):
        E.SubElement(array,'Element',Index=f'[{i}]',Value='-1')


def controller_flags(root, *, rpi='true', redundancy='false', retain='true', firmware='1'):
    controller=root.find('Controller')
    controller.attrib.update(CanUseRPIFromProducer=rpi,InhibitAutomaticFirmwareUpdate=firmware)
    E.SubElement(controller,'RedundancyInfo',Enabled=redundancy,KeepTestEditsOnSwitchOver=retain)
    for name in ('RedundancyByte','RetentionByte'):
        scalar(controller.find('Tags'),name,'SINT')


class GsvConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,logic,*,st=False,mutate=None,harness=False):
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/TaskLab.L5X').getroot()
        controller=root.find('Controller');controller.set('TimeSlice','30');controller.set('ShareUnusedTimeSlice','0')
        tags=controller.find('Tags')
        for name,dtype,value in (('Out','DINT',-7),('PriorityOut','INT',-7),('Index','DINT',0),('Limit','DINT',2),('Flag','BOOL',0)):
            scalar(tags,name,dtype,value)
        tag=E.SubElement(tags,'Tag',Name='NameOut',DataType='STRING',TagType='Base')
        strings.string_data(E.SubElement(tag,'Data',Format='Decorated'),'SAVED')
        routine=controller.find('./Programs/Program[@Name="BackgroundProgram"]/Routines/Routine[@Name="Main"]')
        for node in list(routine):routine.remove(node)
        routine.set('Type','ST' if st else 'RLL');content=E.SubElement(routine,'STContent' if st else 'RLLContent')
        for i,text in enumerate(logic.split('\n') if isinstance(logic,str) else logic):
            if st:E.SubElement(content,'Line',Number=str(i)).text=text
            else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'fixture.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='BackgroundProgram/Main')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_task_rate_and_watchdog_are_microseconds_with_exact_dint_destinations(self):
        for task,attribute,expected in (('FastTask','Rate',10000),('SlowTask','Rate',25000),
                                        ('FastTask','Watchdog',500000),('BackgroundTask','Watchdog',500000)):
            for st in (False,True):
                e=self.checked([f'GSV(Task,{task},{attribute},Out);'],st=st);e.step();self.assertEqual(e.memory.read('Out'),expected)

    def test_periodic_priority_uses_native_int_and_boolean_settings_use_dint(self):
        for task,priority in (('FastTask',2),('SlowTask',5)):
            e=self.checked([f'GSV(Task,{task},Priority,PriorityOut);']);e.step();self.assertEqual(e.memory.read('PriorityOut'),priority)
        for attr,field in (('InhibitTask','InhibitTask'),('DisableUpdateOutputs','DisableUpdateOutputs')):
            for value in ('true','false'):
                def setting(root):root.find('./Controller/Tasks/Task[@Name="SlowTask"]').set(field,value)
                e=self.checked([f'GSV(Task,SlowTask,{attr},Out);'],mutate=setting);e.step()
                self.assertEqual(e.memory.read('Out'),int(value=='true'))

    def test_controller_timeslice_and_sharing_require_explicit_settings(self):
        for attr,expected in (('TimeSlice',30),('ShareUnusedTimeSlice',0)):
            e=self.checked([f'GSV(Controller,,{attr},PriorityOut);']);e.step();self.assertEqual(e.memory.read('PriorityOut'),expected)
            def omitted(root):root.find('Controller').attrib.pop(attr)
            e=self.engine([f'GSV(Controller,,{attr},PriorityOut);'],mutate=omitted)
            self.assertTrue(e.blockers);self.assertIn('explicit',str(e.blockers))

    def test_controller_setting_case_or_namespace_shadows_are_not_silent_source_overrides(self):
        for attr in ('TimeSlice','ShareUnusedTimeSlice'):
            for shadow in (attr.lower(),'{urn:ambiguous}'+attr):
                def ambiguous(root):root.find('Controller').set(shadow,'1')
                self.assertTrue(self.engine([f'GSV(Controller,,{attr},PriorityOut);'],mutate=ambiguous).blockers)

    def test_controller_and_task_names_copy_strings_and_preserve_unused_bytes(self):
        for cls,instance,expected in (('Controller','','TaskLab'),('Task','FastTask','FastTask'),('Task','BackgroundTask','BackgroundTask')):
            for st in (False,True):
                e=self.checked([f'GSV({cls},{instance},Name,NameOut);'],st=st)
                e.memory.write('NameOut','abcdefghijklmnopqrst');e.step();self.assertEqual(e.memory.string('NameOut'),expected)
                self.assertEqual(e.memory.read(f'NameOut.DATA[{len(expected)}]'),ord('abcdefghijklmnopqrst'[len(expected)]))

    def test_identifiers_are_case_insensitive_and_names_keep_source_spelling(self):
        e=self.checked(['GSV(tAsK,fAsTtAsK,rAtE,Out);','GSV(TASK,fasttask,NAME,NameOut);']);e.step()
        self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.string('NameOut'),'FastTask')

    def test_explicit_controller_flags_in_ladder_and_st_have_exact_types(self):
        fields=('CanUseRPIFromProducer','RedundancyEnabled','KeepTestEditsOnSwitchover','InhibitAutomaticFirmwareUpdate')
        destinations=('Out','RedundancyByte','RetentionByte','Flag')
        calls=[f'GSV(cOnTrOlLeR,,{attr},{tag});' for attr,tag in zip(fields,destinations,strict=True)]
        for st in (False,True):
            for enabled in (False,True):
                with self.subTest(st=st,enabled=enabled):
                    def source(root):
                        text=str(enabled).lower()
                        controller_flags(root,rpi=text,redundancy=str(not enabled).lower(),retain=text,firmware=str(int(enabled)))
                    engine=self.checked(calls,st=st,mutate=source)
                    engine.memory.values['flag']=None
                    engine.step()
                    values=tuple(engine.memory.read(tag) for tag in destinations)
                    self.assertEqual(values,(int(enabled),int(not enabled),int(enabled),enabled))
                    self.assertIs(values[-1],enabled)

    def test_controller_flags_withhold_missing_malformed_and_ambiguous_sources(self):
        cases=(
            ('CanUseRPIFromProducer','Out',lambda c,n:c.attrib.pop('CanUseRPIFromProducer')),
            ('CanUseRPIFromProducer','Out',lambda c,n:c.set('CanUseRPIFromProducerUId','true')),
            ('InhibitAutomaticFirmwareUpdate','Flag',lambda c,n:c.set('InhibitAutomaticFirmwareUpdate','255')),
            ('InhibitAutomaticFirmwareUpdate','Flag',lambda c,n:c.attrib.pop('InhibitAutomaticFirmwareUpdate')),
            ('KeepTestEditsOnSwitchover','RetentionByte',lambda c,n:n.attrib.pop('KeepTestEditsOnSwitchOver')),
            ('KeepTestEditsOnSwitchover','RetentionByte',lambda c,n:E.SubElement(c.find('DataTypes'),'{other}RedundancyInfo')),
            ('RedundancyEnabled','RedundancyByte',lambda c,n:E.SubElement(c,'RedundancyInfo',Enabled='false')),
            ('RedundancyEnabled','RedundancyByte',lambda c,n:n.set('Enabled','yes')),
            ('RedundancyEnabled','RedundancyByte',lambda c,n:n.set('Use','Context')),
        )
        for index,(attr,tag,modify) in enumerate(cases):
            with self.subTest(attribute=attr,case=index):
                def malformed(root):
                    controller_flags(root)
                    c=root.find('Controller')
                    modify(c,c.find('RedundancyInfo'))
                engine=self.engine([f'GSV(Controller,,{attr},{tag});'],mutate=malformed)
                self.assertTrue(any('explicit 0/1 setting' in error for error in engine.blockers),engine.blockers)

    def test_controller_flags_reject_wrong_destinations_and_remain_read_only(self):
        for call in ('GSV(Controller,,CanUseRPIFromProducer,PriorityOut);',
                     'GSV(Controller,,KeepTestEditsOnSwitchover,Out);',
                     'GSV(Controller,,RedundancyEnabled,Flag);',
                     'GSV(Controller,,InhibitAutomaticFirmwareUpdate,Out.0);',
                     'SSV(Controller,,InhibitAutomaticFirmwareUpdate,Flag);',
                     'GSV(Controller,THIS,CanUseRPIFromProducer,Out);'):
            self.assertTrue(self.engine([call],mutate=controller_flags).blockers,call)

    def test_module_status_reads_int_and_preserves_dint_upper_word_in_both_languages(self):
        for st in (False,True):
            for attr in ('LEDStatus','ForceStatus'):
                with self.subTest(st=st,attribute=attr):
                    calls=[f'GSV(mOdUlE,,{attr},PriorityOut);',f'GSV(Module,,{attr},Out);']
                    e=self.checked(calls,st=st)
                    e.memory.values['priorityout']=None
                    e.step()
                    self.assertEqual(e.memory.read('PriorityOut'),0)
                    self.assertEqual(e.memory.read('Out'),-65536)
                    skip='IF FALSE THEN '+calls[-1]+' END_IF;' if st else 'AFI()'+calls[-1]
                    e=self.checked([skip],st=st)
                    e.memory.values['out']=None
                    e.step()
                    self.assertIsNone(e.memory.values['out'])

    def test_module_status_requires_proven_source_and_a_blank_instance(self):
        for case in ('missing','external','forced','produced','consumed','encoded'):
            with self.subTest(case=case):
                def source(root):
                    controller=root.find('Controller')
                    if case=='missing':controller.remove(controller.find('Modules'))
                    elif case=='external':E.SubElement(controller.find('Modules'),'Module',Name='Remote')
                    elif case=='forced':E.SubElement(controller,'ForceData')
                    elif case=='encoded':E.SubElement(controller,'EncodedData')
                    else:controller.find('./Tags/Tag').set('TagType',case.title())
                e=self.engine(['GSV(Module,,ForceStatus,Out);'],mutate=source)
                self.assertTrue(any('complete controller-only I/O map' in error for error in e.blockers),e.blockers)
        for call in ('GSV(Module,Local,ForceStatus,Out);','GSV(Module,,EntryStatus,Out);',
                     'GSV(Module,,LEDStatus,Flag);','GSV(Module,,ForceStatus,Out.0);',
                     'SSV(Module,,LEDStatus,Out);'):
            self.assertTrue(self.engine([call]).blockers,call)

    def test_module_status_validates_indirect_dint_on_execution_and_rolls_back(self):
        def buffer(root):device_buffer(root,dtype='DINT',count=3)
        e=self.checked(['GSV(Module,,LEDStatus,PriorityOut);',
                        'GSV(Module,,ForceStatus,DeviceBytes[Index]);'],mutate=buffer)
        e.memory.write('Index',1)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'preserve its upper word'):
            e.step()
        self.assertEqual(e.memory.values,before)
        self.assertEqual((e.time_ms,e.scan_count),(0,0))
        e.memory.write('DeviceBytes[1]',0x1234FFFF);e.step()
        self.assertEqual(e.memory.read('DeviceBytes'),[-1,0x12340000,-1])
        e=self.engine('FOR Index:=0 TO Out DO GSV(Module,,ForceStatus,Out); END_FOR;',st=True)
        self.assertTrue(any('bounds/step' in error for error in e.blockers),e.blockers)

    @staticmethod
    def add_rack_module(root, *, inhibited='true', major_fault='true', parent='Local'):
        modules = root.find('./Controller/Modules')
        E.SubElement(modules, 'Module', Name='Local', ParentModule='Local',
                     CatalogNumber='1756-L85E', Vendor='1', ProductType='14')
        module = E.SubElement(modules, 'Module', Name='RackIO', ParentModule=parent,
                              CatalogNumber='1756-OB16D', ProductType='7')
        if inhibited is not None:
            module.set('Inhibited', inhibited)
        if major_fault is not None:
            module.set('MajorFault', major_fault)
        return module

    @classmethod
    def add_rack_path(cls, root, *, slot='2', controller_slot='0'):
        module = cls.add_rack_module(root)
        local = root.find('./Controller/Modules/Module[@Name="Local"]')
        for item in (local, module):
            item.set('ParentModPortId', '1')
        controller_port = E.SubElement(E.SubElement(local, 'Ports'), 'Port', Id='1',
                                       Type='ICP', Address=controller_slot, Upstream='false')
        E.SubElement(controller_port, 'Bus', Size='17')
        E.SubElement(E.SubElement(module, 'Ports'), 'Port', Id='1', Type='ICP',
                     Address=slot, Upstream='true')
        return module

    def test_module_path_writes_counted_port_and_slot_in_ladder_and_st(self):
        for st, slot, cpu in ((False, '16', '0'), (True, '0', '2')):
            with self.subTest(st=st):
                def source(root):
                    self.add_rack_path(root, slot=slot, controller_slot=cpu)
                    device_buffer(root, count=6)
                e = self.checked(['GSV(Module,rAcKiO,Path,DeviceBytes[1]);'], st=st, mutate=source)
                e.step()
                self.assertEqual(e.memory.read('DeviceBytes'), [-1, 2, 0, 1, int(slot), -1])
                self.assertFalse(e.project.io_map.empty)
                self.assertIsNone(e.project.io_map.connection_class_attributes())
                self.assertEqual(e.project.io_map.description()['named_backplane_paths'], 1)

    @classmethod
    def add_ethernet_path(cls, root, *, bridged=False, address='192.0.2.42'):
        rack = cls.add_rack_path(root, slot='3')
        modules = root.find('./Controller/Modules')
        parent = rack if bridged else modules.find('Module[@Name="Local"]')
        if bridged:
            rack.attrib.update(CatalogNumber='1756-EN2TR', ProductType='12', Vendor='1')
        E.SubElement(parent.find('Ports'), 'Port', Id='2', Type='Ethernet', Upstream='false')
        child = E.SubElement(modules, 'Module', Name='PointRemote', CatalogNumber='1734-AENTR',
                             ProductType='12', ParentModule=parent.get('Name'), ParentModPortId='2',
                             Inhibited='true', MajorFault='false')
        E.SubElement(E.SubElement(child, 'Ports'), 'Port', Id='1', Type='Ethernet',
                     Address=address, Upstream='true')
        return parent, child

    @classmethod
    def add_remote_backplane(cls, root, *, bridged=False, adapter_slot='0', target_slot='4'):
        _, adapter = cls.add_ethernet_path(root, bridged=bridged, address='192.0.2.7')
        adapter.attrib.update(CatalogNumber='1756-EN2TR', Vendor='1')
        ports = adapter.find('Ports')
        ports.find('Port').set('Id', '2')
        backplane = E.SubElement(ports, 'Port', Id='1', Type='ICP', Address=adapter_slot, Upstream='false')
        E.SubElement(backplane, 'Bus', Size='7')
        module = E.SubElement(root.find('./Controller/Modules'), 'Module', Name='RemoteInput',
                              CatalogNumber='1756-IB16', ProductType='7', ParentModule='PointRemote',
                              ParentModPortId='1', Inhibited='true', MajorFault='false')
        E.SubElement(E.SubElement(module, 'Ports'), 'Port', Id='1', Type='ICP',
                     Address=target_slot, Upstream='true')
        return adapter, module

    def test_entry_status_waits_for_an_inhibited_parent_or_ancestor(self):
        for st, bridged in ((False, False), (True, True)):
            with self.subTest(bridged=bridged):
                def source(root):
                    adapter, child = self.add_remote_backplane(root, bridged=bridged)
                    child.set('Inhibited', 'false')
                    if bridged:
                        root.find('./Controller/Modules/Module[@Name="RackIO"]').set('Inhibited', 'true')
                        adapter.set('Inhibited', 'false')
                    else:
                        adapter.set('Inhibited', 'true')
                e = self.checked(['GSV(Module,RemoteInput,EntryStatus,Out);'], st=st, mutate=source)
                e.memory.write('Out', 0x1234ffff)
                e.step()
                self.assertEqual(e.memory.read('Out'), 0x12347000)

    def test_entry_status_follows_live_ancestor_mode_and_rolls_back_on_unknown_state(self):
        def source(root):
            adapter, child = self.add_remote_backplane(root, bridged=True)
            root.find('./Controller/Modules/Module[@Name="RackIO"]').set('Inhibited', 'false')
            adapter.set('Inhibited', 'false')
            child.set('Inhibited', 'false')
        for st in (False, True):
            with self.subTest(st=st):
                setter = 'SSV(Module,RackIO,Mode,PriorityOut);'
                guarded = 'IF Flag THEN ' + setter + ' END_IF;' if st else 'XIC(Flag)' + setter
                e = self.checked([guarded, 'GSV(Module,RemoteInput,EntryStatus,Out);'], st=st, mutate=source)
                e.memory.write('Flag', True)
                e.memory.write('PriorityOut', 4)
                e.step()
                self.assertEqual(e.memory.read('Out'), -65536 + 0x7000)
                e.memory.write('PriorityOut', 0)
                before = copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError, 'no modeled parent is inhibited'):
                    e.step()
                self.assertEqual(e.memory.values, before)
                self.assertEqual(e.scan_count, 1)
                e.memory.write('Flag', False)
                e.step()
                self.assertEqual(e.memory.read('Out'), -65536 + 0x7000)

    def test_entry_status_keeps_own_inhibit_precedence_and_requires_explicit_source(self):
        def source(root):
            adapter, child = self.add_remote_backplane(root)
            adapter.set('Inhibited', 'true')
            return child
        e = self.checked(['GSV(Module,RemoteInput,EntryStatus,PriorityOut);'], mutate=source)
        e.step()
        self.assertEqual(e.memory.read('PriorityOut'), 0x6000)

        def missing_target(root):
            del source(root).attrib['Inhibited']
        e = self.engine(['GSV(Module,RemoteInput,EntryStatus,PriorityOut);'], mutate=missing_target)
        self.assertTrue(any('requires an explicit source Inhibited setting' in error for error in e.blockers))

    @classmethod
    def add_led_inventory(cls, root, *, second_inhibited='true', extra=False):
        first = cls.add_rack_path(root, slot='2')
        first.set('Inhibited', 'false')
        modules = root.find('./Controller/Modules')
        second = copy.deepcopy(first)
        second.attrib.update(Name='RackOther', Inhibited=second_inhibited)
        second.find('./Ports/Port').set('Address', '3')
        modules.append(second)
        if extra:
            third = copy.deepcopy(first)
            third.set('Name', 'RackUnknown')
            third.find('./Ports/Port').set('Address', '4')
            modules.append(third)
        return first, second

    def test_module_led_status_reports_none_some_and_all_running(self):
        from logixlab.gsv_configuration import configure_module_connection

        for st in (False, True):
            with self.subTest(st=st):
                setter = 'SSV(Module,RackOther,Mode,PriorityOut);'
                gated = 'IF Flag THEN ' + setter + ' END_IF;' if st else 'XIC(Flag)' + setter
                e = self.checked([gated, 'GSV(Module,,LEDStatus,Out);'], st=st,
                                 mutate=self.add_led_inventory)
                request = {'module':'RackIO', 'project_generation':1}
                e.memory.write('Out', 0x1234ffff)
                configure_module_connection(e, {**request, 'state':'faulted',
                                                 'fault_code':0x204, 'fault_info':0})
                e.step()
                self.assertEqual(e.memory.read('Out'), 0x12340001)
                configure_module_connection(e, {**request, 'state':'running'})
                e.step()
                self.assertEqual(e.memory.read('Out'), 0x12340002)
                configure_module_connection(e, {**request, 'module':'RackOther', 'state':'running'})
                e.memory.write('PriorityOut', 0)
                e.memory.write('Flag', True)
                e.step()
                self.assertEqual(e.memory.read('Out'), 0x12340003)
                self.assertFalse(e.project.io_map.empty)
                self.assertEqual(e.project.io_map.attributes(), {})

    def test_module_led_status_can_prove_mixed_but_rolls_back_ambiguous_reads(self):
        from logixlab.gsv_configuration import configure_module_connection

        calls = ['MOV(123,Limit);', 'XIC(Flag)GSV(Module,,LEDStatus,Out);']
        e = self.checked(calls, mutate=lambda root: self.add_led_inventory(root, extra=True))
        e.step()
        self.assertEqual(e.memory.read('Out'), -7)
        e.memory.write('Flag', True)
        e.memory.write('Limit', 0)
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, 'module states are unknown'):
            e.step()
        self.assertEqual(e.memory.values, before)
        self.assertEqual(e.scan_count, 1)
        configure_module_connection(e, {'module':'RackIO', 'project_generation':1, 'state':'running'})
        e.step()
        self.assertEqual(e.memory.read('Out'), -65536 + 2)

        e = self.checked(['GSV(Module,,LEDStatus,Out);'],
                         mutate=lambda root: self.add_led_inventory(root, second_inhibited='false'))
        configure_module_connection(e, {'module':'RackIO', 'project_generation':1, 'state':'running'})
        with self.assertRaisesRegex(ModelError, 'module states are unknown'):
            e.step()

    def test_module_led_status_requires_the_entire_supported_inventory(self):
        for case in ('unrouted', 'unknown-inhibit', 'opaque-module-data', 'unsupported-module'):
            with self.subTest(case=case):
                def source(root):
                    _, second = self.add_led_inventory(root)
                    if case == 'unrouted':
                        second.remove(second.find('Ports'))
                    elif case == 'unknown-inhibit':
                        del second.attrib['Inhibited']
                    elif case == 'opaque-module-data':
                        E.SubElement(second, 'Data', Format='Encoded')
                    else:
                        second.set('SafetyNetwork', '16#1')
                e = self.engine(['GSV(Module,,LEDStatus,Out);'], mutate=source)
                self.assertTrue(any('complete supported module inventory' in error for error in e.blockers))
                self.checked(['GSV(Module,RackIO,Mode,PriorityOut);'], mutate=source)

    def test_simulated_module_fault_values_have_logix_destination_widths(self):
        from logixlab.gsv_configuration import configure_module_connection

        def source(root):
            adapter, target = self.add_remote_backplane(root)
            adapter.set('Inhibited', 'false')
            target.set('Inhibited', 'false')

        calls = ['GSV(Module,RemoteInput,EntryStatus,PriorityOut);',
                 'GSV(Module,RemoteInput,FaultCode,Out);',
                 'GSV(Module,RemoteInput,FaultInfo,Limit);']
        e = self.checked(calls, st=True, mutate=source)
        configure_module_connection(e, {'module':'remoteinput', 'project_generation':1,
                                         'state':'faulted', 'fault_code':0xf001, 'fault_info':-42})
        e.memory.write('Out', 0x1234ffff)
        e.step()
        self.assertEqual((e.memory.read('PriorityOut'), e.memory.read('Out'), e.memory.read('Limit')),
                         (0x1000, 0x1234f001, -42))
        e = self.engine(['GSV(Module,RemoteInput,FaultInfo,PriorityOut);'], mutate=source)
        self.assertTrue(any('exact scalar DINT' in error for error in e.blockers))

    def test_simulated_faulted_parent_masks_child_connection_until_recovery(self):
        from logixlab.gsv_configuration import configure_module_connection

        def source(root):
            adapter, child = self.add_remote_backplane(root, bridged=True)
            child.set('Inhibited', 'false')
            adapter.set('Inhibited', 'false')
            root.find('./Controller/Modules/Module[@Name="RackIO"]').set('Inhibited', 'false')

        e = self.checked(['GSV(Module,RemoteInput,EntryStatus,PriorityOut);'], mutate=source)
        configure_module_connection(e, {'module':'RemoteInput', 'project_generation':1, 'state':'running'})
        configure_module_connection(e, {'module':'RackIO', 'project_generation':1,
                                         'state':'faulted', 'fault_code':0x204, 'fault_info':0})
        e.step()
        self.assertEqual(e.memory.read('PriorityOut'), 0x7000)
        configure_module_connection(e, {'module':'RackIO', 'project_generation':1, 'state':'running'})
        e.step()
        self.assertEqual(e.memory.read('PriorityOut'), 0x4000)

    def test_remote_backplane_path_appends_port_and_slot_to_the_counted_route(self):
        for st, prefix, adapter_slot, target_slot in (
                (False, b'', '0', '4'), (True, bytes((1, 3)), '4', '0')):
            with self.subTest(st=st):
                payload = prefix + bytes((18, 9)) + b'192.0.2.7' + bytes((0, 1, int(target_slot)))
                def source(root):
                    self.add_remote_backplane(root, bridged=st, adapter_slot=adapter_slot, target_slot=target_slot)
                    device_buffer(root, count=len(payload) + 4)
                calls = ['GSV(Module,RemoteInput,Path,DeviceBytes[1]);',
                         'GSV(Module,RemoteInput,Mode,PriorityOut);',
                         'GSV(Module,RemoteInput,EntryStatus,Out);']
                e = self.checked(calls, st=st, mutate=source)
                e.step()
                self.assertEqual(e.memory.read('DeviceBytes'), [-1, len(payload), 0, *payload, -1])
                self.assertEqual(e.memory.read('PriorityOut'), 4)
                self.assertEqual(e.memory.read('Out'), -65536 + 0x6000)
                self.assertFalse(e.project.io_map.empty)
                self.assertIsNone(e.project.io_map.connection_class_attributes())

    def test_remote_backplane_path_rejects_unproven_chassis_and_slot(self):
        for case in ('unknown-adapter', 'unsupported-port', 'missing-bus', 'no-adapter-slot',
                     'adapter-slot', 'outside-chassis', 'duplicate-slot', 'duplicate-ip',
                     'wrong-parent-port', 'short'):
            with self.subTest(case=case):
                def source(root):
                    adapter, module = self.add_remote_backplane(root, bridged=True)
                    backplane = adapter.find('./Ports/Port[@Id="1"]')
                    port = module.find('./Ports/Port')
                    modules = root.find('./Controller/Modules')
                    if case == 'unknown-adapter':
                        adapter.set('CatalogNumber', '1734-AENTR')
                    elif case == 'unsupported-port':
                        backplane.set('Type', 'RIO')
                    elif case == 'missing-bus':
                        backplane.remove(backplane.find('Bus'))
                    elif case == 'no-adapter-slot':
                        del backplane.attrib['Address']
                    elif case == 'adapter-slot':
                        port.set('Address', '0')
                    elif case == 'outside-chassis':
                        port.set('Address', '7')
                    elif case in ('duplicate-slot', 'duplicate-ip'):
                        other = copy.deepcopy(module if case == 'duplicate-slot' else adapter)
                        other.set('Name', 'Duplicate')
                        modules.append(other)
                    elif case == 'wrong-parent-port':
                        module.set('ParentModPortId', '2')
                    device_buffer(root, count=18 if case == 'short' else 20)
                e = self.engine(['GSV(Module,RemoteInput,Path,DeviceBytes[1]);'], mutate=source)
                self.assertTrue(any('GSV Module' in error for error in e.blockers), e.blockers)

    def test_module_ethernet_paths_encode_length_and_padding(self):
        for st, bridged, address, payload in (
                (False, False, '192.0.2.42', bytes((18, 10)) + b'192.0.2.42'),
                (True, True, '192.0.2.7', bytes((1, 3, 18, 9)) + b'192.0.2.7' + bytes(1))):
            with self.subTest(st=st, bridged=bridged):
                def source(root):
                    self.add_ethernet_path(root, bridged=bridged, address=address)
                    device_buffer(root, count=len(payload) + 4)
                setter = 'SSV(Module,PointRemote,Mode,PriorityOut);'
                guarded = 'IF Flag THEN ' + setter + ' END_IF;' if st else 'XIC(Flag)' + setter
                calls = [guarded, 'GSV(Module,pointremote,Path,DeviceBytes[1]);',
                         'GSV(Module,PointRemote,Mode,PriorityOut);',
                         'GSV(Module,PointRemote,EntryStatus,Out);']
                e = self.checked(calls, st=st, mutate=source)
                e.step()
                self.assertEqual(e.memory.read('DeviceBytes'), [-1, len(payload), 0, *payload, -1])
                self.assertEqual(e.memory.read('PriorityOut'), 4)
                self.assertEqual(e.memory.read('Out'), -65536 + 0x6000)
                self.assertFalse(e.project.io_map.empty)
                self.assertIsNone(e.project.io_map.connection_class_attributes())
                self.assertEqual(e.project.io_map.description()['named_ethernet_paths'], 1)
                e.memory.write('Flag', True)
                e.memory.write('PriorityOut', 5)
                e.step()
                self.assertEqual(e.memory.read('PriorityOut'), 5)
                self.assertEqual(e.memory.read('DeviceBytes'), [-1, len(payload), 0, *payload, -1])

    def test_module_ethernet_path_rejects_unproven_routes(self):
        for case in ('hostname', 'unspecified', 'multicast', 'duplicate-address', 'own-address',
                     'no-egress', 'duplicate-egress', 'unqualified-bridge', 'wrong-parent-port',
                     'ambiguous-upstream', 'ipv6', 'short'):
            with self.subTest(case=case):
                def source(root):
                    parent, child = self.add_ethernet_path(root, bridged=True)
                    ports = child.find('Ports')
                    port = ports.find('Port')
                    if case in ('hostname', 'unspecified', 'multicast', 'ipv6'):
                        port.set('Address', {'hostname':'adapter.local', 'unspecified':'0.0.0.0',
                                             'multicast':'239.0.0.5', 'ipv6':'2001:db8::1'}[case])
                    elif case == 'duplicate-address':
                        duplicate = copy.deepcopy(child)
                        duplicate.set('Name', 'Duplicate')
                        root.find('./Controller/Modules').append(duplicate)
                    elif case == 'own-address':
                        parent.find('./Ports/Port[@Id="2"]').set('Address', port.get('Address'))
                    elif case == 'no-egress':
                        parent.find('Ports').remove(parent.find('./Ports/Port[@Id="2"]'))
                    elif case == 'duplicate-egress':
                        parent.find('Ports').append(copy.deepcopy(parent.find('./Ports/Port[@Id="2"]')))
                    elif case == 'unqualified-bridge':
                        parent.set('CatalogNumber', 'Unqualified')
                    elif case == 'wrong-parent-port':
                        child.set('ParentModPortId', '1')
                    elif case == 'ambiguous-upstream':
                        E.SubElement(ports, 'Port', Id='2', Type='Ethernet', Upstream='true', Address='192.0.2.8')
                    device_buffer(root, count=10 if case == 'short' else 20)
                e = self.engine(['GSV(Module,PointRemote,Path,DeviceBytes[1]);'], mutate=source)
                self.assertTrue(any('GSV Module' in error for error in e.blockers), e.blockers)

    def test_module_ethernet_path_tracks_its_full_dynamic_write_window(self):
        def source(root):
            self.add_ethernet_path(root, bridged=True, address='192.0.2.7')
            device_buffer(root, count=18)
        call = 'GSV(Module,PointRemote,Path,DeviceBytes[Index]);'
        e = self.checked(['XIC(Flag)' + call], mutate=source)
        e.memory.write('Flag', True)
        e.memory.write('Index', 3)
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, '16 writable contiguous SINT'):
            e.step()
        self.assertEqual(e.memory.values, before)
        e.memory.write('Index', 1)
        e.step()
        self.assertEqual(e.memory.read('DeviceBytes'), [-1, 14, 0, 1, 3, 18, 9, *b'192.0.2.7', 0, -1])
        loop = 'FOR Index:=0 TO DeviceBytes[16] DO GSV(Module,PointRemote,Path,DeviceBytes[1]); END_FOR;'
        e = self.engine(loop, st=True, mutate=source)
        self.assertTrue(any('bounds/step' in error for error in e.blockers), e.blockers)

    def test_module_path_defers_live_selection_and_rolls_back_a_short_window(self):
        def source(root):
            self.add_rack_path(root)
            device_buffer(root, count=6)
        call = 'GSV(Module,RackIO,Path,DeviceBytes[Index]);'
        e = self.checked(['MOV(12,Out);', 'XIC(Flag)' + call], mutate=source)
        e.memory.write('Index', 99)
        e.step()
        self.assertEqual(e.memory.read('DeviceBytes'), [-1, None, None, None, None, -1])
        e.memory.write('Out', -8)
        e.memory.write('Flag', True)
        for index, message in ((99, 'outside bounds'), (3, '4 writable contiguous SINT')):
            e.memory.write('Index', index)
            before = copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError, message):
                e.step()
            self.assertEqual(e.memory.values, before)
            self.assertEqual(e.scan_count, 1)
        e.memory.write('Index', 2)
        e.step()
        self.assertEqual(e.memory.read('DeviceBytes'), [-1, None, 2, 0, 1, 2])

        loop = 'FOR Index:=0 TO DeviceBytes[4] DO GSV(Module,RackIO,Path,DeviceBytes[1]); END_FOR;'
        e = self.engine(loop, st=True, mutate=source)
        self.assertTrue(any('bounds/step' in error for error in e.blockers), e.blockers)

    def test_module_path_requires_valid_source_geometry_and_array_shape(self):
        for case in ('missing', 'root-port', 'out-of-chassis', 'root-slot', 'duplicate',
                     'duplicate-port', 'not-upstream', 'other-parent-port', 'short',
                     'other-type', 'matrix', 'constant'):
            with self.subTest(case=case):
                def source(root):
                    module = self.add_rack_path(root)
                    modules = root.find('./Controller/Modules')
                    port = module.find('./Ports/Port')
                    if case == 'missing':
                        module.remove(module.find('Ports'))
                    elif case == 'root-port':
                        modules.find('./Module/Ports/Port').set('Type', 'Ethernet')
                    elif case == 'out-of-chassis':
                        port.set('Address', '17')
                    elif case == 'root-slot':
                        port.set('Address', '0')
                    elif case == 'duplicate':
                        duplicate = copy.deepcopy(module)
                        duplicate.set('Name', 'Other')
                        modules.append(duplicate)
                    elif case == 'duplicate-port':
                        module.find('Ports').append(copy.deepcopy(port))
                    elif case == 'not-upstream':
                        port.set('Upstream', 'false')
                    elif case == 'other-parent-port':
                        module.set('ParentModPortId', '2')
                    if case == 'matrix':
                        tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='DeviceBytes',
                                           DataType='SINT', TagType='Base', Dimensions='2,3')
                        array = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array',
                                             DataType='SINT', Dimensions='2,3')
                        E.SubElement(array, 'Element', Index='[0,0]', Value='-1')
                    else:
                        device_buffer(root, dtype='INT' if case == 'other-type' else 'SINT',
                                      count=3 if case == 'short' else 6, constant=case == 'constant')
                e = self.engine(['GSV(Module,RackIO,Path,DeviceBytes);'], mutate=source)
                self.assertTrue(any('Module Path' in error or 'Read-only destination' in error
                                    for error in e.blockers), e.blockers)
                e = self.checked(['GSV(Module,RackIO,Mode,PriorityOut);'], mutate=source)
                e.step()
                self.assertEqual(e.memory.read('PriorityOut'), 5)

    def test_named_module_mode_reads_source_bits_in_ladder_and_st(self):
        for st in (False, True):
            for inhibited, major_fault, expected in (('false','false',0), ('false','true',1),
                                                       ('true','false',4), ('true','true',5)):
                with self.subTest(st=st, inhibited=inhibited, major_fault=major_fault):
                    def source(root):
                        module = self.add_rack_module(root, inhibited=inhibited, major_fault=major_fault)
                        E.SubElement(E.SubElement(module, 'Communications'), 'ForceData')
                    e = self.checked(['GSV(Module,rAcKiO,Mode,PriorityOut);',
                                      'GSV(Module,RackIO,Mode,Out);'], st=st, mutate=source)
                    self.assertFalse(e.project.io_map.empty)
                    self.assertEqual(e.project.io_map.attributes(), {})
                    self.assertIsNone(e.project.io_map.connection_class_attributes())
                    e.memory.values['priorityout'] = None
                    e.memory.write('Out', -1)
                    e.step()
                    self.assertEqual(e.memory.read('PriorityOut'), expected)
                    self.assertEqual(e.memory.read('Out'), -65536 + expected)

    def test_named_module_entry_status_skips_unreached_destination_and_rolls_back(self):
        def source(root):
            self.add_rack_module(root, major_fault=None)
            device_buffer(root, dtype='DINT', count=3)
        e = self.checked(['GSV(Module,RackIO,EntryStatus,PriorityOut);',
                          'XIC(Flag)GSV(Module,RackIO,EntryStatus,DeviceBytes[Index]);'], mutate=source)
        e.memory.write('Index', 99)
        e.step()
        self.assertEqual(e.memory.read('PriorityOut'), 0x6000)
        e.memory.write('PriorityOut', -9)
        e.memory.write('Flag', True)
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            e.step()
        self.assertEqual(e.memory.values, before)
        self.assertEqual(e.scan_count, 1)
        e.memory.write('Index', 1)
        e.memory.write('DeviceBytes[1]', 0x1234ffff)
        e.step()
        self.assertEqual(e.memory.read('DeviceBytes'), [-1, 0x12346000, -1])

    def test_named_module_rejects_unsupported_attributes_and_ambiguous_source(self):
        for call in ('GSV(Module,,Mode,Out);', 'GSV(Module,Local,Mode,Out);',
                     'GSV(Module,RackIO,Mode,Flag);', 'GSV(Module,RackIO,FaultCode,Out);',
                     'GSV(Module,Unknown,Mode,Out);', 'GSV(Module,,LEDStatus,Out);',
                     'SSV(Module,RackIO,Mode,Out);', 'SSV(Module,RackIO,EntryStatus,PriorityOut);',
                     'SSV(Module,RackIO,Mode,4);'):
            with self.subTest(call=call):
                self.assertTrue(self.engine([call], mutate=self.add_rack_module).blockers)
        for case in ('duplicate', 'remote', 'no_root', 'context', 'bad_mode', 'missing_major_fault'):
            with self.subTest(case=case):
                def source(root):
                    module = self.add_rack_module(root)
                    modules = root.find('./Controller/Modules')
                    if case == 'duplicate':
                        E.SubElement(modules, 'Module', Name='rackio')
                    elif case == 'remote':
                        module.set('ParentModule', 'Bridge')
                    elif case == 'no_root':
                        modules.remove(modules.find('Module'))
                    elif case == 'context':
                        module.set('Use', 'Context')
                    elif case == 'bad_mode':
                        module.set('Inhibited', 'unknown')
                    else:
                        del module.attrib['MajorFault']
                self.assertTrue(self.engine(['GSV(Module,RackIO,Mode,Out);'], mutate=source).blockers)
        e = self.checked(['GSV(Module,RackIO,EntryStatus,Out);'],
                         mutate=lambda root: self.add_rack_module(root, inhibited='false'))
        with self.assertRaisesRegex(ModelError, 'unavailable while the module is uninhibited'):
            e.step()
        self.assertEqual(e.memory.read('Out'), -7)

    def test_module_mode_write_is_visible_to_later_reads_in_both_languages(self):
        for st in (False, True):
            with self.subTest(st=st):
                e = self.checked(['SSV(Module,rAcKiO,Mode,PriorityOut);',
                                  'GSV(Module,RackIO,Mode,Out);',
                                  'GSV(Module,RackIO,EntryStatus,PriorityOut);'], st=st,
                                 mutate=lambda root: self.add_rack_module(root, inhibited='false'))
                e.memory.write('PriorityOut', 4)
                e.step()
                self.assertEqual(e.memory.read('Out'), -65536 + 4)
                self.assertEqual(e.memory.read('PriorityOut'), 0x6000)
                self.assertEqual(e.project.io_map.named_module('RackIO').mode(), 1)

    def test_module_mode_set_skips_indirect_values_and_rejects_reserved_bits(self):
        def source(root):
            self.add_rack_module(root)
            device_buffer(root, dtype='INT', count=3)
        for st in (False, True):
            with self.subTest(st=st):
                call = 'SSV(Module,RackIO,Mode,DeviceBytes[Index]);'
                write = 'IF Flag THEN ' + call + ' END_IF;' if st else 'XIC(Flag)' + call
                e = self.checked([write, 'GSV(Module,RackIO,Mode,PriorityOut);'], st=st, mutate=source)
                e.memory.write('Index', 99)
                e.step()
                self.assertEqual(e.memory.read('PriorityOut'), 5)
                e.memory.write('Flag', True)
                with self.assertRaisesRegex(ModelError, 'outside bounds'):
                    e.step()
                e.memory.write('Index', 0)
                with self.assertRaisesRegex(ModelError, 'only bits 0 and 2'):
                    e.step()
                self.assertEqual(e.scan_count, 1)
                self.assertEqual(e.memory.read('PriorityOut'), 5)
                e.memory.write('Index', 1)
                with self.assertRaisesRegex(ModelError, 'Unknown initial'):
                    e.step()
                e.memory.write('DeviceBytes[1]', 0)
                e.step()
                self.assertEqual(e.memory.read('PriorityOut'), 0)

    def test_module_mode_override_rolls_back_and_survives_run_entry_and_routine_replacement(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container, xml_source

        logic = ['XIC(Flag)SSV(Module,RackIO,Mode,PriorityOut);',
                 'GSV(Module,RackIO,Mode,Out);',
                 'DIV(1,Limit,Limit);']
        e = self.checked(logic, mutate=self.add_rack_module)
        e.memory.write('Flag', True)
        e.memory.write('PriorityOut', 4)
        e.step()
        self.assertEqual(e.memory.read('Out'), -65536 + 4)
        e.memory.write('PriorityOut', 0)
        e.memory.write('Limit', 0)
        before = copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError, 'rolled back'):
            e.step()
        self.assertEqual(e.memory.values, before)
        self.assertEqual(e.scan_count, 1)
        e.memory.write('Flag', False)
        e.memory.write('Limit', 1)
        e.step()
        self.assertEqual(e.memory.read('Out'), -65536 + 4)
        e.enter_run()
        e.step()
        self.assertEqual(e.memory.read('Out'), -65536 + 4)

        read = 'GSV(Module,RackIO,Mode,PriorityOut);'
        wire = decode(container(E.tostring(xml_source(name='Main', text=read))))
        candidate, _ = prepare(e, wire, (read,), 'BackgroundProgram', 0)
        candidate.step()
        self.assertEqual(candidate.memory.read('PriorityOut'), 4)
        self.assertEqual(e.memory.read('PriorityOut'), 0)
        fresh = Engine(e.project)
        fresh.step()
        self.assertEqual(fresh.memory.read('Out'), -65536 + 5)

    def test_module_status_lab_runs_its_ladder_and_st_routines(self):
        path = Path(__file__).resolve().parents[1] / 'samples/ModuleStatusLab.L5X'
        e = Engine(Project(path))
        self.assertEqual(e.blockers, [])
        e.step()
        self.assertEqual(e.memory.read('StateWord'), -1)
        self.assertEqual(e.memory.read('ModeWord'), 0x1234ffff)
        self.assertEqual(e.memory.read('StMode'), -1)
        self.assertEqual(e.memory.read('PathBytes'), [-99, -7, -7, -7, -7, 99])
        self.assertFalse(e.memory.read('ModuleInhibited'))
        e.memory.write('ReadModule', True)
        e.step()
        self.assertEqual(e.memory.read('StateWord'), 0x6000)
        self.assertEqual(e.memory.read('ModeWord'), 0x12340005)
        self.assertEqual(e.memory.read('StMode'), 5)
        self.assertEqual(e.memory.read('PathBytes'), [-99, 2, 0, 1, 2, 99])
        self.assertEqual(e.memory.read('EthernetPath'), [-99, 12, 0, 18, 10, *b'192.0.2.42', 99])
        self.assertEqual(e.memory.read('RemotePath'), [-99, 14, 0, 18, 9, *b'192.0.2.7', 0, 1, 4, 99])
        self.assertEqual(e.memory.read('RemoteStatus'), 0x7000)
        self.assertTrue(e.memory.read('RemoteWaiting'))
        self.assertTrue(e.memory.read('ModuleInhibited'))
        e.memory.write('ApplyMode', True)
        e.memory.write('ModeCommand', 1)
        e.step()
        self.assertEqual(e.memory.read('ModeWord'), 0x12340001)
        self.assertEqual(e.memory.read('StMode'), 1)
        self.assertEqual(e.memory.read('StateWord'), 0x6000)
        self.assertFalse(e.memory.read('ModuleInhibited'))
        e.memory.write('ApplyMode', False)
        e.memory.write('ApplyModeST', True)
        e.memory.write('ModeCommand', 4)
        e.step()
        self.assertEqual(e.memory.read('ModeWord'), 0x12340004)
        self.assertEqual(e.memory.read('StMode'), 4)
        self.assertTrue(e.memory.read('ModuleInhibited'))

    def test_program_and_routine_names_match_source_case_in_ladder_and_st(self):
        for st in (False,True):
            for cls,instance,expected in (('Program','fAsTpRoGrAm','FastProgram'),
                                          ('Program','THIS','BackgroundProgram'),
                                          ('Routine','mAiN','Main'),
                                          ('Routine','THIS','Main')):
                with self.subTest(st=st,cls=cls,instance=instance):
                    e=self.checked([f'GSV({cls},{instance},Name,NameOut);'],st=st)
                    e.memory.write('NameOut','abcdefghijklmnopqrstuvwxyz')
                    e.step()
                    self.assertEqual(e.memory.string('NameOut'),expected)
                    self.assertEqual(e.memory.read(f'NameOut.DATA[{len(expected)}]'),ord('a')+len(expected))

    def test_task_instance_reads_exact_dint_and_uses_registry_order(self):
        for st in (False,True):
            for instance,slot in (('THIS',0),('FastTask',1),('sLoWtAsK',2)):
                with self.subTest(st=st,instance=instance):
                    e=self.checked([f'GSV(Task,{instance},Instance,Out);'],st=st)
                    e.step(25)
                    self.assertEqual(e.memory.read('Out'),slot)
        self.assertTrue(self.engine(['GSV(Task,FastTask,Instance,PriorityOut);']).blockers)
        self.assertTrue(self.engine(['GSV(Task,FastTask,Instance,Out);'],harness=True).blockers)

    def test_component_names_require_known_scope_and_protect_st_for_bounds(self):
        def other_routine(root):
            routines=root.find('./Controller/Programs/Program[@Name="FastProgram"]/Routines')
            extra=E.SubElement(routines,'Routine',Name='OtherOnly',Type='RLL')
            content=E.SubElement(extra,'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='NOP();'
        for line in ('GSV(Routine,OtherOnly,Name,NameOut);','GSV(Program,,Name,NameOut);',
                     'GSV(Program,Missing,Name,NameOut);','GSV(Routine,THIS,Name,Out);'):
            self.assertTrue(self.engine([line],mutate=other_routine).blockers,line)
        self.assertTrue(self.engine(['GSV(Program,THIS,Name,NameOut);'],harness=True).blockers)
        e=self.engine(['FOR Index := 0 TO NameOut.LEN DO GSV(Routine,THIS,Name,NameOut); END_FOR;'],st=True)
        self.assertTrue(any('bounds/step' in error for error in e.blockers),e.blockers)

    def test_controller_device_scalars_read_project_fields_in_both_languages(self):
        for st in (False,True):
            for model,code in zip(('L81E','L82E','L83E','L84E','L85E'),range(164,169),strict=True):
                with self.subTest(st=st,model=model):
                    fields=('ProductCode','Vendor','Type','ProductRev')
                    def source(root):
                        controller=root.find('Controller')
                        controller.attrib.update(ProcessorType='1756-'+model, MinorRev='201')
                        for field in fields:scalar(controller.find('Tags'),field,'INT')
                    calls=[f'GSV(cOnTrOlLeRdEvIcE,,{field},{field});' for field in fields]
                    e=self.checked(calls,st=st,mutate=source)
                    e.step()
                    self.assertEqual(tuple(e.memory.read(field) for field in fields),(code,1,14,-14045))

    def test_controller_device_requires_canonical_source_types_and_blank_instance(self):
        for attr,field,value in (('ProductRev','MinorRev',None),('ProductRev','MinorRev','256'),
                                 ('ProductRev','MinorRev','+11'),('ProductRev','minorrev','11'),
                                 ('Vendor','processortype','1756-L85E'),('Vendor','{shadow}MajorRev','35')):
            def malformed(root):
                settings=root.find('Controller').attrib
                if value is None:settings.pop(field)
                else:settings[field]=value
            e=self.engine([f'GSV(ControllerDevice,,{attr},PriorityOut);'],mutate=malformed)
            self.assertTrue(e.blockers,(attr,field,value))
        for text in ('GSV(ControllerDevice,THIS,ProductCode,PriorityOut);',
                     'GSV(ControllerDevice,,ProductCode,Out);',
                     'GSV(ControllerDevice,,ProductCode,PriorityOut.0);',
                     'GSV(ControllerDevice,,SerialNumber,Out);',
                     'GSV(ControllerDevice,,Status,Out);',
                     'GSV(ControllerDevice,,Status,PriorityOut.0);',
                     'SSV(ControllerDevice,,Status,PriorityOut);',
                     'SSV(ControllerDevice,,ProductRev,PriorityOut);'):
            self.assertTrue(self.engine([text]).blockers,text)

    def test_device_status_uses_one_entry_sample_and_rolls_back_on_fault(self):
        for st in (False,True):
            with self.subTest(st=st):
                later='Out := 1 / Limit;' if st else 'DIV(1,Limit,Out);'
                e=self.checked(['GSV(ControllerDevice,,Status,PriorityOut);',later],st=st)
                self.assertEqual(e.memory.read('PriorityOut'),-7)
                e.step();self.assertEqual(e.memory.read('PriorityOut'),0x3070)
                e.memory.write('Limit',0)
                before=copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError,'zero'):
                    e.step(running=True)
                self.assertEqual(e.memory.values,before)
                self.assertIsNone(e._scan_controller_status)
                e.memory.write('Limit',2);e.step()
                self.assertEqual(e.memory.read('PriorityOut'),0x3450)
                self.assertEqual(e.controller_mode(),'Program')
                e.step(running=True)
                self.assertEqual(e.memory.read('PriorityOut'),0x3060)

    def test_device_name_writes_a_counted_sint_window_and_preserves_neighbors(self):
        expected=list(bytes((9,))+b'1756-L85E')+[0]*23
        for st in (False,True):
            for ref,offset in (('DeviceBytes',0),('DeviceBytes[Index]',1)):
                with self.subTest(st=st,ref=ref):
                    call=f'GSV(ControllerDevice,,DeviceName,{ref});'
                    e=self.checked([call],st=st,mutate=device_buffer)
                    before=list(e.memory.read('DeviceBytes'))
                    e.memory.write('Index',offset);e.step()
                    self.assertEqual(e.memory.read('DeviceBytes'),before[:offset]+expected+before[offset+33:])
                    skip=f'IF FALSE THEN {call} END_IF;' if st else 'AFI()'+call
                    e=self.checked([skip],st=st,mutate=device_buffer)
                    e.step()
                    self.assertEqual(e.memory.read('DeviceBytes'),before)

    def test_device_name_rejects_short_readonly_and_wrong_type_windows(self):
        for options in ({'count':32},{'dtype':'USINT'},{'constant':True}):
            e=self.engine(['GSV(ControllerDevice,,DeviceName,DeviceBytes);'],
                          mutate=lambda root:device_buffer(root,**options))
            self.assertTrue(e.blockers,options)
        e=self.engine(['GSV(ControllerDevice,,DeviceName,DeviceBytes[4]);'],mutate=device_buffer)
        self.assertTrue(e.blockers)

    def test_device_name_bounds_fail_atomically_and_guard_st_for_effects(self):
        e=self.checked(['GSV(ControllerDevice,,ProductCode,PriorityOut);',
                        'GSV(ControllerDevice,,DeviceName,DeviceBytes[Index]);'],mutate=device_buffer)
        e.memory.write('Index',4)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'33 writable contiguous SINT'):
            e.step()
        self.assertEqual(e.memory.values,before)
        self.assertEqual((e.time_ms,e.scan_count),(0,0))
        e.memory.write('Index',3);e.step()
        self.assertEqual(e.memory.read('DeviceBytes[35]'),0)
        for dest in ('DeviceBytes','DeviceBytes[Limit]'):
            e=self.engine([f'FOR Index:=0 TO DeviceBytes[32] DO GSV(ControllerDevice,,DeviceName,{dest}); END_FOR;'],
                          st=True,mutate=device_buffer)
            self.assertTrue(any('bounds/step' in error for error in e.blockers),e.blockers)

    def test_named_configuration_is_readable_in_an_isolated_routine_harness(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);'],harness=True);e.step()
        self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.read('FastCount'),0)

    def test_no_priority_or_period_is_inferred_for_continuous_tasks(self):
        for attribute,dest in (('Priority','PriorityOut'),('Rate','Out')):
            self.assertTrue(self.engine([f'GSV(Task,BackgroundTask,{attribute},{dest});']).blockers)

    def test_missing_malformed_and_zero_task_settings_are_unavailable(self):
        for attribute,field,value,dest in (('Watchdog','Watchdog',None,'Out'),('Watchdog','Watchdog','0','Out'),
                ('Watchdog','Watchdog','1.0001','Out'),('Rate','Rate',None,'Out'),('Priority','Priority',None,'PriorityOut'),
                ('InhibitTask','InhibitTask',None,'Out'),('DisableUpdateOutputs','DisableUpdateOutputs',None,'Out')):
            def missing(root):
                task=root.find('./Controller/Tasks/Task[@Name="FastTask"]')
                if value is None:task.attrib.pop(field)
                else:task.set(field,value)
            self.assertTrue(self.engine([f'GSV(Task,FastTask,{attribute},{dest});'],mutate=missing).blockers,attribute)

    def test_exact_source_decimal_milliseconds_do_not_round(self):
        def value(root):root.find('./Controller/Tasks/Task[@Name="FastTask"]').set('Watchdog','12.345000')
        e=self.checked(['GSV(Task,FastTask,Watchdog,Out);'],mutate=value);e.step();self.assertEqual(e.memory.read('Out'),12345)

    def test_current_task_aliases_unknown_tasks_and_runtime_attributes_stay_blocked(self):
        for instance,attribute in (('','Rate'),('THIS','Rate'),('Missing','Name'),('Missing','Instance'),
                                  ('FastTask','Status'),('FastTask','OverlapCount')):
            self.assertTrue(self.engine([f'GSV(Task,{instance},{attribute},Out);']).blockers)
        for text in ('GSV(Controller,This,TimeSlice,PriorityOut);','GSV(Module,,EntryStatus,Out);',
                     'SSV(Task,BackgroundTask,Rate,Out);','GSV(Task,FastTask,Rate);'):
            self.assertTrue(self.engine([text]).blockers,text)

    def test_false_rung_skipped_st_and_prescan_retain_outputs(self):
        for logic,st in ((['AFI()GSV(Task,FastTask,Rate,Out);','AFI()GSV(Controller,,Name,NameOut);'],False),
                         ('IF FALSE THEN GSV(Task,FastTask,Rate,Out); GSV(Controller,,Name,NameOut); END_IF;',True)):
            e=self.checked(logic,st=st);self.assertEqual(e.memory.read('Out'),-7);self.assertEqual(e.memory.string('NameOut'),'SAVED')
            e.step();self.assertEqual(e.memory.read('Out'),-7);self.assertEqual(e.memory.string('NameOut'),'SAVED')
        e=self.checked(['GSV(Task,FastTask,Rate,Out)OTE(Flag);']);e.step();self.assertTrue(e.memory.read('Flag'))

    def test_unknown_destinations_can_be_established_without_fabricating_sources(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Name,NameOut);'])
        e.memory.values['out']=None;e.memory.values['nameout']['LEN']=None;e.memory.values['nameout']['DATA'][0]=None
        e.step();self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.string('NameOut'),'FastTask')

    def test_wrong_types_bits_whole_arrays_and_constant_destinations_are_blocked(self):
        for text in ('GSV(Task,FastTask,Rate,PriorityOut);','GSV(Task,FastTask,Priority,Out);',
                     'GSV(Task,FastTask,InhibitTask,Flag);','GSV(Task,FastTask,Rate,Out.0);',
                     'GSV(Task,FastTask,Name,Out);','GSV(Controller,,TimeSlice,NameOut);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for attr,dest in (('Rate','Out'),('Priority','PriorityOut'),('Name','NameOut')):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{dest}"]').set('Constant','true')
            self.assertTrue(self.engine([f'GSV(Task,FastTask,{attr},{dest});'],mutate=constant).blockers)

    def test_alias_and_udt_string_destinations_and_program_local_shadow(self):
        def aliases(root):
            strings.StringOperationTests.custom_strings(root);tags=root.find('./Controller/Tags')
            E.SubElement(tags,'Tag',Name='OutAlias',TagType='Alias',DataType='DINT',AliasFor='Out')
            scalar(root.find('./Controller/Programs/Program[@Name="BackgroundProgram"]/Tags'),'PriorityOut','INT')
        e=self.checked(['GSV(Task,FastTask,Rate,OutAlias);','GSV(Task,FastTask,Name,Record.Text);','GSV(Task,FastTask,Priority,PriorityOut);'],mutate=aliases);e.step()
        self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.string('Record.Text'),'FastTask')
        self.assertEqual(e.memory.read('PriorityOut'),-7);self.assertEqual(e.memory.read('PriorityOut','BackgroundProgram'),2)

    def test_dynamic_scalar_destination_bounds_rechecked_and_prior_writes_rolled_back(self):
        def array(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Words',DataType='DINT',TagType='Base',Dimensions='2')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]',Value='77')
        e=self.checked(['GSV(Task,FastTask,Rate,Words[Index]);'],mutate=array);e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Words'),[77,10000])
        e.memory.write('Index',2);before=copy.deepcopy(e.memory.values);time,scans=e.time_ms,e.scan_count
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.time_ms,e.scan_count),(time,scans))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)

    def test_small_user_string_failure_and_later_fault_roll_back_all_state(self):
        def small(root):
            strings.StringOperationTests.custom_strings(root)
            member=root.find('./Controller/DataTypes/DataType[@Name="UserText"]/Members/Member[@Name="DATA"]');member.set('Dimension','4')
            for arr in root.findall('.//ArrayMember[@Name="DATA"]'):
                if arr.get('Dimensions')=='16':
                    arr.set('Dimensions','4')
                    for item in list(arr)[4:]:arr.remove(item)
        e=self.checked(['MOV(77,Out);','GSV(Task,FastTask,Name,Record.Text);'],mutate=small);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'capacity'):e.step()
        self.assertEqual(e.memory.values,before)
        e=self.checked(['GSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Priority,PriorityOut);','DIV(1,0,Out);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.time_ms,e.scan_count),(0,0))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)

    def test_st_for_contract_protects_numeric_and_string_bound_destinations(self):
        for body,bound in (('GSV(Task,FastTask,Rate,Limit);','Limit'),('GSV(Task,FastTask,Priority,PriorityOut);','PriorityOut'),
                           ('GSV(Task,FastTask,Name,NameOut);','NameOut.LEN')):
            e=self.engine(f'FOR Index:=0 TO {bound} DO {body} END_FOR;',st=True)
            self.assertTrue(e.blockers);self.assertIn('bounds/step',str(e.blockers))
        e=self.checked('FOR Index:=0 TO Limit DO GSV(Task,FastTask,Rate,Out); END_FOR;',st=True);e.step();self.assertEqual(e.memory.read('Out'),10000)

    def test_source_configuration_bytes_equal_existing_task_and_controller_metadata(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Priority,PriorityOut);']);e.step()
        self.assertEqual(struct.pack('<i',e.memory.read('Out')),e.project.task_timing.attributes('FastTask',source_sha256=e.project.sha256)[2])
        self.assertEqual(struct.pack('<h',e.memory.read('PriorityOut')),e.project.task_configuration.attributes('FastTask',source_sha256=e.project.sha256)[6])
        e=self.checked(['GSV(Controller,,TimeSlice,PriorityOut);']);e.step()
        self.assertEqual(struct.pack('<h',e.memory.read('PriorityOut')),e.project.controller_configuration.compatibility_attributes()[3])

    def test_missing_or_conflicting_controller_name_and_incomplete_source_block(self):
        for value in (None,''):
            def missing(root):
                c=root.find('Controller')
                if value is None:c.attrib.pop('Name')
                else:c.set('Name',value)
            self.assertTrue(self.engine(['GSV(Controller,,Name,NameOut);'],mutate=missing).blockers)
        def conflict(root):root.find('Controller').set('name','Other')
        self.assertTrue(self.engine(['GSV(Controller,,Name,NameOut);'],mutate=conflict).blockers)
        def context(root):root.set('ContainsContext','true')
        self.assertTrue(self.engine(['GSV(Task,FastTask,Rate,Out);'],mutate=context).blockers)

    def test_loaded_source_is_immutable_and_rebound_hash_or_profile_mismatch_is_rejected(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['GSV(Task,FastTask,Rate,Out);'],mutate=old).blockers)
        e=self.checked(['GSV(Task,FastTask,Rate,Out);']);e.project.path.write_bytes(e.project.path.read_bytes()+b'\n')
        # Runtime reads its loaded snapshot; a changed disk file is not a reload.
        e.step();self.assertEqual(e.memory.read('Out'),10000)
        e.project.sha256='0'*64
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'unavailable'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_report_keeps_configuration_separate_from_native_runtime_and_ssv(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);']);report=e.report()['system_values']
        self.assertTrue(report['ssv']);self.assertFalse(report['configuration']['native_runtime_equivalence'])
        self.assertIn('Microseconds',report['configuration']['times'])

    def test_aoi_typed_output_and_string_inout_bindings_in_rll_and_st(self):
        for st in (False,True):
            def aoi(root):
                c=root.find('Controller')
                definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='ReadTask',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
                params=E.SubElement(definition,'Parameters')
                for name,dtype,usage,required in (('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),
                                               ('Prio','INT','Output','true'),('Text','STRING','InOut','true'),('Rate','DINT','Output','true')):
                    E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required,TagType='Base')
                E.SubElement(definition,'LocalTags')
                routine=E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST' if st else 'RLL')
                content=E.SubElement(routine,'STContent' if st else 'RLLContent')
                for i,text in enumerate(('GSV(Task,FastTask,Priority,Prio);','GSV(Task,FastTask,Name,Text);','GSV(Task,FastTask,Rate,Rate);')):
                    if st:E.SubElement(content,'Line',Number=str(i)).text=text
                    else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
                tag=E.SubElement(c.find('Tags'),'Tag',Name='Instance',DataType='ReadTask',TagType='Base')
                obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ReadTask')
                for name,dtype in (('EnableIn','BOOL'),('EnableOut','BOOL'),('Prio','INT'),('Rate','DINT')):
                    E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
            e=self.checked(['ReadTask(Instance,PriorityOut,NameOut,Out);'],mutate=aoi);e.step()
            self.assertEqual(e.memory.read('PriorityOut'),2);self.assertEqual(e.memory.string('NameOut'),'FastTask');self.assertEqual(e.memory.read('Out'),10000)


    def test_bundled_system_lab_rll_st_settings_and_schedule(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/SystemLab.L5X'));self.assertEqual(e.blockers,[]);e.step(25)
        self.assertEqual(e.memory.read('FastRate'),10000);self.assertEqual(e.memory.read('SlowRate'),25000)
        self.assertEqual(e.memory.read('FastPriority'),2);self.assertEqual(e.memory.read('CommTimeSlice'),30)
        self.assertEqual(e.memory.string('ControllerName'),'SystemLab');self.assertEqual(e.memory.string('FastTaskName'),'FastTask')
        self.assertEqual(e.memory.read('StSlowRate'),25000);self.assertEqual(e.memory.string('StFastTaskName'),'FastTask')
        self.assertEqual([t['executions'] for t in e.scheduler_description()['tasks']],[1,2,1])


if __name__=='__main__':unittest.main()
