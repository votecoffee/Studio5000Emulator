"""Binary64 FSC comparisons, match/inhibit state and transactional progress."""
import unittest

import test_aoi_files as aois
import test_file_bcd as files


class LrealFscTests(unittest.TestCase):
    setUp = files.FileBcdTests.setUp
    engine = files.FileBcdTests.engine
    checked = files.FileBcdTests.checked
    snapshot = staticmethod(files.FileBcdTests.snapshot)
    fault = files.FileBcdTests.fault

    def test_all_finds_a_binary64_only_difference_and_resumes_after_match(self):
        engine = self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>1.0L);'],
                              source_type='LREAL', values=(1, 1+2**-52, 1, 2, 777))
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 1)
        self.assertTrue(engine.memory.read('Ctl.IN'))
        self.assertTrue(engine.memory.read('Ctl.FD'))
        self.assertFalse(engine.memory.read('Ctl.DN'))
        engine.memory.values['queue'][2] = None
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 1)
        engine.memory.write('Ctl.IN', False)
        self.fault(engine, 'Unknown')
        engine.memory.write('Queue[2]', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 3)
        self.assertTrue(engine.memory.read('Ctl.DN'))

    def test_lreal_literal_selects_binary64_for_every_relation(self):
        for operator, result in (('=',False),('<>',True),('<',True),('<=',True),('>',False),('>=',False)):
            with self.subTest(operator=operator):
                engine = self.checked([f'FSC(Ctl,?,?,ALL,0.1L-0.1{operator}0);'])
                engine.step()
                self.assertIs(engine.memory.read('Ctl.FD'), result)
                self.assertEqual(engine.memory.read('Ctl.POS'), 0 if result else 3)
        engine = self.checked(['FSC(Ctl,?,?,ALL,9007199254740993L=9007199254740992.0L);'])
        engine.step()
        self.assertTrue(engine.memory.read('Ctl.FD'))

    def test_numeric_search_continues_on_false_and_consumes_both_boolean_operands(self):
        engine = self.checked(['XIC(StartPB)FSC(Ctl,?,?,1,(Queue[Ctl.POS]>=2.5L)||(1.0L/Divisor<0));'],
                              source_type='LREAL', values=(1, 2.5, 3.5, 4, 777))
        engine.memory.write('StartPB', True)
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 0)
        engine.memory.write('StartPB', False)
        engine.memory.write('Divisor', 0)
        self.fault(engine, 'divide by zero')
        engine.memory.write('Divisor', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 1)
        self.assertTrue(engine.memory.read('Ctl.IN'))

    def test_incremental_search_requires_an_edge_and_fault_retains_its_progress(self):
        engine = self.checked(['XIC(StartPB)FSC(Ctl,?,?,INC,Queue[Ctl.POS]>=2.5L);'],
                              source_type='LREAL', values=(1, 2.5, 3.5, 4, 777), length=3)
        engine.memory.values['queue'][1] = None
        engine.memory.write('StartPB', True)
        engine.step()
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 0)
        engine.memory.write('StartPB', False)
        engine.step()
        engine.memory.write('StartPB', True)
        self.fault(engine, 'Unknown')
        engine.memory.write('Queue[1]', 2.5)
        engine.step()
        self.assertEqual(engine.memory.read('Ctl.POS'), 1)
        self.assertTrue(engine.memory.read('Ctl.IN'))

    def test_warm_aoi_search_restores_independent_controls_on_a_later_fault(self):
        fixture = aois.AOIFileTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        def binary64_search(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Input[Find.POS]>=Threshold', 'Input[Find.POS]+0.5L>2.25L')
        engine = fixture.checked(binary64_search, kind='ALL')
        engine.step()
        fixture.write(engine, Search=True, FaultDivisor=0)
        self.fault(engine, 'zero')
        fixture.write(engine, FaultDivisor=1)
        engine.step()
        self.assertEqual((engine.memory.read('FindA.POS'), engine.memory.read('FindB.POS')), (0, 1))
        self.assertTrue(engine.memory.read('FindA.FD'))
        self.assertTrue(engine.memory.read('FindB.IN'))

    def test_lreal_type_and_grammar_guards_apply_on_false_rungs(self):
        for expression in ('0.1L', '0.1L>Queue', '0.1L>StartPB', '1e999L>0',
                           'FRD(1)+0.1L>0', '(1.0L AND 1)=1', '16#10000000000000000L>0'):
            with self.subTest(expression=expression):
                self.assertTrue(self.engine([f'AFI()FSC(Ctl,?,?,ALL,{expression});']).blockers)
        for field, value in (('ProcessorType','1756-L75'), ('MajorRev','34')):
            self.assertTrue(self.engine(['AFI()FSC(Ctl,?,?,ALL,0.1L>0);'],
                                        mutate=lambda root: root.find('Controller').set(field,value)).blockers)
