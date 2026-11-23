"""Read and clear modeled overflow records from ordinary ladder logic."""
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.model import ModelError
from logixlab.routine_edits import replacement_engine
from logixlab.runtime import Engine
import test_gsv_configuration as config
from test_program_faults import add_fault_dint_array

GSV = 'GSV(Program,THIS,MinorFaultRecord,FaultSample[1]);'
SSV = 'SSV(Program,THIS,MinorFaultRecord,FaultSample[1]);'
OVERFLOW = 'XIC(Flag)ADD(2147483647,1,Out);'
TYPE_CODE = (4 << 16) | 4
TIMESTAMP = 1760000000000000


def configure(root, *, reporting=True):
    controller = root.find('Controller')
    if reporting is not None:
        controller.set('ReportMinorOverflow', str(reporting).lower())
    tags = controller.find('Tags')
    add_fault_dint_array(tags, 'FaultSample', [77] * 13)
    config.scalar(tags, 'OverflowSeen', 'BOOL', 0)


def record(timestamp):
    low, high = struct.unpack('<2i', struct.pack('<q', timestamp))
    return [low, high, TYPE_CODE] + [None] * 8


class MinorFaultRecordTests(unittest.TestCase):
    setUp = config.GsvConfigurationTests.setUp
    engine = config.GsvConfigurationTests.engine
    checked = config.GsvConfigurationTests.checked

    def test_same_scan_read_persistence_and_clean_native_diagnostics(self):
        engine = self.checked([OVERFLOW, 'XIC(S:MINOR)OTE(OverflowSeen);', 'OTU(S:MINOR);', GSV],
                              mutate=configure)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
            self.assertEqual(engine.memory.read('FaultSample'), [77] + [0] * 11 + [77])
            engine.memory.write('Flag', True)
            engine.step(10)
            self.assertTrue(engine.memory.read('OverflowSeen'))
            self.assertEqual(engine.memory.read('FaultSample'), [77] + record(TIMESTAMP) + [77])
        engine.memory.write('Flag', False)
        engine.step(10)
        self.assertFalse(engine.memory.read('OverflowSeen'))
        self.assertEqual(engine.memory.read('FaultSample'), [77] + record(TIMESTAMP) + [77])
        wire = engine.program_fault_attributes('BackgroundProgram', source_sha256=engine.project.sha256)
        self.assertEqual(wire, {20: bytes(44)})
        engine.enter_run()
        engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample')[1:12], record(TIMESTAMP))
        replacement = replacement_engine(engine, engine.project)
        replacement.step(10)
        self.assertEqual(replacement.memory.read('FaultSample')[1:12], record(TIMESTAMP))
        reset = Engine(engine.project)
        reset.step(10)
        self.assertEqual(reset.memory.read('FaultSample')[1:12], [0] * 11)

    def test_disabled_reporting_and_manual_status_do_not_create_records(self):
        for reported in (False, None):
            with self.subTest(reporting=reported):
                def settings(root):
                    configure(root, reporting=reported)

                engine = self.checked([OVERFLOW, 'OTL(S:MINOR);', 'XIC(S:MINOR)OTE(OverflowSeen);', GSV],
                                      mutate=settings)
                engine.memory.write('Flag', True)
                engine.step(10)
                self.assertTrue(engine.memory.read('OverflowSeen'))
                self.assertEqual(engine.memory.read('FaultSample')[1:12], [0] * 11)
                self.assertEqual(engine.program_fault_description()['program_minor_overflow_records'], 0)

    def test_later_fault_rolls_back_new_record_and_writes(self):
        engine = self.checked([OVERFLOW, GSV, 'CPT(Limit,1/Index);'], mutate=configure)
        engine.memory.write('Index', 1)
        engine.memory.write('Flag', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        engine.memory.write('Index', 0)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP + 100):
            with self.assertRaisesRegex(ModelError, 'zero'):
                engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample')[1:12], record(TIMESTAMP))
        engine.memory.write('Flag', False)
        engine.memory.write('Index', 1)
        engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample')[1:12], record(TIMESTAMP))

    def test_programs_read_separate_records_on_the_same_task(self):
        def settings(root):
            configure(root)
            controller = root.find('Controller')
            add_fault_dint_array(controller.find('Tags'), 'SecondRecord', [77] * 11)
            # Give these two Programs the same owner, so a shared status bit
            # cannot masquerade as a second Program's stored record.
            background = controller.find('./Tasks/Task[@Name="BackgroundTask"]/ScheduledPrograms')
            E.SubElement(background, 'ScheduledProgram', Name='FastProgram')
            tasks = controller.find('Tasks')
            tasks.remove(tasks.find('Task[@Name="FastTask"]'))
            routine = controller.find('./Programs/Program[@Name="FastProgram"]/Routines/Routine[@Name="Main"]')
            routine.clear()
            routine.attrib.update(Name='Main', Type='RLL')
            rung = E.SubElement(E.SubElement(routine, 'RLLContent'), 'Rung', Number='0', Type='N')
            E.SubElement(rung, 'Text').text = 'GSV(Program,THIS,MinorFaultRecord,SecondRecord[0]);'

        engine = self.checked([OVERFLOW, GSV], mutate=settings)
        engine.memory.write('Flag', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample')[1:12], record(TIMESTAMP))
        self.assertEqual(engine.memory.read('SecondRecord'), [0] * 11)

    def test_aoi_overflow_is_recorded_for_its_caller_program(self):
        import test_aoi_queues as aoi

        def settings(root):
            configure(root)
            aoi.logic(root, ['ADD(2147483647,1,Stack[0]);'])
            content = root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
            rung = E.SubElement(content, 'Rung', Number=str(len(content)), Type='N')
            E.SubElement(rung, 'Text').text = GSV

        engine = aoi.AOIQueueTests.engine(self, settings)
        self.assertEqual(engine.blockers, [])
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample')[1:12], record(TIMESTAMP))

    def test_fault_record_udt_stores_split_type_and_code_and_timestamp(self):
        for wide_time in (False, True):
            with self.subTest(wide_time=wide_time):
                def settings(root):
                    configure(root)
                    controller = root.find('Controller')
                    dtype = E.SubElement(controller.find('DataTypes'), 'DataType', Name='FaultLayout', Class='User')
                    members = E.SubElement(dtype, 'Members')
                    time_fields = [('Time', 'LINT', '0')] if wide_time else [('Time', 'DINT', '0'), ('TimeHigh', 'DINT', '0')]
                    for name, kind, dimension in time_fields + [
                        ('Type', 'INT', '0'), ('Code', 'INT', '0'), ('Info', 'DINT', '8')
                    ]:
                        E.SubElement(members, 'Member', Name=name, DataType=kind, Dimension=dimension)
                    tag = E.SubElement(controller.find('Tags'), 'Tag', Name='Sample',
                                       DataType='FaultLayout', TagType='Base')
                    structure = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'),
                                             'Structure', DataType='FaultLayout')
                    E.SubElement(structure, 'DataValueMember', Name='Type', DataType='INT', Value='0')

                engine = self.checked([
                    OVERFLOW, GSV.replace('FaultSample[1]', 'Sample.Time'),
                    'XIO(Flag)CLR(Sample.Type)CLR(Sample.Code);',
                    'XIO(Flag)' + SSV.replace('FaultSample[1]', 'Sample.Time'), GSV,
                ], mutate=settings)
                engine.memory.write('Flag', True)
                with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
                    engine.step(10)
                value = engine.memory.read('Sample')
                self.assertEqual((value['Type'], value['Code'], value['Info']), (4, 4, [None] * 8))
                if wide_time:
                    self.assertEqual(value['Time'], TIMESTAMP)
                else:
                    self.assertEqual([value['Time'], value['TimeHigh']], record(TIMESTAMP)[:2])
                engine.memory.write('Flag', False)
                engine.step(10)
                self.assertEqual(engine.memory.read('FaultSample')[1:12], [0] * 11)

    def test_false_rung_skips_live_index_and_scope_is_checked(self):
        logic = 'XIC(Flag)GSV(Program,THIS,MinorFaultRecord,FaultSample[Index]);'
        engine = self.checked([logic], mutate=configure)
        engine.memory.write('Index', 99)
        engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample'), [77] * 13)
        engine.memory.write('Flag', True)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            engine.step(10)
        self.assertEqual(engine.memory.read('FaultSample'), [77] * 13)
        for args in (
            dict(harness=True),
            dict(st=True),
        ):
            self.assertTrue(self.engine([GSV], mutate=configure, **args).blockers)
        self.assertTrue(self.engine([GSV.replace('THIS', 'MissingProgram')], mutate=configure).blockers)
        self.assertTrue(self.engine([GSV.replace('FaultSample[1]', 'FaultSample[3]')], mutate=configure).blockers)


