"""Tagged binary64 TRN and explicit destination conversions in ladder."""
import math
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.model import Project
from logixlab.runtime import Engine

import test_lreal_math as fixtures
import test_lreal_advanced as advanced


class LrealTruncateTests(unittest.TestCase):
    setUp = fixtures.LrealMathTests.setUp
    snapshot = staticmethod(fixtures.LrealMathTests.snapshot)
    fault = fixtures.LrealMathTests.fault

    def engine(self, rungs=None, **kwargs):
        options = dict(source='LREAL', dest='LREAL', value=16777217.875)
        options.update(kwargs)
        return fixtures.LrealMathTests.engine(self, rungs or ['TRN(Source,Dest);'], **options)

    checked = fixtures.LrealMathTests.checked

    def test_tagged_source_preserves_precision_before_truncation_for_every_destination(self):
        for dtype in ('SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT','REAL','LREAL'):
            for value, expected in ((3.9999999999999996,3),(-0.9999999999999999,0)):
                e=self.checked(dest=dtype,value=value);e.memory.values['dest']=None;e.step()
                self.assertEqual(e.memory.read('Dest'),expected)
                self.assertIs(type(e.memory.read('Dest')),float if dtype in ('REAL','LREAL') else int)
        for dtype,expected in [('DINT',16777217),('LREAL',16777217.0),('REAL',16777216.0)]:
            e=self.checked(dest=dtype);e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_real_sources_and_untyped_immediates_keep_float32_before_lreal_result(self):
        for logic,source in [(['TRN(Source,Dest);'],'REAL'),(['TRN(16777217.875,Dest);'],'LREAL')]:
            e=self.checked(logic,source=source);e.step();self.assertEqual(e.memory.read('Dest'),16777218.0)
        e=self.checked(['TRN(-3.9,Dest);']);e.step();self.assertEqual(e.memory.read('Dest'),-3.0)

    def test_lreal_literal_precision_is_used_before_destination_conversion(self):
        for dtype in ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL', 'LREAL'):
            with self.subTest(dtype=dtype):
                engine = self.checked(['TRN(+3.9999999999999996l,Results[1]);'], dest=dtype)
                engine.step()
                result = engine.memory.read('Results[1]')
                self.assertEqual(result, 3)
                self.assertIs(type(result), float if dtype in ('REAL', 'LREAL') else int)
        engine = self.checked(['TRN(-1.6777217875e7L,Dest);'], dest='LINT')
        engine.step()
        self.assertEqual(engine.memory.read('Dest'), -16777217)

    def test_lreal_literal_obeys_lazy_indices_and_atomic_range_faults(self):
        engine = self.checked(['XIC(StartPB)TRN(16777217.875L,Results[Index]);'], dest='LINT')
        engine.memory.write('Index', 99)
        engine.enter_run()
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [None] * 3)
        engine.memory.write('StartPB', True)
        self.fault(engine, 'outside bounds')
        engine.memory.write('Index', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [None, 16777217, None])
        engine = self.checked(['MOV(99,SpeedCommand);', 'TRN(9223372036854775808.0L,Dest);'], dest='LINT')
        self.fault(engine, 'overflow')

    def test_trn_rejects_typed_integers_and_nonfinite_lreal_literals(self):
        for operand in ('1L', '1U', '1UL', '1.0UL', '16#1L', '1e309L'):
            with self.subTest(operand=operand):
                self.assertTrue(self.engine([f'AFI()TRN({operand},Dest);']).blockers)

    def test_signed_unsigned_boundaries_use_stored_binary64_value(self):
        for dtype,value in [('LINT',math.nextafter(float(2**63),0)),('LINT',float(-2**63)),('ULINT',math.nextafter(float(2**64),0)),('UDINT',4294967295.875)]:
            e=self.checked(dest=dtype,value=value);e.step();self.assertEqual(e.memory.read('Dest'),math.trunc(value))
        for dtype,value in [('LINT',float(2**63)),('LINT',math.nextafter(float(-2**63),-math.inf)),('ULINT',float(2**64)),('ULINT',-1.0),('SINT',2147483648.0),('INT',-2147483649.0)]:
            e=self.checked(['MOV(99,SpeedCommand);','TRN(Source,Dest);'],dest=dtype,value=value);self.fault(e,'overflow')

    def test_narrow_signed_destinations_keep_binary64_until_truncation(self):
        def report_overflow(root):
            root.find('Controller').set('ReportMinorOverflow', 'true')

        cases = (
            ('SINT', 'Source', 127.99999999999999, 127, False),
            ('SINT', '16777217.875L', 0, 1, True),
            ('SINT', 'Source', 256.875, 0, True),
            ('INT', 'Source', -32769.875, 32767, True),
            ('INT', 'Source', 2147483647.875, -1, True),
            ('INT', '-2147483648.875l', 0, 0, True),
        )
        for dtype, operand, value, expected, overflow in cases:
            with self.subTest(dtype=dtype, operand=operand, value=value):
                engine = self.checked([
                    f'TRN({operand},Results[1])[XIC(S:V)OTE(RunLatch),'
                    'XIC(S:Z)OTE(MotorRunning),XIC(S:N)OTE(StopPB)];',
                    'XIC(S:MINOR)OTE(StartPB);',
                ], dest=dtype, value=value, mutate=report_overflow)
                engine.step()
                self.assertEqual(engine.memory.read('Results'), [None, expected, None])
                self.assertIs(engine.memory.read('RunLatch'), overflow)
                self.assertIs(engine.memory.read('MotorRunning'), expected == 0)
                self.assertIs(engine.memory.read('StopPB'), expected < 0)
                self.assertIs(engine.memory.read('StartPB'), overflow)

    def test_finite_extremes_and_signed_zero(self):
        for source, values in (('LREAL', (1e308, -1e308, 5e-324, -5e-324, -0.0, -.9)),
                               ('REAL', (2**-149, -2**-149, -0.0, -.9))):
            for dest in ('REAL', 'LREAL') if source == 'REAL' else ('LREAL',):
                for value in values:
                    with self.subTest(source=source, dest=dest, value=value):
                        e = self.checked(source=source, dest=dest, value=value)
                        e.step()
                        expected = math.copysign(float(abs(math.trunc(value))), value)
                        self.assertEqual(struct.pack('<d', e.memory.read('Dest')), struct.pack('<d', expected))
        e = self.checked(['TRN(-0.9L,Dest);'], dest='REAL')
        e.step()
        self.assertEqual(math.copysign(1, e.memory.read('Dest')), -1)
        e=self.checked(dest='REAL',value=1e308);self.fault(e,'REAL|range|large')

    def test_ladder_trn_preserves_or_converts_exceptional_sources(self):
        def enable_reporting(root):
            root.find('Controller').set('ReportMinorOverflow', 'true')

        destinations = {'REAL': None, 'LREAL': None, 'SINT': 8, 'INT': 16, 'DINT': 32, 'LINT': 64}
        for source in ('REAL', 'LREAL'):
            for dest, bits in destinations.items():
                with self.subTest(source=source, dest=dest):
                    e = self.checked(['TRN(Source,Dest)OTE(RunLatch);', 'XIC(S:MINOR)OTE(MotorRunning);'],
                                     source=source, dest=dest, mutate=enable_reporting)
                    limits = (2**(bits - 1) - 1, -2**(bits - 1), 0) if bits is not None else None
                    for index, value in enumerate((math.inf, -math.inf, math.nan)):
                        e.memory.write_floating_exception('Source', value)
                        e.step()
                        result = e.memory.read('Dest')
                        if limits is not None:
                            self.assertEqual(result, limits[index])
                        elif math.isnan(value):
                            self.assertTrue(math.isnan(result))
                        else:
                            self.assertEqual(result, value)
                        self.assertTrue(e.memory.read('RunLatch'))
                        self.assertEqual(e.memory.read('MotorRunning'), bits is not None and math.isinf(value))

    def test_false_and_prescan_skip_unknowns_and_bad_indices(self):
        e=self.checked(['XIC(StartPB)TRN(Inputs[Index],Results[Index]);']);e.memory.write('Index',99)
        e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None,None,None])
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',3.9999999999999996);e.step();self.assertEqual(e.memory.read('Results'),[None,3.0,None])

    def test_alias_member_overlap_and_unknown_complete_writes(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='TruncPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='TruncPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='TruncPacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['TRN(Source,Source);','TRN(Source,Selected);'],value=-16777217.875,mutate=fields);e.step()
        self.assertEqual((e.memory.read('Source'),e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(-16777217.0,-16777217.0,777))

    def test_late_fault_restores_scheduler_timing_values_then_recovers(self):
        e=self.checked(['TRN(Source,Results[1]);','CPT(SpeedCommand,1/Index);']);self.fault(e,'zero')
        e.memory.write('Index',1);e.memory.write('Source',-3.9999999999999996);e.step();self.assertEqual(e.memory.read('Results[1]'),-3.0)

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups);e=helper.aoi()
        # Rebuild from the same synthetic AOI source with truncation in its logic.
        root=E.parse(e.project.path).getroot()
        advanced.queues.logic(root,['TRN(Stack[0],Buffer[Index]);','TRN(Buffer[Index],Stack[1]);'])
        for suffix,value in [('A','16777217.875'),('B','-3.9999999999999996')]:
            root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]/Element').set('Value',value)
        E.ElementTree(root).write(e.project.path,encoding='utf8',xml_declaration=True)
        return Engine(Project(e.project.path))

    def test_aoi_local_and_inout_arrays_and_warm_state_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.step();e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),(16777217.0,-3.0,16777217.0,-3.0))
        self.assertEqual(e.memory.frames['@AOI:drivera']['buffer'],('BufferA',''))

    def test_ladder_trn_guards_and_structured_text_trunc(self):
        for source in ('DINT','LINT','ULINT','BOOL'):
            self.assertTrue(self.engine(source=source,value=1).blockers)
        for text in ('TRN(Inputs,Dest);','TRN(Source,Results);','TRN(Source,RunLatch);','TRN(TRUE,Dest);','TRUNC(Source,Dest);','SIZE(Results,0,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()TRN(Source,Dest);'],mutate=readonly).blockers)
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='Dest := TRUNC(Source);'
        engine = self.checked(mutate=st, value=16777217.875)
        engine.step()
        self.assertEqual(engine.memory.read('Dest'), 16777217.0)

    def test_report_separates_size_and_trn_types_and_native_boundaries(self):
        d=self.checked().report()['size_truncate'];self.assertEqual(len(d['trn_destinations']),10)
        self.assertIn('LREAL',d['trn_destinations']);self.assertNotIn('LREAL',d['size_destinations']);self.assertFalse(d['native_runtime_parity'])
