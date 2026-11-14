"""Lossless runtime input conversion for bounded standalone integer arithmetic."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.model import INT_BITS, UNSIGNED_BITS, ModelError, Project
from logixlab.runtime import Engine


class CheckedIntegerMathTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def make(self,rungs,*,source='LINT',other='UDINT',dest='DINT',values=(7,3,0),**kwargs):
        return self.engine(rungs,types=(source,other,dest),values=values,**kwargs)

    def test_all_integer_source_result_pairs_and_six_positive_operations(self):
        expected={'ADD':10,'SUB':4,'MUL':21,'DIV':2,'MOD':1,'ABS':7}
        for source,dest in itertools.product(INT_BITS,repeat=2):
            for op,want in expected.items():
                args='Source,Dest' if op=='ABS' else 'Source,Mask,Dest'
                e=self.make([f'{op}({args});'],source=source,other=source,dest=dest)
                e.memory.values['dest']=None;e.step();self.assertEqual(e.memory.read('Dest'),want,(source,dest,op))

    def test_negation_signed_quotient_remainder_and_absolute_value(self):
        for source,dest in itertools.product(('LINT','UDINT','ULINT'),('SINT','INT','DINT','LINT')):
            e=self.make(['NEG(Source,Dest);'],source=source,dest=dest);e.step();self.assertEqual(e.memory.read('Dest'),-7)
        for op,want in [('DIV',-2),('MOD',-1),('ABS',7)]:
            args='Source,Dest' if op=='ABS' else 'Source,Mask,Dest'
            e=self.make([f'{op}({args});'],source='LINT',other='ULINT',dest='DINT',values=(-7,3,0));e.step();self.assertEqual(e.memory.read('Dest'),want)

    def test_mixed_64_bit_values_do_not_round_through_float(self):
        for op,want in [('ADD',9007199254740995),('SUB',9007199254740991),('MUL',18014398509481986),('DIV',4503599627370496),('MOD',1)]:
            e=self.make([f'{op}(Source,Mask,Dest);'],source='ULINT',other='DINT',dest='LINT',values=(9007199254740993,2,0));e.step();self.assertEqual(e.memory.read('Dest'),want)

    def test_typed_decimal_radix_and_signed_dint_constants_fit_before_execution(self):
        for text,want in [('ADD(1UL,2L,Dest);',3),('ADD(16#7L,2#11UL,Dest);',10),
                ('SUB(16#FFFFFFFFL,1UL,Dest);',4294967294),('ADD(Source,16#FFFFFFFF,Dest);',6)]:
            dest='ULINT' if 'SUB' in text else 'DINT'
            e=self.make([text],dest=dest);e.step();self.assertEqual(e.memory.read('Dest'),want,text)
        for text in ('ADD(2147483648L,0UL,Dest);','ADD(128L,0UL,Dest);','ADD(-1UL,1L,Dest);'):
            dest='SINT' if '128L' in text else 'DINT'
            self.assertTrue(self.make(['AFI()'+text],dest=dest,checked=False).blockers,text)

    def test_runtime_input_ranges_are_lazy_atomic_and_repairable(self):
        for value in (128,-129):
            e=self.make(['XIC(StartPB)ADD(Source,Mask,Dest);'],dest='SINT',values=(value,0,0))
            e.step();e.memory.write('StartPB',True);self.fault(e,'overflow|range')
            e.memory.write('Source',7);e.step();self.assertEqual(e.memory.read('Dest'),7)
        e=self.make(['ADD(Source,Mask,Dest);'],source='LINT',other='UDINT',dest='UINT',values=(-1,3,0));self.fault(e,'overflow|range')
        e.memory.write('Source',1);e.step();self.assertEqual(e.memory.read('Dest'),4)

    def test_result_overflow_and_unsigned_negation_are_atomic(self):
        for text,source,other,dest,values in [('ADD(Source,Mask,Dest);','LINT','DINT','SINT',(120,10,0)),
                ('MUL(Source,Mask,Dest);','LINT','DINT','USINT',(100,3,0)),
                ('SUB(Source,Mask,Dest);','LINT','UDINT','UINT',(1,3,0)),
                ('NEG(Source,Dest);','LINT','DINT','UINT',(7,3,0))]:
            e=self.make([text],source=source,other=other,dest=dest,values=values);self.fault(e,'overflow|range')

    def test_every_required_input_is_consumed_even_for_zero_products(self):
        e=self.make(['MUL(Source,Mask,Dest);'],values=(0,3,0));e.memory.values['mask']=None;self.fault(e,'Unknown')
        e=self.make(['MUL(Source,Mask,Dest);'],dest='SINT',values=(1000,0,0));self.fault(e,'overflow|range')
        e=self.make(['ABS(Source,Dest);'],dest='UINT',values=(-7,0,0));self.fault(e,'overflow|range')
        e=self.make(['DIV(Source,Mask,Dest);'],values=(7,0,0));self.fault(e,'zero')

    def test_false_prescan_and_selected_alias_writes_establish_unknowns(self):
        def arrays(root):
            tags=root.find('./Controller/Tags')
            for name,dtype in [('Source','LINT'),('Dest','DINT')]:
                tag=tags.find(f'Tag[@Name="{name}"]');tag.set('Dimensions','3');tag.remove(tag.find('Data'))
                array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='3')
                for i,v in ([(1,7)] if name=='Source' else [(0,101),(2,999)]):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(v))
            E.SubElement(tags,'Tag',Name='Selected',DataType='DINT',TagType='Alias',AliasFor='Dest[SpeedCommand]')
        e=self.make(['XIC(StartPB)ADD(Source[SpeedCommand],Mask,Selected);'],mutate=arrays)
        e.memory.write('SpeedCommand',99);e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('SpeedCommand',0);self.fault(e,'Unknown');e.memory.write('SpeedCommand',1);e.step();self.assertEqual(e.memory.read('Dest'),[101,10,999])

    def test_late_faults_restore_earlier_integer_results_then_retry(self):
        e=self.make(['ADD(Source,Mask,Dest);','DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand',0);self.fault(e,'zero');e.memory.write('SpeedCommand',1);e.step();self.assertEqual(e.memory.read('Dest'),10)

    def test_permissions_shapes_old_profiles_and_unrelated_consumers_stay_separate(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.make(['AFI()ADD(Source,Mask,Dest);'],mutate=constant,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.make(['AFI()ADD(Source,Mask,Dest);'],mutate=lambda root:root.find('Controller').set(key,value),checked=False).blockers)
        self.assertTrue(self.make(['AFI()ADD(Source,StartPB,Dest);'],checked=False).blockers)
        self.assertTrue(self.make(['AFI()CPT(Dest,Source+Mask);'],checked=False).blockers)

    def test_floating_time_and_bitwise_profiles_keep_their_existing_behavior(self):
        e=self.make(['ADD(Source,Mask,Dest);'],source='LINT',other='REAL',dest='DINT',values=(3,.5,0));e.step();self.assertEqual(e.memory.read('Dest'),4)
        e=self.make(['ADD(Source,Mask,Dest);'],source='LREAL',other='LINT',dest='DINT',values=(.5,3,0));e.step();self.assertEqual(e.memory.read('Dest'),4)
        e=self.make(['AND(Source,Mask,Dest);'],source='LINT',other='UDINT',dest='USINT',values=(-1,255,0));e.step();self.assertEqual(e.memory.read('Dest'),255)

    def test_warm_aoi_integer_bindings_and_rollback(self):
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            tags=root.find('./Controller/Tags')
            for suffix in ('A','B'):
                tag=E.SubElement(tags,'Tag',Name='Wide'+suffix,DataType='LINT',TagType='Base')
                E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LINT',Value='7')
            aoi=root.find('.//AddOnInstructionDefinition')
            E.SubElement(aoi.find('Parameters'),'Parameter',Name='Wide',DataType='LINT',TagType='Base',Usage='InOut',Required='true',Visible='true',Constant='false')
            for text in root.findall('.//Programs/Program/Routines/Routine/RLLContent/Rung/Text'):
                for suffix in ('A','B'):text.text=text.text.replace(f'Calc{suffix},Find{suffix})',f'Calc{suffix},Find{suffix},Wide{suffix})')
            body=aoi.find('./Routines/Routine[@Name="Logic"]/RLLContent')
            rung=E.SubElement(body,'Rung',Number='99',Type='N')
            E.SubElement(rung,'Text').text='XIC(Transform)ADD(Wide,1L,Output[Calc.POS]);'
        e=h.checked(fields,kind='1');e.memory.write('Transform',True);e.step();self.assertEqual(e.memory.read('OutputA')[0],8)
        e.memory.write('WideA',1<<31);self.fault(e,'overflow|range')
        e.memory.write('WideA',9);e.step();self.assertEqual(e.memory.read('OutputA')[:2],[8,10])

    def test_public_example_results_live_ranges_fault_repair_and_report(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/IntegerLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('CheckedMathEnabled',True);self.fault(e,'outside bounds');e.memory.write('CheckedMathIndex',1);e.step()
        expected={'Sum':10,'Difference':4,'Product':14,'Quotient':2,'Remainder':1,'Negated':-3,'Absolute':7,'Literal':3,'Selected':[101,10,999]}
        for name,want in expected.items():self.assertEqual(e.memory.read('CheckedMath'+name),want,name)
        for value in (128,-1):e.memory.write('CheckedMathWide',value);self.fault(e,'overflow|range')
        e.memory.write('CheckedMathWide',7);e.memory.write('CheckedMathLateDivisor',0);self.fault(e,'zero')
        e.memory.write('CheckedMathLateDivisor',1);e.step();self.assertEqual(e.memory.read('CheckedMathSelected[1]'),10)
        e.memory.write('CheckedMathEnabled',False);e.memory.write('CheckedMathIndex',99);e.memory.values['checkedmathwide']=None;e.step();self.assertEqual(e.memory.read('CheckedMathSum'),10)
        row=e.report()['scalar_math']['checked_integer_conversion'];self.assertEqual(len(row['instructions']),7);self.assertFalse(row['native_runtime_parity'])


if __name__=='__main__':unittest.main()
