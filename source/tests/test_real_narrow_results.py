"""Float32 source selection, nearest-even narrow results and atomic range checks."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_real_destination_math as fixtures
import test_real_integer_literals as constants
from logixlab.model import INT_BITS, Project
from logixlab.runtime import Engine

NARROW = ('SINT','INT','DINT')


class RealNarrowResultTests(unittest.TestCase):
    setUp = fixtures.RealDestinationMathTests.setUp
    engine = fixtures.RealDestinationMathTests.engine
    checked = fixtures.RealDestinationMathTests.checked
    snapshot = staticmethod(fixtures.RealDestinationMathTests.snapshot)
    fault = fixtures.RealDestinationMathTests.fault

    def test_nineteen_forms_real_tags_and_three_narrow_destinations(self):
        expected={**constants.BINARY,**constants.UNARY}
        for dtype,name in itertools.product(NARROW,expected):
            args='Source,1UL' if name in constants.BINARY else 'Source'
            e=self.checked([f'{name}({args},Results[1]);'],source='REAL',value=1,dest=dtype)
            e.step();self.assertEqual(e.memory.read('Results'),[None,round(expected[name]),None],(dtype,name))
            self.assertEqual(e.memory.read('Source'),1.0)

    def test_floating_literals_and_wide_words_in_both_binary_positions(self):
        for dtype,name,word,position in itertools.product(NARROW,constants.BINARY,('1L','1U','1UL','16#1U'),range(2)):
            args=word+',1.0' if position==0 else '1.0,'+word
            e=self.checked([f'{name}({args},Results[1]);'],dest=dtype);e.step()
            self.assertEqual(e.memory.read('Results[1]'),round(constants.BINARY[name]),(dtype,name,word,position))

    def test_source_precision_precedes_calculation_and_destination_rounding(self):
        for dtype in NARROW:
            e=self.checked(['SUB(16777217U,16777216.0,Results[0]);','SUB(16#1000001U,16777216.0,Results[1]);','SUB(1099511627776UL,1099511627776.0,Results[2]);'],dest=dtype)
            e.step();self.assertEqual(e.memory.read('Results'),[0,0,0])
        e=self.checked(['SQR(Source,Results[1]);'],source='REAL',value=16777217,dest='DINT');e.step();self.assertEqual(e.memory.read('Results[1]'),4096)

    def test_nearest_even_positive_negative_and_signed_zero_results(self):
        for dtype,value in itertools.product(NARROW,(-3.5,-2.5,-1.5,-.5,.5,1.5,2.5,3.5)):
            expected=round(value)
            e=self.checked([f'ADD({value},0UL,Results[1]);'],dest=dtype);e.step();self.assertEqual(e.memory.read('Results[1]'),expected)
        for dtype in NARROW:
            e=self.checked(['NEG(-0.0,Results[1]);'],dest=dtype);e.step();self.assertEqual(e.memory.read('Results[1]'),0)

    def test_signed_range_edges_check_the_rounded_result(self):
        for dtype,value,expected in [('SINT',127.49,127),('SINT',-128.5,-128),('INT',32767.49,32767),
                ('INT',-32768.5,-32768),('DINT',2147483520,2147483520),('DINT',-2147483648,-2147483648)]:
            e=self.checked(['ADD(Source,0UL,Results[1]);'],source='REAL',value=value,dest=dtype);e.step();self.assertEqual(e.memory.read('Results[1]'),expected)
        for dtype,value in [('SINT',127.5),('SINT',-128.6),('INT',32767.5),('INT',-32768.6),('DINT',2147483647),('DINT',-2147483904)]:
            e=self.checked(['ADD(Source,0UL,Results[1]);'],source='REAL',value=value,dest=dtype);self.fault(e,'overflow')

    def test_lreal_priority_and_integer_only_exactness_remain_separate(self):
        for dtype in NARROW:
            e=self.checked(['SUB(16777217.0L,16777216.0,Results[1]);'],dest=dtype);e.step();self.assertEqual(e.memory.read('Results[1]'),1)
        e=self.checked(['ADD(Source,1,Results[1]);'],source='DINT',value=16777217,dest='DINT');e.step();self.assertEqual(e.memory.read('Results[1]'),16777218)
        for dtype in NARROW:
            self.assertTrue(self.engine(['AFI()ADD(Source,1U,Results[1]);'],source='UDINT',value=1,dest=dtype).blockers)
            self.assertTrue(self.engine(['AFI()LN(16#1UL,Results[1]);'],dest=dtype).blockers)

    def test_false_prescan_skip_live_indices_unknowns_and_complete_writes(self):
        e=self.checked(['XIC(StartPB)ADD(Inputs[Index],0UL,Results[Index]);'],source='REAL',dest='DINT')
        e.memory.write('Index',99);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',2.5);e.step();self.assertEqual(e.memory.read('Results'),[None,2,None])

    def test_zero_products_and_unit_powers_require_every_source(self):
        for call in ('MUL(0.0,Inputs[1],Results[1]);','XPY(1.0,Inputs[1],Results[1]);'):
            e=self.checked([call],source='REAL',dest='DINT');self.fault(e,'Unknown')

    def test_domain_underflow_division_and_nonfinite_faults_restore_state(self):
        for call,error in [('DIV(1UL,1e-50,Results[1]);','zero'),('LN(-1.0,Results[1]);','finite'),
                ('XPY(16#FFFFFFFFFFFFFFFFUL,3.0,Results[1]);','finite')]:
            e=self.checked(['MOV(99,SpeedCommand);',call],dest='DINT');self.fault(e,error)
        e=self.checked(['ADD(Source,0UL,Results[1]);','DIV(1,Index,SpeedCommand);'],source='REAL',value=2.5,dest='SINT')
        self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results[1]'),2)

    def test_guards_permissions_and_targets_are_structural_even_when_false(self):
        for call in ('ADD(Inputs,0.5,Results[1]);','ADD(TRUE,0.5,Results[1]);','ADD(4294967296U,0.5,Results[1]);',
                'ADD(16#100000000U,0.5,Results[1]);','ADD(1UL,0.5,Results);','SQR(1.0,RunLatch);'):
            self.assertTrue(self.engine(['AFI()'+call],dest='DINT').blockers,call)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()DIV(7.0,2U,Results[1]);'],dest='DINT',mutate=constant).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()ADD(1UL,0.5,Results[1]);'],dest='DINT',mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_alias_member_unknown_full_writes_overlap_and_neighbors(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='DINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['ADD(1UL,0.5,AliasValue);','MUL(AliasValue,1.5,AliasValue);'],dest='DINT',mutate=fields)
        e.step();self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(3,777))

    def test_warm_aoi_copied_inputs_narrow_inout_locals_and_rollback(self):
        h=constants.RealIntegerLiteralTests();h.setUp();self.addCleanup(h.doCleanups);old=h.aoi();root=E.parse(old.project.path).getroot();definition=root.find('.//AddOnInstructionDefinition')
        definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','DINT')
        for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
            if node.get('DataType')=='REAL':node.set('DataType','DINT')
        for suffix in ('A','B'):
            tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','DINT');tag.find('Data/Array').set('DataType','DINT')
            root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]').set('DataType','DINT')
        import test_aoi_queues as queues
        queues.logic(root,['ADD(Value,0.5,Buffer[Index]);','SQR(4.0,Stack[1]);','GRT(Buffer[Index],0)OTE(LiteralComparedInOut);','EQU(Stack[1],2)OTE(LiteralComparedLocal);'])
        queues.logic(root,['AFI()ADD(1.0,1U,Buffer[Index]);'],name='EnableInFalse')
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True);e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[])
        e.memory.write('ValueA',3);e.memory.write('ValueB',5);e.step();self.assertEqual(e.memory.read('BufferA[1]'),4);self.assertEqual(e.memory.read('DriverA.Stack[1]'),2)
        e.memory.write('IndexA',2);e.memory.write('ValueA',5);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),6)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',99);e.step()

    def test_public_sample_values_boundaries_and_late_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/IntegerLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('NarrowRealEnabled',True);e.memory.write('NarrowRealIndex',1);e.step()
        for name,value in {'SINT':2,'INT':4,'DINT':0,'Root':2,'Power':2,'Radix':2,'Selected':[101,2,999],'RoundedEven':True}.items():self.assertEqual(e.memory.read('NarrowReal'+name),value,name)
        e.memory.write('NarrowRealBoundaryEnabled',True);self.fault(e,'overflow');e.memory.write('NarrowRealBoundarySource',127.49);e.step();self.assertEqual(e.memory.read('NarrowRealBoundaryResult'),127)
        e.memory.write('NarrowRealInput',5.5);e.memory.write('NarrowRealLateDivisor',0);self.fault(e,'zero');e.memory.write('NarrowRealLateDivisor',1);e.step();self.assertEqual(e.memory.read('NarrowRealSINT'),6)
        e.memory.write('NarrowRealEnabled',False);e.memory.write('NarrowRealIndex',99);e.step();self.assertFalse(e.memory.read('NarrowRealRoundedEven'))
        for row in (e.report()['scalar_math']['real_arithmetic'],e.report()['real_math']['real_destination']):self.assertEqual(set(row['integer_destinations']),set(INT_BITS))


if __name__ == '__main__':unittest.main()
