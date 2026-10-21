"""Exact Program Disable bytes require explicit, complete and current source."""
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.program_configuration import ProgramConfiguration


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = 'a' * 64


def source():
    root = E.fromstring((ROOT/'samples/ConveyorDemo.L5X').read_bytes())
    return root, root.find('Controller')


class ProgramConfigurationTests(unittest.TestCase):
    def test_standard_memory_follows_ordinary_kind_without_defaulting_safety_or_opaque_kinds(self):
        root,controller=source();program=controller.find('./Programs/Program')
        program.attrib.pop('Disabled');program.attrib.pop('Class')
        reader=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertEqual(reader.memory_attributes('MAINPROGRAM',source_sha256=SOURCE_HASH),{26:bytes(2)})
        self.assertEqual(reader.memory_attributes(None,source_sha256=SOURCE_HASH),{})
        self.assertEqual(reader.memory_attributes('MainProgram',source_sha256='b'*64),{})
        for field,value in (('Class','Safety'),('Class','Unknown'),('Type','EquipmentPhase'),('DataUse','6'),('ClassUId','unknown')):
            root,controller=source();controller.find('./Programs/Program').set(field,value)
            reader=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
            self.assertEqual(reader.memory_attributes('MainProgram',source_sha256=SOURCE_HASH),{})

    def test_explicit_folder_and_sync_flags_are_independent_immutable_bytes(self):
        for folder in ('true','false'):
            for sync in ('true','false'):
                root,controller=source();program=controller.find('./Programs/Program')
                program.set('UseAsFolder',folder);program.set('SynchronizeRedundancyDataAfterExecution',sync)
                config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
                expected={29:bytes((int(sync=='true'),)),31:bytes((int(folder=='false'),))}
                self.assertEqual(config.flag_attributes('MAINPROGRAM',source_sha256=SOURCE_HASH),expected)
                program.set('UseAsFolder','false');program.set('SynchronizeRedundancyDataAfterExecution','false')
                self.assertEqual(config.flag_attributes('MainProgram',source_sha256=SOURCE_HASH),expected)
                self.assertEqual(config.flag_attributes('MainProgram',source_sha256='b'*64),{})
                self.assertEqual(config.flag_attributes(None,source_sha256=SOURCE_HASH),{})
                with self.assertRaises(TypeError):config._can_schedule['mainprogram']=True

    def test_missing_or_noncanonical_flags_are_unavailable_without_defaulting_other_fields(self):
        for value in (None,'','0','1','TRUE','False','false ',' true'):
            root,controller=source();program=controller.find('./Programs/Program')
            if value is not None:
                program.set('UseAsFolder',value);program.set('SynchronizeRedundancyDataAfterExecution',value)
            config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
            self.assertEqual(config.flag_attributes('MainProgram',source_sha256=SOURCE_HASH),{})
            self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{19:b'\0'})

    def test_flags_require_ordinary_complete_canonical_declarations(self):
        for mode in ('context','Safety','EquipmentPhase','alias','namespace','opaque'):
            root,controller=source();program=controller.find('./Programs/Program')
            program.set('UseAsFolder','false');program.set('SynchronizeRedundancyDataAfterExecution','true')
            if mode=='context':root.set('ContainsContext','true')
            elif mode=='Safety':program.set('Class',mode)
            elif mode=='EquipmentPhase':program.set('Type',mode)
            elif mode=='alias':program.set('useasfolder','true')
            elif mode=='namespace':program.set('{urn:test}UseAsFolder','true')
            else:E.SubElement(program,'VendorFlags')
            config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
            self.assertEqual(config.flag_attributes('MainProgram',source_sha256=SOURCE_HASH),{})
        for flags in ({'mainprogram':0},{'other':True}):
            with self.assertRaises(ValueError):ProgramConfiguration(SOURCE_HASH,True,_ordinary={'mainprogram'},_can_schedule=flags)

    def test_ordinary_user_program_type_is_independent_of_disable_and_bound_to_source(self):
        root,controller=source();program=controller.find('./Programs/Program')
        program.attrib.pop('Disabled');program.attrib.pop('Class')
        config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{})
        self.assertEqual(config.type_attributes('MAINPROGRAM',source_sha256=SOURCE_HASH),{30:b'\1'})
        self.assertEqual(config.type_attributes('MainProgram',source_sha256='b'*64),{})
        self.assertEqual(config.type_attributes('Missing',source_sha256=SOURCE_HASH),{})
        self.assertEqual(config.type_attributes(None,source_sha256=SOURCE_HASH),{})
        program.set('Type','Normal')
        explicit=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertEqual(explicit.type_attributes('MainProgram',source_sha256=SOURCE_HASH),{30:b'\1'})
        program.set('Type','EquipmentPhase')
        self.assertEqual(config.type_attributes('MainProgram',source_sha256=SOURCE_HASH),{30:b'\1'})
        self.assertEqual(config.description()['ordinary_programs_available'],1)
        self.assertFalse(config.description()['phase_sequence_types'])

    def test_type_withheld_for_unknown_kinds_opaque_children_context_and_safety(self):
        for mode in ('Type','ProgramType','programtype','{urn:test}Type','TypeUId','EquipmentPhase',
                     'EquipmentSequence','VendorFlag','opaque','Safety','context','nested','duplicate','major'):
            root,controller=source();program=controller.find('./Programs/Program')
            if mode=='opaque':E.SubElement(program,'VendorKind')
            elif mode=='Safety':program.set('Class','Safety')
            elif mode=='context':root.set('ContainsContext','true')
            elif mode=='nested':E.SubElement(controller,'VendorWrapper').append(copy.deepcopy(program))
            elif mode=='duplicate':controller.find('Programs').append(copy.deepcopy(program))
            elif mode=='major':controller.set('MajorRev','36')
            else:program.set(mode,'Unknown')
            config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
            with self.subTest(mode=mode):self.assertEqual(config.type_attributes('MainProgram',source_sha256=SOURCE_HASH),{})

    def test_type_inventory_constructor_rejects_bad_names_and_copies_mutable_input(self):
        names={'mainprogram'};config=ProgramConfiguration(SOURCE_HASH,True,_ordinary=names)
        names.clear();self.assertEqual(config.type_attributes('MainProgram',source_sha256=SOURCE_HASH),{30:b'\1'})
        for names in ('mainprogram',None,{'MainProgram'},{1},{'bad.name'}):
            with self.assertRaises(ValueError):ProgramConfiguration(SOURCE_HASH,True,_ordinary=names)
        with self.assertRaises(ValueError):ProgramConfiguration(SOURCE_HASH,_ordinary={'mainprogram'})

    def test_explicit_enabled_and_disabled_programs_have_independent_single_byte_values(self):
        root, controller = source();programs = controller.find('Programs')
        other = copy.deepcopy(programs[0]);other.set('Name','DisabledProgram');other.set('Disabled','true');programs.append(other)
        config = ProgramConfiguration.from_source(root, controller, SOURCE_HASH)
        self.assertTrue(config.source_complete)
        self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{19:b'\0'})
        self.assertEqual(config.attributes('DISABLEDPROGRAM',source_sha256=SOURCE_HASH),{19:b'\1'})
        self.assertEqual(config.attributes('MissingProgram',source_sha256=SOURCE_HASH),{})
        self.assertEqual(config.attributes(None,source_sha256=SOURCE_HASH),{})
        self.assertEqual(config.description()['programs_available'],2)
        self.assertEqual(config.description()['programs_unavailable'],0)
        self.assertFalse(config.description()['native_writes'])

    def test_missing_malformed_noncanonical_or_unsupported_disabled_values_are_unavailable(self):
        for value in (None,'','0','1','TRUE','FALSE','True','false ',' true','enabled','0x00'):
            root,controller = source();program = controller.find('./Programs/Program')
            if value is None:program.attrib.pop('Disabled')
            else:program.set('Disabled',value)
            with self.subTest(value=value):
                config = ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
                self.assertTrue(config.source_complete)
                self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{})
                self.assertEqual(config.description()['programs_unavailable'],1)

    def test_incomplete_context_nested_duplicate_and_noncanonical_scope_never_supply_a_value(self):
        for kind in ('context','partial','use','namespace','duplicate','duplicate-case','nested','missing-name','wrong-name','alias','class-alias'):
            root,controller = source();programs = controller.find('Programs');program = programs[0]
            if kind=='context':root.set('ContainsContext','true')
            elif kind=='partial':root.set('TargetType','Program')
            elif kind=='use':program.set('Use','Context')
            elif kind=='namespace':program.tag='{urn:other}Program'
            elif kind=='duplicate':programs.append(copy.deepcopy(program))
            elif kind=='duplicate-case':
                other=copy.deepcopy(program);other.set('Name','MAINPROGRAM');programs.append(other)
            elif kind=='nested':E.SubElement(controller,'VendorWrapper').append(copy.deepcopy(program))
            elif kind=='missing-name':program.attrib.pop('Name')
            elif kind=='wrong-name':program.set('Name','invalid.name')
            elif kind=='alias':program.set('disabled','true')
            else:program.set('{urn:other}Class','Standard')
            with self.subTest(kind=kind):
                config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
                self.assertFalse(config.source_complete)
                self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{})

    def test_safety_unknown_class_and_wrong_major_revision_do_not_expose_standard_fields(self):
        for value in ('Safety','Unknown'):
            root,controller=source();program=controller.find('./Programs/Program')
            if value is None:program.attrib.pop('Class')
            else:program.set('Class',value)
            with self.subTest(value=value):
                config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
                self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{})
        for major in ('34','36',None):
            root,controller=source()
            if major is None:controller.attrib.pop('MajorRev')
            else:controller.set('MajorRev',major)
            config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
            self.assertFalse(config.source_complete)

    def test_native_export_omitting_class_retains_only_its_explicit_disabled_field(self):
        root,controller=source();program=controller.find('./Programs/Program');program.attrib.pop('Class')
        config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{19:b'\0'})
        program.attrib.pop('Disabled')
        unknown=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertEqual(unknown.attributes('MainProgram',source_sha256=SOURCE_HASH),{})

    def test_source_hash_guard_and_immutable_snapshot_prevent_stale_or_external_mutation(self):
        root,controller=source()
        config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertEqual(config.attributes('MainProgram',source_sha256='b'*64),{})
        controller.find('./Programs/Program').set('Disabled','true')
        newer=ProgramConfiguration.from_source(root,controller,'b'*64)
        self.assertEqual(config.attributes('MainProgram',source_sha256=SOURCE_HASH),{19:b'\0'})
        self.assertEqual(newer.attributes('MainProgram',source_sha256='b'*64),{19:b'\1'})
        self.assertEqual(newer.attributes('MainProgram',source_sha256=SOURCE_HASH),{})
        with self.assertRaises(TypeError):config._disabled['mainprogram']=True
        with self.assertRaises(FrozenInstanceError):config.source_sha256='b'*64

    def test_constructor_rejects_unbound_hash_invalid_metadata_and_oversized_inventory(self):
        for digest in ('', 'A'*64, 'a'*63, None):
            with self.assertRaises(ValueError):ProgramConfiguration(digest)
        for values in ({'MainProgram':False},{'mainprogram':0},{'bad.name':False}):
            with self.assertRaises(ValueError):ProgramConfiguration(SOURCE_HASH,True,values)
        with self.assertRaises(ValueError):ProgramConfiguration(SOURCE_HASH,False,{'mainprogram':False})
        with self.assertRaises(ValueError):ProgramConfiguration(SOURCE_HASH,True,{},True)
        root,controller=source()
        with patch('logixlab.program_configuration.MAX_PROGRAMS',0):
            config=ProgramConfiguration.from_source(root,controller,SOURCE_HASH)
        self.assertFalse(config.source_complete)


if __name__=='__main__':unittest.main()
