"""Bounded exact temporal calculations and result conversion across ladder files."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from test_floating_string_conditions import add_strings
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab import time_values

STAMP=1767225600000001000
DURATIONS=('TIME32','TIME','LTIME')
DATES=('DT','LDT')


class TemporalArithmeticTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def make(self,rungs,*,source='LTIME',other='TIME',dest='LTIME',values=(1001,1,0),file=False,change=None,**kwargs):
        def fields(root):
            add_strings(root)
            if change:change(root)
        if not file:kwargs.update(types=(source,other,dest),values=values)
        return self.engine(rungs,file=file,dtype=source,mutate=fields,**kwargs)

    def read(self,e,ref):return e.memory.read(ref,allow_time=True)

    def test_identity_all_same_family_results_establish_unknown_destinations(self):
        for family,base in ((DURATIONS,1000),(DATES,STAMP)):
            for source,dest in itertools.product(family,repeat=2):
                e=self.make(['CPT(Dest,Source);'],source=source,other=source,dest=dest,values=(base//time_values.ns_per_tick(source),0,0))
                e.memory.values['dest']=None;e.step();self.assertEqual(self.read(e,'Dest'),base//time_values.ns_per_tick(dest),(source,dest))

    def test_mixed_duration_addition_and_date_arithmetic_results(self):
        for source,other,dest in itertools.product(DURATIONS,repeat=3):
            e=self.make(['CPT(Dest,Source+Mask);'],source=source,other=other,dest=dest,values=(1000//time_values.ns_per_tick(source),2000//time_values.ns_per_tick(other),0))
            e.step();self.assertEqual(self.read(e,'Dest'),3000//time_values.ns_per_tick(dest))
        for date,duration,dest in itertools.product(DATES,DURATIONS,DATES):
            for expression,sign in [('Source+Mask',1),('Mask+Source',1),('Source-Mask',-1)]:
                e=self.make([f'CPT(Dest,{expression});'],source=date,other=duration,dest=dest,values=(STAMP//time_values.ns_per_tick(date),1000//time_values.ns_per_tick(duration),0))
                e.step();self.assertEqual(self.read(e,'Dest'),(STAMP+sign*1000)//time_values.ns_per_tick(dest))
        for source,other,dest in itertools.product(DATES,DATES,DURATIONS):
            e=self.make(['CPT(Dest,Source-Mask);'],source=source,other=other,dest=dest,values=((STAMP+2000)//time_values.ns_per_tick(source),STAMP//time_values.ns_per_tick(other),0))
            e.step();self.assertEqual(self.read(e,'Dest'),2000//time_values.ns_per_tick(dest))

    def test_constants_unary_signs_exact_intermediates_and_nanosecond_dates(self):
        for dest,expression,want in [('LDT','DT#2026-01-01-00:00:00.000_001+LT#1ns',STAMP+1),
                ('LDT','LT#1ns+DT#2026-01-01-00:00:00.000_001',STAMP+1),
                ('LTIME','LDT#2026-01-01-00:00:00.000_001_001-DT#2026-01-01-00:00:00.000_001',1),
                ('LTIME','-(T#1us-LT#1ns)',-999),('LTIME','+(LT#-1ns)',-1),
                ('TIME','LT#1ns+LT#999ns',1),('LTIME','T#0s-T#1us',-1000)]:
            e=self.make([f'CPT(Dest,{expression});'],dest=dest);e.step();self.assertEqual(self.read(e,'Dest'),want,expression)

    def test_invalid_families_operators_numeric_strings_shapes_permissions_and_profiles(self):
        for expression in ('DT#1970-01-01-00:00:00+DT#1970-01-01-00:00:00','T#1us-DT#1970-01-01-00:00:00',
                '-DT#1970-01-01-00:00:00','Source*Mask','Source/Mask','Source MOD Mask','Source**Mask',
                'Source AND Mask','Source+1','Source+1UL','ABS(Source)','Word','StartPB'):
            self.assertTrue(self.make([f'AFI()CPT(Dest,{expression});'],checked=False).blockers,expression)
        self.assertTrue(self.make(['AFI()CPT(Dest,Source);'],dest='DINT',checked=False).blockers)
        self.assertTrue(self.make(['AFI()CPT(Dest,Source);'],source='LDT',dest='LTIME',values=(STAMP,1,0),checked=False).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.make(['AFI()CPT(Dest,Source);'],change=constant,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.make(['AFI()CPT(Dest,Source);'],change=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_fractional_destination_ticks_are_atomic_and_false_paths_skip_values(self):
        e=self.make(['XIC(StartPB)CPT(Dest,Source+LT#0ns);'],dest='TIME')
        e.memory.values['source']=None;e.step();e.memory.write('StartPB',True);self.fault(e,'Unknown')
        e.memory.write('Source',1001);self.fault(e,'discard');e.memory.write('Source',1000);e.step();self.assertEqual(self.read(e,'Dest'),1)
        e=self.make(['CPT(Dest,Source);'],source='LDT',dest='DT',values=(STAMP+1,0,0));self.fault(e,'discard')
        e.memory.write('Source',STAMP);e.step();self.assertEqual(self.read(e,'Dest'),STAMP//1000)

    def test_destination_and_canonical_intermediate_ranges_rollback_then_repair(self):
        e=self.make(['CPT(Dest,Source+T#1us);'],source='TIME32',other='TIME32',dest='TIME32',values=(2147483647,0,0))
        self.fault(e,'range|requires');e.memory.write('Source',0);e.step();self.assertEqual(self.read(e,'Dest'),1)
        for dest,expression in [('LDT','LDT#2250-12-31-23:59:59.999_999_999+LT#1ns'),
                ('LDT','DT#1970-01-01-00:00:00-LT#1ns'),
                ('LTIME','LT#31d_12h_59m_59s_999ms_999us_999ns+LT#1ns'),
                ('LTIME','DT#2250-01-01-00:00:00-DT#1970-01-01-00:00:00'),
                ('LTIME','(LT#31d_12h_59m_59s_999ms_999us_999ns+LT#1ns)-LT#1ns')]:
            e=self.make([f'CPT(Dest,{expression});'],dest=dest);self.fault(e,'range|requires')

    def test_elapsed_conditions_use_arithmetic_and_eager_string_operands(self):
        e=self.make(['CMP(((Source-Mask)>T#2us)&&(Word>OtherWord))OTE(RunLatch);'],source='LDT',other='DT',values=(STAMP+2001,STAMP//1000,0))
        e.step();self.assertTrue(e.memory.read('RunLatch'));e.memory.write('Source',STAMP+2000);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.values['word']['DATA'][0]=None;self.fault(e,'unknown active')

    def test_selected_alias_outputs_preserve_unknown_siblings_and_live_indices(self):
        def arrays(root):
            tags=root.find('./Controller/Tags')
            for name in ('Source','Dest'):
                tag=tags.find(f'Tag[@Name="{name}"]');tag.set('Dimensions','3');tag.remove(tag.find('Data'))
                array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='LTIME',Dimensions='3')
                for index,value in ([(1,1001)] if name=='Source' else [(0,101),(2,999)]):E.SubElement(array,'Element',Index=f'[{index}]',Value=str(value))
            tag=E.SubElement(tags,'Tag',Name='SourceIndex',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='99')
            E.SubElement(tags,'Tag',Name='Selected',DataType='LTIME',TagType='Alias',AliasFor='Dest[SpeedCommand]')
        e=self.make(['XIC(StartPB)CPT(Selected,Source[SourceIndex]+LT#1ns);'],change=arrays)
        e.memory.write('SpeedCommand',99);e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('SpeedCommand',1);e.memory.write('SourceIndex',0);self.fault(e,'Unknown')
        e.memory.write('SourceIndex',1);e.step();self.assertEqual(self.read(e,'Dest'),[101,1002,999]);self.assertIsNone(e.memory.values['source'][0])

    def test_fal_all_types_all_modes_add_temporal_values_without_repeating_cells(self):
        for dtype,mode in itertools.product(time_values.TYPES,('ALL','1','INC')):
            e=self.make([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Queue[Ctl.POS]+T#1us);'],source=dtype,file=True)
            e.memory.write('StartPB',True);e.step()
            if mode=='1':
                e.memory.write('StartPB',False)
                for _ in range(3):e.step()
            elif mode=='INC':
                prior=self.read(e,'Queue');e.step();self.assertEqual(self.read(e,'Queue'),prior)
                for _ in range(3):e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            delta=1 if time_values.ns_per_tick(dtype)==1000 else 1000
            self.assertEqual(self.read(e,'Queue'),[v+delta for v in (2,4,6,8)]+[99]);self.assertTrue(e.memory.read('Ctl.DN'))

    @staticmethod
    def target(root,dtype='LTIME'):
        tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Target',DataType=dtype,TagType='Base',Dimensions='5')
        array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='5');E.SubElement(array,'Element',Index='[4]',Value='99')

    def test_fal_mixed_precision_establishes_unknown_targets_and_rejects_lost_ticks(self):
        e=self.make(['FAL(Ctl,?,?,ALL,Target[Ctl.POS],Queue[Ctl.POS]+LT#1ns);'],source='TIME',file=True,change=self.target)
        e.step();self.assertEqual(self.read(e,'Target'),[2001,4001,6001,8001,99])
        e=self.make(['FAL(Ctl,?,?,ALL,Target[Ctl.POS],Queue[Ctl.POS]+LT#0ns);'],source='LTIME',file=True,queue=(2000,4001,6000,8000,99),change=lambda root:self.target(root,'TIME'))
        self.fault(e,'discard');self.assertEqual(self.read(e,'Target'),[None,None,None,None,99]);self.assertFalse(e.memory.read('Ctl.ER'))
        e.memory.write('Queue[1]',4000);e.step();self.assertEqual(self.read(e,'Target'),[2,4,6,8,99])

    def test_numeric_and_inc_fal_precision_retry_preserves_prior_committed_prefix(self):
        for mode in ('1','INC'):
            e=self.make([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Target[Ctl.POS],Queue[Ctl.POS]+LT#0ns);'],file=True,queue=(2000,4001,6000,8000,99),change=lambda root:self.target(root,'TIME'))
            e.memory.write('StartPB',True);e.step()
            e.memory.write('StartPB',False)
            if mode=='INC':e.step();e.memory.write('StartPB',True)
            self.fault(e,'discard');self.assertEqual(self.read(e,'Target')[:2],[2,None]);self.assertEqual(e.memory.read('Ctl.POS'),0);self.assertFalse(e.memory.read('Ctl.ER'))
            e.memory.write('Queue[1]',4000);e.step();self.assertEqual(self.read(e,'Target')[:2],[2,4]);self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_mid_file_range_and_unknown_failures_restore_prefix_and_control(self):
        e=self.make(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]-T#3us);'],source='DT',file=True,queue=(4,2,6,8,99))
        self.fault(e,'range|requires');e.memory.write('Queue[1]',4);e.step();self.assertEqual(self.read(e,'Queue'),[1,1,3,5,99])
        e=self.make(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+LT#1ns);'],file=True)
        e.memory.values['queue'][1]=None;self.fault(e,'Unknown');e.memory.write('Queue[1]',4);e.step();self.assertEqual(self.read(e,'Queue'),[3,5,7,9,99])

    def test_fsc_elapsed_arithmetic_all_modes_match_and_resume(self):
        for mode in ('ALL','1','INC'):
            e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},((Queue[Ctl.POS]-LDT#1970-01-01-00:00:00)>T#0us)&&(Codes[Ctl.POS]=Word));'],source='LDT',file=True)
            e.memory.write('StartPB',True);e.step()
            if mode=='1':e.memory.write('StartPB',False);e.step()
            elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1);e.memory.write('Ctl.IN',False);e.memory.write_string('Word','D')
            if mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True)
            e.step()
            if mode=='1':e.step()
            elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),3)

    def test_fal_timestamp_outputs_feed_elapsed_fsc_with_separate_controls(self):
        from test_control_operations import control_data
        def fields(root):
            self.target(root,'LDT');tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='FindCtl',DataType='CONTROL',TagType='Base')
            control_data(E.SubElement(tag,'Data',Format='Decorated'),4)
        for mode in ('ALL','1','INC'):
            e=self.make([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Target[Ctl.POS],Queue[Ctl.POS]+LT#1ns);',
                         f'XIC(StopPB)FSC(FindCtl,?,?,{mode},((Target[FindCtl.POS]-Queue[FindCtl.POS])=LT#1ns)&&(Codes[FindCtl.POS]=Word));'],source='DT',file=True,change=fields)
            e.memory.write('StartPB',True);e.step()
            if mode=='1':
                e.memory.write('StartPB',False)
                for _ in range(3):e.step()
            elif mode=='INC':
                for _ in range(3):e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertEqual(self.read(e,'Target'),[2001,4001,6001,8001,99]);e.memory.write('StopPB',True);e.step()
            if mode=='1':e.memory.write('StopPB',False);e.step()
            elif mode=='INC':e.memory.write('StopPB',False);e.step();e.memory.write('StopPB',True);e.step()
            self.assertTrue(e.memory.read('FindCtl.FD'));self.assertEqual(e.memory.read('FindCtl.POS'),1)

    def test_warm_aoi_temporal_arrays_and_late_fault_restore_canonical_progress(self):
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            for tag in root.findall('./Controller/Tags/Tag'):
                if tag.get('Name') not in ('InputA','InputB','OutputA','OutputB'):continue
                tag.set('DataType','LDT');array=tag.find('./Data/Array');array.set('DataType','LDT')
                if tag.get('Name').startswith('Input'):
                    for element in array:element.set('Value',str((int(element.get('Index')[1:-1])+1)*1000))
            aoi=root.find('.//AddOnInstructionDefinition')
            for param in aoi.findall('./Parameters/Parameter'):
                if param.get('Name') in ('Input','Output'):param.set('DataType','LDT')
            scratch=aoi.find('./LocalTags/LocalTag[@Name="Scratch"]');scratch.set('DataType','LDT')
            for text in aoi.findall('.//Rung/Text'):
                text.text=text.text.replace('Input[Calc.POS]*Gain+Bias','Input[Calc.POS]+LT#1ns').replace('Input[LocalCalc.POS]+Bias','Input[LocalCalc.POS]+LT#2ns').replace('Input[Find.POS]>=Threshold','Input[Find.POS]>LDT#1970-01-01-00:00:00')
                if 'CPT(Total,' in text.text:text.text='NOP();'
        e=h.checked(fields,kind='1');e.memory.write('Transform',True);e.memory.write('Search',True);e.step();self.assertEqual(self.read(e,'OutputA')[0],1001);self.assertEqual(self.read(e,'DriverA.Scratch')[0],1002)
        e.memory.write('Transform',False);e.memory.write('Search',False);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(self.read(e,'OutputA')[:2],[1001,2001])

    def test_generic_cache_scopes_and_public_example_precision_recovery_report(self):
        with self.assertRaises(ModelError):Expression('T#1us+LT#1ns')
        with self.assertRaises(ModelError):Expression('T#1us+LT#1ns',structured=True)
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('TemporalMathEnabled',True);self.fault(e,'outside bounds');e.memory.write('TemporalMathIndex',1);e.step()
        for name,want in {'Elapsed':1,'Next':STAMP+1,'Total':2001,'Negative':-1,'Selected':[101,2001,999]}.items():self.assertEqual(self.read(e,'TemporalMath'+name),want,name)
        self.assertTrue(e.memory.read('TemporalMathMatch'));e.memory.write('TemporalMathCoarseEnabled',True);self.fault(e,'discard')
        e.memory.write('TemporalHighDuration',1000);e.step();self.assertEqual(self.read(e,'TemporalMathCoarse'),2);self.assertFalse(e.memory.read('TemporalMathMatch'))
        e.memory.write('TemporalMathLateDivisor',0);self.fault(e,'zero');e.memory.write('TemporalMathLateDivisor',1);e.step()
        report=e.report()['temporal_expressions'];self.assertEqual(report['consumers'],['CPT','CMP','FAL','FSC']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
