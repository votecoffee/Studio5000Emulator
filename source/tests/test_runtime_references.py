"""Interpreter references are backed, distinct and revoked with their objects."""
import copy
import struct
import unittest
from unittest.mock import patch

import test_runtime as fixtures
from logixlab.runtime import Engine


class RuntimeReferenceTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp
    engine=fixtures.RuntimeTests.engine

    def test_addresses_resolve_actual_targets_and_never_use_object_ids(self):
        engine=self.engine(['NOP();']);project=engine.project;space=engine.runtime_references
        before=copy.deepcopy(engine.memory.values)
        values=space.program_attributes(project,'MAINPROGRAM')
        main,address=(struct.unpack('<I',values[n])[0] for n in (5,16))
        self.assertGreaterEqual(main,0x10000000);self.assertNotEqual(main,address)
        self.assertEqual(main%4,0);self.assertEqual(address%4,0)
        self.assertIs(space.resolve(project,main,'routine'),project.routines['mainprogram/mainroutine'])
        self.assertIs(space.resolve(project,address,'program'),project.programs['MainProgram'])
        self.assertIsNone(space.resolve(project,main,'program'))
        self.assertIsNone(space.resolve(project,True,'program'))
        self.assertEqual(values,space.program_attributes(project,'MainProgram'))
        self.assertEqual(engine.memory.values,before);self.assertEqual(engine.scan_count,0)

    def test_engine_replacement_has_new_addresses_and_cannot_resolve_old_ones(self):
        old=self.engine(['NOP();']);fresh=Engine(old.project)
        a=old.runtime_references.program_attributes(old.project,'MainProgram')
        b=fresh.runtime_references.program_attributes(fresh.project,'MainProgram')
        self.assertFalse(set(a.values())&set(b.values()))
        for number,kind in ((5,'routine'),(16,'program')):
            self.assertIsNone(fresh.runtime_references.resolve(fresh.project,int.from_bytes(a[number],'little'),kind))

    def test_replacing_a_target_revokes_old_reference_without_reusing_its_address(self):
        engine=self.engine(['NOP();']);project=engine.project;space=engine.runtime_references
        before=space.program_attributes(project,'MainProgram')
        project.routines['mainprogram/mainroutine']=copy.deepcopy(project.routines['mainprogram/mainroutine'])
        self.assertIsNone(space.resolve(project,int.from_bytes(before[5],'little'),'routine'))
        after=space.program_attributes(project,'MainProgram')
        self.assertNotEqual(before[5],after[5]);self.assertEqual(before[16],after[16])
        del project.programs['MainProgram']
        self.assertIsNone(space.resolve(project,int.from_bytes(before[16],'little'),'program'))
        self.assertEqual(space.program_attributes(project,'MainProgram'),{})

    def test_missing_main_foreign_project_and_unknown_kinds_never_allocate(self):
        engine=self.engine(['NOP();']);space=engine.runtime_references;other=self.engine(['NOP();'])
        self.assertEqual(space.program_attributes(other.project,'MainProgram'),{})
        self.assertIsNone(space.reference(engine.project,'other','MainProgram'))
        engine.project.programs['MainProgram']['main']='Missing'
        self.assertEqual(space.program_attributes(engine.project,'MainProgram'),{})
        self.assertEqual(space.description()['allocated_objects'],0)

    def test_exhaustion_withholds_values_without_wrapping(self):
        engine=self.engine(['NOP();']);space=engine.runtime_references
        with patch('logixlab.runtime_references._next_address',0x100000000):
            self.assertEqual(space.program_attributes(engine.project,'MainProgram'),{})
        self.assertEqual(space.description()['allocated_objects'],0)

    def test_exhausted_replacement_revokes_both_indexes_and_can_allocate_after_recovery(self):
        engine=self.engine(['NOP();']);project=engine.project;space=engine.runtime_references
        old=int.from_bytes(space.program_attributes(project,'MainProgram')[5],'little')
        project.routines['mainprogram/mainroutine']=copy.deepcopy(project.routines['mainprogram/mainroutine'])
        with patch('logixlab.runtime_references._next_address',0x100000000):
            self.assertEqual(space.program_attributes(project,'MainProgram'),{})
        self.assertIsNone(space.resolve(project,old,'routine'))
        fresh=int.from_bytes(space.program_attributes(project,'MainProgram')[5],'little')
        self.assertNotEqual(fresh,old)
        self.assertIs(space.resolve(project,fresh,'routine'),project.routines['mainprogram/mainroutine'])


if __name__=='__main__':unittest.main()
