"""Binary64 file expressions retain existing FAL iteration and fault behavior."""
import unittest

import test_aoi_files as aois
import test_file_bcd as files


class LrealFalTests(unittest.TestCase):
    setUp = files.FileBcdTests.setUp
    engine = files.FileBcdTests.engine
    checked = files.FileBcdTests.checked
    snapshot = staticmethod(files.FileBcdTests.snapshot)
    fault = files.FileBcdTests.fault

    def test_lreal_destination_selects_binary64_and_preserves_real_literal_precision(self):
        engine = self.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],Queue[Ctl.POS]+0.1);'],
                              dest_type='LREAL', values=(16777217, 0, 1, -1, 777))
        engine.step()
        single_point_one = float.fromhex('0x1.99999ap-4')
        self.assertEqual(engine.memory.read('Results'),
                         [16777217 + single_point_one, single_point_one,
                          1 + single_point_one, -1 + single_point_one, 101.0])
        self.assertEqual(engine.memory.read('Ctl.POS'), 3)
        self.assertTrue(engine.memory.read('Ctl.DN'))

    def test_lreal_source_and_literal_select_binary64_before_destination_conversion(self):
        for dtype in ('SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT','REAL','LREAL'):
            with self.subTest(dtype=dtype):
                engine = self.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],Queue[Ctl.POS]+0.0L);'],
                                      source_type='LREAL', dest_type=dtype,
                                      values=(0.5, 1.5, 2.5, 3.5, 777))
                engine.step()
                expected = [0.5, 1.5, 2.5, 3.5] if dtype in ('REAL', 'LREAL') else [0, 2, 2, 4]
                self.assertEqual(engine.memory.read('Results'), expected + [101])
        engine = self.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],9007199254740992UL+2.0L);'],
                              dest_type='ULINT')
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [9007199254740994]*4 + [101])

    def test_lreal_tag_alone_selects_binary64_and_result_overflow_reverts_progress(self):
        engine = self.checked(['FAL(Ctl,?,?,ALL,Results[Ctl.POS],Queue[Ctl.POS]);'],
                              source_type='LREAL', dest_type='SINT',
                              values=(1.5, 127.5, 4.5, 3.5, 777))
        self.fault(engine, 'SINT overflow')
        self.assertEqual(engine.memory.read('Results'), [None]*4 + [101])
        engine.memory.write('Queue[1]', 126.5)
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [2, 126, 4, 4, 101])

    def test_sequential_overlap_sees_the_previous_iteration_write(self):
        engine = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS+1],Queue[Ctl.POS]+0.25L);'],
                              source_type='LREAL', values=(1, 0, 0, 0, 777))
        engine.step()
        self.assertEqual(engine.memory.read('Queue'), [1, 1.25, 1.5, 1.75, 2])

    def test_incremental_false_and_held_scans_skip_unknown_lreal_and_retry_the_edge(self):
        engine = self.checked(['XIC(StartPB)FAL(Ctl,?,?,INC,Results[Ctl.POS],Queue[Ctl.POS]/2);'],
                              source_type='LREAL', dest_type='LREAL')
        engine.memory.values['queue'][1] = None
        engine.memory.write('StartPB', True)
        engine.step()
        engine.step()
        self.assertEqual(engine.memory.read('Results')[:2], [9, None])
        engine.memory.write('StartPB', False)
        engine.step()
        engine.memory.write('StartPB', True)
        self.fault(engine, 'Unknown')
        engine.memory.write('Queue[1]', 3.5)
        engine.step()
        self.assertEqual(engine.memory.read('Results')[:2], [9, 1.75])
        self.assertEqual(engine.memory.read('Ctl.POS'), 1)

    def test_warm_aoi_inout_and_local_writes_roll_back_on_a_later_rung_fault(self):
        fixture = aois.AOIFileTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        def use_binary64(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                if 'FAL(' in text.text:
                    text.text = text.text.replace('+Bias', '+Bias+0.5L')
        engine = fixture.checked(use_binary64, kind='1')
        fixture.write(engine, Transform=True)
        engine.step()
        self.assertEqual(engine.memory.read('OutputA[0]'), 6)
        self.assertEqual(engine.memory.read('DriverA.Scratch[0]'), 4)
        fixture.write(engine, Transform=False, FaultDivisor=0)
        self.fault(engine, 'zero')
        fixture.write(engine, FaultDivisor=1)
        engine.step()
        self.assertEqual(engine.memory.read('OutputA')[:2], [6, 10])
        self.assertEqual(engine.memory.read('DriverA.Scratch')[:2], [4, 6])
        self.assertEqual(engine.memory.read('CalcA.POS'), 1)

    def test_lreal_type_and_grammar_guards_apply_on_false_rungs(self):
        for expression in ('0.0L+StartPB','0.0L+Queue','1e999L','1.0L AND 1','FRD(1)+0.0L','16#10000000000000000L'):
            with self.subTest(expression=expression):
                self.assertTrue(self.engine([f'AFI()FAL(Ctl,?,?,ALL,Results[Ctl.POS],{expression});'],
                                            dest_type='LREAL').blockers)
        for field, value in (('ProcessorType', '1756-L75'), ('MajorRev', '34')):
            self.assertTrue(self.engine(['AFI()FAL(Ctl,?,?,ALL,Results[Ctl.POS],0.5L);'],
                                        mutate=lambda root: root.find('Controller').set(field, value)).blockers)
