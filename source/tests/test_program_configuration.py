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