READ_BITS = 'GSV(FaultLog,,MinorFaultBits,LogBits);'
READ_COUNT = 'GSV(FaultLog,,MinorEvents,LogCount);'
WRITE_BITS = 'SSV(FaultLog,,MinorFaultBits,BitInput);'
RESET_COUNT = 'SSV(FaultLog,,MinorEvents,CountInput);'
INSTRUCTION_BIT = 1 << 4


def log_tags(root):
    configure(root)
    tags = root.find('./Controller/Tags')
    for name, dtype, initial in (
        ('LogBits', 'DINT', 77), ('LogCount', 'INT', 77),
        ('BitInput', 'DINT', 0), ('CountInput', 'INT', 0),
        ('WriteBits', 'BOOL', 0), ('ResetCount', 'BOOL', 0),
    ):
        config.scalar(tags, name, dtype, initial)


def named_programs(root):
    log_tags(root)
    controller = root.find('Controller')
    tags = controller.find('Tags')
    add_fault_dint_array(tags, 'PeerRecord', [77] * 11)
    add_fault_dint_array(tags, 'ClearWords', [0] * 11)
    config.scalar(tags, 'PeerOverflow', 'BOOL', 0)
    body = controller.find('./Programs/Program[@Name="FastProgram"]/Routines/Routine/RLLContent')
    body.clear()
    rung = E.SubElement(body, 'Rung', Number='0', Type='N')
    E.SubElement(rung, 'Text').text = 'XIC(PeerOverflow)ADD(2147483647,1,Out);'


