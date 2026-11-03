"""Range-preserving mixed integer ladder relations/LIM, read-only and transactional."""
import unittest
from xml.etree import ElementTree as E

import test_numeric_comparisons as fixtures
from logixlab.model import ModelError

RANK = ['SINT','USINT','INT','UINT','DINT','UDINT','LINT','ULINT']
COVERS = {'SINT':{'SINT'},'USINT':{'USINT'},'INT':{'SINT','USINT','INT'},'UINT':{'USINT','UINT'},
          'DINT':{'SINT','USINT','INT','UINT','DINT'},'UDINT':{'USINT','UINT','UDINT'},
          'LINT':{'SINT','USINT','INT','UINT','DINT','UDINT','LINT'},'ULINT':{'USINT','UINT','UDINT','ULINT'}}
RELATIONS = ['EQU','NEQ','LES','LEQ','GRT','GEQ']


class MixedRelationTests(unittest.TestCase):
    setUp=fixtures.NumericComparisonTests.setUp
    engine=fixtures.NumericComparisonTests.engine
    checked=fixtures.NumericComparisonTests.checked
    snapshot=staticmethod(fixtures.NumericComparisonTests.snapshot)

    def test_all_64_type_pairs_and_six_relations_in_both_directions(self):
        def flags(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Flags',DataType='BOOL',Dimensions='6',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='6')
        rungs=[f'{op}(Source,Mask)OTE(Flags[{i}]);' for i,op in enumerate(RELATIONS)]
        for a in RANK:
            for b in RANK:
                with self.subTest(a=a,b=b):
                    common=max((a,b),key=RANK.index);allowed={a,b}<=COVERS[common]
                    e=self.engine(rungs,types=(a,b,'DINT'),values=(3,5,0),mutate=flags);self.assertEqual(not e.blockers,allowed)
                    if allowed:
                        e.step();self.assertEqual(e.memory.read('Flags'),[False,True,True,True,False,False])
                        self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(3,5))
                        e.memory.write('Source',5);e.memory.write('Mask',3);e.step()
                        self.assertEqual(e.memory.read('Flags'),[False,True,False,False,True,True])
                        e.memory.write('Source',3);e.step();self.assertEqual(e.memory.read('Flags'),[True,False,False,True,False,True])

    def test_all_512_lim_type_combinations_use_the_highest_actual_type(self):
        for a in RANK:
            for b in RANK:
                for c in RANK:
                    with self.subTest(types=(a,b,c)):
                        common=max((a,b,c),key=RANK.index);allowed={a,b,c}<=COVERS[common]
                        e=self.engine(['LIM(Source,Mask,Dest)OTE(RunLatch);'],types=(a,b,c),values=(2,5,8))
                        self.assertEqual(not e.blockers,allowed)
                        if allowed:e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(tuple(e.memory.read(t) for t in ('Source','Mask','Dest')),(2,5,8))

    def test_signed_unsigned_meanings_and_lint_udint_equality(self):
        for types,values,op,expected in [(('DINT','LINT','DINT'),(-1,4294967295,0),'LES',True),
                                        (('UDINT','LINT','DINT'),(4294967295,4294967295,0),'EQU',True),
                                        (('INT','USINT','DINT'),(-1,255,0),'LES',True),
                                        (('UINT','DINT','DINT'),(65535,-1,0),'GRT',True),
                                        (('ULINT','UDINT','DINT'),(18446744073709551615,4294967295,0),'GRT',True)]:
            e=self.checked([f'{op}(Source,Mask)OTE(RunLatch);'],types=types,values=values);e.step();self.assertEqual(e.memory.read('RunLatch'),expected)

    def test_mixed_lim_preserves_adjacent_64_bit_values(self):
        e=self.checked(['LIM(Source,Mask,Dest)OTE(RunLatch);'],types=('DINT','LINT','LINT'),values=(0,9007199254740993,9007199254740992))
        e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('Dest',9007199254740993);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Mask'),9007199254740993)

    def test_mixed_lim_inclusive_reversed_and_equal_endpoints(self):
        for low,high,rows in [(2,8,[(1,False),(2,True),(8,True),(9,False)]),
                              (8,2,[(1,True),(2,True),(5,False),(8,True),(9,True)]),
                              (2,2,[(1,False),(2,True),(3,False)])]:
            for value,expected in rows:
                e=self.checked(['LIM(Source,Mask,Dest)OTE(RunLatch);'],types=('LINT','DINT','UINT'),values=(low,value,high))
                e.step();self.assertEqual(e.memory.read('RunLatch'),expected)

    def test_all_relations_skip_false_unknowns_and_indices_and_clear_coils(self):
        for op in RELATIONS:
            e=self.checked([f'XIC(StartPB){op}(Values[Index],Mask)OTE(RunLatch);'],types=('LINT','DINT','DINT'),values=(0,7,0))
            e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Values'),[None]*3)
            e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',7);e.step()
            self.assertEqual(e.memory.read('RunLatch'),op in ('EQU','LEQ','GEQ'))

    def test_lim_requires_every_unknown_operand_even_when_outside_range(self):
        for args,types,values in [('Values[0],Mask,Dest',('LINT','DINT','DINT'),(0,5,10)),
                                  ('Source,Values[0],Dest',('LINT','DINT','DINT'),(0,5,10)),
                                  ('Source,Mask,Values[0]',('LINT','DINT','DINT'),(10,0,0))]:
            e=self.checked([f'LIM({args})OTE(RunLatch);'],types=types,values=values);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_constant_udt_and_program_alias_sources_are_read_only(self):
        def fields(root):
            tags=root.find('./Controller/Tags');tags.find('Tag[@Name="Source"]').set('Constant','true')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name,dtype in [('Compare','LINT'),('Guard','DINT')]:E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
            record=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base',Constant='true'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            for name,dtype,value in [('Compare','LINT','65535'),('Guard','DINT','987')]:E.SubElement(record,'DataValueMember',Name=name,DataType=dtype,Value=value)
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='LINT',TagType='Alias',AliasFor='Packet1.Compare')
        e=self.checked(['EQU(View,Source)GRT(Source,Mask)OTE(RunLatch);'],types=('UINT','DINT','DINT'),values=(65535,0,0),mutate=fields)
        e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet1'),{'Compare':65535,'Guard':987});self.assertEqual(e.memory.read('Source'),65535)

    def test_later_fault_restores_writes_coils_and_scheduler(self):
        e=self.checked(['MOV(99,SpeedCommand);','GRT(Source,Mask)OTE(RunLatch);','LIM(Dest,Values[0],Source)OTE(BatchComplete);'],types=('LINT','DINT','UINT'),values=(10,3,0));before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Values[0]',5);e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertTrue(e.memory.read('BatchComplete'))

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['GEQ(Stack[0],Buffer[Index])OTE(EnableOut);'])
        queues.logic(root,['AFI()GEQ(Stack[0],Buffer[Index])OTE(EnableOut);'],name='EnableInFalse')
        root.find('.//AddOnInstructionDefinition/LocalTags/LocalTag[@Name="Stack"]').set('DataType','LINT')
        for name in ('DriverA','DriverB'):
            array=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]');array.set('DataType','LINT');array.remove(array.find('Element[@Index="[0]"]'))

    def test_aoi_unknown_local_inout_sources_and_binding_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('DriverA.Stack[0]',0);e.memory.write('DriverB.Stack[0]',0);e.step()
        self.assertTrue(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'))
        e.memory.write('BufferA[1]',1);e.step();self.assertFalse(e.memory.read('DriverA.EnableOut'));self.assertTrue(e.memory.read('DriverB.EnableOut'))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step();e.memory.write('EnabledB',True);e.memory.write('BufferA[1]',-1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',2);e.step();self.assertTrue(e.memory.read('DriverA.EnableOut'));self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_lossy_types_immediates_shapes_and_other_profiles_remain_blocked(self):
        for types,values in [(('DINT','UDINT','DINT'),(1,1,0)),(('LINT','ULINT','DINT'),(1,1,0)),(('SINT','USINT','DINT'),(1,1,0)),(('LINT','REAL','DINT'),(1,1,0))]:
            self.assertTrue(self.engine(['AFI()EQU(Source,Mask)OTE(RunLatch);'],types=types,values=values).blockers)
        for text in ('LIM(2147483648,Source,Mask)','EQU(Source,2147483648)','EQU(Source,TRUE)','EQU(Values,Mask)','EQU(Missing,Mask)'):
            self.assertTrue(self.engine(['AFI()'+text+'OTE(RunLatch);'],types=('LINT','DINT','DINT')).blockers)
        e=self.checked(['LIM(0,Source,10)OTE(RunLatch);'],types=('LINT','LINT','LINT'),values=(7,0,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        for processor,revision in [('1756-L75','35'),('1756-L85E','34')]:
            def old(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',revision)
            self.assertTrue(self.engine(['EQU(Source,Mask)OTE(RunLatch);'],types=('LINT','DINT','DINT'),mutate=old).blockers)
        report=self.checked().report()['numeric_comparisons']['mixed_integer_ordering'];self.assertEqual(report['types'],RANK);self.assertEqual(len(report['instructions']),7);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
