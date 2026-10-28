"""An untouched empty native source remains empty after another routine changes."""
import unittest
from xml.etree import ElementTree as ET

from logixlab import routine_read,routine_source
from logixlab.routine_edits import prepare
import test_routine_read as wire
from test_routine_source import container,xml_source


class EmptySourceSnapshotTests(wire.logs.NamespaceFixture,unittest.TestCase):
    setUp=wire.EmptyRoutineReadWireTests.setUp
    complete_tasks=wire.EmptyRoutineReadWireTests.complete_tasks
    configure=wire.EmptyRoutineReadWireTests.configure
    ready_setup=wire.EmptyRoutineReadWireTests.ready_setup
    ready_routines=wire.EmptyRoutineReadWireTests.ready_routines
    next_routines=wire.EmptyRoutineReadWireTests.next_routines
    ready_map=wire.EmptyRoutineReadWireTests.ready_map
    ready_log=wire.EmptyRoutineReadWireTests.ready_log
    proposal=wire.EmptyRoutineReadWireTests.proposal
    ready_install=wire.EmptyRoutineReadWireTests.ready_install
    installed=wire.RoutineReadWireTests.installed

    def test_empty_untouched_source_preserves_exact_bytes_without_inventing_a_rung(self):
        self.installed();before=routine_read.source(self.app,2,1)
        source=routine_source.decode_download(before,empty=True);self.assertEqual(source.rungs,())
        raw=container(ET.tostring(xml_source(name='Reporting')));engine=self.app.engine
        candidate,_=prepare(engine,routine_source.decode(raw),('NOP();',),'MainProgram',0,
            native_source=raw,native_target=(2,2));self.app.engine=candidate
        self.assertEqual(routine_read.source(self.app,2,1),before)
        self.assertEqual(candidate.project.routines['mainprogram/mainroutine'].rungs,[])
        self.assertEqual(candidate.memory.values,engine.memory.values)


if __name__=='__main__':unittest.main()
