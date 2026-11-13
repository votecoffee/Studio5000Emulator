"""Scoped typed radix expressions retain exact integer and transactional rules."""
import copy
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_ladder_integer_literals as direct
import test_file_integer_literals as files
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import ModelError,Project,literal
from logixlab.runtime import Engine


class RadixExpressionTests(unittest.TestCase):
    def engine(self,rungs,*,file=False,checked=True,**kwargs):
        h=files.FileIntegerLiteralTests() if file else direct.LadderIntegerLiteralTests()
        h.setUp();self.addCleanup(h.doCleanups)
        return (h.checked if checked else h.engine)(rungs,**kwargs)

    @staticmethod
    def token(base,value,suffix):return f'{base}#{format(value,{2:"b",8:"o",16:"x"}[base])}{suffix}'

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.calls.stack,e._file_incremental,
                              e._file_arithmetic_retry,e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_three_bases_declared_types_full_patterns_and_zero_fill(self):
        for base,(dtype,suffix,bits) in itertools.product((2,8,16),(('LINT','l',64),('UDINT','U',32),('ULINT','uL',64))):
            token=self.token(base,(1<<bits)-1,suffix);want=-1 if dtype=='LINT' else (1<<bits)-1
            e=self.engine([f'CPT(Dest,{token});'],dtype=dtype);e.memory.values['dest']=None;e.step()
            self.assertEqual(e.memory.read('Dest'),want)
        for token,want in [('16#FFFFFFFFL',4294967295),('16#0000 FFFFl',65535),('2#1_010L',10),('16#8000000000000000L',-(1<<63))]:
            e=self.engine([f'CPT(Dest,{token});']);e.step();self.assertEqual(e.memory.read('Dest'),want)

    def test_arithmetic_bitwise_unary_and_division_remain_exact(self):
        for dtype,text,want in [('LINT','16#0020000000000001L+2#10L',9007199254740995),
                                ('LINT','16#8000000000000000L/8#3L',-3074457345618258602),
                                ('LINT','16#8000000000000000L MOD 8#3L',-2),
                                ('ULINT','16#FFFFFFFFFFFFFFFFUL/2#11UL',6148914691236517205),
                                ('ULINT','NOT 2#0UL',(1<<64)-1),('LINT','-16#FFFFFFFFFFFFFFFFL',1),
                                ('LINT','ABS(16#FFFFFFFFFFFFFFFFL)',1),('UDINT','16#FFFF_FFFFU XOR 2#1U',4294967294)]:
            e=self.engine([f'CPT(Dest,{text});'],dtype=dtype);e.step();self.assertEqual(e.memory.read('Dest'),want)

    def test_cmp_relations_and_boolean_sides_use_exact_eager_values(self):
        for relation,want in [('=',False),('<>',True),('<',True),('<=',True),('>',False),('>=',False)]:
            e=self.engine([f'CMP(16#0020000000000000L{relation}16#0020000000000001L)OTE(RunLatch);'])
            e.step();self.assertEqual(e.memory.read('RunLatch'),want)
        e=self.engine(['CMP(StartPB||(Source=16#1L))OTE(RunLatch);'])
        e.memory.write('StartPB',True);e.memory.values['source']=None;self.fault(e,'Unknown')

    def test_mixed_tags_keep_common_source_types_and_arithmetic_subtree_rules(self):
        types=('LINT','DINT','LINT');values=(9007199254740993,3,0)
        e=self.engine(['CPT(Dest,Source+Mask+16#0020000000000001L);',
                       'CMP(Source+Mask=16#0020000000000004L)OTE(RunLatch);'],types=types,values=values)
        e.step();self.assertEqual(e.memory.read('Dest'),18014398509481989);self.assertTrue(e.memory.read('RunLatch'))
        for text in ['Source+(Mask+16#1L)','Source+Mask+16#1UL','Source+Mask+(2#1L+2#1L)',
                     'Source+ABS(Mask+16#0L)','Source AND Mask+16#1L']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'],types=types,values=values,checked=False).blockers,text)

    def test_false_prescan_and_alias_selected_writes_establish_unknown_cells_only(self):
        def array(root):
            tags=root.find('./Controller/Tags');dest=tags.find('Tag[@Name="Dest"]');dest.set('Dimensions','3');dest.remove(dest.find('Data'))
            obj=E.SubElement(E.SubElement(dest,'Data',Format='Decorated'),'Array',DataType='LINT',Dimensions='3')
            E.SubElement(obj,'Element',Index='[2]',Value='903')
            E.SubElement(tags,'Tag',Name='Selected',DataType='LINT',TagType='Alias',AliasFor='Dest[SpeedCommand]')
        e=self.engine(['XIC(StartPB)CPT(Selected,Source+16#0020000000000001L);'],mutate=array)
        e.memory.write('SpeedCommand',99);e.step();self.assertEqual(e.memory.read('Dest'),[None,None,903])
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('SpeedCommand',1);e.step();self.assertEqual(e.memory.read('Dest'),[None,9007199254741000,903])

    def test_direct_overflow_zero_and_late_fault_restore_all_prior_results(self):
        for text in ['16#7FFFFFFFFFFFFFFFL+2#1L','16#1L/2#0L','ABS(16#8000000000000000L)']:
            e=self.engine(['MOV(77,SpeedCommand);',f'CPT(Dest,{text});']);self.fault(e,'overflow|zero')
        e=self.engine(['CPT(Dest,16#0020000000000001L);','DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand',0);self.fault(e,'zero');e.memory.write('SpeedCommand',1);e.step()
        self.assertEqual(e.memory.read('Dest'),9007199254740993)

    def test_invalid_digits_widths_suffixes_and_permissions_block_false_expressions(self):
        for token in ['16#100000000U','16#10000000000000000L','8#8L','2#2UL','16#FF_L','16#FF L',
                      '16#FFLU','16#FFL2','LINT#16#FF','16#FF.0L']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{token});'],checked=False).blockers,token)
            self.assertTrue(self.engine([f'AFI()FSC(Ctl,?,?,ALL,Queue[Ctl.POS]={token});'],file=True,checked=False).blockers,token)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,16#1L);'],mutate=constant,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,16#1L);'],mutate=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_default_st_index_and_binary64_profiles_do_not_expand_or_share_parser_cache(self):
        for constructor in [lambda:Expression('16#FFL',integer_literals=True),lambda:Expression('16#FFL',structured=True),
                            lambda:Expression('16#FFL',subscript=True),lambda:Condition('16#1L=1L',allow_wide=True,integer_literals=True)]:
            with self.assertRaises(ModelError):constructor()
        with self.assertRaises(ValueError):literal('16#FFL')
        e=self.engine(['CPT(Dest,16#FFL);']);enabled=e.extensions.expression('16#FFL',integer_literals=True,radix_literals=True)
        self.assertEqual(enabled.radix_types,{'LINT'})
        with self.assertRaises(ModelError):e.extensions.expression('16#FFL',integer_literals=True)
        for dtype,text in [('LREAL','16#1L'),('LINT','16#1L+1.0L'),('REAL','16#1L'),('LINT','SQR(16#1L)'),
                           ('LINT','FRD(16#1L)+1.0'),('LINT','16#1L**2')]:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'],dtype=dtype,checked=False).blockers,(dtype,text))

    def test_fal_all_numeric_and_inc_keep_exact_progress_lazy_holds_and_retry(self):
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],16#FFFFFFFFFFFFFFFFUL);'],file=True,dtype='ULINT')
        e.memory.values['queue'][:4]=[None]*4;e.step();self.assertEqual(e.memory.read('Queue'),[(1<<64)-1]*4+[99])
        for mode in ['1','INC']:
            e=self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Incoming+16#0020000000000001L);'],file=True)
            e.memory.write('Incoming',0);e.memory.write('StartPB',True);e.step()
            if mode=='INC':
                e.memory.values['incoming']=None;e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
                e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True)
            else:e.memory.write('StartPB',False);e.memory.values['incoming']=None
            self.fault(e,'Unknown');e.memory.write('Incoming',2);e.step()
            self.assertEqual(e.memory.read('Queue')[:2],[9007199254740993,9007199254740995]);self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_fsc_inhibit_resume_and_unknown_live_sources_retain_cursor_on_fault(self):
        e=self.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=16#0020000000000001L);'],file=True,
                      queue=(0,9007199254740993,9007199254740994,0,99))
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.values['queue'][2]=None;e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Ctl.IN',False);self.fault(e,'Unknown')
        e.memory.write('Queue[2]',9007199254740994);e.step();self.assertEqual(e.memory.read('Ctl.POS'),2)

    def test_mid_file_overflow_and_late_fault_restore_cells_and_control_progress(self):
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+2#1L);'],file=True,queue=(0,(1<<63)-1,0,0,99))
        self.fault(e,'overflow');e.memory.write('Queue[1]',1);e.step();self.assertEqual(e.memory.read('Queue'),[1,2,1,1,99])
        e=self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],16#0020000000000001L);','DIV(1,0,SpeedCommand);'],file=True)
        self.fault(e,'zero')

    def test_warm_aoi_direct_and_file_bindings_keep_exact_values_and_rollback(self):
        import test_aoi_queues as queues
        import test_aoi_files as afiles
        h=queues.AOIQueueTests();h.setUp();self.addCleanup(h.doCleanups)
        def direct_fields(root):
            direct.LadderIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=text.text.replace('9007199254740993L','16#0020000000000001L').replace('+2L','+2#10L')
        e=h.checked(direct_fields);e.memory.write('ValueA',3);e.step()
        self.assertEqual(e.memory.read('DriverA.Stack[1]'),9007199254740996)
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        h=afiles.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def file_fields(root):
            files.FileIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=text.text.replace('9007199254740993L','16#0020000000000001L').replace('>=6L','>=8#6L').replace('+1L','+2#1L')
        e=h.checked(file_fields,kind='1');e.memory.write('Transform',True);e.memory.write('Search',True);e.step()
        e.memory.write('Transform',False);e.memory.write('Search',False);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('OutputA')[:2],[9007199254740995,9007199254740997])

    def test_public_samples_and_reports_keep_existing_results_and_retry(self):
        base=Path(__file__).resolve().parents[1]/'samples'
        e=Engine(Project(base/'WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.memory.write('ILitEnabled',True);e.step()
        self.assertEqual(e.memory.read('ILitSigned'),-(1<<63));self.assertEqual(e.memory.read('ILitQuotient'),6148914691236517205)
        self.assertTrue(e.memory.read('ILitExact'));e.memory.write('ILitLateDivisor',0);self.fault(e,'zero')
        e.memory.write('ILitLateDivisor',1);e.step()
        report=e.report()
        for profile in [report['wide_ladder_expressions']['typed_integer_literals'],report['file_arithmetic']['typed_integer_literals'],report['file_search']['typed_integer_literals']]:
            self.assertEqual(profile['radix_bases'],[2,8,16]);self.assertFalse(profile['native_runtime_parity'])
        e=Engine(Project(base/'StatsLab.L5X'));self.assertEqual(e.blockers,[]);e.memory.write('WideFiles',True);e.step()
        self.assertEqual(e.memory.read('WideMapped'),[18014398509481987,18014398509481989,None])
        self.assertEqual(e.memory.read('UnsignedMapped'),[18446744073709551614,9007199254740992,None])


if __name__=='__main__':unittest.main()
