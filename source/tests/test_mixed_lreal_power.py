"""Mixed numeric tags and bounded integer constants in ladder binary64 XPY."""
import itertools
import struct
import unittest
from xml.etree import ElementTree as E

import test_lreal_advanced as advanced
import test_mixed_lreal_math as mixed
from logixlab.model import Project
from logixlab.runtime import Engine


class MixedLrealPowerTests(unittest.TestCase):
    setUp=mixed.MixedLrealMathTests.setUp
    checked=mixed.MixedLrealMathTests.checked
    snapshot=staticmethod(mixed.MixedLrealMathTests.snapshot)
    fault=mixed.MixedLrealMathTests.fault

    def engine(self,rungs=None,**options):
        defaults=dict(value=2);defaults.update(options)
        return mixed.MixedLrealMathTests.engine(self,rungs or ['XPY(Source,Mask,Results[1]);'],**defaults)

    def test_all_nineteen_tag_pairs_keep_sources_and_establish_unknown_results(self):
        for source,other in itertools.product(mixed.TYPES,repeat=2):
            if 'LREAL' not in (source,other):continue
            with self.subTest(source=source,other=other):
                e=self.checked(source=source,other=other);before=(e.memory.read('Source'),e.memory.read('Mask'));e.step()
                self.assertEqual(e.memory.read('Results'),[None,8.0,None])
                self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),before)

    def test_integer_literals_in_both_positions_and_exact_boundaries(self):
        for args,value,want in [('Source,3',2,8.0),('3,Source',2,9.0),
                                ('Source,-3',2,0.125),('Source,0',0,1.0),
                                ('Source,2147483647',1,1.0),('Source,-2147483648',1,1.0),
                                ('2147483647,Source',1,2147483647.0),('-2147483648,Source',1,-2147483648.0),
                                ('16#7FFF_FFFF,Source',1,2147483647.0),('Source,2#11',2,8.0)]:
            with self.subTest(args=args,value=value):
                e=self.checked([f'XPY({args},Results[1]);'],value=value);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_dint_precision_stored_real_and_binary64_inputs_remain_distinct(self):
        e=self.checked(source='DINT',other='LREAL',value=16777217);e.memory.write('Mask',2);e.step()
        self.assertEqual(e.memory.read('Results[1]'),281475010265089.0)
        e=self.checked(source='REAL',other='LREAL',value=16777217);e.memory.write('Mask',2);e.step()
        self.assertEqual((e.memory.read('Source'),e.memory.read('Results[1]')),(16777216.0,281474976710656.0))
        e=self.checked(['XPY(Source,2,Results[1]);'],value=1.0000000000000002);e.step()
        self.assertEqual(e.memory.read('Results[1]'),1.0000000000000004)

    def test_wide_base_and_exponent_round_before_power(self):
        for dtype,value,want in [('LINT',9007199254740993,9007199254740992.0),('ULINT',2**64-1,float(2**64))]:
            e=self.checked(source=dtype,other='LREAL',value=value);e.memory.write('Mask',1);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        e=self.checked(other='LINT',value=-1);e.memory.write('Mask',9007199254740993);e.step()
        # The odd integer rounds to an even binary64 exponent before calculation.
        self.assertEqual(e.memory.read('Results[1]'),1.0);self.assertEqual(e.memory.read('Mask'),9007199254740993)

    def test_negative_bases_signed_zero_subnormal_and_underflow(self):
        for value,token,want in [(-2,3,-8.0),(-2,2,4.0),(-0.0,3,-0.0),
                                  (5e-324,1,5e-324),(1e-308,2,0.0),(-1e-308,3,-0.0)]:
            e=self.checked([f'XPY(Source,{token},Results[1]);'],value=value);e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',want))
        e=self.checked(other='REAL',value=4);e.memory.write('Mask',0.5);e.step();self.assertEqual(e.memory.read('Results[1]'),2.0)

    def test_domain_overflow_and_later_fault_restore_prior_values_and_timing(self):
        for value,other,exponent in [(-2,'REAL',0.5),(0,'DINT',-1),(1e308,'DINT',2)]:
            e=self.checked(['MOV(99,SpeedCommand);','XPY(Source,Mask,Results[1]);'],value=value,other=other)
            e.memory.write('Mask',exponent);self.fault(e,'finite LREAL')
        e=self.checked(['XPY(Source,3,Results[1]);','DIV(1,Index,SpeedCommand);'])
        self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results[1]'),8.0)

    def test_false_prescan_skip_indices_then_require_selected_sources(self):
        e=self.checked(['XIC(StartPB)XPY(Inputs[Index],3,Results[Index]);'])
        e.memory.write('Index',99);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',2);e.step();self.assertEqual(e.memory.read('Results'),[None,8.0,None])
        e=self.checked(['XIC(StartPB)XPY(3,Inputs[Index],Results[Index]);'])
        e.memory.write('Index',99);e.enter_run();e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')

    def test_zero_exponents_and_unit_bases_do_not_skip_unknowns(self):
        for call,options in [('XPY(Inputs[0],0,Results[1]);',{}),('XPY(1,Inputs[0],Results[1]);',{}),
                              ('XPY(Mask,Inputs[0],Results[1]);',{'source':'DINT','other':'LREAL'})]:
            e=self.checked([call],**options);e.memory.write('Mask',1);self.fault(e,'Unknown')
        e=self.checked(['XPY(Source,3,Results[Index]);']);e.memory.write('Index',99);self.fault(e,'outside bounds')

    def test_alias_udt_and_source_overlap_capture_inputs_before_full_write(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='PowerPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='PowerPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='PowerPacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['XPY(Source,2,Source);','XPY(Source,2,Selected);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Source'),e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(4.0,16.0,777))

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups)
        original=helper.aoi();root=E.parse(original.project.path).getroot()
        advanced.queues.logic(root,['XPY(Stack[0],Value,Buffer[Index]);','XPY(Stack[0],2,Stack[1]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True)
        return Engine(Project(original.project.path))

    def test_warm_aoi_copied_dint_exponents_and_lreal_bindings_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',2);e.memory.write('ValueB',3);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(81.0,64.0))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(81.0,64.0))
        self.assertEqual((e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),(81.0,16.0))

    def test_excluded_literals_types_destinations_and_profiles_remain_guarded(self):
        for token in ('1.0UL','1LU','TRUE','2147483648','-2147483649','1e309L','18446744073709551616UL'):
            for args in ('Source,'+token,token+',Source'):
                self.assertTrue(self.engine(['AFI()XPY('+args+',Dest);']).blockers,args)
        for call in ('XPY(Inputs,Mask,Dest);','XPY(Source,RunLatch,Dest);','XPY(Source,Mask,RunLatch);',
                     'XPY(2.0,3,Results);','CPT(Dest,Source**RunLatch);','EXPT(Source,Mask,Dest);','SQR(TRUE,Dest);'):
            self.assertTrue(self.engine([call]).blockers,call)
        self.assertEqual(self.checked(source='DINT',other='REAL').blockers,[])
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['XPY(Source,2,Results[1]);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_report_separates_mixed_power_from_unary_forms(self):
        d=self.checked().report()['real_math'];p=d['lreal']['power']
        self.assertEqual(len(p['source_types']),10);self.assertEqual(p['instruction'],'XPY')
        self.assertIn('Bounded DINT',p['constants']);self.assertFalse(p['native_runtime_parity'])
        self.assertEqual(d['destinations'],['DINT','INT','REAL','SINT'])