READ_PEER = 'GSV(Program,fAsTpRoGrAm,MinorFaultRecord,PeerRecord[0]);'
CLEAR_PEER = 'XIC(ResetCount)SSV(Program,FastProgram,MinorFaultRecord,ClearWords[0]);'


class NamedMinorFaultRecordTests(unittest.TestCase):
    setUp = config.GsvConfigurationTests.setUp
    engine = config.GsvConfigurationTests.engine
    checked = config.GsvConfigurationTests.checked

    def test_cross_task_read_clear_and_relatch_are_local_to_target(self):
        engine = self.checked([
            OVERFLOW, CLEAR_PEER, READ_PEER, GSV.replace('THIS', 'BackgroundProgram'),
            'XIC(S:MINOR)OTE(OverflowSeen);', READ_BITS, READ_COUNT,
        ], mutate=named_programs)
        memory = engine.memory
        memory.write('Flag', True)
        memory.write('PeerOverflow', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP))
        self.assertEqual(memory.read('PeerRecord'), record(TIMESTAMP))
        self.assertEqual(memory.read('LogCount'), 2)

        memory.write('PeerOverflow', False)
        memory.write('ResetCount', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP + 10):
            engine.step(10)
        self.assertEqual(memory.read('PeerRecord'), [0] * 11)
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP + 10))
        self.assertTrue(memory.read('OverflowSeen'))
        self.assertEqual((memory.read('LogBits'), memory.read('LogCount')), (INSTRUCTION_BIT, 3))
        self.assertEqual(engine.program_fault_attributes('FastProgram', source_sha256=engine.project.sha256),
                         {20: bytes(44)})

        memory.write('Flag', False)
        memory.write('ResetCount', False)
        memory.write('PeerOverflow', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP + 20):
            engine.step(10)
        self.assertEqual(memory.read('PeerRecord'), record(TIMESTAMP + 20))
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP + 10))
        self.assertFalse(memory.read('OverflowSeen'))

    def test_failed_advance_preserves_peers_record(self):
        engine = self.checked([CLEAR_PEER, READ_PEER, 'CPT(Limit,1/Index);'], mutate=named_programs)
        memory = engine.memory
        memory.write('PeerOverflow', True)
        memory.write('Index', 1)
        engine.step(10)
        original = memory.read('PeerRecord').copy()
        self.assertEqual(original[2], TYPE_CODE)

        memory.write('PeerOverflow', False)
        memory.write('ResetCount', True)
        memory.write('Index', 0)
        with self.assertRaisesRegex(ModelError, 'zero'):
            engine.step(10)
        self.assertEqual(memory.read('PeerRecord'), original)
        memory.write('ResetCount', False)
        memory.write('Index', 1)
        engine.step(10)
        self.assertEqual(memory.read('PeerRecord'), original)
        memory.write('ResetCount', True)
        engine.step(10)
        self.assertEqual(memory.read('PeerRecord'), [0] * 11)

    def test_rejects_unscheduled_targets_harnesses_and_structured_text(self):
        def unscheduled(root):
            named_programs(root)
            root.find('./Controller/Tasks/Task[@Name="FastTask"]/ScheduledPrograms').clear()

        for rung in (READ_PEER, CLEAR_PEER):
            with self.subTest(rung=rung):
                self.assertTrue(self.engine([rung], mutate=unscheduled).blockers)
                self.assertTrue(self.engine([rung], mutate=named_programs, harness=True).blockers)
        for line in (READ_PEER, CLEAR_PEER.removeprefix('XIC(ResetCount)')):
            self.assertTrue(self.engine([line], mutate=named_programs, st=True).blockers)


