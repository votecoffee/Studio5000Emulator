"""Source-known null lists and untested RLL require complete canonical source."""
import copy
from dataclasses import FrozenInstanceError
import unittest
from xml.etree import ElementTree as E
import test_program_configuration as fixtures
from logixlab.program_configuration import ProgramConfiguration
from logixlab.program_diagnostics import ProgramDiagnostics
from logixlab.executable_configuration import ExecutableConfiguration
from logixlab.io_map import IOMap

SHA=fixtures.SOURCE_HASH


def build(root,controller,digest=SHA):
    return ProgramDiagnostics.from_source(root,controller,digest,
        ProgramConfiguration.from_source(root,controller,digest),
        ExecutableConfiguration.from_source(root,controller,digest),IOMap.from_source(root,controller))


class ProgramDiagnosticTests(unittest.TestCase):
    def source(self):
        root,controller=fixtures.source();controller.find('./Programs/Program').set('TestEdits','false')
        return root,controller

    def test_available_values_bound_to_source_and_immutable(self):
        root,controller=self.source();reader=build(root,controller)
        self.assertEqual(reader.output_attributes('MAINPROGRAM',source_sha256=SHA),{7:bytes(4)})
        self.assertEqual(reader.edit_attributes('MainProgram',source_sha256=SHA,idle=True),{11:bytes(2)})
        controller.find('./Programs/Program').set('TestEdits','true')
        self.assertEqual(reader.edit_attributes('MainProgram',source_sha256=SHA,idle=True),{11:bytes(2)})
        for name,sha in ((None,SHA),('Missing',SHA),('MainProgram','b'*64)):
            self.assertEqual(reader.output_attributes(name,source_sha256=sha),{})
            self.assertEqual(reader.edit_attributes(name,source_sha256=sha,idle=True),{})
        for idle in (False,None,0,1,'true'):
            self.assertEqual(reader.edit_attributes('MainProgram',source_sha256=SHA,idle=idle),{})
        with self.assertRaises(FrozenInstanceError):reader.source_sha256='b'*64

    def test_unknown_or_nonempty_output_configuration_never_becomes_null(self):
        for mode in ('module','produced','consumed','alias','usage','namespace','connection','opaque','protected','usage-uid','parameter-uid'):
            root,controller=self.source();tag=controller.find('./Tags/Tag')
            if mode=='module':E.SubElement(controller.find('Modules'),'Module',Name='Remote')
            elif mode in ('produced','consumed'):tag.set('TagType',mode.title())
            elif mode=='alias':tag.set('AliasFor','Something')
            elif mode=='usage':tag.set('Usage','Output')
            elif mode=='namespace':tag.set('{urn:test}Usage','Input')
            elif mode=='usage-uid':tag.set('UsageUId','unknown')
            elif mode=='parameter-uid':tag.set('ParameterUId','unknown')
            elif mode=='connection':E.SubElement(controller,'ParameterConnections')
            elif mode=='opaque':E.SubElement(controller,'VendorOutputData')
            else:controller.set('SourceProtection','hidden')
            with self.subTest(mode=mode):self.assertEqual(build(root,controller).output_attributes('MainProgram',source_sha256=SHA),{})

    def test_pending_test_or_unknown_routine_forms_do_not_report_untested(self):
        for mode in ('missing','true','TRUE','0','alias','insert','replace','delete','pending','original','multiple','ST','opaque','nested-edit','nested-text','context'):
            root,controller=self.source();program=controller.find('./Programs/Program');routine=program.find('./Routines/Routine')
            content=routine.find('RLLContent')
            if mode=='missing':program.attrib.pop('TestEdits')
            elif mode in ('true','TRUE','0'):program.set('TestEdits',mode)
            elif mode=='alias':program.set('testedits','false')
            elif mode in ('insert','replace','delete'):content[0].set('Type',mode[0].upper())
            elif mode in ('pending','original'):content.set('OnlineEditType','PendingEdits' if mode=='pending' else 'Original')
            elif mode=='multiple':routine.append(copy.deepcopy(content))
            elif mode=='ST':routine.set('Type','ST');content.tag='STContent'
            elif mode=='nested-edit':content.set('TestEdits','true')
            elif mode=='nested-text':E.SubElement(content[0].find('Text'),'Unknown')
            elif mode=='context':content[0].set('Use','Context')
            else:E.SubElement(content[0],'VendorEdit')
            with self.subTest(mode=mode):self.assertEqual(build(root,controller).edit_attributes('MainProgram',source_sha256=SHA,idle=True),{})

    def test_context_shadow_and_unsupported_programs_withhold_both_fields(self):
        for mode in ('context','Safety','phase','nested','namespace','major'):
            root,controller=self.source();program=controller.find('./Programs/Program')
            if mode=='context':root.set('ContainsContext','true')
            elif mode=='Safety':program.set('Class','Safety')
            elif mode=='phase':program.set('Type','EquipmentPhase')
            elif mode=='nested':E.SubElement(controller,'Wrapper').append(copy.deepcopy(program))
            elif mode=='namespace':program.tag='{urn:test}Program'
            else:controller.set('MajorRev','36')
            reader=build(root,controller)
            self.assertEqual(reader.output_attributes('MainProgram',source_sha256=SHA),{})
            self.assertEqual(reader.edit_attributes('MainProgram',source_sha256=SHA,idle=True),{})

    def test_constructor_copies_and_validates_inventories(self):
        names={'mainprogram'};reader=ProgramDiagnostics(SHA,names,names);names.clear()
        self.assertEqual(reader.output_attributes('MainProgram',source_sha256=SHA),{7:bytes(4)})
        for value in (None,'mainprogram',{'MainProgram'},{1}):
            with self.assertRaises(ValueError):ProgramDiagnostics(SHA,value)
        with self.assertRaises(ValueError):ProgramDiagnostics('invalid')
