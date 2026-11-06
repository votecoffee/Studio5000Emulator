"""Ladder alarm records passed by reference through AOI calls."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


SAMPLE = Path(__file__).resolve().parents[1] / 'samples/AOIAlarmLab.L5X'


class AOIAlarmTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def engine(self, configure=None, *, checked=True):
        source = SAMPLE
        if configure is not None:
            tree = ET.parse(SAMPLE)
            configure(tree.getroot().find('Controller'))
            source = Path(self.directory.name) / 'alarms.L5X'
            tree.write(source, encoding='utf-8', xml_declaration=True)
        engine = Engine(Project(source))
        if checked:
            self.assertEqual(engine.blockers, [])
        return engine

    @staticmethod
    def enable(engine):
        engine.memory.write('RunAlarms', True)
        engine.memory.write('Trip', True)
        engine.memory.write('Pressure', 90)

    def test_live_records_prescan_and_authored_false_mode(self):
        engine = self.engine()
        memory = engine.memory
        self.enable(engine)
        engine.step()
        engine.step()
        self.assertFalse(memory.read('MotorAlarm.InAlarm'))
        self.assertFalse(memory.read('PressureAlarm.HInAlarm'))
        engine.step()
        self.assertTrue(memory.read('MotorAlarm.InAlarmUnack'))
        self.assertTrue(memory.read('PressureAlarm.HHInAlarmUnack'))
        self.assertEqual(set(engine.last_timer), {('ALMD', 'motoralarm'), ('ALMA', 'pressurealarm')})
        memory.write('AckAll', True)
        engine.step()
        self.assertTrue(memory.read('MotorAlarm.Acked'))
        self.assertTrue(memory.read('PressureAlarm.HHAcked'))
        memory.write('RunAlarms', False)
        engine.step()
        self.assertFalse(memory.read('MotorAlarm.EnableOut'))
        self.assertFalse(memory.read('MotorAlarm.InAlarm'))
        self.assertFalse(memory.read('PressureAlarm.EnableOut'))
        self.assertTrue(memory.read('PressureAlarm.HHInAlarm'))
        engine.enter_run()
        self.assertFalse(memory.read('PressureAlarm.HHInAlarm'))
        self.assertEqual(memory.read('PressureAlarm.HHInAlarmTime'), 0)
        self.assertEqual(memory.read('PressureAlarm.HHAlarmCount'), 1)
        self.assertEqual(engine.last_timer, {})

    def test_nested_aoi_resolves_program_scoped_alarm_through_alias(self):
        def configure(controller):
            tags = controller.find('Tags')
            program = controller.find('Programs/Program')
            record = tags.find('Tag[@Name="PressureAlarm"]')
            tags.remove(record)
            program.find('Tags').append(record)
            ET.SubElement(tags, 'Tag', Name='PressureAlias', TagType='Alias',
                          AliasFor='Program:MainProgram.PressureAlarm')
            text = program.find('Routines/Routine/RLLContent/Rung/Text')
            text.text = text.text.replace('LabAlarmMonitor(', 'LabAlarmWrapper(').replace('PressureAlarm', 'PressureAlias')
            definitions = controller.find('AddOnInstructionDefinitions')
            wrapper = copy.deepcopy(definitions[0])
            wrapper.set('Name', 'LabAlarmWrapper')
            definitions.append(wrapper)
            ET.SubElement(wrapper.find('LocalTags'), 'LocalTag', Name='Inner', DataType='LabAlarmMonitor', TagType='Base')
            for routine in wrapper.findall('Routines/Routine'):
                content = routine.find('RLLContent')
                content.clear()
                rung = ET.SubElement(content, 'Rung', Number='0', Type='N')
                prefix = 'AFI()' if routine.get('Name') == 'EnableInFalse' else ''
                ET.SubElement(rung, 'Text').text = prefix + 'LabAlarmMonitor(Inner,DigitalState,AnalogState,Trip,Pressure,AckAll);'
            tag = tags.find('Tag[@Name="Monitor"]')
            tag.set('DataType', 'LabAlarmWrapper')
            state = tag.find('Data/Structure')
            inner = copy.deepcopy(state)
            inner.tag = 'StructureMember'
            inner.set('Name', 'Inner')
            state.set('DataType', 'LabAlarmWrapper')
            state.append(inner)

        engine = self.engine(configure)
        self.enable(engine)
        for _ in range(3):
            engine.step()
        memory = engine.memory
        self.assertTrue(memory.read('PressureAlias.HInAlarm'))
        self.assertTrue(memory.read('Program:MainProgram.PressureAlarm.HInAlarm'))
        self.assertIn(('ALMA', 'program:mainprogram.pressurealarm'), engine.last_timer)
        self.assertEqual(memory.frames['@AOI:monitor.inner']['analogstate'],
                         ('Program:MainProgram.PressureAlarm', ''))

    def test_distinct_callers_keep_independent_alarm_timing(self):
        def configure(controller):
            tags = controller.find('Tags')
            for name in ('Monitor', 'MotorAlarm', 'PressureAlarm'):
                tag = copy.deepcopy(tags.find(f'Tag[@Name="{name}"]'))
                tag.set('Name', name+'B')
                if name.endswith('Alarm'):
                    parameters = tag.find('Data')[0]
                    parameters.set('MinDurationPRE', '40')
                tags.append(tag)
            content = controller.find('Programs/Program/Routines/Routine/RLLContent')
            rung = ET.SubElement(content, 'Rung', Number='1', Type='N')
            ET.SubElement(rung, 'Text').text = 'XIC(RunAlarms)LabAlarmMonitor(MonitorB,MotorAlarmB,PressureAlarmB,Trip,Pressure,AckAll);'

        engine = self.engine(configure)
        self.enable(engine)
        memory = engine.memory
        for _ in range(3):
            engine.step()
        self.assertTrue(memory.read('MotorAlarm.InAlarm'))
        self.assertTrue(memory.read('PressureAlarm.HInAlarm'))
        self.assertFalse(memory.read('MotorAlarmB.InAlarm'))
        self.assertFalse(memory.read('PressureAlarmB.HInAlarm'))
        engine.step(20)
        self.assertTrue(memory.read('MotorAlarmB.InAlarm'))
        self.assertTrue(memory.read('PressureAlarmB.HInAlarm'))

    def test_late_fault_restores_alarm_records_and_binding_history(self):
        def configure(controller):
            tags = controller.find('Tags')
            for name in ('Divisor', 'Quotient'):
                tag = ET.SubElement(tags, 'Tag', Name=name, DataType='DINT', TagType='Base')
                ET.SubElement(ET.SubElement(tag, 'Data', Format='Decorated'),
                              'DataValue', DataType='DINT', Value='1')
            content = controller.find('Programs/Program/Routines/Routine/RLLContent')
            rung = ET.SubElement(content, 'Rung', Number='1', Type='N')
            ET.SubElement(rung, 'Text').text = 'DIV(1,Divisor,Quotient);'

        engine = self.engine(configure)
        self.enable(engine)
        engine.step()
        memory = engine.memory
        memory.write('Divisor', 0)
        def state():
            return (memory.values, memory.frames, memory._resolved, engine.addons.instances,
                    engine.last_timer, engine.time_ms, engine.scan_count, engine.trace)
        before = copy.deepcopy(state())
        with self.assertRaisesRegex(ModelError, '(?i)divide|division'):
            engine.step(20)
        self.assertEqual(state(), before)
        memory.write('Divisor', 1)
        engine.step(20)
        self.assertEqual(memory.read('MotorAlarm.AlarmCount'), 1)
        self.assertEqual(memory.read('PressureAlarm.HAlarmCount'), 1)

    def test_local_alarm_operand_and_wrong_inout_binding_are_rejected(self):
        def local(controller):
            definition = controller.find('AddOnInstructionDefinitions/AddOnInstructionDefinition')
            ET.SubElement(definition.find('LocalTags'), 'LocalTag', Name='LocalAlarm',
                          DataType='ALARM_DIGITAL', TagType='Base')
            text = definition.find('Routines/Routine/RLLContent/Rung/Text')
            text.text = text.text.replace('DigitalState', 'LocalAlarm')

        def wrong(controller):
            text = controller.find('Programs/Program/Routines/Routine/RLLContent/Rung/Text')
            text.text = text.text.replace('MotorAlarm', 'Trip')

        def constant(controller):
            controller.find('Tags/Tag[@Name="MotorAlarm"]').set('Constant', 'true')

        for configure, diagnostic in ((local, 'requires an InOut parameter'), (wrong, 'InOut type/array'),
                                      (constant, 'read-only destination')):
            with self.subTest(case=configure.__name__):
                self.assertIn(diagnostic.lower(), ' '.join(self.engine(configure, checked=False).blockers).lower())


if __name__ == '__main__':
    unittest.main()
