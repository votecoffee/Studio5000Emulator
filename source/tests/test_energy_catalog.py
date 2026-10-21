"""Energy discovery describes only the supported software-controller subset."""
import copy
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.energy_catalog import EnergyCatalog, CLASSES
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.server import Application


class EnergyCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e')
        self.root=E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def catalog(self,root):return EnergyCatalog.from_source(root,root.find('Controller'))

    def call(self,path,data=b'',service=0x4B):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_ordinary_project_has_empty_energy_lists_with_any_cursor(self):
        self.assertTrue(self.catalog(self.root).empty)
        for cls in CLASSES:
            for cursor in (0,1,0xFFFFFFFF):
                path=bytes((0x20,cls,0x26,0))+cursor.to_bytes(4,'little')
                self.assertEqual(self.call(path),b'\xCB\0\0\0')
        self.assertFalse(self.app.engine.project.energy_catalog.description()['physical_inventory'])
        self.assertFalse(self.app.engine.project.energy_catalog.description()['energy_measurement'])

    def test_self_controller_module_is_allowed_but_external_or_ambiguous_modules_are_not(self):
        controller=self.root.find('Controller');modules=controller.find('Modules')
        E.SubElement(modules,'Module',CatalogNumber=controller.get('ProcessorType'))
        self.assertTrue(self.catalog(self.root).empty)
        for mode in ('external','duplicate','unknown','context','container_context','missing_catalog','missing_processor'):
            root=copy.deepcopy(self.root);container=root.find('./Controller/Modules')
            if mode=='external':container[0].set('CatalogNumber','EnergyMeter')
            elif mode=='duplicate':E.SubElement(container,'Module',CatalogNumber=controller.get('ProcessorType'))
            elif mode=='unknown':E.SubElement(container,'EncryptedModule')
            elif mode=='container_context':container.set('Use','Context')
            elif mode=='missing_catalog':container[0].attrib.pop('CatalogNumber')
            elif mode=='missing_processor':root.find('Controller').attrib.pop('ProcessorType')
            else:container[0].set('Use','Context')
            self.assertFalse(self.catalog(root).empty)

    def test_custom_types_aois_object_tags_and_energy_configuration_are_unavailable(self):
        for mode in ('udt','aoi','dtype','format','configuration','namespace','unknown_section'):
            with self.subTest(mode=mode):
                root=copy.deepcopy(self.root);controller=root.find('Controller')
                if mode=='udt':E.SubElement(controller.find('DataTypes'),'DataType',Name='Custom')
                elif mode=='aoi':E.SubElement(controller.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='Proxy')
                elif mode=='dtype':controller.find('./Tags/Tag').set('DataType','UnknownObject')
                elif mode=='format':E.SubElement(controller.find('./Tags/Tag'),'Data',Format='Energy')
                elif mode=='configuration':E.SubElement(controller,'EnergyConfiguration')
                elif mode=='unknown_section':E.SubElement(controller,'OpaqueConfiguration')
                else:E.SubElement(controller,'{urn:extra}EnergyConfiguration')
                self.assertFalse(self.catalog(root).empty)
                self.assertIsNone(self.catalog(root).description()['instance_count'])

    def add_udt(self, root, name='Budget', dtype='DINT'):
        node=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name=name,Class='User',Family='NoFamily')
        member=E.SubElement(E.SubElement(node,'Members'),'Member',Name='Value',DataType=dtype,Dimension='0')
        return node,member

    def test_numeric_nested_and_packed_user_types_prove_empty_without_energy_measurements(self):
        inner,member=self.add_udt(self.root)
        outer,child=self.add_udt(self.root,'Report','Budget');child.set('Dimension','2')
        E.SubElement(self.root.find('./Controller/Programs/Program/Tags'),'Tag',Name='Status',DataType='Report')
        self.assertTrue(self.catalog(self.root).empty)
        members=inner.find('Members');member.set('DataType','SINT');member.set('Hidden','true')
        E.SubElement(members,'Member',Name='Ready',DataType='BIT',Target='Value',BitNumber='0',Dimension='0')
        self.assertTrue(self.catalog(self.root).empty)
        info=self.catalog(self.root).description()
        self.assertEqual(info['new_empty_probe_classes'],[0x4E,0x4F])
        self.assertFalse(info['energy_measurement'])

    def test_ambiguous_incomplete_or_object_user_type_graphs_are_unavailable(self):
        root=copy.deepcopy(self.root);self.add_udt(root)
        for mode in ('unknown','energy','missing_class','missing_family','context','namespace','duplicate',
                     'cycle','opaque','missing_members','member_context','member_shadow','bad_dimensions','bad_bit'):
            with self.subTest(mode=mode):
                candidate=copy.deepcopy(root);node=candidate.find('./Controller/DataTypes/DataType');member=node.find('./Members/Member')
                if mode=='unknown':member.set('DataType','UnknownObject')
                elif mode=='energy':member.set('DataType','ENERGY_BASE')
                elif mode=='missing_class':node.attrib.pop('Class')
                elif mode=='missing_family':node.attrib.pop('Family')
                elif mode=='context':node.set('Use','Context')
                elif mode=='namespace':member.tag='{test}Member'
                elif mode=='duplicate':self.add_udt(candidate,'budget')
                elif mode=='cycle':member.set('DataType','Budget')
                elif mode=='opaque':E.SubElement(node,'EncodedData')
                elif mode=='missing_members':node.remove(node.find('Members'))
                elif mode=='member_context':member.set('Use','Context')
                elif mode=='member_shadow':member.set('datatype','DINT')
                elif mode=='bad_dimensions':member.set('Dimension','opaque')
                else:member.set('DataType','BIT')
                self.assertFalse(self.catalog(candidate).empty)

    def test_deep_cached_graphs_and_type_budgets_remain_bounded(self):
        for index in range(9):self.add_udt(self.root,'T'+str(index),'DINT' if index==0 else 'T'+str(index-1))
        self.assertFalse(self.catalog(self.root).empty)
        container=self.root.find('./Controller/DataTypes');container.remove(container[-1])
        self.assertTrue(self.catalog(self.root).empty)
        for index in range(257):E.SubElement(container[0].find('Members'),'Member',Name='M'+str(index),DataType='DINT')
        self.assertFalse(self.catalog(self.root).empty)

    def test_numeric_udt_source_reaches_legacy_energy_list_without_changing_values(self):
        self.add_udt(self.root)
        path=Path(self.tmp.name)/'ordinary.L5X';E.ElementTree(self.root).write(path)
        self.app.engine.project=Project(path);before=copy.deepcopy(self.app.engine.memory.values)
        for cls in CLASSES:self.assertEqual(self.call(bytes((0x20,cls,0x24,0))),b'\xCB\0\0\0')
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_incomplete_source_and_unknown_program_tags_do_not_prove_empty(self):
        for mode in ('context','missing_tags','duplicate_controller','program_tag'):
            root=copy.deepcopy(self.root);controller=root.find('Controller')
            if mode=='context':root.set('ContainsContext','true')
            elif mode=='missing_tags':controller.remove(controller.find('Tags'))
            elif mode=='duplicate_controller':E.SubElement(root,'Controller')
            else:E.SubElement(controller.find('./Programs/Program/Tags'),'Tag',Name='Unknown',DataType='UnknownObject')
            self.assertFalse(self.catalog(root).empty)

    def test_ordinary_names_do_not_invent_energy_object_presence(self):
        self.root.find('./Controller/Tags/Tag').set('Name','EnergyCost')
        self.assertTrue(self.catalog(self.root).empty)

    def test_source_replacement_changes_availability(self):
        E.SubElement(self.root.find('Controller'),'EnergyConfiguration')
        path=Path(self.tmp.name)/'energy.L5X';E.ElementTree(self.root).write(path)
        self.app.engine.project=Project(path)
        self.assertEqual(self.call(bytes.fromhex('204e2400'))[2],0x0C)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.call(bytes.fromhex('204e2400')),b'\xCB\0\0\0')

    def test_bad_scope_payloads_attributes_and_nonlist_services_do_not_mutate_state(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for cls in CLASSES:
            path=bytes((0x20,cls,0x24,0))
            for target,data,service,status in ((path[:-2],b'',0x4B,4),(path+b'\x30\1',b'',0x4B,4),
                    (path,b'\0',0x4B,0x15),(symbol_path('Program:MainProgram')+path,b'',0x4B,4),
                    (path,b'',0x0E,8),(path,b'\0',0x10,8)):
                self.assertEqual(self.call(target,data,service)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)


if __name__=='__main__':unittest.main()
