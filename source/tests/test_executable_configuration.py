"""Source-backed legacy Executable metadata, without native ID/type guesses."""
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.executable_configuration import (ExecutableConfiguration, ProgramMetadata,
                                                RoutineMetadata)

SOURCE=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
HASH='a'*64


def source():
    root=E.fromstring(SOURCE.read_bytes());controller=root.find('Controller')
    return root,controller


class ExecutableConfigurationTests(unittest.TestCase):
    def test_inventory_preserves_original_names_and_description_exact_bytes(self):
        root,controller=source();routines=controller.find('./Programs/Program/Routines')
        text='Conveyor routine\nReport status.'
        E.SubElement(routines[0],'Description').text=text
        E.SubElement(routines[1],'Description')
        config=ExecutableConfiguration.from_source(root,controller,HASH)
        self.assertTrue(config.source_complete);self.assertEqual(config.program_names,('MainProgram',))
        self.assertEqual(config.routine_names('MAINPROGRAM',source_sha256=HASH),('MainRoutine','Reporting'))
        self.assertEqual(config.attributes('mainprogram','MAINROUTINE',source_sha256=HASH),
                         {7:struct.pack('<H',len(text))+text.encode('ascii')})
        self.assertEqual(config.attributes('MainProgram','Reporting',source_sha256=HASH),{7:bytes(2)})
        self.assertFalse(config.description()['type_enum_inferred'])
        self.assertFalse(config.description()['uid_inferred'])
        self.assertEqual(config.description()['attributes'],[7])

    def test_missing_description_never_becomes_successful_empty(self):
        root,controller=source();config=ExecutableConfiguration.from_source(root,controller,HASH)
        self.assertEqual(config.routine_names('MainProgram',source_sha256=HASH),('MainRoutine','Reporting'))
        self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256=HASH),{})
        self.assertEqual(config.description()['description_attributes_available'],0)

    def test_description_width_ascii_bound_and_no_truncation_or_padding(self):
        for value in ('','A'*128,'A'*129,'naïve','a\0b','\r\nindented\ttext\r\n'):
            root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
            E.SubElement(routine,'Description').text=value
            attrs=ExecutableConfiguration.from_source(root,controller,HASH).attributes(
                'MainProgram','MainRoutine',source_sha256=HASH)
            if len(value)<=128 and value.isascii() and '\0' not in value:
                with self.subTest(value=value):self.assertEqual(attrs,{7:struct.pack('<H',len(value))+value.encode('ascii')})
            else:
                with self.subTest(value=value):self.assertEqual(attrs,{})

    def test_ambiguous_localized_or_structured_descriptions_withhold_only_the_attribute(self):
        for kind in ('duplicate','case','namespace','child','language','format'):
            root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
            desc=E.SubElement(routine,'Description');desc.text='visible'
            if kind=='duplicate':E.SubElement(routine,'Description').text='other'
            elif kind=='case':E.SubElement(routine,'description').text='other'
            elif kind=='namespace':desc.tag='{other}Description'
            elif kind=='child':E.SubElement(desc,'LocalizedText').text='other'
            elif kind=='language':desc.set('Lang','en-US')
            else:desc.set('Format','Text')
            config=ExecutableConfiguration.from_source(root,controller,HASH)
            with self.subTest(kind=kind):
                self.assertIsNotNone(config.routine_names('MainProgram',source_sha256=HASH))
                self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256=HASH),{})

    def test_routine_names_are_scoped_and_sibling_programs_can_share_them(self):
        root,controller=source();programs=controller.find('Programs')
        other=copy.deepcopy(programs[0]);other.set('Name','OtherProgram');programs.append(other)
        E.SubElement(other.find('./Routines/Routine'),'Description').text='other'
        config=ExecutableConfiguration.from_source(root,controller,HASH)
        self.assertEqual(config.program_names,('MainProgram','OtherProgram'))
        self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256=HASH),{})
        self.assertEqual(config.attributes('otherprogram','mainroutine',source_sha256=HASH),{7:b'\x05\0other'})

    def test_empty_canonical_inventory_is_distinct_from_missing_container(self):
        root,controller=source();program=controller.find('./Programs/Program')
        program.find('Routines').clear()
        config=ExecutableConfiguration.from_source(root,controller,HASH)
        self.assertEqual(config.routine_names('MainProgram',source_sha256=HASH),())
        program.remove(program.find('Routines'))
        config=ExecutableConfiguration.from_source(root,controller,HASH)
        self.assertIsNone(config.routine_names('MainProgram',source_sha256=HASH))
        self.assertEqual(config.program_names,());self.assertTrue(config.source_complete)

    def test_known_languages_describe_source_without_inventing_wire_type_codes(self):
        for language in ('RLL','ST','FBD','SFC'):
            root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
            routine.set('Type',language);routine.remove(routine.find('RLLContent'))
            E.SubElement(routine,language+'Content');E.SubElement(routine,'Description').text=language
            config=ExecutableConfiguration.from_source(root,controller,HASH)
            with self.subTest(language=language):
                self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256=HASH),
                                 {7:struct.pack('<H',len(language))+language.encode('ascii')})
        for language in ('Unknown','rll','1',None):
            root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
            if language is None:routine.attrib.pop('Type')
            else:routine.set('Type',language)
            config=ExecutableConfiguration.from_source(root,controller,HASH)
            with self.subTest(language=language):self.assertIsNone(config.routine_names('MainProgram',source_sha256=HASH))

    def test_nonordinary_classes_withhold_whole_program_without_partial_catalog(self):
        for scope in ('Program','Routine'):
            for value in ('Safety','Unknown','standard'):
                root,controller=source();program=controller.find('./Programs/Program')
                target=program if scope=='Program' else program.find('./Routines/Routine');target.set('Class',value)
                config=ExecutableConfiguration.from_source(root,controller,HASH)
                with self.subTest(scope=scope,value=value):
                    self.assertTrue(config.source_complete);self.assertEqual(config.program_names,())
                    self.assertIsNone(config.routine_names('MainProgram',source_sha256=HASH))
        root,controller=source();controller.find('./Programs/Program').attrib.pop('Class')
        self.assertEqual(ExecutableConfiguration.from_source(root,controller,HASH).program_names,('MainProgram',))

    def test_source_protection_markers_withhold_whole_program_even_if_plain_body_is_visible(self):
        for marker in ('SourceKey','EncodedSourceKey','SourceProtectionType','Protected','ProtectedData','License'):
            for scope in ('Program','Routine'):
                root,controller=source();program=controller.find('./Programs/Program')
                target=program if scope=='Program' else program.find('./Routines/Routine');target.set(marker,'present')
                config=ExecutableConfiguration.from_source(root,controller,HASH)
                with self.subTest(marker=marker,scope=scope):
                    self.assertIsNone(config.routine_names('MainProgram',source_sha256=HASH))
        for kind in ('encoded-child','encoded-format','missing-body','multiple-body','unknown-child'):
            root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
            if kind=='encoded-child':E.SubElement(routine,'EncodedData')
            elif kind=='encoded-format':routine.find('RLLContent').set('Format','Encrypted')
            elif kind=='missing-body':routine.remove(routine.find('RLLContent'))
            elif kind=='multiple-body':routine.append(copy.deepcopy(routine.find('RLLContent')))
            else:E.SubElement(routine,'Unknown')
            with self.subTest(kind=kind):
                self.assertIsNone(ExecutableConfiguration.from_source(root,controller,HASH).routine_names('MainProgram',source_sha256=HASH))

    def test_partial_or_shadow_declarations_cannot_create_global_inventory(self):
        for kind in ('context','target','major','program-container','nested-program','duplicate-program',
                     'duplicate-routine','case-routine','nested-routine','multiple-routines','unknown-routine-child',
                     'tagcase','namespace','name-alias','type-alias','class-alias','use-alias','use','protected-container'):
            root,controller=source();programs=controller.find('Programs');program=programs[0]
            routines=program.find('Routines');routine=routines[0]
            if kind=='context':root.set('ContainsContext','true')
            elif kind=='target':root.set('TargetType','Routine')
            elif kind=='major':controller.set('MajorRev','34')
            elif kind=='program-container':controller.append(copy.deepcopy(programs))
            elif kind=='nested-program':E.SubElement(controller,'Wrapper').append(copy.deepcopy(program))
            elif kind=='duplicate-program':other=copy.deepcopy(program);other.set('Name','MAINPROGRAM');programs.append(other)
            elif kind in ('duplicate-routine','case-routine'):
                other=copy.deepcopy(routine)
                if kind=='case-routine':other.set('Name','MAINROUTINE')
                routines.append(other)
            elif kind=='nested-routine':E.SubElement(program,'Wrapper').append(copy.deepcopy(routine))
            elif kind=='multiple-routines':program.append(copy.deepcopy(routines))
            elif kind=='unknown-routine-child':E.SubElement(routines,'Unknown')
            elif kind=='tagcase':routine.tag='routine'
            elif kind=='namespace':routines.tag='{other}Routines'
            elif kind=='name-alias':program.set('name','Shadow')
            elif kind=='type-alias':routine.set('{other}Type','RLL')
            elif kind=='class-alias':routine.set('class','Standard')
            elif kind=='use-alias':routine.set('use','Target')
            elif kind=='use':routine.set('Use','Context')
            else:programs.set('ProtectedData','hidden')
            config=ExecutableConfiguration.from_source(root,controller,HASH)
            with self.subTest(kind=kind):self.assertFalse(config.source_complete);self.assertEqual(config.program_names,())

    def test_snapshots_are_immutable_and_source_hash_guard_rejects_stale_reads(self):
        root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
        E.SubElement(routine,'Description').text='original'
        config=ExecutableConfiguration.from_source(root,controller,HASH)
        routine.find('Description').text='changed';routine.set('Name','Changed')
        self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256=HASH),{7:b'\x08\0original'})
        self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256='b'*64),{})
        self.assertIsNone(config.routine_names('MainProgram',source_sha256='b'*64))
        self.assertEqual(config.attributes('Missing','MainRoutine',source_sha256=HASH),{})
        self.assertIsNone(config.routine_names(None,source_sha256=HASH))
        with self.assertRaises(TypeError):config._programs['other']=ProgramMetadata('Other')
        with self.assertRaises(TypeError):config._programs['mainprogram']._by_name['other']=RoutineMetadata('Other','RLL')
        with self.assertRaises(FrozenInstanceError):config.source_complete=False
        attrs=config.attributes('MainProgram','MainRoutine',source_sha256=HASH);attrs[7]=b'changed'
        self.assertEqual(config.attributes('MainProgram','MainRoutine',source_sha256=HASH),{7:b'\x08\0original'})

    def test_invalid_direct_snapshots_and_bounded_source_inventories(self):
        for digest in ('',None,'A'*64):
            with self.assertRaises(ValueError):ExecutableConfiguration(digest)
        with self.assertRaises(ValueError):ExecutableConfiguration(HASH,False,{'main':ProgramMetadata('Main')})
        with self.assertRaises(ValueError):ProgramMetadata('Main',(RoutineMetadata('Same','RLL'),RoutineMetadata('SAME','ST')))
        for value in (b'A'*129,b'\0',b'\xff',bytearray()):
            with self.assertRaises(ValueError):RoutineMetadata('Main','RLL',value)
        for kind in ('program','routine'):
            root,controller=source();program=controller.find('./Programs/Program')
            target=program if kind=='program' else program.find('./Routines/Routine');target.set('Name','bad.name')
            self.assertFalse(ExecutableConfiguration.from_source(root,controller,HASH).source_complete)


if __name__=='__main__':unittest.main()
