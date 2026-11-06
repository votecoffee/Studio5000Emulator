"""Ladder ALMD import, scan states, commands and transaction boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


SAMPLE = Path(__file__).resolve().parents[1] / 'samples/AlarmLab.L5X'
MOTOR = 'MotorAlarm'


class LadderAlarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, configure=None, *, check=True):
        if configure is None:
            path = SAMPLE
        else:
            tree = ET.parse(SAMPLE)
            configure(tree.getroot().find('Controller'))
            path = Path(self.tmp.name) / 'alarm.L5X'
            tree.write(path, encoding='utf-8', xml_declaration=True)
        engine = Engine(Project(path))
        if check:
            self.assertEqual(engine.blockers, [])
        return engine

    @staticmethod
    def alarm(engine):
        return engine.memory.read(MOTOR)

    @staticmethod
    def motor_parameters(controller):
        return controller.find("./Tags/Tag[@Name='MotorAlarm']/Data/AlarmDigitalParameters")

    def test_delay_starts_on_first_sample_and_restarts_after_normal(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('Trip', True)
        engine.step()
        self.assertFalse(self.alarm(engine)['InAlarm'])
        memory.write('Trip', False)
        engine.step()
        memory.write('Trip', True)
        engine.step()
        engine.step()
        self.assertFalse(self.alarm(engine)['InAlarm'])
        engine.step()
        alarm = self.alarm(engine)
        self.assertTrue(alarm['InAlarmUnack'])
        self.assertEqual(alarm['AlarmCount'], 1)
        self.assertEqual(alarm['MinDurationACC'], 0)

    def test_active_low_executes_on_false_rung_and_keeps_false_power(self):
        engine = self.engine()
        engine.memory.write('Healthy', False)
        engine.memory.write('SignalAlarm.InFault', True)
        engine.step()
        signal = engine.memory.read('SignalAlarm')
        self.assertTrue(signal['InAlarm'])
        self.assertTrue(signal['Acked'])
        self.assertFalse(signal['In'])
        self.assertFalse(signal['EnableOut'])
        self.assertEqual(signal['Status'], 2)
        self.assertTrue(engine.memory.read('SignalAlarm.InFaulted'))
        engine.memory.write('Healthy', True)
        engine.step()
        self.assertFalse(engine.memory.read('SignalAlarm.InAlarm'))

    def test_latch_requires_a_new_reset_edge_after_the_input_goes_normal(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('MotorAlarm.MinDurationPRE', 0)
        memory.write('Trip', True)
        engine.step()
        memory.write('ResetAlarm', True)
        engine.step()
        self.assertTrue(self.alarm(engine)['InAlarmUnack'])
        memory.write('Trip', False)
        engine.step()
        self.assertTrue(self.alarm(engine)['InAlarmUnack'])
        memory.write('ResetAlarm', False)
        engine.step()
        memory.write('ResetAlarm', True)
        engine.step()
        self.assertFalse(self.alarm(engine)['InAlarm'])
        self.assertTrue(self.alarm(engine)['Acked'])

    def test_nonlatched_return_to_normal_keeps_pending_acknowledgment(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('MotorAlarm.MinDurationPRE', 0)
        memory.write('MotorAlarm.Latched', False)
        memory.write('Trip', True)
        engine.step()
        memory.write('Trip', False)
        engine.step()
        self.assertFalse(self.alarm(engine)['InAlarm'])
        self.assertFalse(self.alarm(engine)['Acked'])
        memory.write('MotorAlarm.OperAck', True)
        engine.step()
        self.assertTrue(self.alarm(engine)['Acked'])
        self.assertFalse(self.alarm(engine)['OperAck'])

    def test_enable_precedes_disable_count_saturates_and_reset_command_clears(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('MotorAlarm.MinDurationPRE', 0)
        memory.write('MotorAlarm.AlarmCount', 2147483647)
        memory.write('Trip', True)
        memory.write('DisableAlarm', True)
        memory.write('EnableAlarm', True)
        engine.step()
        self.assertTrue(self.alarm(engine)['InAlarm'])
        self.assertFalse(self.alarm(engine)['Disabled'])
        self.assertEqual(self.alarm(engine)['AlarmCount'], 2147483647)
        memory.write('EnableAlarm', False)
        engine.step()
        self.assertTrue(self.alarm(engine)['Disabled'])
        self.assertFalse(self.alarm(engine)['InAlarm'])
        self.assertFalse(self.alarm(engine)['Acked'])
        memory.write('MotorAlarm.OperAck', True)
        engine.step()
        self.assertTrue(self.alarm(engine)['Acked'])
        memory.write('MotorAlarm.AlarmCountReset', True)
        memory.write('MotorAlarm.OperEnable', True)
        engine.step()
        self.assertTrue(self.alarm(engine)['InAlarm'])
        self.assertEqual(self.alarm(engine)['AlarmCount'], 0)
        self.assertFalse(self.alarm(engine)['AlarmCountReset'])
        self.assertFalse(self.alarm(engine)['OperEnable'])

    def test_failed_later_alarm_rolls_back_delay_and_commands(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('Trip', True)
        memory.write('SignalAlarm.UseProgTime', True)
        baseline = copy.deepcopy((memory.values, engine.last_timer, engine.time_ms, engine.scan_count))
        with self.assertRaisesRegex(ModelError, 'program timestamps'):
            engine.step()
        self.assertEqual((memory.values, engine.last_timer, engine.time_ms, engine.scan_count), baseline)
        memory.write('SignalAlarm.UseProgTime', False)
        engine.step()
        engine.step()
        self.assertFalse(self.alarm(engine)['InAlarm'])
        engine.step()
        self.assertTrue(self.alarm(engine)['InAlarm'])
        memory.write('Acknowledge', True)
        memory.write('SignalAlarm.OperShelve', True)
        with self.assertRaisesRegex(ModelError, 'shelve'):
            engine.step()
        self.assertTrue(self.alarm(engine)['InAlarmUnack'])
        memory.write('SignalAlarm.OperShelve', False)
        engine.step()
        self.assertTrue(self.alarm(engine)['Acked'])

    def test_program_suppression_preserves_delay_and_count_and_unsuppress_rearms(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('MotorAlarm.ProgSuppress', True)
        memory.write('Trip', True)
        engine.step()
        engine.step()
        self.assertTrue(self.alarm(engine)['Suppressed'])
        self.assertFalse(self.alarm(engine)['InAlarm'])
        engine.step()
        alarm = self.alarm(engine)
        self.assertTrue(alarm['InAlarm'])
        self.assertTrue(alarm['Acked'])
        self.assertEqual(alarm['AlarmCount'], 1)

        memory.write('MotorAlarm.ProgUnsuppress', True)
        engine.step()
        self.assertFalse(alarm['Suppressed'])
        self.assertTrue(alarm['InAlarmUnack'])
        self.assertEqual(alarm['AlarmCount'], 1)
        memory.write('MotorAlarm.ProgUnsuppress', False)
        engine.step()
        self.assertTrue(alarm['Suppressed'])
        self.assertTrue(alarm['InAlarmUnack'])

    def test_operator_suppression_on_false_rung_retains_pending_ack_until_acknowledged(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('SignalAlarm.AckRequired', True)
        memory.write('Healthy', False)
        engine.step()
        signal = memory.read('SignalAlarm')
        self.assertTrue(signal['InAlarmUnack'])
        memory.write('SignalAlarm.OperSuppress', True)
        engine.step()
        self.assertTrue(signal['Suppressed'])
        self.assertTrue(signal['InAlarmUnack'])
        self.assertFalse(signal['OperSuppress'])

        memory.write('SignalAlarm.OperAck', True)
        engine.step()
        self.assertTrue(signal['Acked'])
        self.assertFalse(signal['InAlarmUnack'])
        memory.write('Healthy', True)
        memory.write('SignalAlarm.OperSuppress', True)
        memory.write('SignalAlarm.OperUnsuppress', True)
        engine.step()
        self.assertFalse(signal['Suppressed'])
        self.assertFalse(signal['InAlarm'])
        self.assertTrue(signal['Acked'])
        self.assertFalse(signal['OperSuppress'])
        self.assertFalse(signal['OperUnsuppress'])

    def test_suppression_and_operator_command_consumption_roll_back_together(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('MotorAlarm.MinDurationPRE', 0)
        memory.write('MotorAlarm.OperSuppress', True)
        memory.write('Trip', True)
        memory.write('SignalAlarm.UseProgTime', True)
        baseline = copy.deepcopy((memory.values, engine.last_timer, engine.time_ms))
        with self.assertRaisesRegex(ModelError, 'program timestamps'):
            engine.step()
        self.assertEqual((memory.values, engine.last_timer, engine.time_ms), baseline)

        memory.write('SignalAlarm.UseProgTime', False)
        engine.step()
        alarm = self.alarm(engine)
        self.assertTrue(alarm['Suppressed'])
        self.assertTrue(alarm['InAlarm'])
        self.assertTrue(alarm['Acked'])
        self.assertFalse(alarm['OperSuppress'])

    def test_prescan_clears_active_and_operator_requests_but_retains_count(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('Trip', True)
        memory.write('MotorAlarm.MinDurationPRE', 0)
        engine.step()
        memory.write('MotorAlarm.OperSuppress', True)
        engine.step()
        self.assertTrue(self.alarm(engine)['Suppressed'])
        memory.write('MotorAlarm.OperAck', True)
        memory.write('MotorAlarm.OperUnsuppress', True)
        engine.enter_run()
        alarm = self.alarm(engine)
        self.assertFalse(alarm['EnableOut'])
        self.assertFalse(alarm['InAlarm'])
        self.assertTrue(alarm['Acked'])
        self.assertFalse(alarm['OperAck'])
        self.assertFalse(alarm['OperUnsuppress'])
        self.assertTrue(alarm['Suppressed'])
        self.assertEqual(alarm['AlarmCount'], 1)
        self.assertEqual(engine.last_timer, {})

    def test_program_scoped_alias_and_immediate_preset(self):
        def configure(controller):
            tags = controller.find('Tags')
            motor = tags.find("Tag[@Name='MotorAlarm']")
            tags.remove(motor)
            controller.find('./Programs/Program/Tags').append(motor)
            ET.SubElement(tags, 'Tag', Name='MotorAlias', TagType='Alias',
                          AliasFor='Program:MainProgram.MotorAlarm', DataType='ALARM_DIGITAL')
            text = controller.find('.//RLLContent/Rung/Text')
            text.text = text.text.replace('MotorAlarm', 'MotorAlias').replace('?,?', '0,0')
        engine = self.engine(configure)
        engine.memory.write('Trip', True)
        engine.step()
        self.assertTrue(engine.memory.read('MotorAlias.InAlarm'))
        self.assertEqual(engine.memory.read('Program:MainProgram.MotorAlarm.MinDurationPRE'), 0)
        self.assertFalse(engine.project.alarm_catalog.empty)
        self.assertTrue(engine.report()['ladder_alarms']['available'])

    def test_import_and_preflight_reject_unqualified_shapes_and_operands(self):
        for change, expected in (
            (lambda c: c.set('ProcessorType', '1756-L75'), 'v35 ControlLogix 5580'),
            (lambda c: c.find("./Tags/Tag[@Name='MotorAlarm']").set('Dimensions', '2'), 'scalar Standard Alarm data'),
            (lambda c: c.find("./Tags/Tag[@Name='MotorAlarm']").set('Constant', 'true'), 'Read-only destination'),
            (lambda c: self.motor_parameters(c).set('Condition', '2'), 'requires a BOOL value'),
            (lambda c: self.motor_parameters(c).set('Unexpected', '1'), 'parameter Unexpected is unsupported'),
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, ' '.join(self.engine(change, check=False).blockers))

        for before, after, expected in (
            ('Acknowledge', '2', 'scalar BOOL'),
            ('?,?', '1,1', 'zero accumulator'),
            ('?,?', 'Trip,0', 'DINT preset'),
        ):
            def configure(controller):
                text = controller.find('.//RLLContent/Rung/Text')
                text.text = text.text.replace(before, after)
            with self.subTest(after=after):
                self.assertIn(expected, ' '.join(self.engine(configure, check=False).blockers))


if __name__ == '__main__':
    unittest.main()