SHORT_GSV = 'XIC(ResetCount)GSV(Program,FastProgram,MinorFaultRecord,FaultSample[Index]);'
READ_CALLER = 'GSV(Program,THIS,MinorFaultRecord,CallerRecord[0]);'
READ_MINOR = 'XIC(S:MINOR)OTE(MinorSeen);'
SHORT_TYPE_CODE = (7 << 16) | 4


def add_capacity_fixture(root):
    named_programs(root)
    tags = root.find('./Controller/Tags')
    add_fault_dint_array(tags, 'CallerRecord', [77] * 11)
    config.scalar(tags, 'MinorSeen', 'BOOL', 0)


class MinorFaultCapacityTests(unittest.TestCase):
    setUp = config.GsvConfigurationTests.setUp
    engine = config.GsvConfigurationTests.engine
    checked = config.GsvConfigurationTests.checked

    def test_short_live_window_reports_to_caller_and_preserves_entire_destination(self):
        def settings(root):
            add_capacity_fixture(root)
            root.find('Controller').set('ReportMinorOverflow', 'false')

        engine = self.checked([
            SHORT_GSV.removesuffix(';') + 'XIC(S:V)OTE(OverflowSeen);',
            READ_MINOR, READ_CALLER, READ_PEER, READ_BITS, READ_COUNT,
        ], mutate=settings)
        memory = engine.memory
        memory.write('Index', 3)
        engine.step(10)
        self.assertEqual(memory.read('CallerRecord'), [0] * 11)
        self.assertEqual(memory.read('LogCount'), 0)
        memory.write('ResetCount', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        expected = record(TIMESTAMP)
        expected[2] = SHORT_TYPE_CODE
        self.assertEqual(memory.read('CallerRecord'), expected)
        self.assertEqual(memory.read('PeerRecord'), [0] * 11)
        self.assertEqual(memory.read('FaultSample'), [77] * 13)
        self.assertTrue(memory.read('MinorSeen'))
        self.assertFalse(memory.read('OverflowSeen'))
        self.assertEqual((memory.read('LogBits'), memory.read('LogCount')), (INSTRUCTION_BIT, 1))
        wire = {name: engine.program_fault_attributes(name, source_sha256=engine.project.sha256)
                for name in ('BackgroundProgram', 'FastProgram')}
        self.assertEqual(wire['BackgroundProgram'], {20: bytes(44)})
        self.assertEqual(wire['FastProgram'], {20: bytes(44), 21: bytes(44)})
        self.assertEqual(engine.program_fault_description()['program_minor_fault_records'], 1)
        self.assertEqual(engine.program_fault_description()['program_minor_overflow_records'], 0)

        memory.write('Index', 2)
        engine.step(10)
        self.assertEqual(memory.read('FaultSample'), [77, 77] + [0] * 11)
        self.assertEqual(memory.read('CallerRecord'), expected)
        self.assertEqual(memory.read('LogCount'), 1)
        self.assertFalse(memory.read('MinorSeen'))

    def test_late_failure_rolls_back_code_7_and_preserves_previous_overflow(self):
        engine = self.checked([
            OVERFLOW, SHORT_GSV, READ_CALLER, READ_COUNT, 'CPT(Out,1/Limit);',
        ], mutate=add_capacity_fixture)
        memory = engine.memory
        memory.write('Index', 3)
        memory.write('Flag', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        self.assertEqual(memory.read('CallerRecord'), record(TIMESTAMP))
        memory.write('Flag', False)
        memory.write('ResetCount', True)
        memory.write('Limit', 0)
        with self.assertRaisesRegex(ModelError, 'zero'):
            engine.step(10)
        self.assertEqual(memory.read('CallerRecord'), record(TIMESTAMP))
        self.assertEqual(memory.read('LogCount'), 1)
        memory.write('ResetCount', False)
        memory.write('Limit', 2)
        engine.step(10)
        self.assertEqual(memory.read('CallerRecord'), record(TIMESTAMP))
        self.assertEqual(memory.read('LogCount'), 1)
        memory.write('ResetCount', True)
        engine.step(10)
        self.assertEqual(memory.read('CallerRecord[2]'), SHORT_TYPE_CODE)
        self.assertEqual(memory.read('LogCount'), 2)

    def test_static_short_window_and_runtime_out_of_range_keep_existing_errors(self):
        fixed = SHORT_GSV.replace('FaultSample[Index]', 'FaultSample[3]')
        self.assertTrue(self.engine([fixed], mutate=add_capacity_fixture).blockers)
        engine = self.checked([SHORT_GSV, READ_CALLER, READ_COUNT], mutate=add_capacity_fixture)
        memory = engine.memory
        memory.write('Index', 13)
        engine.step(10)
        memory.write('ResetCount', True)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            engine.step(10)
        self.assertEqual(memory.read('LogCount'), 0)
        self.assertEqual(memory.read('CallerRecord'), [0] * 11)


class MinorFaultLogTests(unittest.TestCase):
    setUp = config.GsvConfigurationTests.setUp
    engine = config.GsvConfigurationTests.engine
    checked = config.GsvConfigurationTests.checked

    def test_latched_bits_and_count_are_independent_of_program_record(self):
        engine = self.checked([
            OVERFLOW, 'XIC(WriteBits)' + WRITE_BITS, 'XIC(ResetCount)' + RESET_COUNT,
            'XIC(S:MINOR)OTE(OverflowSeen);', READ_BITS, READ_COUNT, GSV,
        ], mutate=log_tags)
        memory = engine.memory

        def scan(bits, count):
            engine.step(10)
            self.assertEqual((memory.read('LogBits'), memory.read('LogCount')), (bits, count))

        scan(0, 0)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            memory.write('Flag', True)
            scan(INSTRUCTION_BIT, 1)
            scan(INSTRUCTION_BIT, 2)
        self.assertTrue(memory.read('OverflowSeen'))
        memory.write('Flag', False)
        memory.write('WriteBits', True)
        scan(0, 2)
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP))
        self.assertFalse(memory.read('OverflowSeen'))
        # Writing a reason bit changes only the bitmap.
        memory.write('BitInput', 0x200)
        memory.write('ResetCount', True)
        scan(0x200, 0)
        memory.write('WriteBits', False)
        memory.write('ResetCount', False)
        engine.enter_run()
        scan(0x200, 0)
        memory.write('Flag', True)
        scan(0x200 | INSTRUCTION_BIT, 1)
        reset = Engine(engine.project)
        reset.step(10)
        self.assertEqual((reset.memory.read('LogBits'), reset.memory.read('LogCount')), (0, 0))

    def test_clear_preserves_summary_and_status_and_relatches_on_overflow(self):
        engine = self.checked([
            OVERFLOW, GSV, 'XIC(ResetCount)CLR(FaultSample[3]);', 'XIC(ResetCount)' + SSV,
            'XIC(S:MINOR)OTE(OverflowSeen);', GSV, READ_BITS, READ_COUNT,
        ], mutate=log_tags)
        memory = engine.memory
        memory.write('ResetCount', True)
        engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], [0] * 11)
        self.assertEqual(engine.program_fault_attributes('BackgroundProgram', source_sha256=engine.project.sha256),
                         {20: bytes(44), 21: bytes(44)})
        memory.write('Flag', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        self.assertEqual(memory.read('FaultSample'), [77] + [0] * 11 + [77])
        self.assertTrue(memory.read('OverflowSeen'))
        self.assertEqual((memory.read('LogBits'), memory.read('LogCount')), (INSTRUCTION_BIT, 1))
        self.assertEqual(engine.program_fault_attributes('BackgroundProgram', source_sha256=engine.project.sha256),
                         {20: bytes(44)})

        memory.write('Flag', False)
        memory.write('ResetCount', False)
        engine.enter_run()
        replacement = replacement_engine(engine, engine.project)
        replacement.step(10)
        self.assertEqual(replacement.memory.read('FaultSample')[1:12], [0] * 11)
        replacement.memory.write('Flag', True)
        with patch.object(replacement, 'wall_time', return_value=TIMESTAMP + 10):
            replacement.step(10)
        self.assertEqual(replacement.memory.read('FaultSample')[1:12], record(TIMESTAMP + 10))
        self.assertEqual(replacement.memory.read('LogCount'), 2)

    def test_late_failure_rolls_back_clear(self):
        engine = self.checked([
            OVERFLOW, GSV, 'XIC(ResetCount)CLR(FaultSample[3]);', 'XIC(ResetCount)' + SSV,
            GSV, 'CPT(Limit,1/Index);',
        ], mutate=log_tags)
        memory = engine.memory
        memory.write('Index', 1)
        memory.write('Flag', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        memory.write('Flag', False)
        memory.write('ResetCount', True)
        memory.write('Index', 0)
        with self.assertRaisesRegex(ModelError, 'zero'):
            engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP))
        memory.write('ResetCount', False)
        memory.write('Index', 1)
        engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP))
        memory.write('ResetCount', True)
        engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], [0] * 11)

    def test_clear_requires_known_zero_and_valid_live_region(self):
        def settings(root):
            log_tags(root)
            tags = root.find('./Controller/Tags')
            add_fault_dint_array(tags, 'ClearWords', [0] * 12)
            array = tags.find('./Tag[@Name="ClearWords"]/Data/Array')
            array.remove(array.find('./Element[@Index="[3]"]'))

        indirect = 'XIC(ResetCount)' + SSV.replace('FaultSample[1]', 'ClearWords[Index]')
        engine = self.checked([OVERFLOW, indirect, GSV], mutate=settings)
        memory = engine.memory
        memory.write('Index', 99)
        memory.write('Flag', True)
        with patch.object(engine, 'wall_time', return_value=TIMESTAMP):
            engine.step(10)
        memory.write('Flag', False)
        memory.write('ResetCount', True)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            engine.step(10)
        memory.write('Index', 1)
        with self.assertRaisesRegex(ModelError, 'known zero Type and Code'):
            engine.step(10)
        memory.write('ClearWords[3]', TYPE_CODE)
        with self.assertRaisesRegex(ModelError, 'known zero Type and Code'):
            engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], record(TIMESTAMP))
        memory.write('ClearWords[3]', 0)
        engine.step(10)
        self.assertEqual(memory.read('FaultSample')[1:12], [0] * 11)
        for rung, options in (
            (SSV, {'harness': True}),
            (SSV, {'st': True}),
            (SSV.replace('THIS', 'MissingProgram'), {}),
            (SSV.replace('FaultSample[1]', 'FaultSample[3]'), {}),
        ):
            self.assertTrue(self.engine([rung], mutate=log_tags, **options).blockers)

    def test_controller_summary_is_visible_to_a_second_program(self):
        def settings(root):
            log_tags(root)
            controller = root.find('Controller')
            tags = controller.find('Tags')
            config.scalar(tags, 'SecondBits', 'DINT', -1)
            config.scalar(tags, 'SecondCount', 'INT', -1)
            scheduled = controller.find('./Tasks/Task[@Name="BackgroundTask"]/ScheduledPrograms')
            E.SubElement(scheduled, 'ScheduledProgram', Name='FastProgram')
            tasks = controller.find('Tasks')
            tasks.remove(tasks.find('Task[@Name="FastTask"]'))
            routine = controller.find('./Programs/Program[@Name="FastProgram"]/Routines/Routine[@Name="Main"]')
            routine.clear()
            routine.attrib.update(Name='Main', Type='RLL')
            body = E.SubElement(routine, 'RLLContent')
            for n, line in enumerate((READ_BITS.replace('LogBits', 'SecondBits'),
                                      READ_COUNT.replace('LogCount', 'SecondCount'))):
                E.SubElement(E.SubElement(body, 'Rung', Number=str(n), Type='N'), 'Text').text = line

        engine = self.checked([OVERFLOW], mutate=settings)
        engine.memory.write('Flag', True)
        engine.step(10)
        self.assertEqual(engine.memory.read('SecondBits'), INSTRUCTION_BIT)
        self.assertEqual(engine.memory.read('SecondCount'), 1)

    def test_late_failure_restores_the_controller_summary_and_readbacks(self):
        engine = self.checked([
            OVERFLOW, 'XIC(WriteBits)' + WRITE_BITS, 'XIC(ResetCount)' + RESET_COUNT,
            READ_BITS, READ_COUNT, 'CPT(Limit,1/Index);',
        ], mutate=log_tags)
        memory = engine.memory
        memory.write('Index', 1)
        memory.write('Flag', True)
        engine.step(10)
        memory.write('WriteBits', True)
        memory.write('ResetCount', True)
        memory.write('Index', 0)
        with self.assertRaisesRegex(ModelError, 'zero'):
            engine.step(10)
        self.assertEqual((memory.read('LogBits'), memory.read('LogCount')), (INSTRUCTION_BIT, 1))
        for ref in ('Flag', 'WriteBits', 'ResetCount'):
            memory.write(ref, False)
        memory.write('Index', 1)
        engine.step(10)
        self.assertEqual((memory.read('LogBits'), memory.read('LogCount')), (INSTRUCTION_BIT, 1))
        replacement = replacement_engine(engine, engine.project)
        replacement.step(10)
        self.assertEqual((replacement.memory.read('LogBits'), replacement.memory.read('LogCount')),
                         (INSTRUCTION_BIT, 1))

    def test_disabled_reporting_and_manual_status_leave_log_empty(self):
        def settings(root):
            log_tags(root)
            root.find('Controller').set('ReportMinorOverflow', 'false')

        engine = self.checked([OVERFLOW, 'OTL(S:MINOR);', READ_BITS, READ_COUNT], mutate=settings)
        engine.memory.write('Flag', True)
        engine.step(10)
        self.assertEqual((engine.memory.read('LogBits'), engine.memory.read('LogCount')), (0, 0))

    def test_count_is_bounded_to_the_int_result(self):
        engine = self.checked([OVERFLOW, READ_COUNT], mutate=log_tags)
        engine._minor_fault_log.events = 32766
        engine.memory.write('Flag', True)
        for _ in range(2):
            engine.step(10)
            self.assertEqual(engine.memory.read('LogCount'), 32767)

    def test_false_write_skips_live_index_and_invalid_operands_are_rejected(self):
        engine = self.checked([
            'XIC(WriteBits)SSV(FaultLog,,MinorFaultBits,FaultSample[Index]);',
            'XIC(ResetCount)' + RESET_COUNT, READ_BITS, READ_COUNT,
        ], mutate=log_tags)
        engine.memory.write('Index', 99)
        engine.step(10)
        self.assertEqual(engine.memory.read('LogBits'), 0)
        engine.memory.write('WriteBits', True)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):
            engine.step(10)
        engine.memory.write('WriteBits', False)
        engine.memory.write('ResetCount', True)
        engine.memory.write('CountInput', 1)
        with self.assertRaisesRegex(ModelError, 'MinorEvents requires zero'):
            engine.step(10)
        for rung in (READ_BITS.replace(',,', ',Named,'),
                     READ_COUNT.replace('LogCount', 'LogBits'),
                     WRITE_BITS.replace('BitInput', 'CountInput')):
            self.assertTrue(self.engine([rung], mutate=log_tags).blockers)
        self.assertTrue(self.engine([READ_BITS], mutate=log_tags, harness=True).blockers)
