"""REAL results select finite float32 inputs across common ladder math."""
import itertools
import math
import struct
import unittest
from xml.etree import ElementTree as E

import test_lreal_destination_math as fixtures
import test_lreal_unary_sources as unary
from logixlab.model import INT_BITS,Project
from logixlab.real_math import real
from logixlab.runtime import Engine

TYPES=(*INT_BITS,'REAL')
EXPECTED=fixtures.EXPECTED
CASES=unary.CASES


class RealDestinationMathTests(unittest.TestCase):
    setUp=fixtures.LrealDestinationMathTests.setUp
    checked=fixtures.LrealDestinationMathTests.checked
    snapshot=staticmethod(fixtures.LrealDestinationMathTests.snapshot)
    fault=fixtures.LrealDestinationMathTests.fault

    def engine(self,rungs=None,**options):
        options.setdefault('dest','REAL')
        return fixtures.LrealDestinationMathTests.engine(self,rungs,**options)

    def test_all_81_pairs_and_six_binary_forms_preserve_sources(self):
        for source,other,name in itertools.product(TYPES,TYPES,EXPECTED):
            with self.subTest(source=source,other=other,name=name):
                e=self.checked([f'{name}(Source,Mask,Results[1]);'],source=source,other=other)
                e.memory.write('Mask',2);before=(e.memory.read('Source'),e.memory.read('Mask'));e.step()
                self.assertEqual(e.memory.read('Results'),[None,real(EXPECTED[name]),None])
                self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),before)

    def test_neg_abs_and_all_eleven_functions_across_nine_tag_types(self):
        for source,name in itertools.product(TYPES,('NEG','ABS')):
            e=self.checked([f'{name}(Source,Results[1]);'],source=source);e.step()
            self.assertEqual(e.memory.read('Results[1]'),-3.0 if name=='NEG' else 3.0)
        for source,name in itertools.product(TYPES,CASES):
            value,want=CASES[name]
            e=self.checked([f'{name}(Source,Results[1]);'],source=source,value=value);e.step()
            self.assertEqual(e.memory.read('Results'),[None,real(want),None]);self.assertEqual(e.memory.read('Source'),value)

    def test_tag_constants_both_positions_and_floating_literals(self):
        expected={'ADD':(5,5),'SUB':(1,-1),'MUL':(6,6),'DIV':(1.5,2/3),'MOD':(1,2),'XPY':(9,8)}
        for source,name,position,token in itertools.product(TYPES,expected,range(2),('2','2.0')):
            args='Source,'+token if position==0 else token+',Source'
            e=self.checked([f'{name}({args},Results[1]);'],source=source);e.step()
            self.assertEqual(e.memory.read('Results[1]'),real(expected[name][position]))

    def test_constant_only_calls_and_signed_boundaries(self):
        for name,args,want in [('ADD','3,2',5),('SUB','3,2',1),('MUL','3,2',6),('DIV','3,2',1.5),
                               ('MOD','-7,3',-1),('XPY','3,2',9),('NEG','3',-3),('ABS','-3',3),
                               ('ADD','1.1,0',real(1.1)),('DIV','3.0,2',1.5),('XPY','2,-3',.125),
                               ('NEG','-2147483648',2147483648),('ABS','-2147483648',2147483648)]:
            e=self.checked([f'{name}({args},Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        for name,(value,want) in CASES.items():
            e=self.checked([f'{name}({value},Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),real(want))

    def test_dint_and_wide_promotion_happens_before_calculation(self):
        e=self.checked(['ADD(Source,1,Results[1]);','SUB(Source,16777216,Results[2]);'],value=16777217);e.step()
        self.assertEqual(e.memory.read('Results'),[None,16777216.0,0.0]);self.assertEqual(e.memory.read('Source'),16777217)
        e=self.checked(['MOD(Source,Mask,Results[1]);','NEG(Source,Results[2]);'],source='ULINT',other='LINT',value=2**64-1);e.step()
        self.assertEqual(e.memory.read('Results'),[None,1.0,-float(2**64)]);self.assertEqual(e.memory.read('Source'),2**64-1)
        e=self.checked(['SQR(Source,Results[1]);'],source='ULINT',value=2**64-1);e.step();self.assertEqual(e.memory.read('Results[1]'),float(2**32))
        e=self.checked(['SQR(Source,Results[1]);'],source='LINT',value=-16);e.step();self.assertEqual(e.memory.read('Results[1]'),4)

    def test_signed_zero_subnormal_and_literal_underflow(self):
        for call in ('NEG(0,Results[1]);','SIN(Source,Results[1]);','TAN(Source,Results[1]);'):
            e=self.checked([call],source='REAL',value=-0.0);e.step()
            self.assertEqual(struct.pack('<f',e.memory.read('Results[1]')),struct.pack('<f',-0.0))
        e=self.checked(['ADD(Source,1e-50,Results[1]);'],source='REAL',value=1.401298464324817e-45);e.step()
        self.assertEqual(e.memory.read('Results[1]'),e.memory.read('Source'))
        e=self.checked(['DIV(1,1e-50,Results[1]);']);self.fault(e,'zero')

    def test_all_nineteen_forms_skip_false_prescan_and_require_live_sources(self):
        for name in (*EXPECTED,'NEG','ABS',*CASES):
            args='Inputs[Index],2' if name in EXPECTED else 'Inputs[Index]'
            e=self.checked([f'XIC(StartPB){name}({args},Results[Index]);']);e.memory.write('Index',99);e.enter_run();e.step()
            self.assertEqual(e.memory.read('Results'),[None]*3);e.memory.write('StartPB',True);self.fault(e,'outside bounds')
            e.memory.write('Index',1);self.fault(e,'Unknown')
        for call in ('MUL(0,Inputs[0],Results[1]);','XPY(1,Inputs[0],Results[1]);','XPY(Inputs[0],0,Results[1]);'):
            e=self.checked([call]);self.fault(e,'Unknown')

    def test_zero_domains_overflow_and_late_faults_restore_advance(self):
        for call in ('DIV(1,0,Results[1]);','MOD(1,0,Results[1]);','XPY(0,-1,Results[1]);',
                     'LN(0,Results[1]);','LOG(-1,Results[1]);','ASN(2,Results[1]);',
                     'ACS(-2,Results[1]);','XPY(2147483647,2147483647,Results[1]);',
                     'MUL(3.4e38,2,Results[1]);'):
            e=self.checked(['MOV(99,SpeedCommand);',call]);self.fault(e,'zero|finite REAL|REAL value')
        e=self.checked(['XPY(Source,Mask,Results[1]);'],value=-2,other='REAL');e.memory.write('Mask',.5);self.fault(e,'finite REAL')
        e=self.checked(['ADD(Source,2,Results[1]);','SQR(Source,Results[2]);','DIV(1,Index,SpeedCommand);'])
        self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results'),[None,5.0,real(math.sqrt(3))])

    def test_alias_udt_unknown_writes_overlap_and_guards(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='RealPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='REAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='RealPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='RealPacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='REAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['ADD(Source,2,Selected);','XPY(Selected,2,Selected);','SQR(Selected,Selected);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(5.0,777))

    def aoi(self):
        helper=fixtures.LrealDestinationMathTests();helper.setUp();self.addCleanup(helper.doCleanups)
        original=helper.aoi();root=E.parse(original.project.path).getroot();definition=root.find('.//AddOnInstructionDefinition')
        definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','REAL')
        for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
            if node.get('DataType')=='LREAL':node.set('DataType','REAL')
        for suffix in ('A','B'):
            tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','REAL');tag.find('Data/Array').set('DataType','REAL')
            root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]').set('DataType','REAL')
        fixtures.advanced.queues.logic(root,['ADD(Value,1,Buffer[Index]);','SQR(Value,Stack[1]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True);return Engine(Project(original.project.path))

    def test_warm_aoi_copied_inputs_real_outputs_and_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',4);e.memory.write('ValueB',9);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'),e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),(5.0,10.0,2.0,3.0))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),(2.0,3.0))

    def test_non_numeric_and_unqualified_operands_remain_structural(self):
        for token in ('TRUE','2147483648','-2147483649','1e40','1e999','1LU','Inputs','RunLatch'):
            for call in (f'ADD(Source,{token},Results[1]);',f'SQR({token},Results[1]);'):
                self.assertTrue(self.engine(['AFI()'+call]).blockers,call)
        self.assertTrue(self.engine(['SQR(Source,SpeedCommand);'],source='ULINT').blockers)
        e=self.checked(['ADD(Source,1,SpeedCommand);'],source='REAL');e.step();self.assertEqual(e.memory.read('SpeedCommand'),4)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['ADD(1,2,Results[1]);'],mutate=constant).blockers)

    def test_report_records_real_result_and_separate_lreal_profile(self):
        r=self.checked().report();a=r['scalar_math']['real_arithmetic'];u=r['real_math']['real_destination']
        self.assertEqual(len(a['source_types']),9);self.assertEqual(len(a['instructions']),7);self.assertFalse(a['native_runtime_parity'])
        self.assertEqual(len(u['instructions']),12);self.assertIn('float32',u['calculation']);self.assertFalse(u['native_runtime_parity'])
        self.assertIn('no LREAL source',r['scalar_math']['lreal_arithmetic']['operands'])
