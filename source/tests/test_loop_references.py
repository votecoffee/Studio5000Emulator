"""Indirect ladder FOR operands, explicit sampling and atomic advances."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_ladder_loops as fixtures
from logixlab.model import ModelError


class LoopReferenceTests(unittest.TestCase):
    setUp = fixtures.LadderLoopTests.setUp
    routine = fixtures.LadderLoopTests.routine
    tag = fixtures.LadderLoopTests.tag
    values = fixtures.LadderLoopTests.values
    text = 'XIC(SelectedLoop)FOR(Body,IndexSlots[LoopSlot],InitialValues[BoundsSlot],TerminalValues[BoundsSlot],StepValues[BoundsSlot]);'

    def engine(self, rungs=None, body=None, mutate=None):
        self.routine('Body', body or ['ADD(SelectedIterations,1,SelectedIterations)ADD(SelectedTotal,IndexSlots[LoopSlot],SelectedTotal);'])
        return fixtures.LadderLoopTests.engine(self, [self.text] if rungs is None else rungs, mutate)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs); self.assertEqual(e.blockers, []); self.assertFalse(e.memory.structural); return e

    @staticmethod
    def configure(e, slot=1, start=0, finish=4, step=1):
        for name, value in [('LoopSlot', slot), ('BoundsSlot', slot), (f'InitialValues[{slot}]', start),
                            (f'TerminalValues[{slot}]', finish), (f'StepValues[{slot}]', step), ('SelectedLoop', True)]:
            e.memory.write(name, value)

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.calls.stack, e.scan_count,
                              e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def test_dormant_unknown_and_invalid_indices_then_required_faults_and_recovery(self):
        e = self.checked(); e.step(); self.assertIsNone(e.memory.read('IndexSlots')[1])
        e.memory.write('SelectedLoop', True)
        for expected, writes in [('outside bounds', []), ('outside bounds', [('LoopSlot', 1)]),
                                  ('Unknown', [('BoundsSlot', 1)]), ('Unknown', [('InitialValues[1]', 0)]),
                                  ('Unknown', [('TerminalValues[1]', 4)])]:
            for name, value in writes:e.memory.write(name, value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, expected):e.step()
            self.assertEqual(self.snapshot(e), before); self.assertFalse(e.memory.structural)
        e.memory.write('StepValues[1]', 1); e.step()
        self.assertEqual(self.values(e, 'SelectedTotal', 'SelectedIterations', 'IndexSlots[1]'), (10, 5, 5))
        self.assertIsNone(e.memory.read('IndexSlots')[0])

    def test_later_invocation_reselects_cells_and_false_skips_unknown_subscripts(self):
        e = self.checked(); self.configure(e); e.step(); self.configure(e, 2, 3, -1, -2); e.step()
        self.assertEqual(self.values(e, 'SelectedTotal', 'SelectedIterations'), (13, 8))
        self.assertEqual(e.memory.read('IndexSlots'), [None, 5, -3]); e.memory.write('SelectedLoop', False)
        e.memory.values['loopslot'] = e.memory.values['boundsslot'] = None; before = copy.deepcopy(e.memory.values)
        e.step(); self.assertEqual(e.memory.values, before)

    def test_index_cell_retained_while_bound_addresses_are_live(self):
        body = ['ADD(SelectedIterations,1,SelectedIterations)ADD(SelectedTotal,IndexSlots[1],SelectedTotal);', 'MOV(2,LoopSlot)MOV(2,BoundsSlot);']
        e = self.checked(body=body); self.configure(e)
        e.memory.write('TerminalValues[2]', 2); e.memory.write('StepValues[2]', 2); e.step()
        self.assertEqual(self.values(e, 'SelectedTotal', 'SelectedIterations', 'IndexSlots[1]', 'LoopSlot'), (2, 2, 4, 2))
        self.assertIsNone(e.memory.read('IndexSlots')[2])

    def test_initial_read_before_assignment_and_bounds_selected_after_assignment(self):
        text = 'FOR(Body,IndexSlots[LoopSlot],IndexSlots[LoopSlot],IndexSlots[LoopSlot],1);'
        # Terminal aliases the live index, so BRK must terminate this loop.
        e = self.checked([text], ['ADD(SelectedIterations,1,SelectedIterations)BRK();'])
        e.memory.write('LoopSlot', 1); e.memory.write('IndexSlots[1]', 3); e.step()
        self.assertEqual(self.values(e, 'SelectedIterations', 'IndexSlots[1]'), (1, 3))
        e = self.checked(['FOR(Body,IndexSlots[LoopSlot],0,IndexSlots[LoopSlot],1);'], ['BRK();'])
        e.memory.write('LoopSlot', 1); e.step(); self.assertEqual(e.memory.read('IndexSlots')[1], 0)
        e = self.checked([text], ['BRK();']); e.memory.write('LoopSlot', 1)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertIsNone(e.memory.read('IndexSlots')[1])

    def test_break_skips_changed_bad_step_but_ret_tnd_reselect_and_fault(self):
        for end in ('BRK()', 'RET()', 'TND()'):
            e = self.checked(body=['MOV(99,BoundsSlot)' + end + ';']); self.configure(e)
            if end == 'BRK()':
                e.step(); self.assertEqual(e.memory.read('IndexSlots')[1], 0); self.assertEqual(e.memory.read('BoundsSlot'), 99)
            else:
                e.memory.write('SelectedLoop', False); e.step(); e.memory.write('SelectedLoop', True); before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
                self.assertEqual(self.snapshot(e), before); self.assertEqual(e.calls.stack, [])

    def test_dynamic_aliases_and_program_local_subscripts_share_selection(self):
        def aliases(root):
            tags = root.find('./Controller/Tags'); local = root.find('./Controller/Programs/Program/Tags')
            for name in ('LoopSlot', 'BoundsSlot'):
                tag = tags.find(f'./Tag[@Name="{name}"]'); tags.remove(tag); local.append(tag)
            for name, ref in [('IndexView', 'IndexSlots[LoopSlot]'), ('InitialView', 'InitialValues[BoundsSlot]'),
                              ('TerminalView', 'TerminalValues[BoundsSlot]'), ('StepView', 'StepValues[BoundsSlot]')]:
                E.SubElement(local, 'Tag', Name=name, TagType='Alias', AliasFor=ref)
        text = 'XIC(SelectedLoop)FOR(Body,IndexView,InitialView,TerminalView,StepView);'
        e = self.checked([text], mutate=aliases)
        for name, value in [('LoopSlot', 1), ('BoundsSlot', 1)]:e.memory.write(name, value, 'MainProgram')
        for name, value in [('InitialValues[1]', 0), ('TerminalValues[1]', 2), ('StepValues[1]', 1), ('SelectedLoop', True)]:e.memory.write(name, value)
        e.step(); self.assertEqual(self.values(e, 'SelectedTotal', 'SelectedIterations', 'IndexSlots[1]'), (3, 3, 3))

    def test_multidimensional_member_and_expression_subscripts(self):
        def grid(root):
            tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Grid', DataType='DINT', TagType='Base', Dimensions='2,3')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='DINT', Dimensions='2,3')
            dtype = E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='Bounds', Family='NoFamily', Class='User')
            members = E.SubElement(dtype, 'Members')
            for name in ('Initial', 'Terminal', 'Step'):E.SubElement(members, 'Member', Name=name, DataType='DINT', Dimension='0')
            tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Records', DataType='Bounds', TagType='Base', Dimensions='3')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='Bounds', Dimensions='3')
        text = 'XIC(SelectedLoop)FOR(Body,Grid[LoopSlot-1,BoundsSlot],Records[BoundsSlot].Initial,Records[BoundsSlot].Terminal,Records[BoundsSlot].Step);'
        e = self.checked([text], ['ADD(SelectedTotal,Grid[0,1],SelectedTotal);'], grid)
        for name, value in [('LoopSlot', 1), ('BoundsSlot', 1), ('Records[1].Initial', 1), ('Records[1].Terminal', 3), ('Records[1].Step', 1), ('SelectedLoop', True)]:e.memory.write(name, value)
        e.step(); self.assertEqual(self.values(e, 'SelectedTotal', 'Grid[0,1]'), (6, 4)); self.assertIsNone(e.memory.read('Grid')[1][1])

    def test_nested_or_later_fault_restores_loop_cells_and_stack(self):
        for nested in (True, False):
            body = ['ADD(SelectedIterations,1,SelectedIterations)ADD(SelectedTotal,IndexSlots[LoopSlot],SelectedTotal);']
            rungs = [self.text]
            if nested:body += ['DIV(1,FaultDivisor,GuardResult);']
            else:rungs += ['DIV(1,FaultDivisor,GuardResult);']
            e = self.checked(rungs, body); e.step(); self.configure(e); e.memory.write('FaultDivisor', 0); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'zero'):e.step()
            self.assertEqual(self.snapshot(e), before); self.assertEqual(e.calls.stack, [])
            e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('SelectedTotal'), 10)

    def test_required_post_call_bound_faults_and_recovers(self):
        e = self.checked(body=['MOV(2,BoundsSlot)ADD(SelectedIterations,1,SelectedIterations);']); e.step(); self.configure(e)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('StepValues[2]', 1); e.memory.write('TerminalValues[2]', 0); e.step()
        self.assertEqual(self.values(e, 'SelectedIterations', 'IndexSlots[1]', 'BoundsSlot'), (1, 1, 2))

    def test_zero_step_budget_and_index_overflow_rollback(self):
        for start, finish, step, expected in [(0, 1, 0, 'budget'), (2147483647, 2147483647, 1, 'DINT overflow')]:
            # TerminalValues is SINT in the example, so use direct DINT bounds here.
            text = f'XIC(SelectedLoop)FOR(Body,IndexSlots[LoopSlot],{start},{finish},{step});'
            e = self.checked([text], ['NOP();']); e.step(); e.memory.write('LoopSlot', 1); e.memory.write('SelectedLoop', True); e.instruction_limit = 80; before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, expected):e.step()
            self.assertEqual(self.snapshot(e), before); self.assertEqual(e.calls.stack, [])

    def test_literal_bounds_permissions_shapes_types_and_syntax_guarded_while_false(self):
        for args in [('IndexSlots[99]', '0', '2', '1'), ('IndexSlots[LoopSlot].0', '0', '2', '1'),
                     ('IndexSlots', '0', '2', '1'), ('IndexSlots[LoopSlot]', 'InitialValues', '2', '1'),
                     ('IndexSlots[LoopSlot]', '0', 'TerminalValues[99]', '1'), ('IndexSlots[LoopSlot]', '0', '2', '1.0'),
                     ('IndexSlots[LoopSlot]', '0', '2', 'TRUE'), ('IndexSlots[LoopSlot]', 'InitialValues[Missing]', '2', '1')]:
            with self.subTest(args=args):self.assertTrue(self.engine(['AFI()FOR(Body,' + ','.join(args) + ');']).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="IndexSlots"]').set('Constant', 'true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_false_mcr_and_loop_report_keep_live_operands_dormant(self):
        e = self.checked(['AFI()MCR();', self.text, 'MCR();']); e.step()
        self.assertEqual(e.memory.read('LoopSlot'), 99); self.assertEqual(e.memory.read('IndexSlots'), [None, None, None])
        report = e.report()['ladder_loops']; self.assertIn('Structural', report['selection']); self.assertIn('retained', report['index']); self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
